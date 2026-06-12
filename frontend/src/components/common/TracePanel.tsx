import { CheckCircleOutlined, CopyOutlined } from '@ant-design/icons';
import { Progress, Space, Tag } from 'antd';

interface TracePanelProps {
  intent: string;
  tools: string[];
  sources: string[];
  refs: string[];
  traceId: string;
  confidence: number;
}

export function TracePanel({ intent, tools, sources, refs, traceId, confidence }: TracePanelProps) {
  return (
    <div className="trace-panel">
      <div className="trace-block">
        <h4>识别意图</h4>
        <p>{intent}</p>
      </div>
      <div className="trace-block">
        <h4>调用工具</h4>
        <Space wrap>
          {tools.map((tool) => (
            <Tag key={tool}>{tool}</Tag>
          ))}
        </Space>
      </div>
      <div className="trace-block">
        <h4>数据来源</h4>
        {sources.map((item) => (
          <p key={item}>
            <CheckCircleOutlined /> {item}
          </p>
        ))}
      </div>
      <div className="trace-block">
        <h4>知识库引用</h4>
        {refs.map((item) => (
          <p key={item}>{item}</p>
        ))}
      </div>
      <div className="trace-row">
        <div>
          <h4>Trace ID</h4>
          <p>
            {traceId} <CopyOutlined />
          </p>
        </div>
        <div className="confidence-card">
          <h4>可信度</h4>
          <Progress type="dashboard" percent={confidence} strokeColor="#00B894" size={110} />
        </div>
      </div>
    </div>
  );
}
