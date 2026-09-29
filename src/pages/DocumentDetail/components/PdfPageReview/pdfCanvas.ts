import workerUrl from 'pdfjs-dist/build/pdf.worker.min.mjs?url';

export async function renderPdfPage(canvas: HTMLCanvasElement, url: string, pageNumber: number,
                                    scale: number, signal: AbortSignal): Promise<void> {
  const pdfjs = await import('pdfjs-dist');
  if (signal.aborted) return;
  pdfjs.GlobalWorkerOptions.workerSrc = workerUrl;
  const loading = pdfjs.getDocument({ url });
  try {
    const pdf = await loading.promise;
    if (signal.aborted) return;
    const page = await pdf.getPage(pageNumber);
    if (signal.aborted) return;
    const viewport = page.getViewport({ scale });
    const context = canvas.getContext('2d');
    if (!context) throw new Error('浏览器无法绘制 PDF 页面。');
    canvas.width = Math.ceil(viewport.width);
    canvas.height = Math.ceil(viewport.height);
    const task = page.render({ canvas, canvasContext: context, viewport });
    signal.addEventListener('abort', () => task.cancel(), { once: true });
    await task.promise;
  } finally {
    await loading.destroy();
  }
}
