import { LearningTask, request } from './api'
import { PollControl } from './polling'
export type CharacterId = 'pink' | 'orange'
export interface CompanionMemory { id: string; kind: 'name' | 'study' | 'support'; text: string }
export interface CompanionReply { dialogue: string; emotion: 'calm' | 'happy' | 'shy' | 'warm' | 'thoughtful'; action: 'read' | 'wave' | 'nod' | 'celebrate'; used_memory_ids: string[]; memory_suggestion: Omit<CompanionMemory, 'id'> | null }
export interface CompanionDetail {
  character_id: CharacterId; version: number; turn_count: number; pending_task_id: string | null
  character: { name: string; age: number; role: string; primary: string; secondary: string; intro: string; motif: string }
  memories: CompanionMemory[]; story: { id: string; title: string; text: string; threshold: number }[]
  chapters: { id: string; title: string; threshold: number; unlocked: boolean }[]
  turns: { number: number; task_id: string; message: string; response: CompanionReply; created_at: string }[]
  canon_version: string
}
export const getCompanion = (identity: CharacterId, control?: PollControl) => request<CompanionDetail>(`/companions/${identity}`, { control })
export const sendCompanion = (identity: CharacterId, version: number, message: string, key: string, control?: PollControl) => request<LearningTask>(`/companions/${identity}/turns`, { method: 'POST', data: { version, message }, idempotencyKey: key, control })
export const saveCompanionMemory = (identity: CharacterId, version: number, items: CompanionMemory[]) => request<CompanionDetail>(`/companions/${identity}/memories`, { method: 'PUT', data: { version, items } })
export const resetCompanion = (identity: CharacterId, version: number, mode: 'history' | 'memory' | 'all') => request<CompanionDetail>(`/companions/${identity}/reset`, { method: 'POST', data: { version, mode, confirmed: true } })
export interface CompanionDraft { character: CharacterId; version: number; text: string; key: string; taskId?: string }
export function companionDraft(value: unknown): CompanionDraft | null {
  if (!value || typeof value !== 'object') return null
  const draft = value as CompanionDraft
  return ['pink', 'orange'].includes(draft.character) && Number.isInteger(draft.version) && draft.version >= 0 && typeof draft.text === 'string' && draft.text.length <= 1000 && typeof draft.key === 'string' && /^[a-zA-Z0-9:_-]{8,100}$/.test(draft.key) && (!draft.taskId || /^job_[a-f0-9]{32}$/.test(draft.taskId)) ? draft : null
}
