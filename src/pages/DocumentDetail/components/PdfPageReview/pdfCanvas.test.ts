// @vitest-environment jsdom
import { expect, test, vi } from 'vitest';
import { renderPdfPage } from './pdfCanvas';

const pdfMocks = vi.hoisted(() => ({ getDocument: vi.fn(), worker: { workerSrc: '' } }));
vi.mock('pdfjs-dist', () => ({ getDocument: pdfMocks.getDocument, GlobalWorkerOptions: pdfMocks.worker }));

test('aborted page request never paints an obsolete zoom level', async () => {
  let finishPage!: (value: unknown) => void;
  const pagePromise = new Promise(resolve => { finishPage = resolve; });
  const render = vi.fn(() => ({ promise: Promise.resolve(), cancel: vi.fn() }));
  const getPage = vi.fn(() => pagePromise);
  const destroy = vi.fn(async () => {});
  pdfMocks.getDocument.mockReturnValue({ promise: Promise.resolve({ getPage }), destroy });
  const canvas = document.createElement('canvas');
  vi.spyOn(canvas, 'getContext').mockReturnValue({} as CanvasRenderingContext2D);
  const controller = new AbortController();

  const pending = renderPdfPage(canvas, '/pdf', 9, 1.1, controller.signal);
  await vi.waitFor(() => expect(getPage).toHaveBeenCalledWith(9));
  controller.abort();
  finishPage({ getViewport: () => ({ width: 100, height: 100 }), render });
  await pending;

  expect(pdfMocks.worker.workerSrc).toMatch(/[?&]mime=javascript(?:&|$)/);
  expect(render).not.toHaveBeenCalled();
  expect(destroy).toHaveBeenCalledOnce();
});
