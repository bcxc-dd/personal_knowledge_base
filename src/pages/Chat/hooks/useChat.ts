import { useEffect, useRef, useState } from 'react';
import { useSearchParams } from 'react-router-dom';
import { api, errorMessage } from '../../../services/api';
import type { Citation, Conversation, KnowledgeBase, KnowledgeDocument, Message, ModelSettings } from '../../../types';

export function useChat() {
  const [params, setParams] = useSearchParams();
  const kb = params.get('kb') ?? 'default';
  const selectedDoc = params.get('doc') ?? '';
  const [kbs, setKbs] = useState<KnowledgeBase[]>([]);
  const [documents, setDocuments] = useState<KnowledgeDocument[]>([]);
  const [settings, setSettings] = useState<ModelSettings | null>(null);
  const [conversations, setConversations] = useState<Conversation[]>([]);
  const [conversationId, setConversationId] = useState<string>();
  const [messages, setMessages] = useState<Message[]>([]);
  const [input, setInput] = useState('');
  const [error, setError] = useState('');
  const [warning, setWarning] = useState('');
  const [busy, setBusy] = useState(false);
  const [loading, setLoading] = useState(false);
  const [status, setStatus] = useState('');
  const [saved, setSaved] = useState<Record<string, boolean>>({});
  const [sources, setSources] = useState<Citation[]>([]);
  const [activeSource, setActiveSource] = useState<Citation | null>(null);
  const abort = useRef<AbortController | null>(null);
  const bottom = useRef<HTMLDivElement>(null);
  const sending = useRef(false);

  useEffect(() => {
    let alive = true;
    setMessages([]); setConversationId(undefined); setSources([]); setActiveSource(null); setError('');
    const load = () => Promise.all([api.kbs(), api.documents(kb), api.settings(), api.conversations()]).then(([k, d, s, c]) => { if (alive) { setKbs(k); setDocuments(d); setSettings(s); setConversations(c); } }).catch(e => { if (alive) setError(errorMessage(e)); });
    load(); const timer = setInterval(load, 5000);
    return () => { alive = false; clearInterval(timer); abort.current?.abort(); };
  }, [kb, selectedDoc]);
  useEffect(() => { bottom.current?.scrollIntoView({ behavior: 'smooth', block: 'end' }); }, [messages]);

  const send = async (value = input) => {
    const question = value.trim();
    if (!question || sending.current || loading) return;
    sending.current = true; setBusy(true); setInput(''); setError(''); setWarning(''); setSources([]); setActiveSource(null); setStatus('正在检索相关资料…');
    const id = crypto.randomUUID();
    setMessages(prev => [...prev, { id: crypto.randomUUID(), role: 'user', content: question, citations: [], status: 'complete' }, { id, role: 'assistant', content: '', citations: [], status: 'streaming' }]);
    const patch = (fields: Partial<Message>) => setMessages(prev => prev.map(m => m.id === id ? { ...m, ...fields } : m));
    const controller = new AbortController(); abort.current = controller;
    try {
      await api.ask({ question, kb_id: kb, document_ids: selectedDoc ? [selectedDoc] : [], conversation_id: conversationId }, controller.signal, ({ event, data }) => {
        if (event === 'meta') setConversationId(data.conversation_id);
        if (event === 'status') setStatus(data);
        if (event === 'sources') { const refs = data.citations ?? data; setSources(refs); setActiveSource(refs[0] ?? null); patch({ citations: refs, retrieval_diagnostics: data.retrieval_diagnostics }); setStatus('正在结合资料组织回答…'); }
        if (event === 'token') setMessages(prev => prev.map(m => m.id === id ? { ...m, content: m.content + data } : m));
        if (event === 'done') { patch({ content: data.content, citations: data.citations, status: 'complete' }); setWarning(data.warning ?? ''); }
      });
    } catch (e) {
      const stopped = controller.signal.aborted;
      setError(stopped ? '已停止生成。已有内容未完成，请核对或重新提问。' : errorMessage(e));
      patch({ status: 'interrupted' });
      setInput(question);
    } finally {
      sending.current = false; setBusy(false); setStatus(''); abort.current = null;
      api.conversations().then(setConversations).catch(() => {});
    }
  };
  const newChat = () => { if (sending.current) return; setMessages([]); setConversationId(undefined); setSources([]); setActiveSource(null); setError(''); setWarning(''); };
  const loadConversation = async (id: string) => {
    if (!id) { newChat(); return; }
    setLoading(true); setError(''); setWarning('');
    try { const convo = await api.conversation(id); setMessages(convo.messages); setConversationId(id); const refs = convo.messages.at(-1)?.citations ?? []; setSources(refs); setActiveSource(refs[0] ?? null); }
    catch (e) { setError(errorMessage(e)); } finally { setLoading(false); }
  };
  const deleteConversation = async () => {
    if (!conversationId || !window.confirm('删除这段会话及其问答记录？此操作不会删除原始资料。')) return;
    try { await api.deleteConversation(conversationId); newChat(); setConversations(await api.conversations()); }
    catch (e) { setError(errorMessage(e)); }
  };
  const selectSource = (citation: Citation, refs?: Citation[]) => { if (refs) setSources(refs); setActiveSource(citation); };
  const saveNote = async (message: Message) => {
    if (!message.content || message.role !== 'assistant') return;
    const index = messages.indexOf(message);
    const question = index > 0 ? messages[index - 1]?.content ?? '' : '';
    await api.createNote({ title: question.slice(0, 40) || '复习笔记', question, content: message.content, citations: message.citations });
    setSaved(prev => ({ ...prev, [message.id]: true }));
  };
  const setScope = (nextKb: string, doc = '') => { if (!busy) setParams({ kb: nextKb, ...(doc ? { doc } : {}) }); };
  return { kb, selectedDoc, kbs, documents, settings, conversations: conversations.filter(c => c.kb_id === kb), conversationId, messages, input, setInput, error, warning, busy, loading, status, sources, activeSource, bottom, saved, saveNote, send, stop: () => abort.current?.abort(), newChat, loadConversation, deleteConversation, selectSource, setScope };
}
