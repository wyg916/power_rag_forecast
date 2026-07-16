export function toNumber(value: unknown): number | null {
  const num = Number(value);
  return Number.isFinite(num) ? num : null;
}

export function formatNumber(value: unknown, digits = 1, fallback = '--') {
  const num = toNumber(value);
  if (num === null) return fallback;
  return num.toLocaleString('zh-CN', {
    maximumFractionDigits: digits,
    minimumFractionDigits: digits
  });
}

export function formatCompact(value: unknown, digits = 0, fallback = '--') {
  const num = toNumber(value);
  if (num === null) return fallback;
  return num.toLocaleString('zh-CN', {
    notation: Math.abs(num) >= 10000 ? 'compact' : 'standard',
    maximumFractionDigits: digits
  });
}

export function formatPercent(value: unknown, digits = 1) {
  const num = toNumber(value);
  if (num === null) return '--';
  return `${num.toFixed(digits)}%`;
}

export function statusClass(status?: string) {
  const value = String(status || 'info').toLowerCase();
  if (value.includes('high') || value.includes('danger') || value.includes('failed')) return 'danger';
  if (value.includes('medium') || value.includes('warning') || value.includes('pending')) return 'warning';
  if (value.includes('success') || value.includes('low') || value.includes('active')) return 'success';
  return 'info';
}

export function statusText(status?: string) {
  const value = statusClass(status);
  if (value === 'danger') return '高风险';
  if (value === 'warning') return '关注';
  if (value === 'success') return '正常';
  return '监控中';
}

export function timeText(value: unknown) {
  const text = String(value || '');
  if (!text) return '--';
  if (text.length >= 16) return text.slice(11, 16);
  return text;
}

export function dateTimeText(value: unknown) {
  const text = String(value || '');
  if (!text) return '--';
  return text.slice(0, 16);
}

export function sourceLabel(source?: string) {
  const value = source || 'unknown';
  const lower = value.toLowerCase();
  if (lower.includes('mock') || lower.includes('demo')) return `非生产数据：${value}`;
  if (lower.includes('derived')) return '计算指标';
  if (lower.includes('postgres')) return '业务数据';
  if (lower.includes('file')) return `文件数据：${value}`;
  return `数据源：${value}`;
}
