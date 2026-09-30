// @vitest-environment jsdom
import { afterEach, expect, test, vi } from 'vitest';
import { cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react';
import { MemoryRouter, Route, Routes } from 'react-router-dom';
import DocumentDetail from '../../index';

vi.mock('./pdfCanvas', () => ({ renderPdfPage: async () => {} }));

const documentData = {
  id: 'pdf1', kb_id: 'default', name: '推免细则.pdf', suffix: '.pdf', size: 2048,
  status: 'ready', error: '', chunk_count: 2, created_at: '2026-09-29T00:00:00Z',
  updated_at: '2026-09-29T00:00:00Z', needs_reindex: false,
  suspicious_pages: [9],
  chunks: [
    { id: 'pdf1:0', text: 'CSP g_i \uf03d 0.2', ordinal: 0, location: '第 9 页', suspected: true },
    { id: 'pdf1:1', text: '普通说明', ordinal: 1, location: '第 10 页', suspected: false },
  ],
};

const pageData = {
  raw_text: 'CSP g_i \uf03d 0.2\n其他要求。', page_count: 10,
  source_hash: 'source-sha', raw_text_hash: 'raw-sha', suspected: true,
  correction: null, revision: null, rect: null, has_image: false,
};
const reviewModule = './index.tsx';
const reviewHookModule = './hooks/usePdfPageReview.ts';

function response(value: unknown, status = 200) {
  return { ok: status < 400, status, json: async () => value };
}

afterEach(() => { cleanup(); vi.unstubAllGlobals(); Reflect.deleteProperty(HTMLElement.prototype, 'scrollIntoView'); });

test('PDF detail flags suspect page and keeps manual review entry on normal page', async () => {
  vi.stubGlobal('fetch', vi.fn(async () => response(documentData)));
  render(<MemoryRouter initialEntries={['/documents/pdf1']}><Routes><Route path="/documents/:id" element={<DocumentDetail />} /></Routes></MemoryRouter>);

  expect(await screen.findByText('疑似解析异常')).toBeTruthy();
  expect(screen.getAllByRole('button', { name: '校对本页' })).toHaveLength(2);
});

test('clicking review brings the panel into view, including when reopening the same page', async () => {
  const scrollIntoView = vi.fn();
  HTMLElement.prototype.scrollIntoView = scrollIntoView;
  vi.stubGlobal('fetch', vi.fn(async (input: string) => response(
    input.includes('/pdf-pages/') ? pageData : documentData,
  )));
  render(<MemoryRouter initialEntries={['/documents/pdf1']}><Routes><Route path="/documents/:id" element={<DocumentDetail />} /></Routes></MemoryRouter>);

  const buttons = await screen.findAllByRole('button', { name: '校对本页' });
  fireEvent.click(buttons[0]);
  expect(await screen.findByLabelText('第 9 页公式校对')).toBeTruthy();
  expect(scrollIntoView).toHaveBeenCalledWith({ behavior: 'auto', block: 'start' });
  fireEvent.click(buttons[0]);
  expect(scrollIntoView).toHaveBeenCalledTimes(2);
});

test('review compares original text, confirms full-page change, and sends hashes once', async () => {
  let finishSave: ((value: ReturnType<typeof response>) => void) | undefined;
  const save = new Promise<ReturnType<typeof response>>(resolve => { finishSave = resolve; });
  const fetcher = vi.fn(async (input: string, init?: RequestInit) => {
    if (!init || init.method === 'GET') return response(pageData);
    if (init.method === 'PUT') return save;
    return response({ ok: true });
  });
  vi.stubGlobal('fetch', fetcher);
  const { default: PdfPageReview } = await import(/* @vite-ignore */ reviewModule);
  const onSaved = vi.fn(async () => {});
  render(<PdfPageReview documentId="pdf1" pageNumber={9} onClose={() => {}} onSaved={onSaved} />);

  expect(await screen.findByText('原始提取文本')).toBeTruthy();
  expect(screen.getAllByText(/CSP g_i/).length).toBeGreaterThan(0);
  const editor = screen.getByRole('textbox', { name: '校对后的整页文本' });
  fireEvent.change(editor, { target: { value: 'g_i = 0.2 if x_i >= 300\n其他要求。' } });
  expect(screen.getByText('整页替换预览')).toBeTruthy();
  const submit = screen.getByRole('button', { name: '确认并重建索引' });
  expect((submit as HTMLButtonElement).disabled).toBe(true);
  fireEvent.click(screen.getByRole('checkbox', { name: /已对照原 PDF/ }));
  fireEvent.click(submit);
  fireEvent.click(submit);
  await waitFor(() => expect(fetcher.mock.calls.filter(([, init]) => init?.method === 'PUT')).toHaveLength(1));
  expect((editor as HTMLTextAreaElement).disabled).toBe(true);
  expect((screen.getByLabelText('上传公式截图') as HTMLInputElement).disabled).toBe(true);
  const put = fetcher.mock.calls.find(([, init]) => init?.method === 'PUT')!;
  const form = put[1]!.body as FormData;
  expect(form.get('source_hash')).toBe('source-sha');
  expect(form.get('raw_text_hash')).toBe('raw-sha');
  expect(form.get('corrected_text')).toBe('g_i = 0.2 if x_i >= 300\n其他要求。');
  expect(form.get('expected_revision')).toBe('');
  finishSave!(response({ ok: true, revision: 'new-revision' }));
  await waitFor(() => expect(onSaved).toHaveBeenCalledTimes(1));
});

test('review shows upload errors and permits reverting an existing correction', async () => {
  const fetcher = vi.fn(async (_input: string, init?: RequestInit) =>
    response(!init || init.method === 'GET'
      ? { ...pageData, correction: 'Fixed formula.\n其他要求。', revision: 'revision-1' }
      : { ok: true }));
  vi.stubGlobal('fetch', fetcher);
  const { default: PdfPageReview } = await import(/* @vite-ignore */ reviewModule);
  render(<PdfPageReview documentId="pdf1" pageNumber={9} onClose={() => {}} onSaved={async () => {}} />);

  const file = await screen.findByLabelText('上传公式截图');
  fireEvent.change(file, { target: { files: [new File(['x'], 'proof.bmp', { type: 'image/bmp' })] } });
  expect(screen.getByText(/PNG 或 JPEG/)).toBeTruthy();
  fireEvent.click(screen.getByRole('button', { name: '撤销本页修订' }));
  fireEvent.click(screen.getByRole('button', { name: '确认撤销' }));
  await waitFor(() => expect(fetcher.mock.calls.some(([, init]) => init?.method === 'DELETE')).toBe(true));
  const withdrawal = fetcher.mock.calls.find(([, init]) => init?.method === 'DELETE')!;
  expect(withdrawal[0]).toContain('expected_revision=revision-1');
});

test('selection coordinates are normalized and clamped to the PDF canvas', async () => {
  const { normalizeSelection } = await import(/* @vite-ignore */ reviewHookModule);
  const bounds = { left: 10, top: 20, width: 200, height: 100 };
  expect(normalizeSelection(bounds, { x: 170, y: 100 }, { x: 30, y: 40 })).toEqual([0.1, 0.2, 0.8, 0.8]);
  expect(normalizeSelection(bounds, { x: -20, y: 0 }, { x: 250, y: 150 })).toEqual([0, 0, 1, 1]);
});
