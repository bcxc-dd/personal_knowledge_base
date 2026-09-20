import type { Conversation, DocumentDetail, KnowledgeBase, KnowledgeDocument, Message, ModelSettings } from '../types';
export interface Note { id: string; title: string; question: string; content: string; created_at: string; updated_at: string; citations: any[] }
import { consumeEvents, type StreamEvent } from './stream';

async function responseError(response: Response) {
  const data = await response.json().catch(() => ({}));
  return new Error(typeof data.detail === 'string' ? data.detail : `请求失败 (${response.status})，请检查输入或服务状态。`);
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const response = await fetch('/api' + path, init);
  if (!response.ok) throw await responseError(response);
  return response.json();
}
const json = (method: string, body?: unknown): RequestInit => ({ method, headers: { 'Content-Type': 'application/json' }, body: body === undefined ? undefined : JSON.stringify(body) });

export const api = {
  kbs: () => request<KnowledgeBase[]>('/knowledge-bases'),
  createKb: (name: string) => request<KnowledgeBase>('/knowledge-bases', json('POST', { name })),
  documents: (kb?: string) => request<KnowledgeDocument[]>('/documents' + (kb ? `?kb_id=${encodeURIComponent(kb)}` : '')),
  document: (id: string) => request<DocumentDetail>(`/documents/${id}`),
  upload: (file: File, kb: string) => {
    const form = new FormData(); form.append('file', file); form.append('kb_id', kb);
    return request<{ document: KnowledgeDocument; duplicate: boolean }>('/documents', { method: 'POST', body: form });
  },
  retry: (id: string) => request(`/documents/${id}/retry`, json('POST')),
  remove: (id: string) => request(`/documents/${id}`, json('DELETE')),
  settings: () => request<ModelSettings>('/settings'),
  saveSettings: (value: Partial<ModelSettings> & { chat_key?: string; embedding_key?: string }) => request<ModelSettings>('/settings', json('PUT', value)),
  reindex: () => request('/settings/reindex', json('POST')),
  conversations: () => request<Conversation[]>('/conversations'),
  conversation: (id: string) => request<Conversation & { messages: Message[] }>(`/conversations/${id}`),
  deleteConversation: (id: string) => request(`/conversations/${id}`, json('DELETE')),
  notes: (query?: string) => request<Note[]>('/notes' + (query ? `?query=${encodeURIComponent(query)}` : '')),
  note: (id: string) => request<Note>(`/notes/${id}`),
  createNote: (value: { title: string; question: string; content: string; citations: any[] }) => request<Note>('/notes', json('POST', value)),
  updateNote: (id: string, value: { title: string; content: string }) => request<Note>(`/notes/${id}`, json('PATCH', value)),
  deleteNote: (id: string) => request(`/notes/${id}`, json('DELETE')),
  ask: async (payload: { question: string; kb_id: string; document_ids: string[]; conversation_id?: string }, signal: AbortSignal, onEvent: (e: StreamEvent) => void) => {
    const response = await fetch('/api/chat', { ...json('POST', payload), signal });
    if (!response.ok) throw await responseError(response);
    if (!response.body) throw new Error('浏览器不支持流式响应。');
    await consumeEvents(response.body, onEvent);
  },
};

export const notifyChange = () => window.dispatchEvent(new Event('knowledge-changed'));
export const errorMessage = (e: unknown) => e instanceof Error ? e.message : '操作失败，请重试。';
export function sizeLabel(size: number) { return size >= 1024 * 1024 ? `${(size / 1024 / 1024).toFixed(1)} MB` : `${Math.max(1, Math.round(size / 1024))} KB`; }
export function dateLabel(date: string) { return new Date(date).toLocaleDateString('zh-CN', { month: 'short', day: 'numeric' }); }
export function documentStatus(doc: KnowledgeDocument) {
  if (doc.needs_reindex) return { label: '需要重建索引', tone: 'warning' };
  const values: Record<string, { label: string; tone: string }> = {
    ready: { label: '可问答', tone: 'success' }, failed: { label: '处理失败', tone: 'danger' },
    queued: { label: '等待处理', tone: 'neutral' }, parsing: { label: '正在解析', tone: 'processing' },
    embedding: { label: '正在向量化', tone: 'processing' }, indexing: { label: '建立索引中', tone: 'processing' },
    waiting_config: { label: '等待配置', tone: 'warning' },
  };
  return values[doc.status] ?? { label: doc.status, tone: 'neutral' };
}
