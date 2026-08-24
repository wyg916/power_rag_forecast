import type { AssistantMode } from '../../services/assistantApi';

export type AssistantAnswerStyle =
  | 'chatbi'
  | 'professional_brief'
  | 'plain_language'
  | 'business_advice'
  | 'report_style';

export interface AssistantModeContract {
  key: AssistantAnswerStyle;
  label: string;
  auditName: string;
  requestMode: AssistantMode;
}

export const DEFAULT_ASSISTANT_ANSWER_STYLE: AssistantAnswerStyle = 'professional_brief';

export const ASSISTANT_MODE_CONTRACTS: readonly AssistantModeContract[] = [
  { key: 'chatbi', label: '经营分析', auditName: '标准模式', requestMode: 'chatbi' },
  { key: 'professional_brief', label: '专业解读', auditName: '专业解读', requestMode: 'general' },
  { key: 'plain_language', label: '通俗解释', auditName: '通俗解释', requestMode: 'general' },
  { key: 'business_advice', label: '业务建议', auditName: '业务建议', requestMode: 'general' },
  { key: 'report_style', label: '报告摘要', auditName: '报告摘要', requestMode: 'general' }
] as const;

export function isAssistantAnswerStyle(value: unknown): value is AssistantAnswerStyle {
  return ASSISTANT_MODE_CONTRACTS.some((item) => item.key === value);
}

export function resolveAssistantRequestMode(
  answerStyle: AssistantAnswerStyle,
  options: { hasImage?: boolean; hasAttachments?: boolean } = {}
): AssistantMode {
  if (options.hasImage) return 'vision';
  if (options.hasAttachments) return 'file';
  return ASSISTANT_MODE_CONTRACTS.find((item) => item.key === answerStyle)?.requestMode || 'general';
}
