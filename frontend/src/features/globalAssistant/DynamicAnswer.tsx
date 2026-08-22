import { CopyOutlined, DislikeOutlined, LikeOutlined } from '@ant-design/icons';
import { Button, Collapse, Space, Table } from 'antd';
import type { ReactNode } from 'react';

function inlineText(text: string): ReactNode[] {
  return text.split(/(`[^`]+`|\*\*[^*]+\*\*)/g).filter(Boolean).map((part, index) => {
    if (part.startsWith('`') && part.endsWith('`')) return <code key={index}>{part.slice(1, -1)}</code>;
    if (part.startsWith('**') && part.endsWith('**')) return <strong key={index}>{part.slice(2, -2)}</strong>;
    return <span key={index}>{part}</span>;
  });
}

function parseTable(lines: string[]) {
  const rows = lines.map((line) => line.trim().replace(/^\||\|$/g, '').split('|').map((cell) => cell.trim()));
  if (rows.length < 2 || !rows[1].every((cell) => /^:?-{3,}:?$/.test(cell))) return null;
  const headers = rows[0];
  const data = rows.slice(2).map((row, index) => Object.fromEntries(headers.map((header, column) => [String(column), row[column] || ''])));
  return <Table key={`table-${lines[0]}`} size="small" pagination={false} rowKey={(_, index) => String(index)} dataSource={data} columns={headers.map((header, index) => ({ title: header, dataIndex: String(index), key: String(index) }))} scroll={{ x: true }} />;
}

export function MarkdownContent({ markdown }: { markdown: string }) {
  const lines = String(markdown || '').replace(/\r\n/g, '\n').split('\n');
  const nodes: ReactNode[] = [];
  for (let index = 0; index < lines.length; index += 1) {
    const line = lines[index];
    if (!line.trim()) continue;
    if (line.includes('|') && lines[index + 1]?.includes('|')) {
      const tableLines = [line];
      while (index + 1 < lines.length && lines[index + 1].includes('|')) tableLines.push(lines[++index]);
      const table = parseTable(tableLines);
      if (table) { nodes.push(table); continue; }
      index -= tableLines.length - 1;
    }
    if (/^#{1,4}\s/.test(line)) {
      const level = Math.min(4, line.match(/^#+/)?.[0].length || 2);
      const content = line.replace(/^#{1,4}\s+/, '');
      nodes.push(level <= 2 ? <h3 key={index}>{inlineText(content)}</h3> : <h4 key={index}>{inlineText(content)}</h4>);
    } else if (/^[-*]\s+/.test(line)) {
      const items = [line.replace(/^[-*]\s+/, '')];
      while (/^[-*]\s+/.test(lines[index + 1] || '')) items.push(lines[++index].replace(/^[-*]\s+/, ''));
      nodes.push(<ul key={index}>{items.map((item, itemIndex) => <li key={itemIndex}>{inlineText(item)}</li>)}</ul>);
    } else if (/^\d+[.)]\s+/.test(line)) {
      const items = [line.replace(/^\d+[.)]\s+/, '')];
      while (/^\d+[.)]\s+/.test(lines[index + 1] || '')) items.push(lines[++index].replace(/^\d+[.)]\s+/, ''));
      nodes.push(<ol key={index}>{items.map((item, itemIndex) => <li key={itemIndex}>{inlineText(item)}</li>)}</ol>);
    } else if (/^>\s?/.test(line)) {
      nodes.push(<blockquote key={index}>{inlineText(line.replace(/^>\s?/, ''))}</blockquote>);
    } else {
      nodes.push(<p key={index}>{inlineText(line)}</p>);
    }
  }
  return <div className="assistant-markdown">{nodes}</div>;
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
  citations?: any[];
  attachmentCitations?: any[];
  onCopy: () => void;
  onFeedback: (rating: 'up' | 'down') => void;
  onContinue?: () => void;
}) {
  const citationItems = [...citations, ...attachmentCitations];
  return (
    <article className="dynamic-answer">
      <MarkdownContent markdown={markdown} />
      {citationItems.length > 0 && (
        <Collapse ghost size="small" items={[{
          key: 'citations',
          label: `查看引用（${citationItems.length}）`,
          children: <ol className="assistant-citations">{citationItems.map((citation, index) => <li key={citation.citation_id || index}>{citation.title || citation.file_name || citation.source || '引用'}{citation.quote ? `：${citation.quote}` : ''}</li>)}</ol>
        }]} />
      )}
      <Space size={4} className="dynamic-answer-actions">
        <Button type="text" size="small" icon={<CopyOutlined />} onClick={onCopy}>复制</Button>
        {onContinue ? <Button type="text" size="small" onClick={onContinue}>继续追问</Button> : null}
        <Button type="text" size="small" aria-label="回答有帮助" icon={<LikeOutlined />} onClick={() => onFeedback('up')} />
        <Button type="text" size="small" aria-label="回答需改进" icon={<DislikeOutlined />} onClick={() => onFeedback('down')} />
      </Space>
    </article>
  );
}
