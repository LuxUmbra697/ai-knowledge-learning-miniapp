import { Evidence, LearningTask, request } from './api'
import { PollControl } from './polling'

export interface TutorConfig { goal: string; mode: 'socratic' | 'diagnosis'; doc_ids: string[]; card_id?: string }
export type TutorEvidence = Evidence | { id: string; source_type: 'stored_practice'; content: string; quiz_id: string; question_id: string; file_name: string; verification: string }
export interface TutorResponse {
  status: 'hint' | 'diagnosis' | 'no_evidence'; hint: string; question: string
  citations: { evidence_id: string; quote: string }[]; evidence: TutorEvidence[]
  diagnosis: string | null; diagnosis_source: string | null
  practice: { count: number; focus: string; doc_id: string | null; requires_confirmation: true; created: false } | null
  memory_turns: number; config_version: string; retrieval_status: string
  tool_summary?: { evidence_count: number; learning_concepts: number; due_review_sample: number; practice_proposed: boolean; fresh_tool_calls: number; max_tool_calls: number }
}
export interface TutorSession extends TutorConfig {
  session_id: string; version: number; pending_task_id: string | null; created_at: string; max_turns: number
  confirmed_diagnosis?: string | null
  turns?: { number: number; task_id: string; message: string; response: TutorResponse; created_at: string }[]
}
export interface TutorDraft { config: TutorConfig; createKey: string; sessionId?: string; turnKey?: string; version?: number; message?: string; taskId?: string }
const base = '/learning/tutor/sessions'
export const listTutorSessions = (control?: PollControl) => request<{ items: TutorSession[] }>(base, { control })
export const getTutorSession = (id: string, control?: PollControl) => request<TutorSession>(`${base}/${encodeURIComponent(id)}`, { control })
export const createTutor = (config: TutorConfig, key: string, control?: PollControl) => request<TutorSession>(base, { method: 'POST', data: config, idempotencyKey: key, control })
export const sendTutorTurn = (id: string, version: number, message: string, key: string, control?: PollControl) => request<LearningTask>(`${base}/${encodeURIComponent(id)}/turns`, { method: 'POST', data: { version, message }, idempotencyKey: key, control })
export const deleteTutor = (id: string) => request(`${base}/${encodeURIComponent(id)}`, { method: 'DELETE' })
export const confirmTutorPractice = (id: string, number: number, version: number) => request<LearningTask>(`${base}/${encodeURIComponent(id)}/turns/${number}/practice`, { method: 'POST', data: { version, confirmed: true } })
export const getTutorContext = (quizId: string, questionId: string, control?: PollControl) => request<{ card_id: string }>(`/learning/tutor/context?quiz_id=${encodeURIComponent(quizId)}&question_id=${encodeURIComponent(questionId)}`, { control })
