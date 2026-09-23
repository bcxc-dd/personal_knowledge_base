import { useState } from 'react';
import type { RetrievalDiagnostics as Data } from '../../../../types';
import s from './style/index.module.scss';

export default function RetrievalDiagnostics({ data }: { data?: Data }) {
  const [open, setOpen] = useState(false);
  if (!data || !data.items.length) return null;
  const rows = (title: string, items: Data['items']) => <section><strong>{title}</strong>{items.map(item => <div className={`${s.row} ${item.selected ? s.selected : ''}`} key={`${title}-${item.chunk_id}`}><div className={s.name}>{item.name} · {item.location}{item.selected && <b>已选</b>}</div><small>{item.vector_similarity == null ? '' : `向量 ${(item.vector_similarity).toFixed(3)} · `}{item.lexical_score == null ? '' : `词法 ${item.lexical_score} · `}{item.fused_score == null ? '' : `RRF ${item.fused_score.toFixed(4)}`}</small></div>)}</section>;
  return <div className={s.box}><button className={s.toggle} onClick={() => setOpen(!open)}>{open ? '收起检索分析' : '查看检索分析'}<span>{data.fallback ? 'RRF 回退' : `${data.provider} · ${data.device}`}</span></button>{open && <div className={s.body}><p>融合候选 {data.candidate_count} 个，RRF k={data.rrf_k ?? 60}。</p>{data.vector_items?.length ? rows('向量候选', data.vector_items) : null}{data.lexical_items?.length ? rows('术语候选', data.lexical_items) : null}{rows('最终回答证据', data.items.filter(item => item.selected))}</div>}</div>;
}
