export type AssistantMarkdownBlock =
  | { type: 'heading'; key: string; level: 1 | 2 | 3; text: string }
  | { type: 'paragraph'; key: string; text: string }
  | { type: 'unordered-list'; key: string; items: string[] }
  | { type: 'ordered-list'; key: string; items: string[] }
  | { type: 'blockquote'; key: string; text: string }
  | { type: 'code'; key: string; language: string; value: string; closed: boolean }
  | { type: 'table'; key: string; headers: string[]; rows: Array<{ key: string; cells: string[] }> };

export interface NormalizedAssistantCitation {
  key: string;
  title: string;
  sourceId: string;
  quote: string;
  href?: string;
}

function stableHash(value: string) {
  let hash = 2166136261;
  for (let index = 0; index < value.length; index += 1) {
    hash ^= value.charCodeAt(index);
    hash = Math.imul(hash, 16777619);
  }
  return (hash >>> 0).toString(36);
}

function safeJson(value: unknown) {
  try {
    return JSON.stringify(value, null, 2);
  } catch {
    return String(value ?? '');
  }
}

export function resolveAssistantAnswerMarkdown(value: unknown, streamedMarkdown = ''): string {
  if (typeof value === 'string') return value.trim() || streamedMarkdown.trim();
  if (typeof value === 'number' || typeof value === 'boolean') return String(value);
  if (value && typeof value === 'object') {
    const record = value as Record<string, unknown>;
    for (const key of ['markdown', 'text', 'content', 'summary', 'answer']) {
      if (typeof record[key] === 'string' && record[key]) return String(record[key]).trim();
    }
    return `\`\`\`json\n${safeJson(value)}\n\`\`\``;
  }
  return streamedMarkdown.trim();
}

function splitTableRow(line: string) {
  const value = line.trim().replace(/^\|/, '').replace(/\|$/, '');
  const cells: string[] = [];
  let current = '';
  let escaped = false;
  for (const character of value) {
    if (escaped) {
      current += character;
      escaped = false;
    } else if (character === '\\') {
      escaped = true;
    } else if (character === '|') {
      cells.push(current.trim());
      current = '';
    } else {
      current += character;
    }
  }
  cells.push(current.trim());
  return cells;
}

function isTableDelimiter(line: string) {
  const cells = splitTableRow(line);
  return cells.length > 0 && cells.every((cell) => /^:?-{3,}:?$/.test(cell));
}

function isBlockStart(lines: string[], index: number) {
  const line = lines[index] || '';
  return /^```/.test(line.trim())
    || /^#{1,3}\s+/.test(line)
    || /^[-*+]\s+/.test(line)
    || /^\d+[.)]\s+/.test(line)
    || /^>\s?/.test(line)
    || (line.includes('|') && isTableDelimiter(lines[index + 1] || ''));
}

function jsonCodeBlock(markdown: string): AssistantMarkdownBlock[] | null {
  const trimmed = markdown.trim();
  if (!(trimmed.startsWith('{') || trimmed.startsWith('['))) return null;
  try {
    const value = JSON.parse(trimmed);
    return [{ type: 'code', key: `json-${stableHash(trimmed)}`, language: 'json', value: safeJson(value), closed: true }];
  } catch {
    return null;
  }
}

export function tokenizeAssistantMarkdown(markdown: string): AssistantMarkdownBlock[] {
  const normalized = String(markdown || '').replace(/\r\n?/g, '\n');
  const json = jsonCodeBlock(normalized);
  if (json) return json;
  const lines = normalized.split('\n');
  const blocks: AssistantMarkdownBlock[] = [];
  let index = 0;
  const blockKey = (type: string, seed: string) => `${type}-${blocks.length}-${stableHash(seed)}`;

  while (index < lines.length) {
    const line = lines[index];
    if (!line.trim()) {
      index += 1;
      continue;
    }

    const fence = line.trim().match(/^```([^`]*)$/);
    if (fence) {
      const language = fence[1].trim().toLowerCase();
      const content: string[] = [];
      index += 1;
      let closed = false;
      while (index < lines.length) {
        if (/^```\s*$/.test(lines[index].trim())) {
          closed = true;
          index += 1;
          break;
        }
        content.push(lines[index]);
        index += 1;
      }
      const value = content.join('\n');
      blocks.push({ type: 'code', key: blockKey('code', `${language}\n${value}`), language, value, closed });
      continue;
    }

    if (line.includes('|') && isTableDelimiter(lines[index + 1] || '')) {
      const headers = splitTableRow(line);
      index += 2;
      const rows: Array<{ key: string; cells: string[] }> = [];
      const occurrences = new Map<string, number>();
      while (index < lines.length && lines[index].trim() && lines[index].includes('|')) {
        const cells = splitTableRow(lines[index]);
        const signature = cells.join('\u241f');
        const occurrence = occurrences.get(signature) || 0;
        occurrences.set(signature, occurrence + 1);
        rows.push({ key: `row-${stableHash(signature)}-${occurrence}`, cells });
        index += 1;
      }
      blocks.push({ type: 'table', key: blockKey('table', headers.join('|')), headers, rows });
      continue;
    }

    const heading = line.match(/^(#{1,3})\s+(.+)$/);
    if (heading) {
      blocks.push({
        type: 'heading',
        key: blockKey('heading', line),
        level: heading[1].length as 1 | 2 | 3,
        text: heading[2].trim()
      });
      index += 1;
      continue;
    }

    if (/^[-*+]\s+/.test(line)) {
      const items: string[] = [];
      while (index < lines.length && /^[-*+]\s+/.test(lines[index])) {
        items.push(lines[index].replace(/^[-*+]\s+/, '').trim());
        index += 1;
      }
      blocks.push({ type: 'unordered-list', key: blockKey('ul', items.join('\n')), items });
      continue;
    }

    if (/^\d+[.)]\s+/.test(line)) {
      const items: string[] = [];
      while (index < lines.length && /^\d+[.)]\s+/.test(lines[index])) {
        items.push(lines[index].replace(/^\d+[.)]\s+/, '').trim());
        index += 1;
      }
      blocks.push({ type: 'ordered-list', key: blockKey('ol', items.join('\n')), items });
      continue;
    }

    if (/^>\s?/.test(line)) {
      const quote: string[] = [];
      while (index < lines.length && /^>\s?/.test(lines[index])) {
        quote.push(lines[index].replace(/^>\s?/, ''));
        index += 1;
      }
      const text = quote.join('\n');
      blocks.push({ type: 'blockquote', key: blockKey('quote', text), text });
      continue;
    }

    const paragraph = [line.trim()];
    index += 1;
    while (index < lines.length && lines[index].trim() && !isBlockStart(lines, index)) {
      paragraph.push(lines[index].trim());
      index += 1;
    }
    const text = paragraph.join('\n');
    blocks.push({ type: 'paragraph', key: blockKey('paragraph', text), text });
  }
  return blocks;
}

export function normalizeAssistantCitation(
  value: unknown,
  index: number,
  kind: 'rag' | 'attachment'
): NormalizedAssistantCitation {
  if (typeof value === 'string') {
    return { key: `${kind}-${stableHash(value)}-${index}`, title: value || '引用', sourceId: '', quote: '' };
  }
  const citation = value && typeof value === 'object' ? value as Record<string, unknown> : {};
  const title = String(citation.title || citation.file_name || citation.filename || citation.source || '引用');
  const sourceId = String(citation.citation_id || citation.attachment_id || citation.source_id || citation.id || '');
  const quote = String(citation.quote || citation.snippet || citation.content || citation.summary || '');
  const rawHref = String(citation.url || citation.href || '');
  const href = /^https?:\/\//i.test(rawHref) ? rawHref : undefined;
  return { key: `${kind}-${sourceId || stableHash(`${title}-${quote}`)}-${index}`, title, sourceId, quote, href };
}
