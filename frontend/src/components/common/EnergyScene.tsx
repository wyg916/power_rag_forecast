import { VerifiedOutlined } from '@ant-design/icons';
import energyScene from '../../assets/hero/energy-3d-scene.png';

interface EnergyMetric {
  label: string;
  value: string;
}

export function EnergyScene({ metrics = [] }: { metrics?: EnergyMetric[] }) {
  return (
    <div className="energy-scene">
      <img src={energyScene} alt="新能源系统主视觉" />
      <div className="scene-title">
        <h3>能源系统全景</h3>
        <p>预测、风险、策略与任务状态统一监控</p>
      </div>
      {metrics.length > 0 && (
        <div className="scene-bottom">
          {metrics.map((item) => (
          <div key={item.label} className="scene-bottom-item">
            <VerifiedOutlined />
            <span>{item.label}</span>
            <strong>{item.value}</strong>
          </div>
          ))}
        </div>
      )}
    </div>
  );
}
