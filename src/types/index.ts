export interface KnowledgeBase { id: string; name: string; document_count: number }
export interface KnowledgeDocument {
  id: string; kb_id: string; name: string; suffix: string; size: number; status: string;
  error: string; chunk_count: number; created_at: string; updated_at: string; needs_reindex: boolean;
}
export interface Chunk { id: string; text: string; ordinal: number; location: string }
export interface DocumentDetail extends KnowledgeDocument { chunks: Chunk[] }
export interface Citation { id: number; document_id: string; chunk_id: string; name: string; text: string; location: string; deleted?: boolean }
export interface RetrievalDiagnosticItem extends Citation { vector_similarity?: number; distance?: number; rerank_score?: number; vector_rank?: number; rerank_rank?: number; selected?: boolean }
export interface RetrievalDiagnostics { candidate_count: number; items: RetrievalDiagnosticItem[]; provider: string; device: string; fallback: boolean; error?: string | null }
export interface Message { id: string; role: 'user' | 'assistant'; content: string; citations: Citation[]; status: string; retrieval_diagnostics?: RetrievalDiagnostics }
export interface Conversation { id: string; title: string; kb_id: string; created_at: string }
export interface ModelSettings {
  chat_url: string; chat_model: string; chat_key_set: boolean;
  embedding_mode: 'local' | 'api'; embedding_url: string; embedding_model: string;
  embedding_key_set: boolean; allow_external: boolean;
  reranker_enabled: boolean; reranker_device: 'auto' | 'cuda' | 'cpu'; reranker_model: string; reranker_candidates: number; reranker_evidence: number;
}
