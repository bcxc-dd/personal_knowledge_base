import { useEffect, useState } from 'react';
import { useParams, useSearchParams } from 'react-router-dom';
import { api, errorMessage } from '../../../services/api';
import type { DocumentDetail } from '../../../types';

export function useDocumentDetail() {
  const { id } = useParams(); const [params] = useSearchParams();
  const [doc, setDoc] = useState<DocumentDetail | null>(null);
  const [error, setError] = useState('');
  const [query, setQuery] = useState('');
  const [loading, setLoading] = useState(true);
  const chunkId = params.get('chunk');
  useEffect(() => {
    let active = true;
    const load = () => api.document(id!).then(d => { if (active) { setDoc(d); setError(''); } }).catch(e => { if (active) setError(errorMessage(e)); }).finally(() => { if (active) setLoading(false); });
    load(); const timer = setInterval(load, 4000);
    return () => { active = false; clearInterval(timer); };
  }, [id]);
  useEffect(() => { if (doc && chunkId) document.getElementById(chunkId)?.scrollIntoView({ behavior: 'smooth', block: 'center' }); }, [doc?.id, chunkId]);
  return { doc, loading, error, query, setQuery, chunkId };
}
