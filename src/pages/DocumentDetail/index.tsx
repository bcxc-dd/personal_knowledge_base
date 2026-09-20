import { ArrowLeft, Download, FileText, LoaderCircle, MessageSquare, Search } from 'lucide-react';
import { Link } from 'react-router-dom';
import { documentStatus, sizeLabel } from '../../services/api';
import { useDocumentDetail } from './hooks/useDocumentDetail';
import s from './style/index.module.scss';

export default function DocumentDetail() {
  const m = useDocumentDetail();
  if (m.error) return <><Link className="secondary" to="/library"><ArrowLeft size={15} />返回资料库</Link><div className="notice error" style={{ marginTop: 20 }}>{m.error}</div></>;
  if (m.loading || !m.doc) return <div className="loading"><LoaderCircle size={20} className="spin" />加载资料中</div>;
  const doc = m.doc; const status = documentStatus(doc);
  const chunks = doc.chunks.filter(c => c.text.toLowerCase().includes(m.query.toLowerCase()));
  return <div className={s.page}>
    <Link className={s.back} to={`/library?kb=${doc.kb_id}`}><ArrowLeft size={14} />返回资料库</Link>
    <div className="pageHeading"><div><div className="eyebrow">DOCUMENT READER</div><h1 className={s.title}>{doc.name}</h1><div className={s.meta}><span>{doc.suffix.slice(1).toUpperCase()}</span><i />{sizeLabel(doc.size)}<i />{doc.chunk_count} 个片段<span className={`badge ${status.tone}`}>{status.label}</span></div></div><div className={s.buttons}><a className="secondary" href={`/api/documents/${doc.id}/file`}><Download size={15} />原文件</a><Link className="primary" to={`/chat?kb=${doc.kb_id}&doc=${doc.id}`}><MessageSquare size={15} />基于此资料提问</Link></div></div>
    {doc.error && <div className="notice error">{doc.error}</div>}
    <div className={s.reader}><header><span><FileText size={16} />提取正文与知识片段</span><label><Search size={14} /><input placeholder="在正文中查找…" aria-label="查找正文" value={m.query} onChange={e => m.setQuery(e.target.value)} /></label></header><div className={s.explainer}>以下为实际用于检索的文本。相邻片段可能保留少量重叠，以避免上下文在边界处丢失。</div>{chunks.length ? chunks.map(c => <section id={c.id} key={c.id} className={`${s.chunk} ${m.chunkId === c.id ? s.highlight : ''}`}><div><span>{c.location}</span><small>CHUNK {String(c.ordinal + 1).padStart(2, '0')}</small></div><p>{c.text}</p></section>) : <div className="emptyState"><p>{doc.chunks.length ? '没有找到匹配的正文' : '正文尚未解析完成，请稍候或在资料库重试。'}</p></div>}</div>
  </div>;
}
