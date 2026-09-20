import { ArrowUp, FileText, LoaderCircle, Plus, UploadCloud } from 'lucide-react';
import { useUploadZone } from './hooks/useUploadZone';
import s from './style/index.module.scss';

export default function UploadZone({ onUpload, disabled }: { onUpload: (files: File[]) => void; disabled: boolean }) {
  const { input, dragging, setDragging, onDrop } = useUploadZone(onUpload, disabled);
  return <div className={`${s.zone} ${dragging ? s.dragging : ''}`} onDragOver={e => { e.preventDefault(); setDragging(true); }} onDragLeave={() => setDragging(false)} onDrop={onDrop}>
    <div className={s.illustration}><div className={s.backSheet} /><div className={s.frontSheet}><FileText size={28} strokeWidth={1.1} /></div><span><ArrowUp size={13} /></span><i className={s.spark1}>+</i><i className={s.spark2}>+</i></div>
    <div className={s.copy}><h2>{disabled ? '正在上传你的资料…' : '把知识放在这里，让答案有迹可循'}</h2><p>拖拽文件到这里，或点击上传。解析、切分与索引交给知屿。</p><div className={s.formats}><span>PDF</span><span>DOCX</span><span>TXT</span><span>Markdown</span><i />每份最大 20 MB</div></div>
    <button className={`primary ${s.upload}`} disabled={disabled} onClick={() => input.current?.click()}>{disabled ? <LoaderCircle size={16} className="spin" /> : <Plus size={16} />}上传资料</button>
    <input ref={input} type="file" accept=".pdf,.docx,.txt,.md" multiple hidden aria-label="上传资料文件" onChange={e => { onUpload(Array.from(e.target.files ?? [])); e.target.value = ''; }} />
    <UploadCloud className={s.cloud} size={135} strokeWidth={.5} />
  </div>;
}
