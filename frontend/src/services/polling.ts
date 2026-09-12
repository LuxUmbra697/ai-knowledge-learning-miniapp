export class PollControl {
  cancelled = false
  private listeners = new Set<() => void>()
  cancel() { this.cancelled = true; for (const listener of this.listeners) listener(); this.listeners.clear() }
  onCancel(listener: () => void) {
    if (this.cancelled) listener()
    else this.listeners.add(listener)
    return () => { this.listeners.delete(listener) }
  }
  check() { if (this.cancelled) throw new Error('poll cancelled') }
}

export async function pollUntil<T>(load: () => Promise<T>, done: (value: T) => boolean, {
  intervalMs = 3000, maxAttempts = 100, control = new PollControl(),
}: { intervalMs?: number; maxAttempts?: number; control?: PollControl } = {}): Promise<T> {
  for (let attempt = 0; attempt < maxAttempts; attempt++) {
    control.check()
    const value = await load()
    control.check()
    if (done(value)) return value
    if (attempt + 1 < maxAttempts) await new Promise<void>(resolve => {
      const cleanup = control.onCancel(() => { clearTimeout(timer); resolve() })
      const timer = setTimeout(() => { cleanup(); resolve() }, intervalMs)
    })
  }
  throw new Error('poll timeout: 处理尚未结束，请稍后查看任务')
}
