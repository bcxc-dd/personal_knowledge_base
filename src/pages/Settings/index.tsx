import { ArrowUpRight, Check, Cpu, Database, KeyRound, LoaderCircle, LockKeyhole, RefreshCw, Save, ShieldCheck, Sparkles } from 'lucide-react';
import { useSettings } from './hooks/useSettings';
import type { ModelSettings } from '../../types';
import s from './style/index.module.scss';

export default function Settings() {
  const m = useSettings();
  const c = m.config;
  return <div className={s.page}>
    <div className="pageHeading"><div><div className="eyebrow">MAKE IT YOUR OWN</div><h1>为你的知识，连接智能</h1><p className="subtitle">一个模型理解资料，一个模型组织答案。各司其职，清晰可控。</p></div></div>
    {m.loading ? <div className="loading"><LoaderCircle size={20} className="spin" />加载配置中</div> : <>
      {m.error && <div className="notice error" role="alert">{m.error}</div>}{m.message && <div className="notice success" role="status"><Check size={16} />{m.message}</div>}
      {c && <form onSubmit={e => { e.preventDefault(); m.save(); }}>
        <section className={s.card}><div className={s.cardHeading}><span className={s.icon}><Sparkles size={20} /></span><div><h2>回答模型</h2><p>根据检索到的资料，生成有来源的回答</p></div><span className={s.pill}>支持 DeepSeek</span></div>
          <div className={s.grid}><label>服务地址<input required type="url" value={c.chat_url} onChange={e => m.change('chat_url', e.target.value)} placeholder="https://api.deepseek.com" /><small>填写基础地址，不包含 /chat/completions</small></label><label>模型名称<input required value={c.chat_model} onChange={e => m.change('chat_model', e.target.value)} placeholder="deepseek-flash" /><small>支持 OpenAI 兼容的聊天接口</small></label></div>
          <label className={s.keyLabel}><span>API Key {c.chat_key_set && <span className={s.saved}><ShieldCheck size={12} />已保存在本机</span>}</span><div className={s.keyInput}><KeyRound size={16} /><input type="password" autoComplete="new-password" value={m.chatKey} onChange={e => m.setChatKey(e.target.value)} placeholder={c.chat_key_set ? '留空保留已保存的密钥' : '在这里填写你的 DeepSeek API Key'} /></div></label>
          <div className={s.cardFooter}><span><LockKeyhole size={12} />密钥只保存在本机后端，保存后不会回传浏览器</span>{c.chat_key_set && <button type="button" onClick={m.clearKey} disabled={m.busy}>删除已存密钥</button>}</div>
        </section>
        <section className={s.card}><div className={s.cardHeading}><span className={`${s.icon} ${s.purple}`}><Cpu size={20} /></span><div><h2>向量模型</h2><p>把资料和问题转换为向量，找到语义相关的内容</p></div><span className={s.pill}>Embedding</span></div>
          <div className={s.choices}><button type="button" className={c.embedding_mode === 'local' ? s.chosen : ''} onClick={() => { m.change('embedding_mode', 'local'); m.change('embedding_model', 'BAAI/bge-small-zh-v1.5'); }}><span><Cpu size={17} />本地中文模型<small>推荐</small></span><p>无需 API Key，资料在本机完成向量化</p><i /></button><button type="button" className={c.embedding_mode === 'api' ? s.chosen : ''} onClick={() => { m.change('embedding_mode', 'api'); m.change('embedding_model', ''); }}><span><ArrowUpRight size={17} />自定义 API</span><p>使用你已有的兼容 Embedding 服务</p><i /></button></div>
          {c.embedding_mode === 'local' ? <div className={s.localInfo}><Database size={18} /><div><strong>BAAI / bge-small-zh-v1.5</strong><p>首次处理资料时下载约 90 MB 模型，后续从本机缓存加载。适合中文资料，也支持英文片段；无需独立显卡。</p></div></div> : <><div className={s.grid}><label>向量服务地址<input required type="url" value={c.embedding_url} onChange={e => m.change('embedding_url', e.target.value)} placeholder="https://your-provider.com/v1" /></label><label>向量模型名称<input required value={c.embedding_model} onChange={e => m.change('embedding_model', e.target.value)} placeholder="服务商提供的 Embedding 模型名称" /></label></div><label className={s.keyLabel}>向量服务 API Key<input type="password" autoComplete="new-password" value={m.embeddingKey} onChange={e => m.setEmbeddingKey(e.target.value)} placeholder={c.embedding_key_set ? '留空保留已保存的密钥' : '本地兼容服务可留空'} /></label><p className={s.help}>回答模型与向量模型是两个独立接口，请使用提供 /embeddings 的服务。</p></>}
        </section>
        <section className={s.card}><div className={s.cardHeading}><span className={`${s.icon} ${s.purple}`}><Sparkles size={20} /></span><div><h2>本地重排</h2><p>对召回片段再次评分，提升证据相关性</p></div><span className={s.pill}>Rerank</span></div><div className={s.grid}><label><span><input type="checkbox" checked={c.reranker_enabled} onChange={e => m.change('reranker_enabled', e.target.checked)} /> 启用本地重排</span><small>首次使用会下载模型；不可用时自动回退到向量检索</small></label><label>重排策略<select value={c.reranker_model} onChange={e => m.change('reranker_model', e.target.value)}><option value="BAAI/bge-reranker-base">BGE Reranker Base（中文/多语言通用）</option><option value="jinaai/jina-reranker-v2-base-multilingual">Jina Reranker v2（多语言，模型更大）</option></select><small>策略决定本地下载和推理使用的重排模型</small></label><label>运行设备<select value={c.reranker_device} onChange={e => m.change('reranker_device', e.target.value as ModelSettings['reranker_device'])}><option value="auto">自动选择</option><option value="cuda">CUDA GPU</option><option value="cpu">CPU</option></select><small>RTX 4060 Laptop 8GB 可选择自动或 CUDA</small></label></div></section>
        <section className={s.privacy}><ShieldCheck size={22} /><div><h3>由你决定资料的使用范围</h3><p>生成回答会将问题和相关片段发送到上方配置的回答服务。若选择向量 API，切分后的正文也会发送给向量服务。</p><label><input type="checkbox" checked={c.allow_external} onChange={e => m.change('allow_external', e.target.checked)} />我允许将上述内容发送到我配置的模型服务</label></div></section>
        <div className={s.saveRow}><span>配置修改仅在保存后生效</span><button className="primary" disabled={m.busy} type="submit">{m.busy ? <LoaderCircle size={15} className="spin" /> : <Save size={15} />}保存配置</button></div>
      </form>}
      <section className={s.maintenance}><div><h2>索引维护</h2><p>更换向量模型后，重建索引以保持资料与问题使用相同的向量空间。</p></div><button className="secondary" onClick={m.reindex} disabled={m.busy}><RefreshCw size={14} />重建所有索引</button></section>
    </>}
  </div>;
}
