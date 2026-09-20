import { useEffect, useState } from 'react';
import ReactMarkdown from 'react-markdown';
import { api, type Note } from '../../services/api';
import s from './style/index.module.scss';

export default function Notes() {
  const [notes, setNotes] = useState<Note[]>([]); const [active, setActive] = useState<Note | null>(null); const [title, setTitle] = useState(''); const [content, setContent] = useState(''); const [query, setQuery] = useState('');
  const load = () => api.notes(query).then(setNotes).catch(() => {});
  useEffect(() => { load(); }, [query]);
  const open = (note: Note) => { setActive(note); setTitle(note.title); setContent(note.content); };
  const save = async () => { if (!active) return; const updated = await api.updateNote(active.id, { title, content }); setActive(updated); await load(); };
  const remove = async () => { if (!active || !window.confirm('删除这篇复习笔记？')) return; await api.deleteNote(active.id); setActive(null); await load(); };
  return <div className={s.page}><div className="pageHeading"><div><div className="eyebrow">REVIEW NOTES</div><h1>复习笔记</h1><p className="subtitle">保存值得回看的回答，来源仍可回到原文核对。</p></div></div><div className={s.layout}><aside><input placeholder="搜索笔记标题" value={query} onChange={e => setQuery(e.target.value)} />{notes.map(note => <button className={active?.id === note.id ? s.active : ''} key={note.id} onClick={() => open(note)}><b>{note.title}</b><small>{new Date(note.updated_at).toLocaleDateString('zh-CN')}</small></button>)}</aside><section className={s.editor}>{active ? <><input className={s.title} value={title} onChange={e => setTitle(e.target.value)} /><textarea value={content} onChange={e => setContent(e.target.value)} /><div><button className="primary" onClick={save}>保存修改</button><button className="secondary" onClick={remove}>删除</button></div><div className={s.preview}><ReactMarkdown>{content}</ReactMarkdown></div><div className={s.refs}><strong>来源</strong>{active.citations.map((c: any) => <p key={c.id}>{c.deleted ? '来源已删除' : `${c.name} · ${c.location}`}</p>)}</div></> : <p className={s.empty}>选择一篇笔记开始复习。</p>}</section></div></div>;
}
