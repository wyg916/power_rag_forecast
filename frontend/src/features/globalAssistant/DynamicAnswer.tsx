import { CopyOutlined, DislikeOutlined, LikeOutlined } from '@ant-design/icons';
import { Button, Collapse, Space } from 'antd';
import type { ReactNode } from 'react';
import { normalizeAssistantCitation, tokenizeAssistantMarkdown } from './assistantContent';
import type { AssistantMarkdownBlock, NormalizedAssistantCitation } from './assistantContent';

const inlinePattern = /(`[^`\n]+`|\*\*[^*\n]+\*\*|\[[^\]]+\]\(https?:\/\/[^\s)]+\)|https?:\/\/[^\s<]+)/g;

function inlineText(text: string): ReactNode[] {
  const nodes: ReactNode[] = [];
  let offset = 0;
  for (const match of text.matchAll(inlinePattern)) {
    const start = match.index ?? 0;
    if (start > offset) nodes.push(<span key={`text-${offset}`}>{text.slice(offset, start)}</span>);
    const token = match[0];
    if (token.startsWith('`') && token.endsWith('`')) {
      nodes.push(<code key={`code-${start}`}>{token.slice(1, -1)}</code>);
    } else if (token.startsWith('**') && token.endsWith('**')) {
      nodes.push(<strong key={`strong-${start}`}>{token.slice(2, -2)}</strong>);
    } else {
      const markdownLink = token.match(/^\[([^\]]+)]\((https?:\/\/[^\s)]+)\)$/);
      const href = markdownLink?.[2] || token;
      const label = markdownLink?.[1] || token;
      nodes.push(<a key={`link-${start}`} href={href} target="_blank" rel="noreferrer">{label}</a>);
    }
    offset = start + token.length;
  }
  if (offset < text.length) nodes.push(<span key={`text-${offset}`}>{text.slice(offset)}</span>);
  return nodes;
}

function MarkdownTable({ block }: { block: Extract<AssistantMarkdownBlock, { type: 'table' }> }) {
  return (
    <div className="assistant-markdown-table-scroll" role="region" aria-label="回答数据表" tabIndex={0}>
      <table>
        <thead><tr>{block.headers.map((header, index) => <th key={`header-${index}-${header}`}>{inlineText(header)}</th>)}</tr></thead>
        <tbody>
          {block.rows.map((row) => (
            <tr key={row.key}>
              {block.headers.map((_, index) => <td key={`${row.key}-cell-${index}`}>{inlineText(row.cells[index] || '')}</td>)}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

function parseTable(block: Extract<AssistantMarkdownBlock, { type: 'table' }>) {
  return <MarkdownTable block={block} />;
}

function MarkdownBlock({ block }: { block: AssistantMarkdownBlock }) {
  if (block.type === 'heading') {
    if (block.level === 1) return <h1>{inlineText(block.text)}</h1>;
    if (block.level === 2) return <h2>{inlineText(block.text)}</h2>;
    return <h3>{inlineText(block.text)}</h3>;
  }
  if (block.type === 'paragraph') return <p>{inlineText(block.text)}</p>;
  if (block.type === 'blockquote') return <blockquote>{inlineText(block.text)}</blockquote>;
  if (block.type === 'unordered-list') return <ul>{block.items.map((item, index) => <li key={`${block.key}-${index}`}>{inlineText(item)}</li>)}</ul>;
  if (block.type === 'ordered-list') return <ol>{block.items.map((item, index) => <li key={`${block.key}-${index}`}>{inlineText(item)}</li>)}</ol>;
  if (block.type === 'table') return parseTable(block);
  return (
    <div className={`assistant-code-block ${block.closed ? '' : 'is-streaming'}`}>
      {block.language ? <div className="assistant-code-language">{block.language}</div> : null}
      <pre><code>{block.value}</code></pre>
    </div>
  );
}

export function MarkdownContent({ markdown }: { markdown: string }) {
  const blocks = tokenizeAssistantMarkdown(markdown);
  return <div className="assistant-markdown">{blocks.map((block) => <section className={`assistant-markdown-block block-${block.type}`} key={block.key}><MarkdownBlock block={block} /></section>)}</div>;
}

function CitationList({ items }: { items: NormalizedAssistantCitation[] }) {
  return (
    <ol className="assistant-citations">
      {items.map((citation) => (
        <li key={citation.key}>
          <div className="assistant-citation-title">{citation.href ? <a href={citation.href} target="_blank" rel="noreferrer">{citation.title}</a> : citation.title}</div>
          {citation.sourceId ? <code className="assistant-citation-id">{citation.sourceId}</code> : null}
          {citation.quote ? <p>{citation.quote}</p> : null}
        </li>
      ))}
    </ol>
  );
}

export function DynamicAnswer({
  markdown,
  citations = [],
  attachmentCitations = [],
  onCopy,
  onFeedback,
  onContinue
}: {
  markdown: string;
  citations?: unknown[];
  attachmentCitations?: unknown[];
  onCopy: () => void;
  onFeedback: (rating: 'up' | 'down') => void;
  onContinue?: () => void;
}) {
  const ragItems = citations.map((citation, index) => normalizeAssistantCitation(citation, index, 'rag'));
  const attachmentItems = attachmentCitations.map((citation, index) => normalizeAssistantCitation(citation, index, 'attachment'));
  const collapseItems = [
    ...(ragItems.length ? [{ key: 'rag-citations', label: `知识引用（${ragItems.length}）`, children: <CitationList items={ragItems} /> }] : []),
    ...(attachmentItems.length ? [{ key: 'attachment-citations', label: `附件来源（${attachmentItems.length}）`, children: <CitationList items={attachmentItems} /> }] : [])
  ];
  return (
    <article className="dynamic-answer">
      <MarkdownContent markdown={markdown} />
      {collapseItems.length > 0 ? <Collapse ghost size="small" items={collapseItems} /> : null}
      <Space size={4} className="dynamic-answer-actions">
        <Button type="text" size="small" icon={<CopyOutlined />} onClick={onCopy}>复制</Button>
        {onContinue ? <Button type="text" size="small" onClick={onContinue}>继续追问</Button> : null}
        <Button type="text" size="small" aria-label="回答有帮助" icon={<LikeOutlined />} onClick={() => onFeedback('up')} />
        <Button type="text" size="small" aria-label="回答需改进" icon={<DislikeOutlined />} onClick={() => onFeedback('down')} />
      </Space>
    </article>
  );
}
