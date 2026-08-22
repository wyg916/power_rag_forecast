import { CloseOutlined, FileOutlined, PictureOutlined, ReloadOutlined, UploadOutlined } from '@ant-design/icons';
import { Button, Progress, Tag, Tooltip } from 'antd';
import { useRef, useState } from 'react';
import type { ClipboardEvent, DragEvent, ReactNode } from 'react';
import type { GlobalAssistantAttachment } from './globalAssistantStore';

const supportedExtensions = ['png', 'jpg', 'jpeg', 'webp', 'pdf', 'docx', 'txt', 'md', 'xlsx', 'csv'];
export const attachmentAccept = supportedExtensions.map((extension) => `.${extension}`).join(',');

const statusLabels: Record<string, string> = {
  uploading: '上传中',
  parsing: '解析中',
  ready: '可使用',
  failed: '失败',
  cancelled: '已取消',
  deleted: '已删除'
};

export function isSupportedAttachment(file: File) {
  const extension = file.name.split('.').pop()?.toLowerCase() || '';
  return supportedExtensions.includes(extension);
}

export function pastedFiles(event: Pick<ClipboardEvent<HTMLElement>, 'clipboardData'>) {
  return Array.from(event.clipboardData?.items || [])
    .filter((item) => item.kind === 'file')
    .map((item) => item.getAsFile())
    .filter((file): file is File => Boolean(file));
}

export function AttachmentComposer({
  attachments,
  disabled,
  onFiles,
  onRemove,
  onRetry,
  onNotice,
  children
}: {
  attachments: GlobalAssistantAttachment[];
  disabled?: boolean;
  onFiles: (files: File[]) => void;
  onRemove: (attachment: GlobalAssistantAttachment) => void;
  onRetry: (attachment: GlobalAssistantAttachment) => void;
  onNotice: (message: string) => void;
  children?: ReactNode;
}) {
  const inputRef = useRef<HTMLInputElement>(null);
  const [dragging, setDragging] = useState(false);

  function acceptFiles(files: File[]) {
    const supported = files.filter(isSupportedAttachment);
    const rejected = files.filter((file) => !isSupportedAttachment(file));
    if (rejected.length) onNotice(`不支持 ${rejected.map((file) => file.name).join('、')}；请选择 PNG、JPG、WEBP、PDF、DOCX、TXT、MD、XLSX 或 CSV。`);
    if (supported.length) onFiles(supported);
  }

  function handleDrop(event: DragEvent<HTMLDivElement>) {
    event.preventDefault();
    setDragging(false);
    acceptFiles(Array.from(event.dataTransfer.files || []));
  }

  function handlePaste(event: ClipboardEvent<HTMLDivElement>) {
    const fileItems = Array.from(event.clipboardData?.items || []).filter((item) => item.kind === 'file');
    if (!fileItems.length) return;
    const files = pastedFiles(event);
    if (!files.length) {
      onNotice('浏览器无法直接读取该文件，请拖拽或选择文件');
      return;
    }
    event.preventDefault();
    acceptFiles(files);
  }

  return (
    <div
      className={`attachment-composer ${dragging ? 'is-dragging' : ''}`}
      onDragOver={(event) => { event.preventDefault(); setDragging(true); }}
      onDragLeave={() => setDragging(false)}
      onDrop={handleDrop}
      onPaste={handlePaste}
    >
      {children}
      <input
        ref={inputRef}
        type="file"
        multiple
        accept={attachmentAccept}
        hidden
        onChange={(event) => {
          acceptFiles(Array.from(event.target.files || []));
          event.target.value = '';
        }}
      />
      <Button icon={<UploadOutlined />} disabled={disabled} onClick={() => inputRef.current?.click()}>选择文件</Button>
      <span className="attachment-drop-hint">拖拽文件或粘贴截图</span>
      {attachments.length > 0 && (
        <div className="attachment-list" aria-label="附件列表">
          {attachments.map((attachment) => {
            const image = attachment.media_type.startsWith('image/');
            const error = typeof attachment.error === 'string' ? attachment.error : attachment.error?.message;
            return (
              <div className={`attachment-item attachment-${attachment.status}`} key={attachment.client_id}>
                <div className="attachment-thumb">
                  {attachment.preview_url ? <img src={attachment.preview_url} alt="" /> : image ? <PictureOutlined /> : <FileOutlined />}
                </div>
                <div className="attachment-copy">
                  <strong title={attachment.file_name}>{attachment.file_name}</strong>
                  <span>{attachment.media_type || '文件'} · {formatFileSize(attachment.size_bytes)}</span>
                  {attachment.status === 'uploading' && <Progress percent={45} showInfo={false} size="small" status="active" />}
                  {attachment.status === 'parsing' && <Progress percent={75} showInfo={false} size="small" status="active" />}
                  {error && <small title={error}>{error}</small>}
                </div>
                <Tag color={attachment.status === 'ready' ? 'success' : attachment.status === 'failed' ? 'error' : 'processing'}>{statusLabels[attachment.status] || attachment.status}</Tag>
                {attachment.status === 'failed' && <Tooltip title="重试"><Button type="text" size="small" aria-label={`重试 ${attachment.file_name}`} icon={<ReloadOutlined />} onClick={() => onRetry(attachment)} /></Tooltip>}
                <Tooltip title="删除"><Button type="text" size="small" aria-label={`删除 ${attachment.file_name}`} icon={<CloseOutlined />} onClick={() => onRemove(attachment)} /></Tooltip>
              </div>
            );
          })}
        </div>
      )}
    </div>
  );
}

function formatFileSize(size: number) {
  if (!Number.isFinite(size) || size <= 0) return '大小未知';
  if (size < 1024) return `${size} B`;
  if (size < 1024 * 1024) return `${(size / 1024).toFixed(1)} KB`;
  return `${(size / 1024 / 1024).toFixed(1)} MB`;
}
