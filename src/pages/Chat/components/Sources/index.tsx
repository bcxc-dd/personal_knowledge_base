import { ArrowUpRight, BookOpen, FileCheck2, FileText, Quote } from 'lucide-react';
import { Link } from 'react-router-dom';
import type { Citation } from '../../../../types';
import { useSources } from './hooks/useSources';
import s from './style/index.module.scss';

export default function Sources({ sources, active, onSelect }: { sources: Citation[]; active: Citation | null; onSelect: (source: Citation) => void }) {
  const { href } = useSources(active);
  return <aside className={s.panel}><header><BookOpen size={15} />参考资料<span>{sources.length}</span></header>{sources.length ? <><div className={s.list}>{sources.map(c => <button key={c.id} onClick={() => onSelect(c)} className={active?.id === c.id ? s.active : ''}><span className={s.number}>{c.id}</span><span><strong>{c.name}</strong><small>{c.deleted ? '来源已删除' : c.location}</small></span><FileText size={14} /></button>)}</div>{active && <div className={s.excerpt}><div><Quote size={15} /><span>检索片段</span></div><p>{active.deleted ? '这份资料已被删除，无法继续查看原文。' : active.text}</p>{href && <Link to={href}>查看原文位置<ArrowUpRight size={13} /></Link>}</div>}<p className={s.note}>这里展示本次检索的相关片段。回答中的引用编号与来源对应，请核对关键结论。</p></> : <div className={s.empty}><div><FileCheck2 size={30} strokeWidth={1.2} /></div><h3>每条答案，都有出处</h3><p>提问后，相关的资料片段会出现在这里。随时回到原文，确认每一个细节。</p><span>READ · CONNECT · UNDERSTAND</span></div>}</aside>;
}
