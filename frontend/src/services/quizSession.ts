export function restorableQuiz(value: unknown): { key: string; taskId?: string } | null {
  if (!value || typeof value !== 'object') return null
  const pending = value as { key?: unknown; taskId?: unknown }
  if (typeof pending.key !== 'string' || !/^[a-zA-Z0-9:_-]{8,100}$/.test(pending.key)) return null
  if (pending.taskId !== undefined && (typeof pending.taskId !== 'string' || !/^job_[a-f0-9]{32}$/.test(pending.taskId))) return null
  return { key: pending.key, taskId: pending.taskId as string | undefined }
}

export function quizTaskResult(task: { kind: string; status: string; result?: { quiz_id?: unknown } | null }): string | null {
  if (task.kind !== 'quiz') throw new Error('任务不属于知识练习，请从任务记录重新进入')
  if (task.status !== 'completed') return null
  const quizId = task.result?.quiz_id
  if (typeof quizId !== 'string' || !/^quiz_[a-f0-9]{32}$/.test(quizId)) throw new Error('练习记录不完整，请重新读取任务')
  return quizId
}
