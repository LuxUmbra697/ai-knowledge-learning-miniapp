import { request } from './api'
import type { PollControl } from './polling'
import type { StudyMap } from './learningMap'

export interface PathConcept { concept_id: string; label: string; mastery: number; attempts: number; mapping_confidence: string }
export interface LearningPath { version: number; edges: [string, string][]; concepts: PathConcept[]; truncated: boolean }
export interface PlanItem {
  id: string; kind: 'review' | 'read'; concept_id: string; label: string; card_id: string; card_version: number
  quiz_id: string; question_id: string; minutes: number; priority: number; completed?: boolean; completion_source?: string | null
  basis: { due: boolean; overdue_days: number; mastery: number; attempts: number; supports_prerequisite: boolean }
}
export interface LearningPlan {
  plan_id?: string; fingerprint: string; items: PlanItem[]; concepts: PathConcept[]; edges: [string, string][]
  minutes: number; budget_minutes: number; day: string; timezone: string; path_version: number; truncated: boolean
  blocked: Record<string, string[]>; order: string[]; isolated: string[]; path_changed?: boolean; previous_day?: boolean
}
export interface PlanListItem { plan_id: string; day: string; minutes: number; created_at: string }
export const getLearningPath = (control?: PollControl) => request<LearningPath>('/learning/path', { control })
export const saveLearningPath = (version: number, edges: [string, string][]) => request<LearningPath>('/learning/path', { method: 'PUT', data: { version, edges } })
export const previewPlan = (minutes: number, timezone: string, control?: PollControl) => request<LearningPlan>(`/learning/plans/preview?minutes=${minutes}&timezone=${encodeURIComponent(timezone)}`, { control })
export const listPlans = (control?: PollControl) => request<{ items: PlanListItem[] }>('/learning/plans', { control })
export const getPlan = (id: string, control?: PollControl) => request<LearningPlan>(`/learning/plans/${id}`, { control })
export const confirmPlan = (plan: LearningPlan) => request<{ plan_id: string }>('/learning/plans', { method: 'POST', idempotencyKey: `plan_${plan.fingerprint}`, data: { fingerprint: plan.fingerprint, minutes: plan.budget_minutes, timezone: plan.timezone, confirmed: true } })
export const markPlanRead = (planId: string, itemId: string) => request(`/learning/plans/${planId}/read/${itemId}`, { method: 'PUT' })

export function pathDiagram(path: LearningPath): StudyMap {
  const ids = new Map(path.concepts.map((node, i) => [node.concept_id, `c${i}`]))
  return { version: 'study-map-v1', source_hash: '', mapping_basis: 'User-confirmed prerequisites, not model-inferred facts',
    nodes: path.concepts.map(node => ({ id: ids.get(node.concept_id)!, kind: 'concept', label: node.label, state: 'neutral' })),
    edges: path.edges.map(([a, b]) => ({ source: ids.get(a) || '', target: ids.get(b) || '', relation: 'precedes' })) }
}
