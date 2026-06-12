export function currency(value: number) {
  return `￥${value.toLocaleString('zh-CN', { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`;
}

export function percent(value: number) {
  return `${value.toFixed(2)}%`;
}

export function fixed(value: number, digits = 4) {
  return value.toFixed(digits);
}
