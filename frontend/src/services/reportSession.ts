export interface PendingReport { key: string; taskId?: string }

const taskIdPattern = /^job_[a-f0-9]{32}$/
export function restorableReport(routeId: string | undefined, saved: unknown): PendingReport | null {
  if (saved && typeof saved === 'object') {
    const value = saved as PendingReport
    if (typeof value.key === 'string' && /^[a-zA-Z0-9:_-]{8,100}$/.test(value.key)
      && (value.taskId === undefined || typeof value.taskId === 'string' && taskIdPattern.test(value.taskId))) return value
  }
  return routeId && taskIdPattern.test(routeId) ? { key: `view_${routeId}`, taskId: routeId } : null
}

export function reportTaskMatches(task: { kind: string; resource_id?: string }, quizId: string) {
  return task.kind === 'report' && task.resource_id === quizId
}
