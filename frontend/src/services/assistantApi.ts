import { assistantMock } from '../mock/assistantMock';
import { api } from '../api';
import { mockFallback, withServiceState } from './serviceState';

export async function getAssistantData() {
  try {
    const sessions = await api.chatSessions();
    const rows = Array.isArray(sessions?.sessions) ? sessions.sessions : [];
    return withServiceState({
      ...assistantMock,
      dataSource: rows.length ? 'postgresql.ai_chat_sessions' : 'mock_fallback',
      conversations: rows.length
        ? rows.map((item: any) => [
            item.title || item.session_id || 'AI 会话',
            String(item.updated_at || item.created_at || '').slice(5, 16)
          ])
        : assistantMock.conversations
    }, {
      empty: !rows.length,
      mockFallback: !rows.length,
      fallbackReason: !rows.length ? 'AI 会话接口未返回历史记录，助手侧边栏使用本地兜底会话。' : undefined
    });
  } catch (error) {
    return mockFallback(assistantMock, error, 'AI 助手会话接口请求失败，已切换到本地兜底数据。');
  }
}

export async function askAssistant(question: string, sessionId?: string, options: any = {}) {
  try {
    return await api.chat(question, sessionId, options);
  } catch (error) {
    return {
      session_id: sessionId || 'offline_session',
      answer: [
        `结论：已收到问题“${question}”，当前后端 AI 工具链暂不可达，已进入离线降级回答。`,
        '',
        '数据依据：本地兜底数据源，仅用于保持页面交互闭环。',
        '',
        '原因解释：请求 AI 分析接口失败，前端保留自然回答展示，开发者模式下可继续排查。',
        '',
        '业务建议：恢复后端服务后重新提问，系统会自动切换为 PostgreSQL、知识库和工具链证据回答。',
        '',
        '风险提示：离线降级回答不能作为正式交易依据。'
      ].join('\n'),
      intent: 'mock_fallback',
      confidence: 0.62,
      evidence_summary: ['mock_fallback'],
      warnings: ['离线降级回答不能作为正式交易依据。'],
      data_used: { prediction: false, model: false, report: false, knowledge: false },
      dataSource: 'mock_fallback',
      error: error instanceof Error ? error.message : String(error),
      mockFallback: true,
      fallbackReason: 'AI 分析接口不可用，当前回答为离线降级结果。'
    };
  }
}
