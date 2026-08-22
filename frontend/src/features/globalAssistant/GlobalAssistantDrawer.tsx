import {
  CloseOutlined,
  MinusOutlined,
  PauseCircleOutlined,
  PlusOutlined,
  RobotOutlined,
  SendOutlined
} from '@ant-design/icons';
import { Alert, App, Button, Drawer, Empty, FloatButton, Input, Space, Switch, Tooltip } from 'antd';
import { useMemo, useRef, useSyncExternalStore } from 'react';
import type { KeyboardEvent } from 'react';
import {
  askAssistantStream,
  createAssistantRequestId,
  deleteAssistantAttachment,
  getAssistantAttachment,
  sendAssistantFeedback,
  uploadAssistantAttachment
} from '../../services/assistantApi';
import type { AssistantPageContext } from '../../services/assistantApi';
import { SectionUnavailable } from '../../components/security/PermissionGate';
import { AttachmentComposer } from './AttachmentComposer';
import { DynamicAnswer } from './DynamicAnswer';
import { globalAssistantStore } from './globalAssistantStore';
import type { GlobalAssistantAttachment } from './globalAssistantStore';

const pollingTerminal = new Set(['ready', 'failed', 'cancelled', 'deleted']);

function messageId(prefix: string) {
  return `${prefix}_${Date.now().toString(36)}_${Math.random().toString(36).slice(2, 8)}`;
}

function wait(delay: number) {
  return new Promise((resolve) => window.setTimeout(resolve, delay));
}

function errorText(error: unknown) {
  if (error instanceof DOMException && error.name === 'AbortError') return '已停止生成。';
  const text = error instanceof Error ? error.message : String(error || '');
  return text || '本次请求未完成，请稍后重试。';
}

export function GlobalAssistantDrawer({
  routeKey,
  pageTitle,
  permissionSnapshotHash,
  assistantAllowed,
  onOpenFullAssistant
}: {
  routeKey: string;
  pageTitle: string;
  permissionSnapshotHash: string;
  assistantAllowed: boolean;
  onOpenFullAssistant: () => void;
}) {
  const { message } = App.useApp();
  const state = useSyncExternalStore(globalAssistantStore.subscribe, globalAssistantStore.getSnapshot);
  const controllerRef = useRef<AbortController | null>(null);
  const readyAttachments = useMemo(() => state.attachments.filter((item) => item.status === 'ready'), [state.attachments]);

  const pageContext: AssistantPageContext = {
    route_key: routeKey,
    page_title: pageTitle,
    active_filters: {},
    selected_entity: null,
    visible_summary: { page: pageTitle },
    permission_snapshot_hash: permissionSnapshotHash
  };

  async function pollAttachment(clientId: string, attachment: GlobalAssistantAttachment) {
    if (!attachment.attachment_id || pollingTerminal.has(attachment.status)) return;
    let current = attachment;
    for (let attempt = 0; attempt < 15 && !pollingTerminal.has(current.status); attempt += 1) {
      await wait(1200);
      try {
        const record = await getAssistantAttachment(current.attachment_id, current.session_id || state.sessionId || undefined);
        current = { ...current, ...record };
        globalAssistantStore.replaceAttachment(clientId, current);
      } catch (error) {
        current = { ...current, status: 'failed', error: errorText(error) };
        globalAssistantStore.replaceAttachment(clientId, current);
      }
    }
  }

  async function uploadFile(file: File, retryItem?: GlobalAssistantAttachment) {
    const uploadSessionId = state.sessionId || messageId('sess');
    if (!state.sessionId) globalAssistantStore.setSessionId(uploadSessionId);
    const clientId = retryItem?.client_id || messageId('attachment');
    const previewUrl = retryItem?.preview_url || (file.type.startsWith('image/') ? URL.createObjectURL(file) : undefined);
    const pending: GlobalAssistantAttachment = {
      client_id: clientId,
      attachment_id: '',
      file_name: file.name,
      media_type: file.type || 'application/octet-stream',
      size_bytes: file.size,
      status: 'uploading',
      file,
      preview_url: previewUrl,
      error: null
    };
    if (retryItem) globalAssistantStore.replaceAttachment(clientId, pending);
    else globalAssistantStore.addAttachment(pending);
    try {
      const record = await uploadAssistantAttachment(file, uploadSessionId, file.type.startsWith('image/') ? 'image' : 'attachment');
      const uploaded = { ...pending, ...record };
      globalAssistantStore.replaceAttachment(clientId, uploaded);
      if (record.session_id && !state.sessionId) globalAssistantStore.setSessionId(record.session_id);
      void pollAttachment(clientId, uploaded);
    } catch (error) {
      globalAssistantStore.replaceAttachment(clientId, { ...pending, status: 'failed', error: errorText(error) });
    }
  }

  async function removeAttachment(attachment: GlobalAssistantAttachment) {
    if (attachment.attachment_id) {
      try {
        await deleteAssistantAttachment(attachment.attachment_id);
      } catch (error) {
        message.warning(errorText(error));
        return;
      }
    }
    if (attachment.preview_url) URL.revokeObjectURL(attachment.preview_url);
    globalAssistantStore.removeAttachment(attachment.client_id);
  }

  async function send() {
    const text = state.draft.trim();
    if (!assistantAllowed || state.streaming || !text) return;
    if (state.attachments.some((item) => item.status === 'uploading' || item.status === 'parsing')) {
      message.info('附件仍在处理，ready 后才可用于问答。');
      return;
    }
    const requestId = createAssistantRequestId();
    const assistantId = messageId('assistant');
    globalAssistantStore.appendMessage({ id: messageId('user'), role: 'user', markdown: text, status: 'completed' });
    globalAssistantStore.appendMessage({ id: assistantId, role: 'assistant', markdown: '', status: 'pending', requestId });
    globalAssistantStore.setDraft('');
    globalAssistantStore.setStreaming(true, requestId);
    const controller = new AbortController();
    controllerRef.current = controller;
    let streamed = '';
    try {
      const response = await askAssistantStream(text, state.sessionId || undefined, {
        request_id: requestId,
        mode: readyAttachments.some((item) => item.media_type.startsWith('image/')) ? 'vision' : readyAttachments.length ? 'file' : 'general',
        requested_tier: 'standard',
        attachment_ids: readyAttachments.map((item) => item.attachment_id),
        page_context: state.includePageContext ? pageContext : null,
        knowledge_scope: readyAttachments.length ? 'authorized_enterprise_and_attachments' : 'authorized_enterprise'
      }, (event, payload) => {
        if (event === 'meta' && payload?.session_id) globalAssistantStore.setSessionId(payload.session_id);
        if (event === 'delta') {
          streamed += payload?.text || payload?.delta || payload?.markdown || '';
          globalAssistantStore.updateMessage(assistantId, { markdown: streamed, status: 'streaming' });
        }
      }, controller.signal);
      if (response.session_id) globalAssistantStore.setSessionId(response.session_id);
      const markdown = String(response.answer?.markdown || streamed || '').trim();
      if (!markdown) throw new Error('回答为空，未作为成功结果展示。');
      globalAssistantStore.updateMessage(assistantId, {
        markdown,
        status: response.status === 'cancelled' ? 'cancelled' : 'completed',
        citations: response.citations || [],
        attachmentCitations: response.attachment_citations || []
      });
    } catch (error) {
      const cancelled = controller.signal.aborted;
      globalAssistantStore.updateMessage(assistantId, {
        markdown: cancelled ? '已停止生成。' : errorText(error),
        status: cancelled ? 'cancelled' : 'failed'
      });
    } finally {
      controllerRef.current = null;
      globalAssistantStore.setStreaming(false, null);
    }
  }

  function handleComposerKeyDown(event: KeyboardEvent<HTMLTextAreaElement>) {
    if (event.key === 'Enter' && !event.shiftKey) {
      event.preventDefault();
      void send();
    }
  }

  return (
    <>
      <Tooltip title="AI 助手" placement="left">
        <FloatButton
          className="global-assistant-fab"
          aria-label="打开全局 AI 助手"
          icon={<RobotOutlined />}
          onClick={() => globalAssistantStore.setOpen(true)}
        />
      </Tooltip>
      <Drawer
        className="global-assistant-drawer"
        title={<Space><RobotOutlined /><span>全局 AI 助手</span></Space>}
        placement="right"
        width="min(500px, 100vw)"
        open={state.open}
        onClose={() => globalAssistantStore.setOpen(false)}
        closeIcon={<CloseOutlined />}
        extra={(
          <Space size={4}>
            <Tooltip title="新会话"><Button type="text" aria-label="新会话" icon={<PlusOutlined />} onClick={() => globalAssistantStore.newConversation()} /></Tooltip>
            <Tooltip title="收起"><Button type="text" aria-label="收起助手" icon={<MinusOutlined />} onClick={() => globalAssistantStore.setOpen(false)} /></Tooltip>
          </Space>
        )}
      >
        {!assistantAllowed ? <SectionUnavailable title="当前账号未开通 AI 助手" /> : (
          <div className="global-assistant-shell">
            <div className="global-assistant-context-bar">
              <span title={pageTitle}>{pageTitle}</span>
              <Space size={6}><span>关联当前页面</span><Switch size="small" checked={state.includePageContext} onChange={(checked) => globalAssistantStore.setIncludePageContext(checked)} /></Space>
            </div>
            <div className="global-assistant-messages" aria-live="polite">
              {!state.messages.length && <Empty image={Empty.PRESENTED_IMAGE_SIMPLE} description="可以直接提问，也可以添加文件或粘贴截图。" />}
              {state.messages.map((item) => (
                <div className={`global-assistant-message message-${item.role} status-${item.status}`} key={item.id}>
                  {item.role === 'assistant' ? (
                    item.markdown ? <DynamicAnswer
                      markdown={item.markdown}
                      citations={item.citations}
                      attachmentCitations={item.attachmentCitations}
                      onCopy={() => navigator.clipboard.writeText(item.markdown).then(() => message.success('已复制')).catch(() => message.warning('复制失败，请手动选择文本'))}
                      onFeedback={(rating) => sendAssistantFeedback({ request_id: item.requestId, session_id: state.sessionId, rating }).then(() => message.success('感谢反馈')).catch((error) => message.warning(errorText(error)))}
                      onContinue={() => globalAssistantStore.setDraft('请继续分析：')}
                    /> : <div className="assistant-thinking">正在组织回答…</div>
                  ) : <div className="user-message-copy">{item.markdown}</div>}
                </div>
              ))}
            </div>
            <AttachmentComposer
              attachments={state.attachments}
              disabled={state.streaming}
              onFiles={(files) => files.forEach((file) => void uploadFile(file))}
              onRemove={(attachment) => void removeAttachment(attachment)}
              onRetry={(attachment) => attachment.file ? void uploadFile(attachment.file, attachment) : message.info('浏览器已释放原文件，请重新选择文件。')}
              onNotice={(notice) => message.warning(notice)}
            >
              <Input.TextArea
                value={state.draft}
                autoSize={{ minRows: 3, maxRows: 7 }}
                placeholder="输入问题；Enter 发送，Shift + Enter 换行"
                onChange={(event) => globalAssistantStore.setDraft(event.target.value)}
                onKeyDown={handleComposerKeyDown}
                disabled={state.streaming}
              />
            </AttachmentComposer>
            {state.attachments.some((item) => item.status === 'failed') && <Alert type="warning" showIcon message="部分附件处理失败，可删除或重试。" />}
            <div className="global-assistant-footer">
              <Button type="link" onClick={onOpenFullAssistant}>打开完整 AI 页面</Button>
              {state.streaming ? (
                <Button danger icon={<PauseCircleOutlined />} onClick={() => controllerRef.current?.abort()}>停止生成</Button>
              ) : (
                <Button type="primary" icon={<SendOutlined />} disabled={!state.draft.trim()} onClick={() => void send()}>发送</Button>
              )}
            </div>
          </div>
        )}
      </Drawer>
    </>
  );
}
