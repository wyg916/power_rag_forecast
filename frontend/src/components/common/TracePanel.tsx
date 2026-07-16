import { CheckCircleOutlined, CopyOutlined } from '@ant-design/icons';
import { Button, Empty, Progress, Space, Tag, message } from 'antd';

interface TracePanelProps {
  intent: string;
  tools: string[];
  sources: string[];
  refs: string[];
  traceId: string;
  confidence: number;
}

export function TracePanel({ intent, tools, sources, refs, traceId, confidence }: TracePanelProps) {
  async function copyTraceId() {
    if (!traceId) {
      message.warning('暂无 Trace ID');
      return;
    }
    await navigator.clipboard.writeText(traceId);
    message.success('Trace ID 已复制');
  }

  return (
    <div className="trace-panel">
      <div className="trace-block">
        <h4>识别意图</h4>
        <p>{intent || '待提问'}</p>
      </div>
      <div className="trace-block">
        <h4>调用工具</h4>
        {tools.length ? (
          <Space wrap>
            {tools.map((tool) => (
              <Tag key={tool}>{tool}</Tag>
            ))}
          </Space>
        ) : (
          <Empty image={Empty.PRESENTED_IMAGE_SIMPLE} description="暂无工具调用" />
        )}
      </div>
      <div className="trace-block">
        <h4>数据来源</h4>
        {sources.length ? (
          sources.map((item) => (
            <p key={item}>
              <CheckCircleOutlined /> {item}
            </p>
          ))
        ) : (
          <Empty image={Empty.PRESENTED_IMAGE_SIMPLE} description="暂无数据来源" />
        )}
      </div>
      <div className="trace-block">
        <h4>知识库引用</h4>
        {refs.length ? refs.map((item) => <p key={item}>{item}</p>) : <Empty image={Empty.PRESENTED_IMAGE_SIMPLE} description="暂无知识引用" />}
      </div>
      <div className="trace-row">
        <div>
          <h4>Trace ID</h4>
          <p>
            {traceId || '--'}
            <Button type="text" size="small" icon={<CopyOutlined />} onClick={copyTraceId} />
          </p>
        </div>
        <div className="confidence-card">
          <h4>可信度</h4>
          <Progress type="dashboard" percent={confidence || 0} strokeColor="#00B894" size={110} />
        </div>
      </div>
    </div>
  );
}
