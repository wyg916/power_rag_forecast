const fieldLabels: Record<string, string> = {
  action: '建议动作',
  category: '类别',
  code: '编码',
  end: '结束',
  hours: '时段',
  label: '名称',
  level: '等级',
  message: '说明',
  name: '名称',
  period: '时段',
  priority: '优先级',
  reason: '原因',
  risk_level: '风险等级',
  start: '开始',
  status: '状态',
  type: '类型',
  value: '值'
};

function scalar(value: unknown) {
  if (value === null || value === undefined || value === '') return '--';
  if (typeof value === 'boolean') return value ? '是' : '否';
  if (typeof value === 'string' || typeof value === 'number' || typeof value === 'bigint') return String(value);
  return '';
}

function labelFor(key: string) {
  return fieldLabels[key] || key.replace(/_/g, ' ');
}

export function pickReportScalar(value: unknown, preferredKeys: string[] = []): string {
  const direct = scalar(value);
  if (direct) return direct;
  if (Array.isArray(value)) {
    const items = value.map((item) => pickReportScalar(item, preferredKeys)).filter((item) => item && item !== '--');
    return items.length ? items.join('、') : '--';
  }
  if (value && typeof value === 'object') {
    const record = value as Record<string, unknown>;
    for (const key of preferredKeys) {
      const selected = scalar(record[key]);
      if (selected) return selected;
    }
    for (const item of Object.values(record)) {
      const selected = scalar(item);
      if (selected) return selected;
    }
  }
  return '--';
}

export function formatReportValueLines(value: unknown, depth = 0): string[] {
  const direct = scalar(value);
  if (direct) return [direct];
  if (depth >= 3) return ['--'];
  if (Array.isArray(value)) {
    if (!value.length) return ['--'];
    return value.flatMap((item, index) =>
      formatReportValueLines(item, depth + 1).map((line) => value.length > 1 ? `第 ${index + 1} 项：${line}` : line)
    );
  }
  if (value && typeof value === 'object') {
    const entries = Object.entries(value as Record<string, unknown>);
    if (!entries.length) return ['--'];
    return entries.flatMap(([key, item]) => {
      const lines = formatReportValueLines(item, depth + 1);
      return lines.map((line, index) => `${index === 0 ? `${labelFor(key)}：` : '　'}${line}`);
    });
  }
  return ['--'];
}
