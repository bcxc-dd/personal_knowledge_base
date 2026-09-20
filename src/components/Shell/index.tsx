import { BookOpen, ChevronRight, CircleHelp, Database, FolderClosed, Layers3, MessageSquare, Settings2, Sparkles, StickyNote } from 'lucide-react';
import { Link, NavLink, Outlet, useLocation } from 'react-router-dom';
import { useShell } from './hooks/useShell';
import s from './style/index.module.scss';

export default function Shell() {
  const { kbs, online } = useShell();
  const { pathname } = useLocation();
  const title = pathname.startsWith('/chat') ? '知识问答' : pathname.startsWith('/notes') ? '复习笔记' : pathname.startsWith('/settings') ? '模型设置' : pathname.startsWith('/documents') ? '资料详情' : '资料库';
  return <div className={s.shell}>
    <aside className={s.sidebar}>
      <Link to="/library" className={s.brand}><span className={s.logo}><Layers3 size={23} strokeWidth={1.7} /></span><span>知屿<small>YOUR KNOWLEDGE, CONNECTED</small></span></Link>
      <div className={s.workspace}><span className={s.avatar}>我</span><div>个人工作空间<small>Personal workspace</small></div><span className={s.local}>LOCAL</span></div>
      <span className={s.label}>工作空间</span>
      <nav className={s.nav}>
        <NavLink to="/library" className={({ isActive }) => isActive ? s.active : ''}><BookOpen size={18} />资料库<span className={s.count}>{kbs.reduce((sum, kb) => sum + kb.document_count, 0)}</span></NavLink>
        <NavLink to="/chat" className={({ isActive }) => isActive ? s.active : ''}><MessageSquare size={18} />知识问答<Sparkles size={13} className={s.navSpark} /></NavLink>
        <NavLink to="/notes" className={({ isActive }) => isActive ? s.active : ''}><StickyNote size={18} />复习笔记</NavLink>
      </nav>
      <span className={s.label}>我的知识库</span>
      <div className={s.kbs}>{kbs.map(kb => <Link to={`/library?kb=${kb.id}`} key={kb.id}><FolderClosed size={15} /><span>{kb.name}</span><small>{kb.document_count}</small></Link>)}</div>
      <div className={s.tip}><span><Sparkles size={15} />让知识产生连接</span><p>把散落的资料，变成随时可用的答案。</p><Link to="/chat">开始一次对话 <ChevronRight size={14} /></Link></div>
      <nav className={`${s.nav} ${s.bottom}`}><NavLink to="/settings" className={({ isActive }) => isActive ? s.active : ''}><Settings2 size={18} />模型设置</NavLink><a href="http://127.0.0.1:8765/docs" target="_blank" rel="noreferrer"><CircleHelp size={18} />接口文档<small>MVP 0.1</small></a></nav>
      <div className={s.profile}><span className={s.profileIcon}>P</span><span>我的知识空间<small>每一份积累，都有回响</small></span></div>
    </aside>
    <div className={s.main}>
      <header className={s.topbar}><span>工作空间 <ChevronRight size={13} /> <strong>{title}</strong></span><span className={s.connection}><i className={online ? s.on : s.off} />{online ? '本地服务已连接' : '正在连接本地服务'}<span className={s.divider} /><Database size={13} /> Chroma</span></header>
      <main className={s.content}><Outlet /></main>
      <footer className={s.footer}><span>知屿 · 让知识触手可及</span><span>LOCAL FIRST <span>•</span> BUILT FOR YOUR MIND</span></footer>
    </div>
  </div>;
}
