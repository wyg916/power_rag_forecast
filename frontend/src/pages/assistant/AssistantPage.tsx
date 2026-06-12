import { CopyOutlined, PlusOutlined, RobotOutlined, SearchOutlined, SendOutlined } from '@ant-design/icons';
import { Button, Input, List, Select, Space, Switch, Table, Tag, message } from 'antd';
import { useEffect, useMemo, useState } from 'react';
import { api } from '../../api';
import { SectionCard } from '../../components/cards/SectionCard';
import { PageTabs } from '../../components/common/PageTabs';
import { DataStateBanner } from '../../components/common/States';
import { TracePanel } from '../../components/common/TracePanel';
import { useAuth } from '../../context/AuthContext';
import { ResponsiveGrid } from '../../components/layout/UnifiedPage';
import { assistantMock } from '../../mock/assistantMock';
import { askAssistant, getAssistantData } from '../../services/assistantApi';
import type { PageProps } from '../../types/ui';

const tabs = [
  { key: 'assistant-chat', label: '智能问答' },
  { key: 'assistant-tools', label: '工具调用' },
  { key: 'assistant-trace', label: 'Trace' },
  { key: 'assistant-faq', label: '常见问题' }
];

const answerStyleOptions = [
  { value: 'professional_brief', label: '专业简洁' },
  { value: 'professional_deep', label: '专业详细' },
  { value: 'business_advice', label: '业务建议' },
  { value: 'plain_language', label: '通俗解释' },
  { value: 'report_style', label: '日报风格' }
];

const modelProviderOptions = [
  { value: 'auto', label: '自动' },
  { value: 'deepseek', label: 'DeepSeek' },
  { value: 'ollama', label: '本地 Qwen3' }
];

const providerDisplayLabels: Record<string, string> = {
  deterministic: '快速回答',
  deepseek: '在线模型',
  ollama: '本地模型',
  fallback: '兜底回答',
  template: '兜底回答',
  auto: '自动'
};

function providerDisplayName(value?: string) {
  if (!value) return undefined;
  const key = String(value).toLowerCase();
  return providerDisplayLabels[key] || value;
}

function sanitizeEvidenceLabel(value: string) {
  const raw = String(value || '').trim();
  if (!raw) return '';
  const withoutScore = raw.replace(/\s*\(?score\s*=\s*[-.\d]+\)?/gi, '').trim();
  const normalized = withoutScore.replace(/\\/g, '/');
  const parts = normalized.split('/').filter(Boolean);
  const last = parts[parts.length - 1] || normalized;
  return last.replace(/\.(md|txt|json|jsonl)$/i, '').trim() || '知识依据';
}

function compactEvidenceItems(items?: string[]) {
  return Array.from(new Set((items || []).map(sanitizeEvidenceLabel).filter(Boolean))).slice(0, 5);
}

function renderAnswerText(text?: string) {
  const lines = String(text || '').split(/\n+/).map((line) => line.trim()).filter(Boolean);
  return lines.map((line, index) => {
    const bullet = line.match(/^[-•]\s*(.+)$/);
    if (bullet) {
      return <div className="answer-line answer-bullet" key={`${index}-${line}`}>• {bullet[1]}</div>;
    }
    const numbered = line.match(/^(\d+[.、])\s*(.+)$/);
    if (numbered) {
      return <div className="answer-line answer-bullet" key={`${index}-${line}`}>{numbered[1]} {numbered[2]}</div>;
    }
    const section = line.match(/^([\u4e00-\u9fa5A-Za-z0-9/（）()]{2,18})[：:]\s*(.*)$/);
    if (section) {
      return (
        <div className="answer-line answer-section-line" key={`${index}-${line}`}>
          <strong>{section[1]}：</strong>{section[2]}
        </div>
      );
    }
    return <div className="answer-line" key={`${index}-${line}`}>{line}</div>;
  });
}

function sectionText(answer: string, title: string, fallback = '-') {
  const escaped = title.replace(/[.*+?^${}()|[\]\\]/g, '\\$&');
  const match = answer.match(new RegExp(`${escaped}[：:]?\\s*([\\s\\S]*?)(?=\\n\\s*(结论|数据依据|原因解释|业务建议|风险提示)[：:]?|$)`));
  return (match?.[1] || fallback).trim();
}

export function AssistantPage({ activeSubKey, onSubNavigate }: PageProps) {
  const { hasPermission, user } = useAuth();
  const [assistantData, setAssistantData] = useState(assistantMock);
  const [input, setInput] = useState('');
  const [sessionId, setSessionId] = useState<string>();
  const [loading, setLoading] = useState(false);
  const [currentQuestion, setCurrentQuestion] = useState(assistantMock.answer.question);
  const [currentAnswer, setCurrentAnswer] = useState<string>();
  const [trace, setTrace] = useState(assistantMock.trace);
  const [questionOffset, setQuestionOffset] = useState(0);
  const [traceRows, setTraceRows] = useState<any[]>([]);
  const [selectedTrace, setSelectedTrace] = useState<any | null>(null);
  const [answerState, setAnswerState] = useState<any>({});
  const [developerMode, setDeveloperMode] = useState(false);
  const [answerStyle, setAnswerStyle] = useState('professional_brief');
  const [modelProvider, setModelProvider] = useState('auto');
  const canUseDeveloperMode = Boolean(user?.role === 'admin' || hasPermission('assistant:debug') || hasPermission('trace:read'));
  const visibleTabs = useMemo(
    () => tabs.filter((item) => (developerMode && canUseDeveloperMode) || !['assistant-tools', 'assistant-trace'].includes(item.key)),
    [developerMode, canUseDeveloperMode]
  );
  const effectiveSubKey = (developerMode && canUseDeveloperMode) || !['assistant-tools', 'assistant-trace'].includes(activeSubKey)
    ? activeSubKey
    : 'assistant-chat';

  useEffect(() => {
    if (!canUseDeveloperMode && developerMode) setDeveloperMode(false);
  }, [canUseDeveloperMode, developerMode]);

  useEffect(() => {
    let mounted = true;
    getAssistantData().then((data) => {
      if (mounted) setAssistantData(data);
    });
    if (developerMode && canUseDeveloperMode) {
      api.aiTraces(30).then((payload) => {
        if (mounted) {
          const rows = payload.traces || [];
          setTraceRows(rows);
          setSelectedTrace(rows[0] || null);
        }
      }).catch(() => undefined);
    }
    return () => {
      mounted = false;
    };
  }, [developerMode, canUseDeveloperMode]);

  const answer = useMemo(() => {
    if (!currentAnswer) return assistantData.answer;
    return {
      question: currentQuestion,
      conclusion: sectionText(currentAnswer, '结论', currentAnswer),
      evidence: sectionText(currentAnswer, '数据依据').split(/\n+/).filter(Boolean),
      reason: sectionText(currentAnswer, '原因解释'),
      suggestion: sectionText(currentAnswer, '业务建议').split(/\n+/).filter(Boolean),
      warning: sectionText(currentAnswer, '风险提示')
    };
  }, [assistantData.answer, currentAnswer, currentQuestion]);

  const toolRows = (trace.tools || []).map((tool, index) => ({
    key: `${tool}-${index}`,
    tool,
    source: trace.sources?.[index] || 'tool_evidence',
    ref: trace.refs?.[index] || trace.traceId,
    status: 'success'
  }));

  const visibleQuestions = useMemo(() => {
    const questions = assistantData.questions || [];
    if (questions.length <= 4) return questions;
    return [...questions, ...questions].slice(questionOffset, questionOffset + 4);
  }, [assistantData.questions, questionOffset]);

  const selectedTraceView = useMemo(() => {
    if (!selectedTrace) return trace;
    const rawConfidence = Number(selectedTrace.confidence || trace.confidence || 80);
    const confidence = rawConfidence <= 1 ? Math.round(rawConfidence * 100) : Math.round(rawConfidence);
    return {
      intent: selectedTrace.intent || trace.intent,
      tools: (selectedTrace.tools || selectedTrace.tool_calls || trace.tools || []).map((item: any) => item.name || item.tool_name || item),
      sources: (selectedTrace.evidence || trace.sources || []).map((item: any) => item.source || item.tool || item),
      refs: (selectedTrace.evidence || trace.refs || []).map((item: any) => item.report_id || item.trace_id || item.source || item).filter(Boolean),
      traceId: selectedTrace.trace_id || selectedTrace.traceId || trace.traceId,
      confidence
    };
  }, [selectedTrace, trace]);

  async function submitQuestion(question: string) {
    const text = question.trim();
    if (!text) return;
    setLoading(true);
    setCurrentQuestion(text);
    try {
      const response = await askAssistant(text, sessionId, {
        answer_style: answerStyle,
        model_provider: modelProvider,
        debug: developerMode && canUseDeveloperMode
      });
      const rawSource = response.dataSource || response.model_provider_used || response.intent;
      setAnswerState({
        source: providerDisplayName(rawSource),
        rawSource,
        error: response.error,
        mockFallback: response.mockFallback,
        fallbackReason: response.fallbackReason,
        evidenceSummary: developerMode && canUseDeveloperMode ? compactEvidenceItems(response.evidence_summary || []) : [],
        knowledgeEvidenceSummary: developerMode && canUseDeveloperMode ? compactEvidenceItems(response.knowledge_evidence_summary || []) : [],
        rag: response.rag,
        warnings: response.warnings || []
      });
      setSessionId(response.session_id);
      setCurrentAnswer(response.answer || '');
      setTrace({
        intent: response.intent || '智能问答',
        tools: (response.tools || response.tool_calls || []).map((item: any) => item.name || item.tool_name || 'tool'),
        sources: (response.evidence || []).map((item: any) => item.source || item.tool || '系统数据'),
        refs: (response.evidence || []).map((item: any) => item.report_id || item.fields?.join(', ') || item.time || item.source).filter(Boolean),
        traceId: response.trace_id || response.trace?.trace_id || 'trace_frontend',
        confidence: Math.round(Number(response.confidence || 0.8) * 100)
      });
      setInput('');
      if (developerMode && canUseDeveloperMode) api.aiTraces(30).then((payload) => setTraceRows(payload.traces || [])).catch(() => undefined);
    } catch (error) {
      message.error(error instanceof Error ? error.message : 'AI 助手请求失败');
    } finally {
      setLoading(false);
    }
  }

  function newConversation() {
    setSessionId(undefined);
    setCurrentAnswer(undefined);
    setAnswerState({});
    setCurrentQuestion('新会话已创建，请输入问题。');
    setInput('');
    message.success('已创建新会话');
  }

  function rotateQuestions() {
    const total = assistantData.questions.length || 1;
    setQuestionOffset((value) => (value + 4) % total);
  }

  function exportConversation() {
    const payload = {
      session_id: sessionId || 'local_session',
      question: currentQuestion,
      answer: currentAnswer || answer.conclusion,
      trace_id: trace.traceId
    };
    const blob = new Blob([JSON.stringify(payload, null, 2)], { type: 'application/json;charset=utf-8' });
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = `assistant_conversation_${Date.now()}.json`;
    a.click();
    URL.revokeObjectURL(url);
  }

  async function copyText(text?: string) {
    const value = String(text || '').trim();
    if (!value) {
      message.warning('暂无可复制内容');
      return;
    }
    try {
      await navigator.clipboard.writeText(value);
      message.success('已复制');
    } catch {
      const textarea = document.createElement('textarea');
      textarea.value = value;
      textarea.style.position = 'fixed';
      textarea.style.left = '-9999px';
      document.body.appendChild(textarea);
      textarea.focus();
      textarea.select();
      document.execCommand('copy');
      document.body.removeChild(textarea);
      message.success('已复制');
    }
  }

  return (
    <div className="page-stack">
      <PageTabs items={visibleTabs} activeKey={effectiveSubKey} onChange={onSubNavigate} />
      <DataStateBanner
        scope="AI 助手"
        loading={loading}
        source={answerState.source || providerDisplayName((assistantData as any).dataSource)}
        error={answerState.error || (assistantData as any).error}
        empty={(assistantData as any).empty}
        mockFallback={answerState.mockFallback || (assistantData as any).mockFallback}
        fallbackReason={answerState.fallbackReason || (assistantData as any).fallbackReason}
        partialErrors={(assistantData as any).partialErrors}
      />
      {developerMode && canUseDeveloperMode && effectiveSubKey === 'assistant-tools' && (
        <ResponsiveGrid minColumnWidth={360}>
          <SectionCard title="工具调用记录">
            <Table
              size="small"
              pagination={false}
              scroll={{ x: 720 }}
              dataSource={toolRows}
              columns={[
                { title: '工具', dataIndex: 'tool' },
                { title: '数据来源', dataIndex: 'source' },
                { title: '证据引用', dataIndex: 'ref', ellipsis: true },
                { title: '状态', dataIndex: 'status', render: (value) => <Tag color="success">{value}</Tag> }
              ]}
            />
          </SectionCard>
          <SectionCard title="工具调用说明">
            <div className="advice-panel">
              <h4>结论</h4>
              <p>AI 助手回答优先使用工具证据，当前问题已关联 {toolRows.length || 0} 个工具或证据来源。</p>
              <h4>风险提示</h4>
              <p>当本地模型不可用时，系统继续使用事实数据和工具结果生成结构化回答，不直接编造数值。</p>
            </div>
          </SectionCard>
        </ResponsiveGrid>
      )}

      {developerMode && canUseDeveloperMode && effectiveSubKey === 'assistant-trace' && (
        <div className="forecast-main-grid">
          <SectionCard title="Trace 列表" extra={<Button onClick={() => api.aiTraces(30).then((payload) => setTraceRows(payload.traces || []))}>刷新</Button>} scrollable height={520}>
            <div className="trace-list">
              {(traceRows.length ? traceRows : [{ trace_id: trace.traceId, intent: trace.intent, question: currentQuestion, created_at: '当前会话' }]).map((item) => (
                <div className="trace-list-item" key={item.trace_id || item.traceId} onClick={() => setSelectedTrace(item)}>
                  <strong>{item.trace_id || item.traceId}</strong>
                  <span>{item.intent || 'unknown_intent'}</span>
                  <span>{item.question || item.created_at || '--'}</span>
                </div>
              ))}
            </div>
          </SectionCard>
          <SectionCard title="Trace 详情" scrollable height={520}>
            <TracePanel {...selectedTraceView} />
          </SectionCard>
          <SectionCard title="当前回答结构" className="assistant-bottom-card">
            <div className="answer-card">
              <h4>结论</h4>
              <p>{answer.conclusion}</p>
              <h4>数据依据</h4>
              <ul>{answer.evidence.map((item) => <li key={item}>{item}</li>)}</ul>
              <h4 className="danger-title">风险提示</h4>
              <p>{answer.warning}</p>
            </div>
          </SectionCard>
        </div>
      )}

      {effectiveSubKey === 'assistant-faq' && (
        <ResponsiveGrid minColumnWidth={320}>
          <SectionCard title="常用问题">
            <div className="question-list faq-grid">
              {assistantData.questions.map((item, index) => (
                <div key={item}>
                  <span>{index + 1}</span>
                  <p>{item}</p>
                  <Button type="link" size="small" onClick={() => submitQuestion(item)}>提问</Button>
                </div>
              ))}
            </div>
          </SectionCard>
          <SectionCard title="会话历史">
            <List
              className="session-list"
              dataSource={assistantData.conversations}
              renderItem={(item, index) => (
                <List.Item className={index === 0 ? 'active-session' : ''}>
                  <div>
                    <strong>{item[0]}</strong>
                    <span>{item[1]}</span>
                  </div>
                </List.Item>
              )}
            />
          </SectionCard>
        </ResponsiveGrid>
      )}

      {effectiveSubKey === 'assistant-chat' && <>
      <div className={`assistant-chat-grid ${developerMode && canUseDeveloperMode ? 'has-debug-panel' : 'compact'}`}>
        <div className="assistant-left">
          <SectionCard title="会话历史" extra={<Button type="primary" size="small" icon={<PlusOutlined />} onClick={newConversation}>新建对话</Button>}>
            <Input prefix={<SearchOutlined />} placeholder="搜索会话" />
            <List
              className="session-list"
              dataSource={assistantData.conversations}
              renderItem={(item, index) => (
                <List.Item className={index === 0 ? 'active-session' : ''}>
                  <div>
                    <strong>{item[0]}</strong>
                    <span>{item[1]}</span>
                  </div>
                </List.Item>
              )}
            />
            <a className="section-footer-link" onClick={() => onSubNavigate('assistant-faq')}>查看全部历史记录 →</a>
          </SectionCard>
          <SectionCard title="常用问题" extra={<a onClick={rotateQuestions}>换一换</a>}>
            <div className="question-list">
              {visibleQuestions.map((item, index) => (
                <div key={item}>
                  <span>{index + 1}</span>
                  <p>{item}</p>
                  <Button type="link" size="small" onClick={() => submitQuestion(item)}>去提问</Button>
                </div>
              ))}
            </div>
          </SectionCard>
        </div>

        <div className="assistant-center">
          <SectionCard
            title="对话窗口"
            extra={
              <Space wrap>
                <Select size="small" value={answerStyle} options={answerStyleOptions} style={{ width: 112 }} onChange={setAnswerStyle} />
                <Select size="small" value={modelProvider} options={modelProviderOptions} style={{ width: 112 }} onChange={setModelProvider} />
                {canUseDeveloperMode && (
                  <Switch size="small" checked={developerMode} onChange={setDeveloperMode} checkedChildren="开发" unCheckedChildren="普通" />
                )}
                <Button onClick={() => setCurrentAnswer(undefined)}>清空对话</Button>
                <Button onClick={exportConversation}>导出</Button>
              </Space>
            }
          >
            <div className="chat-window">
              <div className="user-message">
                <div className="message-copy-row">
                  <span>{answer.question}</span>
                  <Button
                    type="text"
                    size="small"
                    icon={<CopyOutlined />}
                    aria-label="复制问题"
                    title="复制问题"
                    onClick={() => copyText(answer.question)}
                  />
                </div>
                <small>10:28</small>
              </div>
              <div className="ai-message">
                <RobotOutlined />
                <div className="answer-card">
                  <div className="answer-card-actions">
                    <Button
                      type="text"
                      size="small"
                      icon={<CopyOutlined />}
                      aria-label="复制回答"
                      title="复制回答"
                      onClick={() => copyText(currentAnswer || answer.conclusion)}
                    >
                      复制
                    </Button>
                  </div>
                  {currentAnswer ? (
                    <>
                      <div className="answer-text">{renderAnswerText(currentAnswer)}</div>
                      {!!answerState.evidenceSummary?.length && (
                        <>
                          <h4>数据依据</h4>
                          <ul>{answerState.evidenceSummary.map((item: string) => <li key={item}>{item}</li>)}</ul>
                        </>
                      )}
                      {!!answerState.knowledgeEvidenceSummary?.length && (
                        <>
                          <h4>知识依据</h4>
                          <ul>{answerState.knowledgeEvidenceSummary.map((item: string) => <li key={item}>{item}</li>)}</ul>
                        </>
                      )}
                      {!!answerState.warnings?.length && (
                        <>
                          <h4 className="danger-title">待验证问题</h4>
                          <ul>{answerState.warnings.map((item: string) => <li key={item}>{item}</li>)}</ul>
                        </>
                      )}
                    </>
                  ) : (
                    <>
                      <h4>结论</h4>
                      <p>{answer.conclusion}</p>
                      <h4>数据依据</h4>
                      <ul>{answer.evidence.map((item) => <li key={item}>{item}</li>)}</ul>
                      <h4>原因解释</h4>
                      <p>{answer.reason}</p>
                      <h4>业务建议</h4>
                      <ol>{answer.suggestion.map((item) => <li key={item}>{item}</li>)}</ol>
                      <h4 className="danger-title">风险提示</h4>
                      <p>{answer.warning}</p>
                    </>
                  )}
                </div>
              </div>
            </div>
            <div className="chat-input">
              <Input
                value={input}
                placeholder="请输入您的问题，例如：查询浙江杭州2022年并网光伏补贴电价"
                onChange={(event) => setInput(event.target.value)}
                onPressEnter={() => submitQuestion(input)}
              />
              <Button type="primary" icon={<SendOutlined />} loading={loading} onClick={() => submitQuestion(input)} />
            </div>
            <Space wrap className="quick-questions">
              {['建议购电策略', '明日分时电价预测', '高峰风险评估', '查询浙江光伏电价政策', '生成日报'].map((item) => <Button key={item} onClick={() => submitQuestion(item)}>{item}</Button>)}
            </Space>
          </SectionCard>
        </div>

        {developerMode && canUseDeveloperMode && (
          <div className="assistant-right">
            <SectionCard title="开发者调试">
              <TracePanel {...trace} />
            </SectionCard>
            {!!answerState.rag?.items?.length && (
              <SectionCard title="RAG 命中证据">
                <Table
                  size="small"
                  pagination={false}
                  scroll={{ x: 760, y: 280 }}
                  dataSource={(answerState.rag.items || []).map((item: any, index: number) => ({ key: item.chunk_id || index, ...item }))}
                  columns={[
                    { title: '文档', dataIndex: 'title', ellipsis: true },
                    { title: 'chunk', dataIndex: 'chunk_id', ellipsis: true },
                    { title: 'K', dataIndex: 'keyword_score', render: (value) => Number(value || 0).toFixed(3) },
                    { title: 'V', dataIndex: 'vector_score', render: (value) => Number(value || 0).toFixed(3) },
                    { title: 'R', dataIndex: 'rerank_score', render: (value) => Number(value || 0).toFixed(3) },
                    { title: 'Final', dataIndex: 'final_score', render: (value) => Number(value || 0).toFixed(3) },
                    { title: '片段', dataIndex: 'content', ellipsis: true }
                  ]}
                />
              </SectionCard>
            )}
          </div>
        )}
      </div>
      <div className="assistant-support-grid">
        <SectionCard title="最近知识库文档" className="assistant-bottom-card">
          <Table
            size="small"
            pagination={false}
            dataSource={assistantData.docs.map((row, index) => ({ key: index, row }))}
            columns={[
              { title: '文档名称', render: (_, record) => record.row[0] },
              { title: '类型', render: (_, record) => <Tag>{record.row[1]}</Tag> },
              { title: '大小', render: (_, record) => record.row[2] }
            ]}
          />
        </SectionCard>
        <SectionCard title="最近模型运行" className="assistant-bottom-card">
          <Table
            size="small"
            pagination={false}
            dataSource={assistantData.modelRuns.map((row, index) => ({ key: index, row }))}
            columns={[
              { title: '模型名称', render: (_, record) => record.row[0] },
              { title: '任务类型', render: (_, record) => record.row[1] },
              { title: '状态', render: (_, record) => <Tag color="success">{record.row[2]}</Tag> },
              { title: '耗时', render: (_, record) => record.row[3] }
            ]}
          />
        </SectionCard>
      </div>
      </>}
    </div>
  );
}
