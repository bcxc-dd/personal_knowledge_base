import { useCallback, useEffect, useState } from 'react';
import { useSearchParams } from 'react-router-dom';
import { api, errorMessage, notifyChange } from '../../../services/api';
import type { KnowledgeBase, KnowledgeDocument } from '../../../types';

export function useLibrary() {
  const [params, setParams] = useSearchParams();
  const kb = params.get('kb') ?? 'default';
  const [kbs, setKbs] = useState<KnowledgeBase[]>([]);
  const [documents, setDocuments] = useState<KnowledgeDocument[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');
  const [notice, setNotice] = useState('');
  const [uploading, setUploading] = useState(false);
  const [query, setQuery] = useState('');
  const [filter, setFilter] = useState('all');
  const [newKb, setNewKb] = useState(false);
  const [kbName, setKbName] = useState('');
  const [deleting, setDeleting] = useState<KnowledgeDocument | null>(null);
  const [busy, setBusy] = useState(false);

  const refresh = useCallback(async () => {
    const [rows, bases] = await Promise.all([api.documents(kb), api.kbs()]);
    setDocuments(rows); setKbs(bases);
  }, [kb]);
  useEffect(() => {
    let alive = true;
    setLoading(true); setError('');
    const load = async () => {
      try {
        const [rows, bases] = await Promise.all([api.documents(kb), api.kbs()]);
        if (alive) { setDocuments(rows); setKbs(bases); setError(''); }
      } catch (e) { if (alive) setError(errorMessage(e)); }
      finally { if (alive) setLoading(false); }
    };
    load(); const timer = setInterval(load, 2500);
    return () => { alive = false; clearInterval(timer); };
  }, [kb]);

  const upload = async (files: File[]) => {
    if (!files.length || uploading) return;
    if (files.length > 20) { setNotice('一次最多上传 20 份资料。'); return; }
    setUploading(true); setNotice('');
    let added = 0, duplicates = 0;
    const failures: string[] = [];
    for (const file of files) {
      if (file.size > 20 * 1024 * 1024) { failures.push(`${file.name} 超过 20 MB`); continue; }
      try { const result = await api.upload(file, kb); result.duplicate ? duplicates++ : added++; }
      catch (e) { failures.push(`${file.name}：${errorMessage(e)}`); }
    }
    setNotice([added ? `已上传 ${added} 份资料，正在自动处理。` : '', duplicates ? `${duplicates} 份重复资料已跳过。` : '', ...failures].filter(Boolean).join(' '));
    setUploading(false); notifyChange(); await refresh().catch(() => {});
  };
  const retry = async (doc: KnowledgeDocument) => { try { await api.retry(doc.id); setNotice('已加入处理队列。'); await refresh(); } catch (e) { setNotice(errorMessage(e)); } };
  const remove = async () => {
    if (!deleting) return;
    setBusy(true);
    try { await api.remove(deleting.id); setDeleting(null); notifyChange(); await refresh(); setNotice('资料及其索引已删除。'); }
    catch (e) { setNotice(errorMessage(e)); }
    finally { setBusy(false); }
  };
  const createKb = async () => {
    if (!kbName.trim()) return;
    setBusy(true);
    try { const item = await api.createKb(kbName); setParams({ kb: item.id }); setKbName(''); setNewKb(false); notifyChange(); }
    catch (e) { setNotice(errorMessage(e)); }
    finally { setBusy(false); }
  };
  const filtered = documents.filter(d => d.name.toLowerCase().includes(query.toLowerCase()) && (filter === 'all' || (filter === 'ready' ? d.status === 'ready' && !d.needs_reindex : d.status !== 'ready' || d.needs_reindex)));
  return { kb, kbs, documents, filtered, loading, error, notice, setNotice, uploading, upload, retry, query, setQuery, filter, setFilter, setParams, newKb, setNewKb, kbName, setKbName, createKb, deleting, setDeleting, remove, busy };
}
