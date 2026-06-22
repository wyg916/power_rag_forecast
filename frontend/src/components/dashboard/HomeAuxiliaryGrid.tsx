import { CheckCircleOutlined, DatabaseOutlined, ThunderboltOutlined } from '@ant-design/icons';
import { Empty, Progress, Table, Tag } from 'antd';
import type { ColumnsType } from 'antd/es/table';
import { HomeSourceTag } from './HomeDataState';
import { dateTimeText, formatNumber, formatPercent, timeText } from './utils';

function predictionRows(forecast?: any) {
  const summary = forecast?.summary || {};
  return [
    { key: 'max', metric: '最高价', value: summary.max_price, compare: summary.max_hour, trend: '高风险复核窗口' },
    { key: 'min', metric: '最低价', value: summary.min_price, compare: summary.min_hour, trend: '低价采购/充电窗口' },
    { key: 'avg', metric: '均价', value: summary.avg_price, compare: `${summary.record_count || 0} 条`, trend: '24小时预测均值' },
    { key: 'spread', metric: '峰谷价差', value: summary.peak_valley_spread, compare: `${summary.high_risk_hours || 0} 高风险`, trend: '策略收益候选空间' }
  ];
}

export function HomeAuxiliaryGrid({ forecast, kpi }: { forecast?: any; kpi?: any }) {
  const context = kpi?.context || {};
  const confidence = context.forecast_confidence || {};
  const model = confidence.model || {};
  const dataHealth = context.data_health || {};
  const dataScore = Number(dataHealth.score || 0);
  const columns: ColumnsType<any> = [
    { title: '指标', dataIndex: 'metric', width: 110 },
    { title: '当前值', dataIndex: 'value', align: 'right', render: (value) => `${formatNumber(value, 3)} 元/kWh` },
    { title: '时段/样本', dataIndex: 'compare', render: (value) => String(value || '').includes('-') ? dateTimeText(value) : timeText(value) },
    { title: '趋势含义', dataIndex: 'trend' }
  ];
  const sources = dataHealth.sources || [];
  return (
    <section className="home-aux-grid">
      <div className="home-card home-table-card">
        <div className="home-card-head compact">
          <div>
            <h2>关键预测指标趋势（24小时）</h2>
            <p>全部指标来自 /api/forecast/24h 汇总，不使用模拟数据。</p>
          </div>
          <HomeSourceTag source={forecast?.data_source} />
        </div>
        <Table
          size="small"
          pagination={false}
          rowKey="key"
          columns={columns}
          dataSource={predictionRows(forecast)}
        />
      </div>

      <div className="home-card home-model-card">
        <div className="home-card-head compact">
          <div>
            <h2><ThunderboltOutlined /> 模型状态</h2>
            <p>Active 模型与评估指标</p>
          </div>
          <Tag color={model?.model_version ? 'success' : 'warning'}>{model?.model_version ? 'Active' : '待接入'}</Tag>
        </div>
        {model?.model_version ? (
          <div className="home-model-list">
            <div><span>模型版本</span><strong>{model.model_version}</strong></div>
            <div><span>MAE</span><strong>{formatNumber(confidence.mae, 4)}</strong></div>
            <div><span>RMSE</span><strong>{formatNumber(confidence.rmse, 4)}</strong></div>
            <div><span>最近激活</span><strong>{dateTimeText(model.activated_at || model.created_at)}</strong></div>
          </div>
        ) : (
          <Empty image={Empty.PRESENTED_IMAGE_SIMPLE} description="模型注册信息不足，保留待接入态" />
        )}
      </div>

      <div className="home-card home-health-card">
        <div className="home-card-head compact">
          <div>
            <h2><DatabaseOutlined /> 数据健康</h2>
            <p>来源覆盖、异常源和缺失率</p>
          </div>
          <HomeSourceTag source={dataHealth.data_source} />
        </div>
        {dataHealth.score == null ? (
          <Empty image={Empty.PRESENTED_IMAGE_SIMPLE} description="暂无数据健康评分" />
        ) : (
          <div className="home-health-body">
            <Progress type="circle" percent={Math.round(dataScore)} strokeColor="#00B894" size={96} />
            <div className="home-health-list">
              <p><CheckCircleOutlined /> 数据源覆盖 <strong>{dataHealth.source_count || 0}</strong></p>
              <p>异常数据源 <strong>{dataHealth.exception_count || 0}</strong></p>
              <p>健康得分 <strong>{formatPercent(dataHealth.score)}</strong></p>
            </div>
          </div>
        )}
        <div className="home-source-mini-list">
          {sources.slice(0, 4).map((item: any) => (
            <span key={item.name}>{item.name}: {item.status || '--'}</span>
          ))}
        </div>
      </div>
    </section>
  );
}
