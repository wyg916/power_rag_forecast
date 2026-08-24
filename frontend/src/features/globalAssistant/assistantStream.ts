export interface AssistantStreamEvent {
  event: string;
  payload: any;
}

export interface AssistantStreamResult {
  finalEvent: 'done' | 'finish';
  finalPayload: any;
  streamedMarkdown: string;
  terminalEventCount: number;
}

function streamErrorText(payload: any) {
  const detail = payload?.error;
  if (typeof detail === 'string') return detail;
  if (typeof detail?.message === 'string') return detail.message;
  if (typeof detail?.code === 'string') return detail.code;
  if (typeof payload?.message === 'string') return payload.message;
  return '流式问答返回错误';
}

function parsePayload(dataText: string) {
  if (!dataText) return {};
  try {
    return JSON.parse(dataText);
  } catch {
    throw new Error('流式问答返回了无法解析的事件数据。');
  }
}

export class AssistantSseParser {
  private buffer = '';
  private finalEvent: 'done' | 'finish' | null = null;
  private finalPayload: any = null;
  private streamedMarkdown = '';
  private terminalEventCount = 0;

  constructor(private readonly onEvent: (event: string, payload: any) => void = () => undefined) {}

  push(chunk: string) {
    if (!chunk) return;
    this.buffer += chunk.replace(/\r\n?/g, '\n');
    const frames = this.buffer.split('\n\n');
    this.buffer = frames.pop() || '';
    frames.forEach((frame) => this.consumeFrame(frame));
  }

  finish(): AssistantStreamResult {
    if (this.buffer.trim()) this.consumeFrame(this.buffer);
    this.buffer = '';
    if (!this.finalEvent) throw new Error('流式问答未返回完成事件。');
    return {
      finalEvent: this.finalEvent,
      finalPayload: this.finalPayload || {},
      streamedMarkdown: this.streamedMarkdown,
      terminalEventCount: this.terminalEventCount
    };
  }

  private consumeFrame(frame: string) {
    const lines = frame.split('\n').filter((line) => line && !line.startsWith(':'));
    if (!lines.length) return;
    const event = lines.find((line) => line.startsWith('event:'))?.slice(6).trim() || 'message';
    const dataText = lines
      .filter((line) => line.startsWith('data:'))
      .map((line) => line.slice(5).replace(/^ /, ''))
      .join('\n');
    const payload = parsePayload(dataText);

    if (event === 'done' || event === 'finish') {
      this.terminalEventCount += 1;
      if (this.finalEvent) return;
      this.finalEvent = event;
      this.finalPayload = payload;
      this.onEvent(event, payload);
      return;
    }
    if (this.finalEvent) return;
    this.onEvent(event, payload);
    if (event === 'delta') {
      const delta = payload?.text ?? payload?.delta ?? payload?.markdown ?? '';
      if (typeof delta === 'string') this.streamedMarkdown += delta;
    }
    if (event === 'error') throw new Error(streamErrorText(payload));
  }
}
