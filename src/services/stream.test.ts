import { describe, expect, it } from 'vitest';

describe('answer event stream', () => {
  it('preserves Chinese tokens split across network chunks', async () => {
    const module = await import('./stream');
    const bytes = new TextEncoder().encode('event: token\ndata: "中文"\n\nevent: done\ndata: {"content":"中文"}\n\n');
    const chunks = [bytes.slice(0, 23), bytes.slice(23, 25), bytes.slice(25)];
    const body = new ReadableStream<Uint8Array>({ start(controller) { chunks.forEach(c => controller.enqueue(c)); controller.close(); } });
    const events: Array<{ event: string; data: unknown }> = [];
    await module.consumeEvents(body, e => events.push(e));
    expect(events).toEqual([{ event: 'token', data: '中文' }, { event: 'done', data: { content: '中文' } }]);
  });
  it('rejects a disconnected response rather than marking it complete', async () => {
    const module = await import('./stream');
    const body = new ReadableStream<Uint8Array>({ start(controller) { controller.enqueue(new TextEncoder().encode('event: token\ndata: "partial"\n\n')); controller.close(); } });
    await expect(module.consumeEvents(body, () => {})).rejects.toThrow('中断');
  });
});
