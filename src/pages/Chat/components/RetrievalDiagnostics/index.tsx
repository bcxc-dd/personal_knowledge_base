import { useState } from 'react';
import type { RetrievalDiagnostics as Data } from '../../../../types';
import s from './style/index.module.scss';

export default function RetrievalDiagnostics({ data }: { data?: Data }) {
  const [open, setOpen] = useState(false);
  if (!data || !data.items.length) return null;
  return <div className={s.box}><button className={s.toggle} onClick={() => setOpen(!open)}>{open ? '收起检索分析' : '查看检索分析'}<span>{data.fallback ? '向量回退' : `${data.provider} · ${data.device}`}</span></button>{open && <div className={s.body}><p>候选 {data.candidate_count} 个，最终选中 {data.items.filter(i => i.selected).length} 个。向量相似度与重排分数仅用于相对比较。</p>{data.items.map(item => <div className={`${s.row} ${item.selected ? s.selected : ''}`} key={item.chunk_id}><div className={s.name}>{item.name} · {item.location}{item.selected && <b>已选</b>}</div><div className={s.meter}><i style={{ width: `${Math.max(5, Math.min(100, (item.vector_similarity ?? 0) * 100))}%` }} /></div><small>向量相似度 {(item.vector_similarity ?? 0).toFixed(3)}{item.rerank_score === undefined ? '' : ` · 重排 ${item.rerank_score.toFixed(3)}`}</small></div>)}</div>}</div>;
}
