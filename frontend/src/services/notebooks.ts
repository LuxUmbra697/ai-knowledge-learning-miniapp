import { request, ReviewCard } from './api'
import { PollControl } from './polling'

export interface Notebook { notebook_id: string; name: string; version: number; question_count?: number }
export type NotebookTarget = { cardId: string } | { quizId: string; questionId: string }
const path = (id: string) => `/learning/notebooks/${encodeURIComponent(id)}`
export const listNotebooks = (control?: PollControl) => request<{ items: Notebook[] }>('/learning/notebooks', { control })
export const createNotebook = (name: string, control?: PollControl) => request<Notebook>('/learning/notebooks', { method: 'POST', data: { name }, control })
export const renameNotebook = (book: Notebook, name: string, control?: PollControl) => request<Notebook>(path(book.notebook_id), { method: 'PUT', data: { name, version: book.version }, control })
export const deleteNotebook = (book: Notebook) => request(`${path(book.notebook_id)}?version=${book.version}`, { method: 'DELETE' })
export const notebookCards = (id: string, control?: PollControl) => request<{ items: ReviewCard[] }>(`${path(id)}/cards`, { control })
export const removeNotebookCard = (id: string, cardId: string) => request(`${path(id)}/cards/${encodeURIComponent(cardId)}`, { method: 'DELETE' })
export const addNotebookQuestion = (id: string, target: NotebookTarget, control?: PollControl) => 'cardId' in target
  ? request<{ added: boolean }>(`${path(id)}/cards/${encodeURIComponent(target.cardId)}`, { method: 'PUT', control })
  : request<{ added: boolean }>(`${path(id)}/questions`, { method: 'POST', data: { quiz_id: target.quizId, question_id: target.questionId }, control })
