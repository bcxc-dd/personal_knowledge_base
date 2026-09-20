import type { Citation } from '../../../../../types';
export function useSources(source: Citation | null) {
  return { href: source && !source.deleted ? `/documents/${source.document_id}?chunk=${encodeURIComponent(source.chunk_id)}` : null };
}
