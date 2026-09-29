import { LoaderCircle, Minus, Plus, RotateCcw, X } from 'lucide-react';
import { usePdfPageReview, type ReviewRect } from './hooks/usePdfPageReview';
import s from './style/index.module.scss';

function rectangleStyle(rect: ReviewRect) {
  return { left: `${rect[0] * 100}%`, top: `${rect[1] * 100}%`,
    width: `${(rect[2] - rect[0]) * 100}%`, height: `${(rect[3] - rect[1]) * 100}%` };
}

export default function PdfPageReview({ documentId, pageNumber, onClose, onSaved }: {
  documentId: string; pageNumber: number; onClose: () => void; onSaved: () => Promise<void>;
}) {
  const m = usePdfPageReview(documentId, pageNumber, onSaved);
  const sourceUrl = `/api/documents/${documentId}/file#page=${pageNumber}`;
  const before = m.baseline.split('\n');
  const after = m.draft.split('\n');
  const onPaste = (event: React.ClipboardEvent) => {
    const image = Array.from(event.clipboardData.files).find(file => file.type.startsWith('image/'));
    if (image) { event.preventDefault(); m.setImage(image); }
  };

  return <section className={s.panel} aria-label={`第 ${pageNumber} 页公式校对`} onPaste={onPaste}>
    <header className={s.header}><div><small>PDF REVIEW</small><h2>第 {pageNumber} 页 · 公式校对</h2><p>对照原页，修订实际用于检索的整页文本。</p></div><button type="button" className={s.close} aria-label="关闭校对" onClick={onClose}><X size={17} /></button></header>
    {m.loading ? <div className={s.loading}><LoaderCircle size={18} className="spin" />正在读取原页…</div> : !m.page ? <div className="notice error">{m.error || '无法读取 PDF 页面。'}</div> : <>
      <div className={s.columns}>
        <div className={s.visual}><div className={s.sectionHeading}><strong>原 PDF 页面</strong><div className={s.zoom}><button type="button" aria-label="缩小 PDF" onClick={() => m.setZoom(Math.max(0.6, +(m.zoom - 0.2).toFixed(1)))}><Minus size={13} /></button><span>{Math.round(m.zoom * 100)}%</span><button type="button" aria-label="放大 PDF" onClick={() => m.setZoom(Math.min(2.4, +(m.zoom + 0.2).toFixed(1)))}><Plus size={13} /></button></div></div>
          <p className={s.hint}>在页面上拖动框选公式，便于再次核对。框选本身不会改变检索文本。</p>
          <div className={s.canvasScroll}><div ref={m.canvasWrapRef} className={s.canvasWrap} onPointerDown={m.pointerDown} onPointerMove={m.pointerMove} onPointerUp={m.pointerUp}><canvas ref={m.canvasRef} aria-label={`PDF 第 ${pageNumber} 页`} />{m.rect && <div className={s.selection} style={rectangleStyle(m.rect)} />}</div></div>
          {m.renderError && <p className={s.error}>页面预览失败：{m.renderError} <a href={sourceUrl} target="_blank" rel="noreferrer">打开原 PDF 第 {pageNumber} 页</a></p>}
          <label className={s.imageInput}>上传公式截图<input type="file" aria-label="上传公式截图" accept="image/png,image/jpeg" onChange={event => m.setImage(event.target.files?.[0] ?? null)} /></label>
          <p className={s.hint}>也可在此区域粘贴 PNG/JPEG 截图，最多 2 MB。截图只用于人工核对。</p>
          {m.screenshotUrl && <img className={s.screenshot} src={m.screenshotUrl} alt="公式校对截图" />}
        </div>
        <div className={s.textPanel}><div className={s.sectionHeading}><strong>原始提取文本</strong>{m.page.suspected && <span className={s.warning}>检测到可疑字符</span>}</div><pre className={s.raw}>{m.page.raw_text}</pre>
          <label className={s.editorLabel} htmlFor="pdf-correction-text">校对后的整页文本</label>
          <textarea id="pdf-correction-text" aria-label="校对后的整页文本" value={m.draft} maxLength={100_001} rows={15} onChange={event => m.setDraft(event.target.value)} />
          <p className={s.hint}>请保留本页其他有效正文。公式可以用清晰的线性表达与变量说明录入。</p>
        </div>
      </div>
      {m.changed && <div className={s.diff}><h3>整页替换预览</h3><p>确认后，新文本会替换本页的解析结果，并重新切分与建立索引。</p><div><section><strong>当前索引文本</strong>{before.map((line, index) => <pre key={`old-${index}`} className={line !== after[index] ? s.changed : ''}>{line || ' '}</pre>)}</section><section><strong>校对后</strong>{after.map((line, index) => <pre key={`new-${index}`} className={line !== before[index] ? s.changed : ''}>{line || ' '}</pre>)}</section></div></div>}
      <div className={s.footer}><label className={s.confirm}><input type="checkbox" aria-label="已对照原 PDF 确认整页文本" checked={m.confirmed} onChange={event => m.setConfirmed(event.target.checked)} />我已对照原 PDF，确认整页文本及公式无误</label><div className={s.actions}>{m.page.correction && <>{m.confirmRevert ? <button type="button" className={s.danger} disabled={m.busy} onClick={() => void m.revert()}>确认撤销</button> : <button type="button" className={s.secondary} disabled={m.busy} onClick={() => m.setConfirmRevert(true)}><RotateCcw size={14} />撤销本页修订</button>}</>}<button type="button" className="primary" disabled={!m.canSave} onClick={() => void m.save()}>{m.busy ? '正在保存…' : '确认并重建索引'}</button></div></div>
      {m.error && <div className="notice error" role="alert">{m.error}</div>}
      {m.notice && <div className="notice" role="status">{m.notice}</div>}
      <p className={s.history}>原 PDF 保持不变。历史会话和笔记中的引用保留当时文本，可能与本次修订后的检索片段不同。</p>
    </>}
  </section>;
}
