export function restorableAnswer(params: { taskId?: string; docId?: string }, saved: { taskId?: string; docIds?: string[] } | null): string {
  if (params.taskId) return params.taskId
  if (!saved?.taskId) return ''
  return !params.docId || saved.docIds?.includes(params.docId) ? saved.taskId : ''
}
