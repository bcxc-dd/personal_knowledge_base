import { useCallback, useEffect, useRef, useState } from 'react';
import { api, errorMessage } from '../../../../../services/api';
import type { PdfPageResponse } from '../../../../../types';
import { renderPdfPage } from '../pdfCanvas';

type Point = { x: number; y: number };
type Bounds = Pick<DOMRect, 'left' | 'top' | 'width' | 'height'>;
export type ReviewRect = [number, number, number, number];

export function normalizeSelection(bounds: Bounds, start: Point, end: Point): ReviewRect | null {
  if (bounds.width <= 0 || bounds.height <= 0) return null;
  const clamp = (value: number) => Math.max(0, Math.min(1, value));
  const x1 = clamp((Math.min(start.x, end.x) - bounds.left) / bounds.width);
  const y1 = clamp((Math.min(start.y, end.y) - bounds.top) / bounds.height);
  const x2 = clamp((Math.max(start.x, end.x) - bounds.left) / bounds.width);
  const y2 = clamp((Math.max(start.y, end.y) - bounds.top) / bounds.height);
  return x2 > x1 && y2 > y1 ? [x1, y1, x2, y2] : null;
}

export function usePdfPageReview(documentId: string, pageNumber: number, onSaved: () => Promise<void>) {
  const [page, setPage] = useState<PdfPageResponse | null>(null);
  const [draft, setDraft] = useState('');
  const [rect, setRect] = useState<ReviewRect | null>(null);
  const [screenshot, setScreenshot] = useState<File | null>(null);
  const [screenshotUrl, setScreenshotUrl] = useState<string | null>(null);
  const [confirmed, setConfirmed] = useState(false);
  const [confirmRevert, setConfirmRevert] = useState(false);
  const [busy, setBusy] = useState(false);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');
  const [notice, setNotice] = useState('');
  const [zoom, setZoom] = useState(1.1);
  const [renderError, setRenderError] = useState('');
  const [dragStart, setDragStart] = useState<Point | null>(null);
  const [dragCurrent, setDragCurrent] = useState<Point | null>(null);
  const canvasRef = useRef<HTMLCanvasElement>(null);
  const canvasWrapRef = useRef<HTMLDivElement>(null);
  const objectUrl = useRef<string | null>(null);

  const load = useCallback(async () => {
    const current = await api.pdfPage(documentId, pageNumber);
    setPage(current);
    setDraft(current.correction ?? current.raw_text);
    setRect(current.rect);
    setConfirmed(false);
    setConfirmRevert(false);
    setScreenshot(null);
    if (objectUrl.current) URL.revokeObjectURL(objectUrl.current);
    objectUrl.current = null;
    setScreenshotUrl(current.has_image
      ? `/api/documents/${documentId}/pdf-pages/${pageNumber}/correction-image` : null);
    setError('');
  }, [documentId, pageNumber]);

  useEffect(() => {
    let active = true;
    api.pdfPage(documentId, pageNumber).then(current => {
      if (!active) return;
      setPage(current);
      setDraft(current.correction ?? current.raw_text);
      setRect(current.rect);
      setScreenshotUrl(current.has_image
        ? `/api/documents/${documentId}/pdf-pages/${pageNumber}/correction-image` : null);
    }).catch(exc => { if (active) setError(errorMessage(exc)); })
      .finally(() => { if (active) setLoading(false); });
    return () => { active = false; };
  }, [documentId, pageNumber]);

  useEffect(() => () => { if (objectUrl.current) URL.revokeObjectURL(objectUrl.current); }, []);

  useEffect(() => {
    if (!page || !canvasRef.current) return;
    const controller = new AbortController();
    setRenderError('');
    renderPdfPage(canvasRef.current, `/api/documents/${documentId}/file`, pageNumber, zoom, controller.signal)
      .catch(exc => { if (!controller.signal.aborted) setRenderError(errorMessage(exc)); });
    return () => controller.abort();
  }, [page?.source_hash, documentId, pageNumber, zoom]);

  const setImage = (file: File | null) => {
    if (busy) return;
    if (!file) return;
    if (!['image/png', 'image/jpeg'].includes(file.type)) {
      setError('截图请使用 PNG 或 JPEG 格式。');
      return;
    }
    if (file.size > 2 * 1024 * 1024) {
      setError('截图不能超过 2 MB。');
      return;
    }
    if (objectUrl.current) URL.revokeObjectURL(objectUrl.current);
    objectUrl.current = URL.createObjectURL(file);
    setScreenshot(file);
    setScreenshotUrl(objectUrl.current);
    setError('');
  };

  const baseline = page?.correction ?? page?.raw_text ?? '';
  const changed = !!page && draft.trim() !== baseline && !!draft.trim() && draft.length <= 100_000;
  const canSave = changed && confirmed && !busy;

  const save = async () => {
    if (!page || !canSave) return;
    setBusy(true); setError(''); setNotice('');
    const form = new FormData();
    form.set('source_hash', page.source_hash);
    form.set('raw_text_hash', page.raw_text_hash);
    form.set('corrected_text', draft);
    form.set('expected_revision', page.revision ?? '');
    if (rect) form.set('rect', JSON.stringify(rect));
    if (screenshot) form.set('image', screenshot);
    try {
      await api.savePdfCorrection(documentId, pageNumber, form);
      await load();
      await onSaved();
      setNotice('校对已保存，资料正在重新处理；可问答状态恢复后，新问题将使用修订文本。');
    } catch (exc) {
      setError(errorMessage(exc));
    } finally {
      setBusy(false);
    }
  };

  const revert = async () => {
    if (!page?.correction || !page.revision || busy || !confirmRevert) return;
    setBusy(true); setError(''); setNotice('');
    try {
      await api.removePdfCorrection(documentId, pageNumber, page.revision);
      await load();
      await onSaved();
      setNotice('修订已撤销，资料正在重新处理。');
    } catch (exc) {
      setError(errorMessage(exc));
    } finally {
      setBusy(false);
    }
  };

  const pointerDown = (event: React.PointerEvent<HTMLDivElement>) => {
    if (busy) return;
    setDragStart({ x: event.clientX, y: event.clientY });
    setDragCurrent({ x: event.clientX, y: event.clientY });
    event.currentTarget.setPointerCapture?.(event.pointerId);
  };
  const pointerMove = (event: React.PointerEvent<HTMLDivElement>) => {
    if (!busy && dragStart) setDragCurrent({ x: event.clientX, y: event.clientY });
  };
  const pointerUp = (event: React.PointerEvent<HTMLDivElement>) => {
    if (!busy && dragStart && canvasWrapRef.current) {
      const selection = normalizeSelection(canvasWrapRef.current.getBoundingClientRect(), dragStart,
        { x: event.clientX, y: event.clientY });
      if (selection) setRect(selection);
    }
    setDragStart(null); setDragCurrent(null);
  };
  const liveRect = dragStart && dragCurrent && canvasWrapRef.current
    ? normalizeSelection(canvasWrapRef.current.getBoundingClientRect(), dragStart, dragCurrent) : null;

  return { page, draft, setDraft: (value: string) => { if (!busy) { setDraft(value); setConfirmed(false); } }, baseline,
    rect: liveRect ?? rect, setRect, screenshotUrl, setImage, confirmed, setConfirmed, confirmRevert, setConfirmRevert,
    busy, loading, error, notice, zoom, setZoom, renderError, canvasRef, canvasWrapRef,
    pointerDown, pointerMove, pointerUp, changed, canSave, save, revert };
}
