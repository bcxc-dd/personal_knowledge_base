import { useEffect, useState } from 'react';
import { api, errorMessage, notifyChange } from '../../../services/api';
import type { ModelSettings } from '../../../types';

export function useSettings() {
  const [config, setConfig] = useState<ModelSettings | null>(null);
  const [chatKey, setChatKey] = useState('');
  const [embeddingKey, setEmbeddingKey] = useState('');
  const [loading, setLoading] = useState(true);
  const [busy, setBusy] = useState(false);
  const [message, setMessage] = useState('');
  const [error, setError] = useState('');
  useEffect(() => { api.settings().then(setConfig).catch(e => setError(errorMessage(e))).finally(() => setLoading(false)); }, []);
  const change = <K extends keyof ModelSettings>(key: K, value: ModelSettings[K]) => setConfig(prev => prev ? { ...prev, [key]: value } : prev);
  const save = async () => {
    if (!config) return;
    setBusy(true); setError(''); setMessage('');
    try {
      const { chat_key_set, embedding_key_set, ...values } = config;
      const result = await api.saveSettings({ ...values, ...(chatKey ? { chat_key: chatKey } : {}), ...(embeddingKey ? { embedding_key: embeddingKey } : {}) });
      setConfig(result); setChatKey(''); setEmbeddingKey('');
      setMessage('配置已保存。如修改了向量模型，请重建现有资料索引。'); notifyChange();
    } catch (e) { setError(errorMessage(e)); }
    finally { setBusy(false); }
  };
  const clearKey = async () => {
    setBusy(true); setError('');
    try { setConfig(await api.saveSettings({ chat_key: '' })); setChatKey(''); setMessage('已删除保存的回答模型密钥。'); }
    catch (e) { setError(errorMessage(e)); } finally { setBusy(false); }
  };
  const reindex = async () => {
    setBusy(true); setMessage(''); setError('');
    try { await api.reindex(); setMessage('资料已加入重新处理队列，可在资料库查看进度。'); }
    catch (e) { setError(errorMessage(e)); } finally { setBusy(false); }
  };
  return { config, change, loading, busy, message, error, chatKey, setChatKey, embeddingKey, setEmbeddingKey, save, reindex, clearKey };
}
