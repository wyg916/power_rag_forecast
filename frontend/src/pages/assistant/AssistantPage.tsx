import {
  BarChartOutlined,
  BulbOutlined,
  CheckCircleOutlined,
  ClockCircleOutlined,
  CopyOutlined,
  DatabaseOutlined,
  DownloadOutlined,
  ExclamationCircleOutlined,
  FileSearchOutlined,
  FileTextOutlined,
  InfoCircleOutlined,
  PaperClipOutlined,
  PictureOutlined,
  PlusOutlined,
  RobotOutlined,
  SearchOutlined,
  SendOutlined,
  SettingOutlined,
  ThunderboltOutlined
} from '@ant-design/icons';
import { Alert, App, Button, Drawer, Empty, Input, List, Modal, Select, Space, Switch, Table, Tag } from 'antd';
import { useEffect, useMemo, useRef, useState } from 'react';
import { api } from '../../api';
import { SectionCard } from '../../components/cards/SectionCard';
import { AppChart } from '../../components/charts/AppChart';
import { TracePanel } from '../../components/common/TracePanel';
import { useAuth } from '../../context/AuthContext';
import {
  askAssistant,
  askAssistantStream,
  askChatBI,
  exportAssistantConversation,
  getAssistantData,
  getAssistantReferenceOptions,
  uploadAssistantAttachment
} from '../../services/assistantApi';
import type { PageProps } from '../../types/ui';

const answerModeTabs = [
  { key: 'chatbi', label: '经营分析' },
  { key: 'professional_brief', label: '专业解读' },
  { key: 'plain_language', label: '通俗解释' },
  { key: 'business_advice', label: '业务建议' },
  { key: 'report_style', label: '报告摘要' }
];

const modelProviderOptions = [
  { value: 'auto', label: 'AUTO（推荐）' },
  { value: 'kimi', label: 'Kimi K2.6' },
  { value: 'mimo', label: 'MiMo V2.5' },
  { value: 'deepseek', label: 'DeepSeek V4-Flash' }
];

const dataSourceOptions = [
  { value: 'all', label: '全部数据源' },
  { value: 'prediction', label: '预测数据' },
  { value: 'knowledge', label: '知识库' },
  { value: 'strategy', label: '策略数据' }
];

const businessQuestions = [
  '当前电力供需如何',
  '明日分时电价预测',
  '新能源出力预测',
  '高峰时段负荷预测',
  '建议购电策略',
  '风险识别与评估',
  '生成交易报告',
  '政策解读与影响'
];

const assistantQuickQuestions = [
  '查看分时电价预测',
  '解释高价风险原因',
  '生成购电建议方案',
  '对比历史同期情况',
  '生成完整分析报告'
];

const ASSISTANT_CHAT_TIMEOUT_MS = 60000;

const providerDisplayLabels: Record<string, string> = {
  deterministic: '快速回答',
  kimi: 'Kimi K2.6',
  mimo: 'MiMo V2.5',
  deepseek: 'DeepSeek V4-Flash',
  ollama: '本地模型',
  fallback: '降级回答',
  template: '规则回答',
  auto: '自动'
};

const emptyTrace = {
  intent: '待提问',
  tools: [] as string[],
  sources: [] as string[],
  refs: [] as string[],
  traceId: '',
  confidence: 0
};

const kpiDefinitions = [
  { key: 'loadPeak', label: '负荷峰值', unit: 'MW', tone: 'info', note: '本次回答暂无该指标' },
  { key: 'renewablePeak', label: '新能源出力峰值', unit: 'MW', tone: 'success', note: '本次回答暂无该指标' },
  { key: 'gapPeriod', label: '最大缺口时段', unit: '', tone: 'danger', note: '本次回答暂无该指标' },
  { key: 'gapMax', label: '缺口最大值', unit: 'MW', tone: 'warning', note: '本次回答暂无该指标' },
  { key: 'priceRange', label: '分时电价区间', unit: '元/kWh', tone: 'success', note: '本次回答暂无该指标' },
  { key: 'avgPrice', label: '平均电价', unit: '元/kWh', tone: 'warning', note: '本次回答暂无该指标' }
];

type TraceView = typeof emptyTrace;

type AnswerState = {
  source?: string;
  rawSource?: string;
  businessMeta?: Record<string, any>;
  evidenceSummary?: string[];
  knowledgeEvidenceSummary?: string[];
  keyMetrics?: Record<string, any>;
  dataUsed?: Record<string, boolean>;
  llmUsed?: boolean;
  modelFallback?: boolean;
  modelProviderUsed?: string;
  modelProviderRequested?: string;
  riskLevel?: string;
  focusPeriods?: string[];
  warnings?: string[];
  rag?: any;
  debugPayload?: any;
  error?: string;
  degraded?: boolean;
  attachments?: AssistantAttachment[];
  references?: AssistantReference[];
  streamEvents?: Array<{ event: string; message: string }>;
  chatbi?: any;
};

type AssistantAttachment = {
  attachment_id: string;
  filename: string;
  kind?: string;
  content_type?: string;
  size?: number;
  summary?: string;
};

type AssistantReference = {
  id: string;
  label: string;
  type: string;
  summary?: string;
  payload?: any;
};

type AssistantMessage = {
  id: string;
  role: 'user' | 'assistant';
  content: string;
  createdAt: string;
  status?: 'pending' | 'streaming' | 'done' | 'error';
  question?: string;
  answerState?: AnswerState;
  trace?: TraceView;
};

function providerDisplayName(value?: string) {
  if (!value) return undefined;
  const key = String(value).toLowerCase();
  return providerDisplayLabels[key] || value;
}

function nowText() {
  return new Date().toLocaleTimeString('zh-CN', { hour: '2-digit', minute: '2-digit' });
}

function messageId(prefix: string) {
  return `${prefix}_${Date.now()}_${Math.random().toString(16).slice(2, 8)}`;
}

function sanitizeEvidenceLabel(value: string) {
  const raw = String(value || '').trim();
  if (!raw) return '';
  const withoutScore = raw.replace(/\s*\(?score\s*=\s*[-.\d]+\)?/gi, '').trim();
  const normalized = withoutScore.replace(/\\/g, '/');
  const parts = normalized.split('/').filter(Boolean);
  const last = parts[parts.length - 1] || normalized;
  return last.replace(/\.(md|txt|json|jsonl|docx)$/i, '').trim() || '知识依据';
}

function compactEvidenceItems(items?: string[]) {
  return Array.from(new Set((items || []).map(sanitizeEvidenceLabel).filter(Boolean))).slice(0, 8);
}

function asList(value: any): string[] {
  if (Array.isArray(value)) return value.map((item) => String(item)).filter(Boolean);
  if (value === undefined || value === null || value === '') return [];
  return [String(value)];
}

function sectionText(answer: string, title: string, fallback = '') {
  const escaped = title.replace(/[.*+?^${}()|[\]\\]/g, '\\$&');
  const titles = ['结论', '数据依据', '原因解释', '业务建议', '风险提示'];
  const next = titles.filter((item) => item !== title).join('|');
  const match = answer.match(new RegExp(`${escaped}[：:]?\\s*([\\s\\S]*?)(?=\\n\\s*(${next})[：:]?|$)`));
  return (match?.[1] || fallback).trim();
}

function splitContent(value: any): string[] {
  if (Array.isArray(value)) return value.map((item) => String(item).trim()).filter(Boolean);
  return String(value || '').split(/\n+/).map((item) => item.trim()).filter(Boolean);
}

function firstBusinessOutput(response: any) {
  const calls = Array.isArray(response?.tool_calls) ? response.tool_calls : [];
  const outputs = calls.map((item: any) => item.output).filter(Boolean);
  return outputs.find((item: any) => item.query_summary || item.table_name || item.tables || item.fields || item.not_found_reason) || {};
}

function extractBusinessMeta(response: any) {
  const output = firstBusinessOutput(response);
  const tables = Array.from(
    new Set(
      [...asList(output.table_name), ...asList(output.tables)]
        .flatMap((item) => String(item).split(','))
        .map((item) => item.trim())
        .filter(Boolean)
    )
  );
  const fields = Array.from(
    new Set(
      asList(output.fields)
        .flatMap((item) => String(item).split(','))
        .map((item) => item.trim())
        .filter(Boolean)
    )
  ).slice(0, 12);
  const timeRange = output.time_range
    ? `${output.time_range.field || '时间字段'}：${output.time_range.start || output.time_range.min || '--'} ~ ${output.time_range.end || output.time_range.max || '--'}`
    : '';
  return {
    tables,
    fields,
    timeRange,
    rowCount: output.row_count ?? output.total ?? undefined,
    querySummary: output.query_summary || output.summary || '',
    notFoundReason: output.not_found_reason || output.reason || '',
    safe: output.safe,
    available: output.available,
    knowledgeEvidence: compactEvidenceItems(response?.knowledge_evidence_summary || [])
  };
}

function normalizeTrace(response: any): TraceView {
  if (response?.analysis_plan && response?.lineage) {
    return {
      intent: '经营分析',
      tools: ['AnalysisPlan', 'Validator', ...(response.result_dataset ? ['Query Compiler'] : [])],
      sources: (response.result_dataset?.schema || []).map((item: any) => item.business_name).filter(Boolean),
      refs: response.lineage.result_hash ? [`result_hash:${response.lineage.result_hash}`] : [],
      traceId: response.lineage.run_id || '',
      confidence: response.validation?.valid ? 100 : 0
    };
  }
  const rawConfidence = Number(response.confidence ?? 0);
  const confidence = rawConfidence <= 1 && rawConfidence > 0 ? Math.round(rawConfidence * 100) : Math.round(rawConfidence || 0);
  return {
    intent: response.intent || '智能问答',
    tools: (response.tools || response.tool_calls || []).map((item: any) => item.name || item.tool_name || 'tool'),
    sources: (response.evidence || []).map((item: any) => item.source || item.tool || item.title || '系统数据'),
    refs: (response.evidence || [])
      .map((item: any) => item.title || item.report_id || item.fields?.join(', ') || item.time || item.source)
      .filter(Boolean),
    traceId: response.trace_id || response.trace?.trace_id || '',
    confidence
  };
}

function normalizeAnswerState(response: any): AnswerState {
  const isChatBI = Boolean(response?.analysis_plan && response?.validation);
  const chatbiMeta = isChatBI
    ? {
        tables: response.result_dataset ? ['受控业务指标查询'] : [],
        fields: (response.result_dataset?.schema || []).map((item: any) => item.business_name).filter(Boolean),
        timeRange: response.analysis_plan?.time_range
          ? `${response.analysis_plan.time_range.start} ~ ${response.analysis_plan.time_range.end}`
          : '',
        rowCount: response.result_dataset?.row_count,
        querySummary: response.state === 'clarification_required' ? '等待补充分析条件' : '分析计划已验证并执行',
        available: response.available,
        knowledgeEvidence: []
      }
    : extractBusinessMeta(response);
  const rawSource = response.dataSource || response.model_provider_used || response.intent;
  return {
    source: isChatBI ? '经营分析' : providerDisplayName(rawSource),
    rawSource,
    businessMeta: chatbiMeta,
    evidenceSummary: compactEvidenceItems(response.evidence_summary || []),
    knowledgeEvidenceSummary: compactEvidenceItems(response.knowledge_evidence_summary || []),
    keyMetrics: response.key_metrics || response.metrics || response.business_metrics || {},
    dataUsed: response.data_used || {},
    llmUsed: response.llm_used,
    modelFallback: response.model_fallback,
    modelProviderUsed: response.model_provider_used || response.planner?.provider,
    modelProviderRequested: response.model_provider_requested,
    riskLevel: response.risk_level,
    focusPeriods: response.focus_periods || [],
    warnings: response.warnings || [],
    rag: response.rag,
    debugPayload: response,
    degraded: Boolean(response.model_fallback || response.warnings?.length),
    chatbi: isChatBI ? response : undefined
  };
}

function buildChatBIChartOption(payload: any) {
  const dataset = payload?.result_dataset;
  const spec = payload?.chart_spec;
  if (!dataset || !spec || spec.chart_type === 'table' || spec.data_hash !== dataset.result_hash) return null;
  const labels = Object.fromEntries((dataset.schema || []).map((item: any) => [item.field, item.business_name]));
  const rows = dataset.rows || [];
  if (spec.chart_type === 'pie') {
    const field = spec.y?.[0];
    return {
      tooltip: { trigger: 'item' },
      legend: { bottom: 0 },
      series: [{
        name: labels[field] || field,
        type: 'pie',
        radius: ['42%', '68%'],
        data: rows.map((row: any) => ({ name: String(row[spec.x] ?? '--'), value: row[field] }))
      }]
    };
  }
  const xValues = Array.from(new Set(rows.map((row: any) => String(row[spec.x] ?? '--'))));
  const seriesValues = spec.series
    ? Array.from(new Set(rows.map((row: any) => String(row[spec.series] ?? '--'))))
    : [null];
  return {
    tooltip: { trigger: 'axis' },
    legend: { bottom: 0 },
    grid: { left: 48, right: 20, top: 24, bottom: 52 },
    xAxis: { type: 'category', data: xValues },
    yAxis: { type: 'value', name: spec.unit || '' },
    series: (spec.y || []).flatMap((field: string) => seriesValues.map((seriesValue: any) => ({
        name: seriesValue === null ? (labels[field] || field) : `${seriesValue} · ${labels[field] || field}`,
        type: spec.chart_type,
        smooth: spec.chart_type === 'line',
        data: xValues.map((xValue) => rows.find((row: any) =>
          String(row[spec.x] ?? '--') === xValue
          && (seriesValue === null || String(row[spec.series] ?? '--') === seriesValue)
        )?.[field] ?? null)
      })))
  };
}

function ChatBIArtifacts({ payload }: { payload: any }) {
  if (!payload) return null;
  if (payload.state === 'clarification_required') {
    return <Alert className="assistant-chatbi-state" type="info" showIcon message="需要补充分析条件" description={payload.clarification?.question} />;
  }
  const dataset = payload.result_dataset;
  const spec = payload.chart_spec;
  if (!dataset || !spec) return null;
  const hashesMatch = dataset.result_hash === spec.data_hash && dataset.result_hash === payload.narrative?.result_hash;
  if (!hashesMatch) {
    return <Alert className="assistant-chatbi-state" type="error" showIcon message="结果一致性校验未通过" description="表格、图表与分析结论未共享同一结果版本，本次结果已停止展示。" />;
  }
  const schema = dataset.schema || [];
  const columns = schema.map((item: any) => ({
    title: `${item.business_name}${item.unit ? `（${item.unit}）` : ''}`,
    dataIndex: item.field,
    key: item.field,
    ellipsis: true
  }));
  const chartOption = buildChatBIChartOption(payload);
  return (
    <section className="assistant-chatbi-artifacts">
      <div className="assistant-chatbi-status">
        <strong>分析计划</strong>
        <Tag color={payload.validation?.valid ? 'success' : 'default'}>{payload.validation?.valid ? '验证通过' : '未执行'}</Tag>
        {payload.memory_context?.used && <Tag color="blue">已承接上一轮条件</Tag>}
        <span>{dataset.row_count} 条结果 · {String(dataset.executed_at || '').replace('T', ' ').slice(0, 19)}</span>
      </div>
      {dataset.state === 'empty' && <Alert type="info" showIcon message="所选条件暂无数据" />}
      {dataset.state === 'insufficient_data' && <Alert type="warning" showIcon message="对比数据不足" />}
      {chartOption && dataset.state === 'success' && <div className="assistant-chatbi-chart"><AppChart option={chartOption} height={260} /></div>}
      <Table
        className="assistant-chatbi-table"
        size="small"
        pagination={dataset.row_count > 12 ? { pageSize: 12, size: 'small' } : false}
        rowKey={(row: any) => JSON.stringify(row)}
        dataSource={dataset.rows || []}
        columns={columns}
        scroll={{ x: true }}
        locale={{ emptyText: <Empty image={Empty.PRESENTED_IMAGE_SIMPLE} description="暂无可展示结果" /> }}
      />
    </section>
  );
}

function fallbackBusinessAnswer(error: unknown) {
  const detail = error instanceof Error ? error.message : String(error || '');
  return [
    '结论：当前 AI 服务暂时不可用，未生成可用于业务决策的回答。',
    '',
    '数据依据：本次请求没有取得后端 AI/RAG/工具链返回结果。',
    '',
    '原因解释：可能是网络、认证、后端服务或模型服务暂时异常。',
    '',
    '业务建议：请稍后重试，或先查看预测中心、策略中心和知识库中的已有业务结果。',
    '',
    `风险提示：本次失败不代表供需、电价或交易风险发生变化。${detail ? `错误摘要：${detail}` : ''}`
  ].join('\n');
}

function withAssistantTimeout<T>(promise: Promise<T>, timeoutMs = ASSISTANT_CHAT_TIMEOUT_MS) {
  let timer: ReturnType<typeof setTimeout> | undefined;
  const timeout = new Promise<never>((_, reject) => {
    timer = setTimeout(() => {
      reject(new Error(`AI 问答请求超过 ${Math.round(timeoutMs / 1000)} 秒未返回，请稍后重试。`));
    }, timeoutMs);
  });
  return Promise.race([promise, timeout]).finally(() => {
    if (timer) clearTimeout(timer);
  });
}

function buildAnswerModules(message?: AssistantMessage) {
  const answerText = String(message?.content || '').trim();
  const state = message?.answerState || {};
  const evidenceSummary = compactEvidenceItems(state.evidenceSummary || []);
  const knowledgeSummary = compactEvidenceItems(state.knowledgeEvidenceSummary || []);
  const streamEvents = state.streamEvents || [];
  if (!answerText && (message?.status === 'pending' || message?.status === 'streaming')) {
    return [
      {
        key: 'progress',
        title: '生成进度',
        icon: <ClockCircleOutlined />,
        tone: 'info',
        lines: streamEvents.length ? streamEvents.map((item) => item.message) : ['正在识别问题并调用业务工具链。']
      }
    ];
  }

  const hasStructuredSections = ['结论', '数据依据', '原因解释', '业务建议', '风险提示'].some((title) =>
    new RegExp(`${title}[：:]`).test(answerText)
  );
  const warningLines = splitContent(sectionText(answerText, '风险提示'));
  if (state.modelFallback) warningLines.push('模型生成发生降级，建议结合数据依据复核后再用于业务判断。');
  if (state.warnings?.length) warningLines.push(...state.warnings);

  const modules: Array<{ key: string; title: string; icon: any; tone: string; lines: string[] }> = [
    {
      key: 'conclusion',
      title: '结论',
      icon: <CheckCircleOutlined />,
      tone: 'success',
      lines: splitContent(hasStructuredSections ? sectionText(answerText, '结论', answerText) : answerText)
    },
    {
      key: 'evidence',
      title: '数据依据',
      icon: <BarChartOutlined />,
      tone: 'info',
      lines: [
        ...splitContent(sectionText(answerText, '数据依据')),
        ...evidenceSummary.map((item) => `数据摘要：${item}`),
        ...knowledgeSummary.map((item) => `知识引用：${item}`)
      ]
    }
  ];

  if (hasStructuredSections) {
    modules.push(
      {
        key: 'reason',
        title: '原因解释',
        icon: <BulbOutlined />,
        tone: 'purple',
        lines: splitContent(sectionText(answerText, '原因解释'))
      },
      {
        key: 'suggestion',
        title: '业务建议',
        icon: <FileTextOutlined />,
        tone: 'warning',
        lines: splitContent(sectionText(answerText, '业务建议'))
      },
      {
        key: 'warning',
        title: '风险提示',
        icon: <ExclamationCircleOutlined />,
        tone: 'danger',
        lines: warningLines
      }
    );
  } else if (warningLines.length) {
    modules.push({
      key: 'warning',
      title: '风险提示',
      icon: <ExclamationCircleOutlined />,
      tone: 'danger',
      lines: warningLines
    });
  }

  return modules.filter((item) => item.lines.length);
}

function buildEvidenceRows(message?: AssistantMessage) {
  if (!message || message.status === 'pending') return [];
  const state = message.answerState || {};
  const meta = state.businessMeta || {};
  const rows: Array<{ key: string; source: string; timeRange: string; confidence: string; status: string }> = [];

  if (meta.tables?.length) {
    rows.push({
      key: 'business-meta',
      source: meta.tables.join('、'),
      timeRange: meta.timeRange || '随本次回答返回',
      confidence: meta.available === false ? '需复核' : '已采用',
      status: meta.querySummary || '业务数据查询'
    });
  }

  compactEvidenceItems(state.evidenceSummary || []).forEach((item, index) => {
    rows.push({
      key: `evidence-${index}`,
      source: item,
      timeRange: '随本次回答返回',
      confidence: '已采用',
      status: '数据摘要'
    });
  });

  return rows;
}

function buildKpiCards(message?: AssistantMessage) {
  const metrics = message?.answerState?.keyMetrics || {};
  return kpiDefinitions.map((item) => {
    const payload = metrics[item.key] || metrics[item.label];
    const value = payload?.value ?? payload ?? '--';
    const hasValue = value !== undefined && value !== null && value !== '' && value !== '--';
    return {
      ...item,
      value: hasValue ? String(value) : '--',
      note: payload?.time || payload?.note || item.note,
      status: hasValue ? '已采用' : '暂无数据'
    };
  });
}

function buildKnowledgeItems(message?: AssistantMessage) {
  const state = message?.answerState || {};
  const returnedItems = compactEvidenceItems([
    ...(state.knowledgeEvidenceSummary || []),
    ...(state.businessMeta?.knowledgeEvidence || []),
    ...(message?.trace?.refs || [])
  ]);
  if (returnedItems.length) {
    return returnedItems.map((item) => ({ title: item, tag: '本次引用', date: '来自回答依据' }));
  }
  return [];
}

export function AssistantPage({ onSubNavigate }: PageProps) {
  const { message } = App.useApp();
  const { hasPermission, user } = useAuth();
  const [assistantData, setAssistantData] = useState<any>({
    conversations: [],
    questions: businessQuestions,
    empty: true
  });
  const [input, setInput] = useState('');
  const [sessionId, setSessionId] = useState<string>();
  const [messages, setMessages] = useState<AssistantMessage[]>([]);
  const [activeAssistantId, setActiveAssistantId] = useState<string>();
  const [loading, setLoading] = useState(false);
  const [questionOffset, setQuestionOffset] = useState(0);
  const [developerMode, setDeveloperMode] = useState(false);
  const [developerOpen, setDeveloperOpen] = useState(false);
  const [answerStyle, setAnswerStyle] = useState('professional_brief');
  const [selectedDataSource, setSelectedDataSource] = useState('all');
  const [modelProvider, setModelProvider] = useState('auto');
  const [sessionProviders, setSessionProviders] = useState<Record<string, string>>({});
  const [traceRows, setTraceRows] = useState<any[]>([]);
  const [attachments, setAttachments] = useState<AssistantAttachment[]>([]);
  const [selectedReferences, setSelectedReferences] = useState<AssistantReference[]>([]);
  const [referenceOptions, setReferenceOptions] = useState<AssistantReference[]>([]);
  const [referenceOpen, setReferenceOpen] = useState(false);
  const [referenceLoading, setReferenceLoading] = useState(false);
  const [exportOpen, setExportOpen] = useState(false);
  const [detailPanel, setDetailPanel] = useState<'evidence' | 'knowledge' | null>(null);
  const [uploadingAttachment, setUploadingAttachment] = useState(false);
  const messageScrollRef = useRef<HTMLDivElement>(null);
  const attachmentInputRef = useRef<HTMLInputElement>(null);
  const imageInputRef = useRef<HTMLInputElement>(null);

  const canUseDeveloperMode = Boolean(user?.role === 'admin' || user?.role === 'developer' || hasPermission('assistant:debug') || hasPermission('trace:read'));
  const visibleQuestions = useMemo(() => [...businessQuestions, ...businessQuestions].slice(questionOffset, questionOffset + 8), [questionOffset]);
  const assistantMessages = messages.filter((item) => item.role === 'assistant');
  const activeAssistant = assistantMessages.find((item) => item.id === activeAssistantId) || assistantMessages[assistantMessages.length - 1];
  const activeTrace = activeAssistant?.trace || emptyTrace;
  const evidenceRows = useMemo(() => buildEvidenceRows(activeAssistant), [activeAssistant]);
  const kpiCards = useMemo(() => buildKpiCards(activeAssistant), [activeAssistant]);
  const knowledgeItems = useMemo(() => buildKnowledgeItems(activeAssistant), [activeAssistant]);
  const answerModules = useMemo(() => buildAnswerModules(activeAssistant), [activeAssistant]);
  const providerSessionKey = sessionId || 'new-conversation';

  useEffect(() => {
    let mounted = true;
    getAssistantData().then((data) => {
      if (mounted) setAssistantData(data);
    });
    return () => {
      mounted = false;
    };
  }, []);

  useEffect(() => {
    if (!canUseDeveloperMode && developerMode) setDeveloperMode(false);
  }, [canUseDeveloperMode, developerMode]);

  useEffect(() => {
    messageScrollRef.current?.scrollTo({ top: messageScrollRef.current.scrollHeight, behavior: 'smooth' });
  }, [messages]);

  useEffect(() => {
    if (!developerOpen || !canUseDeveloperMode) return;
    api.aiTraces(30).then((payload) => setTraceRows(payload.traces || [])).catch(() => undefined);
  }, [developerOpen, canUseDeveloperMode]);

  function updateAssistantMessage(id: string, updater: (message: AssistantMessage) => AssistantMessage) {
    setMessages((current) => current.map((item) => (item.id === id ? updater(item) : item)));
  }

  function appendStreamEvent(id: string, event: string, payload: any) {
    const messageText = payload?.message || payload?.source || payload?.name || event;
    updateAssistantMessage(id, (item) => ({
      ...item,
      answerState: {
        ...(item.answerState || {}),
        streamEvents: [...(item.answerState?.streamEvents || []), { event, message: String(messageText) }].slice(-6)
      }
    }));
  }

  function finalizeAssistantMessage(id: string, response: any, context?: { attachments: AssistantAttachment[]; references: AssistantReference[] }) {
    const content = String(response.answer || response.narrative?.text || response.clarification?.question || '').trim() || '本次请求未返回回答内容。';
    const answerState = {
      ...normalizeAnswerState(response),
      attachments: context?.attachments,
      references: context?.references
    };
    const trace = normalizeTrace(response);
    if (response.session_id) {
      setSessionId(response.session_id);
      setSessionProviders((current) => ({ ...current, [response.session_id]: modelProvider }));
    }
    updateAssistantMessage(id, (item) => ({
      ...item,
      content,
      status: 'done',
      answerState,
      trace
    }));
    if (developerMode && canUseDeveloperMode) {
      api.aiTraces(30).then((payload) => setTraceRows(payload.traces || [])).catch(() => undefined);
    }
  }

  async function submitQuestion(question: string) {
    const text = question.trim();
    if (!text || loading) return;
    const userMessage: AssistantMessage = {
      id: messageId('user'),
      role: 'user',
      content: text,
      createdAt: nowText()
    };
    const assistantId = messageId('assistant');
    const assistantMessage: AssistantMessage = {
      id: assistantId,
      role: 'assistant',
      question: text,
      content: '',
      createdAt: nowText(),
      status: 'pending',
      trace: emptyTrace
    };
    setMessages((current) => [...current, userMessage, assistantMessage]);
    setActiveAssistantId(assistantId);
    setInput('');
    setLoading(true);
    const contextAttachments = [...attachments];
    const contextReferences = [...selectedReferences];

    const options = {
      answer_style: answerStyle,
      model_provider: modelProvider,
      page_context: {
        page: 'assistant',
        data_source_scope: selectedDataSource,
        attachments: contextAttachments.map((item) => ({
          attachment_id: item.attachment_id,
          filename: item.filename,
          kind: item.kind,
          summary: item.summary
        })),
        references: contextReferences.map((item) => ({
          id: item.id,
          label: item.label,
          type: item.type,
          summary: item.summary
        }))
      },
      debug: developerMode && canUseDeveloperMode
    };

    if (answerStyle === 'chatbi') {
      const activeSessionId = sessionId || `chatbi_${Date.now().toString(36)}`;
      setSessionId(activeSessionId);
      setSessionProviders((current) => ({ ...current, [activeSessionId]: modelProvider }));
      try {
        const response = await withAssistantTimeout(askChatBI(text, activeSessionId, { model_provider: modelProvider }));
        finalizeAssistantMessage(assistantId, response);
      } catch (error) {
        updateAssistantMessage(assistantId, (item) => ({
          ...item,
          content: fallbackBusinessAnswer(error),
          status: 'error',
          answerState: {
            error: error instanceof Error ? error.message : String(error || ''),
            degraded: true,
            debugPayload: { error: error instanceof Error ? error.message : String(error || '') }
          },
          trace: emptyTrace
        }));
        message.error('经营分析请求失败，请检查条件后重试');
      } finally {
        setLoading(false);
      }
      return;
    }

    try {
      const controller = new AbortController();
      const timer = window.setTimeout(() => controller.abort(), ASSISTANT_CHAT_TIMEOUT_MS);
      let streamedText = '';
      const response = await askAssistantStream(
        text,
        sessionId,
        options,
        (event, payload) => {
          if (event === 'token') {
            streamedText += payload?.text || '';
            updateAssistantMessage(assistantId, (item) => ({
              ...item,
              content: streamedText,
              status: 'streaming'
            }));
            return;
          }
          appendStreamEvent(assistantId, event, payload);
        },
        controller.signal
      ).finally(() => window.clearTimeout(timer));
      finalizeAssistantMessage(assistantId, response, { attachments: contextAttachments, references: contextReferences });
      setAttachments([]);
    } catch (error) {
      try {
        appendStreamEvent(assistantId, 'fallback', { message: '实时输出暂不可用，正在切换普通回答。' });
        const response = await withAssistantTimeout(askAssistant(text, sessionId, options));
        finalizeAssistantMessage(assistantId, response, { attachments: contextAttachments, references: contextReferences });
        setAttachments([]);
        message.warning('实时输出暂不可用，已切换普通回答');
      } catch (fallbackError) {
        const content = fallbackBusinessAnswer(fallbackError);
        updateAssistantMessage(assistantId, (item) => ({
          ...item,
          content,
          status: 'error',
          answerState: {
            error: fallbackError instanceof Error ? fallbackError.message : String(fallbackError || ''),
            degraded: true,
            attachments: contextAttachments,
            references: contextReferences,
            debugPayload: { error: fallbackError instanceof Error ? fallbackError.message : String(fallbackError || '') }
          },
          trace: emptyTrace
        }));
        message.error('AI 助手请求失败，请稍后重试');
      }
    } finally {
      setLoading(false);
    }
  }

  function newConversation() {
    setSessionId(undefined);
    setMessages([]);
    setActiveAssistantId(undefined);
    setInput('');
    setModelProvider('auto');
    message.success('已创建新会话');
  }

  function selectConversation(nextSessionId: string) {
    setSessionId(nextSessionId);
    setModelProvider(sessionProviders[nextSessionId] || 'auto');
  }

  function changeModelProvider(value: string) {
    setModelProvider(value);
    setSessionProviders((current) => ({ ...current, [providerSessionKey]: value }));
  }

  function rotateQuestions() {
    setQuestionOffset((value) => (value + 4) % businessQuestions.length);
  }

  async function handleUploadFiles(fileList: FileList | null, kind: 'attachment' | 'image') {
    const files = Array.from(fileList || []);
    if (!files.length) return;
    setUploadingAttachment(true);
    try {
      const uploaded: AssistantAttachment[] = [];
      for (const file of files) {
        const payload = await uploadAssistantAttachment(file, kind);
        uploaded.push(payload);
      }
      setAttachments((current) => [...current, ...uploaded]);
      message.success(`已上传 ${uploaded.length} 个文件`);
    } catch (error) {
      message.error(error instanceof Error ? error.message : '附件上传失败');
    } finally {
      setUploadingAttachment(false);
      if (attachmentInputRef.current) attachmentInputRef.current.value = '';
      if (imageInputRef.current) imageInputRef.current.value = '';
    }
  }

  async function openReferencePicker() {
    setReferenceOpen(true);
    setReferenceLoading(true);
    try {
      const options = await getAssistantReferenceOptions(input || activeAssistant?.question || '');
      setReferenceOptions(options);
    } catch (error) {
      message.error(error instanceof Error ? error.message : '引用数据加载失败');
      setReferenceOptions([]);
    } finally {
      setReferenceLoading(false);
    }
  }

  function toggleReference(item: AssistantReference) {
    setSelectedReferences((current) => {
      if (current.some((selected) => selected.id === item.id)) {
        return current.filter((selected) => selected.id !== item.id);
      }
      return [...current, item].slice(0, 8);
    });
  }

  function conversationExportPayload() {
    const payload = {
      session_id: sessionId || 'local_session',
      messages: messages.map((item) => ({
        role: item.role,
        content: item.content,
        created_at: item.createdAt,
        trace_id: item.trace?.traceId
      }))
    };
    return payload;
  }

  async function exportConversation(format: 'docx' | 'pdf') {
    try {
      const { blob, filename } = await exportAssistantConversation(format, conversationExportPayload());
      const url = URL.createObjectURL(blob);
      const a = document.createElement('a');
      a.href = url;
      a.download = filename;
      a.click();
      URL.revokeObjectURL(url);
      message.success(`已导出 ${format === 'docx' ? 'Word' : 'PDF'} 文件`);
      setExportOpen(false);
    } catch (error) {
      message.warning(error instanceof Error ? error.message : '导出失败');
    }
  }

  function removeAttachment(attachmentId: string) {
    setAttachments((current) => current.filter((item) => item.attachment_id !== attachmentId));
  }

  function removeReference(referenceId: string) {
    setSelectedReferences((current) => current.filter((item) => item.id !== referenceId));
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

  const sessionItems = assistantData.conversations || [];
  const evidenceColumns = [
    { title: '数据表 / 来源', dataIndex: 'source', key: 'source', ellipsis: true },
    { title: '时间范围', dataIndex: 'timeRange', key: 'timeRange', width: 148 },
    {
      title: '状态',
      dataIndex: 'confidence',
      key: 'confidence',
      width: 82,
      render: (value: string) => <Tag color={value === '已采用' || value.endsWith('%') ? 'success' : 'default'}>{value}</Tag>
    }
  ];

  return (
    <div className="assistant-workspace-page">
      {assistantData.error && (
        <Alert
          className="assistant-business-alert"
          type="warning"
          showIcon
          message="会话历史暂时不可用"
          description="当前不影响发起新的 AI 问答；历史会话恢复后会自动显示。"
        />
      )}

      {canUseDeveloperMode && (
        <div className="assistant-title-actions">
          <Button
            type="text"
            size="small"
            className="assistant-dev-entry"
            icon={<SettingOutlined />}
            onClick={() => setDeveloperOpen(true)}
          >
            开发者信息
          </Button>
        </div>
      )}

      <div className="assistant-workspace-grid">
        <aside className="assistant-left-rail">
          <SectionCard
            title="会话列表"
            className="assistant-session-card"
            extra={<Button type="primary" size="small" icon={<PlusOutlined />} onClick={newConversation}>新建对话</Button>}
          >
            <Input prefix={<SearchOutlined />} placeholder="搜索会话标题或内容" />
            <List
              className="assistant-session-list"
              locale={{ emptyText: <Empty image={Empty.PRESENTED_IMAGE_SIMPLE} description="暂无历史会话" /> }}
              dataSource={sessionItems}
              renderItem={(item: any, index) => (
                <List.Item className={index === 0 ? 'active-session' : ''}>
                  <button type="button" onClick={() => selectConversation(item.session_id)}>
                    <strong>{item.title || item.session_id || 'AI 会话'}</strong>
                    <span>{String(item.updated_at || item.created_at || '').slice(5, 16) || '当前'}</span>
                    <Tag color={index === 0 ? 'success' : 'default'}>{index === 0 ? '进行中' : '已完成'}</Tag>
                  </button>
                </List.Item>
              )}
            />
            <a className="section-footer-link" onClick={() => onSubNavigate?.('assistant-faq')}>查看全部历史记录 →</a>
          </SectionCard>

          <SectionCard title="常用问题" className="assistant-question-card" extra={<a onClick={rotateQuestions}>换一批</a>}>
            <div className="question-chip-grid">
              {visibleQuestions.map((item) => (
                <Button key={`${item}-${questionOffset}`} onClick={() => submitQuestion(item)} disabled={loading}>{item}</Button>
              ))}
            </div>
          </SectionCard>
        </aside>

        <main className="assistant-chat-main">
          <SectionCard
            className="assistant-chat-card"
            title={
              <div className="assistant-mode-tabs" role="tablist" aria-label="回答模式">
                {answerModeTabs.map((item) => (
                  <Button key={item.key} type={answerStyle === item.key ? 'primary' : 'default'} onClick={() => setAnswerStyle(item.key)}>
                    {item.label}
                  </Button>
                ))}
              </div>
            }
            extra={
              <Space className="assistant-chat-tools" size={8}>
                <span>数据源：</span>
                <Select size="small" value={selectedDataSource} options={dataSourceOptions} style={{ width: 126 }} onChange={setSelectedDataSource} />
                <Button icon={<DownloadOutlined />} onClick={() => setExportOpen(true)}>导出本次会话</Button>
              </Space>
            }
          >
            <div className="assistant-chat-body">
              <div className="assistant-message-scroll" ref={messageScrollRef}>
                {messages.length ? (
                  messages.map((item) => {
                    if (item.role === 'user') {
                      return (
                        <div className="user-message assistant-user-bubble" key={item.id}>
                          <div className="message-copy-row">
                            <span>{item.content}</span>
                            <Button type="text" size="small" icon={<CopyOutlined />} aria-label="复制问题" title="复制问题" onClick={() => copyText(item.content)} />
                          </div>
                          <small>{item.createdAt}</small>
                        </div>
                      );
                    }
                    return (
                      <div className={`ai-message assistant-ai-response ${activeAssistantId === item.id ? 'active-answer' : ''}`} key={item.id} onClick={() => setActiveAssistantId(item.id)}>
                        <RobotOutlined />
                        <div className="assistant-structured-answer">
                          <div className="assistant-answer-intro">
                            <strong>{item.status === 'pending' || item.status === 'streaming' ? 'AI 助手正在生成业务研判' : '本次业务研判结果'}</strong>
                            <Space size={6}>
                              {item.answerState?.modelProviderUsed && item.answerState.modelProviderUsed !== 'unavailable' && (
                                <Tag color={item.answerState.modelFallback ? 'warning' : 'blue'}>
                                  实际模型：{providerDisplayName(item.answerState.modelProviderUsed)}
                                </Tag>
                              )}
                              {item.answerState?.modelProviderUsed === 'unavailable' && <Tag color="error">所选模型不可用</Tag>}
                              {item.answerState?.modelFallback && <Tag color="warning">AUTO 已降级</Tag>}
                              {item.status === 'streaming' && <Tag color="processing">实时输出</Tag>}
                              {item.status === 'error' && <Tag color="error">请求失败</Tag>}
                              <Button type="text" size="small" icon={<CopyOutlined />} aria-label="复制回答" title="复制回答" onClick={() => copyText(item.content)}>复制</Button>
                            </Space>
                          </div>
                          {buildAnswerModules(item).map((module) => (
                            <section className={`assistant-answer-module module-${module.tone}`} key={module.key}>
                              <div className="assistant-module-title">
                                <span>{module.icon}</span>
                                <strong>{module.title}</strong>
                              </div>
                              <div className="assistant-module-content">
                                {module.lines.map((line) => <p key={`${module.key}-${line}`}>{line}</p>)}
                              </div>
                            </section>
                          ))}
                          <ChatBIArtifacts payload={item.answerState?.chatbi} />
                        </div>
                      </div>
                    );
                  })
                ) : (
                  <div className="assistant-welcome-state assistant-business-empty">
                    <RobotOutlined />
                    <h3>我是电力交易业务决策助手</h3>
                    <p>请选择左侧常用问题，或输入供需研判、电价预测、策略解释、风险识别相关问题。未取得可信业务依据前，本页面不会生成业务数值。</p>
                  </div>
                )}
              </div>

              <div className="quick-questions assistant-action-row">
                {assistantQuickQuestions.map((item) => (
                  <Button key={item} onClick={() => submitQuestion(item)} disabled={loading}>{item}</Button>
                ))}
              </div>

              <div className="chat-input p6-chat-input assistant-input-box">
                <Input.TextArea
                  value={input}
                  autoSize={{ minRows: 2, maxRows: 4 }}
                  placeholder="请输入您的问题，Shift + Enter 换行，Enter 发送"
                  onChange={(event) => setInput(event.target.value)}
                  onPressEnter={(event) => {
                    if (!event.shiftKey) {
                      event.preventDefault();
                      submitQuestion(input);
                    }
                  }}
                />
                {(attachments.length > 0 || selectedReferences.length > 0) && (
                  <div className="assistant-context-tags">
                    {attachments.map((item) => (
                      <Tag key={item.attachment_id} closable onClose={() => removeAttachment(item.attachment_id)} icon={<PaperClipOutlined />}>
                        {item.filename}
                      </Tag>
                    ))}
                    {selectedReferences.map((item) => (
                      <Tag key={item.id} closable onClose={() => removeReference(item.id)} icon={<DatabaseOutlined />}>
                        {item.label}
                      </Tag>
                    ))}
                  </div>
                )}
                <input
                  ref={attachmentInputRef}
                  type="file"
                  multiple
                  className="assistant-hidden-input"
                  onChange={(event) => handleUploadFiles(event.target.files, 'attachment')}
                />
                <input
                  ref={imageInputRef}
                  type="file"
                  multiple
                  accept="image/*"
                  className="assistant-hidden-input"
                  onChange={(event) => handleUploadFiles(event.target.files, 'image')}
                />
                <Space className="chat-input-tools">
                  <span className="assistant-model-label">AI 对话模型</span>
                  <Select
                    className="assistant-model-selector"
                    size="small"
                    aria-label="AI 对话模型"
                    value={modelProvider}
                    options={modelProviderOptions}
                    style={{ width: 178 }}
                    onChange={changeModelProvider}
                  />
                  <Button icon={<PaperClipOutlined />} loading={uploadingAttachment} onClick={() => attachmentInputRef.current?.click()}>上传附件</Button>
                  <Button icon={<DatabaseOutlined />} onClick={openReferencePicker}>引用数据</Button>
                  <Button icon={<PictureOutlined />} loading={uploadingAttachment} onClick={() => imageInputRef.current?.click()}>截图/图表</Button>
                </Space>
                <Button type="primary" icon={<SendOutlined />} loading={loading} onClick={() => submitQuestion(input)}>发送</Button>
              </div>
            </div>
          </SectionCard>
        </main>

        <aside className="assistant-right-rail">
          <SectionCard
            title="数据依据"
            className="assistant-evidence-card"
            extra={<Button type="link" size="small" disabled={!evidenceRows.length} onClick={() => setDetailPanel('evidence')}>查看全部</Button>}
          >
            <div className="assistant-card-subtitle">本次回答引用</div>
            <Table
              size="small"
              pagination={false}
              rowKey="key"
              dataSource={evidenceRows}
              columns={evidenceColumns}
              locale={{ emptyText: <Empty image={Empty.PRESENTED_IMAGE_SIMPLE} description="提问后展示本次回答采用的数据依据" /> }}
            />
            <p className="assistant-evidence-note">置信度由模型质量、数据完整性与时效性综合评估；本栏仅展示本次回答可追溯的业务依据。</p>
          </SectionCard>

          <SectionCard title="关键指标摘要" className="assistant-kpi-card">
            <div className="assistant-card-subtitle">本次回答包含结构化指标时在此汇总展示</div>
            <div className="assistant-metric-grid assistant-business-kpi-grid">
              {kpiCards.map((item) => (
                <div className={`assistant-metric-card ${item.tone}`} key={item.key}>
                  <span>{item.label}</span>
                  <strong>{item.value}<small>{item.value === '--' ? '' : item.unit}</small></strong>
                  <p>{item.note}</p>
                  <Tag color={item.status === '已采用' ? 'success' : 'default'}>{item.status}</Tag>
                </div>
              ))}
            </div>
          </SectionCard>

          <SectionCard
            title="相关知识与策略建议"
            className="assistant-knowledge-card"
            extra={<Button type="link" size="small" disabled={!knowledgeItems.length} onClick={() => setDetailPanel('knowledge')}>查看全部</Button>}
          >
            <div className="knowledge-suggestion-list assistant-knowledge-list">
              {knowledgeItems.length ? (
                knowledgeItems.map((item) => (
                  <div key={item.title}>
                    <FileTextOutlined />
                    <span>{item.title}</span>
                    <Tag color={item.tag === '本次引用' ? 'blue' : 'default'}>{item.tag}</Tag>
                    <small>{item.date}</small>
                  </div>
                ))
              ) : (
                <Empty image={Empty.PRESENTED_IMAGE_SIMPLE} description="本次回答暂无知识引用" />
              )}
            </div>
            <div className="assistant-side-actions">
              <Button icon={<ThunderboltOutlined />} onClick={() => submitQuestion('基于当前回答生成购电策略')} disabled={loading}>生成购电策略</Button>
              <Button icon={<ExclamationCircleOutlined />} onClick={() => submitQuestion('基于当前回答进行风险评估')} disabled={loading}>进行风险评估</Button>
              <Button icon={<BarChartOutlined />} onClick={() => submitQuestion('对比历史同期情况')} disabled={loading}>对比历史同期</Button>
              <Button icon={<FileSearchOutlined />} onClick={() => submitQuestion('生成日报报告')} disabled={loading}>生成日报报告</Button>
            </div>
          </SectionCard>
        </aside>
      </div>

      {canUseDeveloperMode && (
        <Drawer
          title="开发者信息"
          placement="right"
          width={560}
          open={developerOpen}
          onClose={() => setDeveloperOpen(false)}
          destroyOnHidden
        >
          <div className="assistant-dev-drawer">
            <Alert type="info" showIcon message="普通用户默认不展示 Trace、工具调用日志和原始 JSON。" />
            <div className="assistant-dev-toolbar">
              <span>调试模式</span>
              <Switch size="small" checked={developerMode} onChange={setDeveloperMode} checkedChildren="开发" unCheckedChildren="普通" />
              <Select size="small" value={modelProvider} options={modelProviderOptions} style={{ width: 178 }} onChange={changeModelProvider} />
            </div>
            <TracePanel {...activeTrace} />
            <SectionCard title="当前回答状态" compact>
              <Space wrap>
                <Tag icon={<InfoCircleOutlined />}>{activeAssistant?.status || '待提问'}</Tag>
                <Tag icon={<ClockCircleOutlined />}>{activeAssistant?.createdAt || '--'}</Tag>
                {activeAssistant?.answerState?.modelFallback && <Tag color="warning">model_fallback</Tag>}
                {activeAssistant?.answerState?.llmUsed !== undefined && <Tag>{activeAssistant.answerState.llmUsed ? 'llm_used' : 'template_or_tool'}</Tag>}
              </Space>
            </SectionCard>
            <SectionCard title="Trace 列表" compact>
              <List
                size="small"
                dataSource={traceRows}
                locale={{ emptyText: <Empty image={Empty.PRESENTED_IMAGE_SIMPLE} description="暂无 Trace 记录" /> }}
                renderItem={(item: any) => (
                  <List.Item>
                    <List.Item.Meta title={item.trace_id || item.traceId || 'trace'} description={item.intent || item.question || item.created_at} />
                  </List.Item>
                )}
              />
            </SectionCard>
            <SectionCard title="原始返回" compact>
              <pre className="assistant-raw-json">{JSON.stringify(activeAssistant?.answerState?.debugPayload || {}, null, 2)}</pre>
            </SectionCard>
          </div>
        </Drawer>
      )}

      <Modal
        title="导出本次会话"
        open={exportOpen}
        onCancel={() => setExportOpen(false)}
        footer={null}
        destroyOnHidden
      >
        <Space direction="vertical" className="assistant-export-options" size={12}>
          <Button block icon={<FileTextOutlined />} onClick={() => exportConversation('docx')}>
            导出 Word 文档
          </Button>
          <Button block icon={<DownloadOutlined />} onClick={() => exportConversation('pdf')}>
            导出 PDF 文档
          </Button>
          <Alert
            type="info"
            showIcon
            message="导出由系统服务生成"
            description="当前 Word 导出已可用；PDF 如转换引擎尚未部署，会给出明确提示。"
          />
        </Space>
      </Modal>

      <Modal
        title="引用数据"
        open={referenceOpen}
        onCancel={() => setReferenceOpen(false)}
        onOk={() => setReferenceOpen(false)}
        okText="完成"
        cancelText="取消"
        width={680}
        destroyOnHidden
      >
        <List
          className="assistant-reference-list"
          loading={referenceLoading}
          dataSource={referenceOptions}
          locale={{ emptyText: <Empty image={Empty.PRESENTED_IMAGE_SIMPLE} description="暂无可引用的数据" /> }}
          renderItem={(item) => {
            const selected = selectedReferences.some((selectedItem) => selectedItem.id === item.id);
            return (
              <List.Item
                className={selected ? 'selected' : ''}
                actions={[
                  <Button key="select" size="small" type={selected ? 'primary' : 'default'} onClick={() => toggleReference(item)}>
                    {selected ? '已选择' : '选择'}
                  </Button>
                ]}
              >
                <List.Item.Meta
                  avatar={<DatabaseOutlined />}
                  title={
                    <Space size={8}>
                      <span>{item.label}</span>
                      <Tag>{item.type}</Tag>
                    </Space>
                  }
                  description={item.summary || '来自现有业务数据服务'}
                />
              </List.Item>
            );
          }}
        />
      </Modal>

      <Drawer
        title={detailPanel === 'evidence' ? '全部数据依据' : '相关知识与策略建议'}
        placement="right"
        width={560}
        open={Boolean(detailPanel)}
        onClose={() => setDetailPanel(null)}
        destroyOnHidden
      >
        {detailPanel === 'evidence' ? (
          <Table size="small" pagination={false} rowKey="key" dataSource={evidenceRows} columns={evidenceColumns} />
        ) : (
          <List
            dataSource={knowledgeItems}
            locale={{ emptyText: <Empty image={Empty.PRESENTED_IMAGE_SIMPLE} description="本次回答暂无知识引用" /> }}
            renderItem={(item) => (
              <List.Item>
                <List.Item.Meta
                  avatar={<FileTextOutlined />}
                  title={item.title}
                  description={`${item.tag} · ${item.date}`}
                />
              </List.Item>
            )}
          />
        )}
      </Drawer>
    </div>
  );
}
