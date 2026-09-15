import type { TutorDraft } from './tutor'

export function tutorDraft(value: unknown): TutorDraft | null {
  if (!value || typeof value !== 'object') return null
  const draft = value as TutorDraft, config = draft.config
  if (!config || typeof config.goal !== 'string' || !config.goal.trim() || config.goal.length > 1000 || !['socratic', 'diagnosis'].includes(config.mode)) return null
  if (Object.keys(config).some(key => !['goal', 'mode', 'doc_ids', 'card_id'].includes(key))) return null
  if (config.card_id !== undefined && (typeof config.card_id !== 'string' || !config.card_id || config.card_id.length > 64)) return null
  if (!Array.isArray(config.doc_ids) || config.doc_ids.length > 3 || config.doc_ids.some(id => typeof id !== 'string' || !id || id.length > 64)) return null
  if (config.mode === 'socratic' ? !config.doc_ids.length || !!config.card_id : !config.card_id || config.doc_ids.length > 0) return null
  if (typeof draft.createKey !== 'string' || !/^[a-zA-Z0-9:_-]{8,100}$/.test(draft.createKey)) return null
  if (draft.sessionId && !/^tutor_[a-f0-9]{32}$/.test(draft.sessionId)) return null
  if (draft.turnKey && (typeof draft.turnKey !== 'string' || !/^[a-zA-Z0-9:_-]{8,100}$/.test(draft.turnKey))) return null
  if (draft.version !== undefined && (!Number.isInteger(draft.version) || draft.version < 0 || draft.version > 5)) return null
  if (draft.message !== undefined && (typeof draft.message !== 'string' || !draft.message.trim() || draft.message.length > 1000)) return null
  if (draft.taskId && !/^job_[a-f0-9]{32}$/.test(draft.taskId)) return null
  return draft
}
