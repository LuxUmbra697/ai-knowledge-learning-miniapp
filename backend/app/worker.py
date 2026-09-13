"""Bounded worker runtime. Task state and budgets live in MySQL, not this process."""
import asyncio
from time import perf_counter

from fastapi import HTTPException
import structlog

from app.repositories import job_repository as jobs

logger = structlog.get_logger()


class TaskContext:
    def __init__(self, row):
        self.task_id, self.user_id = row['task_id'], row['user_id']
        self.kind, self.payload = row['kind'], row['payload_json']
        self.lease_token = row['lease_token']
        self.checkpoints = row['state_json'].get('checkpoints', {})
        self._last_stage = perf_counter()

    async def checkpoint(self, stage, value):
        now = perf_counter()
        await jobs.checkpoint(self.task_id, self.lease_token, stage, value, (now-self._last_stage)*1000)
        self.checkpoints[stage] = value
        self._last_stage = now

    async def external(self, stage, operation, input_bytes=0):
        """One attempt only. The stage handler owns any bounded semantic/transport retry."""
        await jobs.reserve_call(self.task_id, self.lease_token, stage, input_bytes)
        try:
            output, tokens = await operation()
        except Exception as error:
            await jobs.complete_call(self.task_id, self.lease_token, stage, {'error_type': type(error).__name__}, None)
            raise
        await jobs.complete_call(self.task_id, self.lease_token, stage, {'output': output}, tokens)
        self.checkpoints[stage] = {'output': output}
        return output


async def run_once(handlers):
    row = await jobs.claim()
    if row is None:
        return False
    context = TaskContext(row)
    execution = asyncio.current_task()
    lease_lost = False

    async def renew():
        nonlocal lease_lost
        try:
            while True:
                await asyncio.sleep(8)
                if not await jobs.heartbeat(context.task_id, context.lease_token):
                    lease_lost = True
                    execution.cancel()
                    return
        except Exception:
            lease_lost = True
            execution.cancel()

    heartbeat = asyncio.create_task(renew())
    try:
        handler = handlers.get(row['kind'])
        if handler is None:
            raise RuntimeError('Unsupported worker handler')
        result = await asyncio.wait_for(handler(context), timeout=170)
        await jobs.finish(context.task_id, context.lease_token, result)
    except asyncio.CancelledError:
        if not lease_lost:
            # Shutdown leaves a lease/checkpoint for recovery, not a fabricated failure.
            raise
    except jobs.TaskLeaseLost:
        pass
    except jobs.TaskBudgetExceeded:
        await jobs.finish(context.task_id, context.lease_token, None, 'budget_exhausted', '任务调用预算已用完，未继续请求模型')
    except asyncio.TimeoutError:
        await jobs.finish(context.task_id, context.lease_token, None, 'timeout', '任务处理超时，请稍后重试')
    except HTTPException as error:
        await jobs.finish(context.task_id, context.lease_token, None, f'input_{error.status_code}', str(error.detail)[:300])
    except Exception as error:
        logger.warning('worker_task_failed', task_id=context.task_id, error_type=type(error).__name__)
        await jobs.finish(context.task_id, context.lease_token, None, 'processing_failed', '处理暂时失败，已保存任务记录')
    finally:
        heartbeat.cancel()
        await asyncio.gather(heartbeat, return_exceptions=True)
    return True


async def run(handlers, stop: asyncio.Event | None = None, maintenance=None):
    stop = stop or asyncio.Event()
    last_maintenance = 0
    while not stop.is_set():
        try:
            if maintenance and perf_counter() - last_maintenance >= 10:
                await maintenance()
                last_maintenance = perf_counter()
            worked = await run_once(handlers)
        except Exception as error:
            logger.warning('worker_poll_failed', error_type=type(error).__name__)
            worked = False
        if not worked:
            try:
                await asyncio.wait_for(stop.wait(), timeout=1)
            except asyncio.TimeoutError:
                pass
