import { api } from '../api';

export interface ModelVersionRow {
  model_version: string;
  model_name?: string;
  model_type?: string;
  status?: string;
  is_active?: boolean;
  created_at?: string;
  updated_at?: string;
  mae?: number;
  rmse?: number;
  mape?: number;
  peak_error?: number;
  sample_count?: number;
  validated_at?: string;
  activation_eligible?: boolean;
  rollback_eligible?: boolean;
}

export interface ModelCenterOverview {
  available: boolean;
  seed_available?: boolean;
  filters: Record<string, unknown>;
  active: ModelVersionRow;
  candidate: ModelVersionRow;
  versions: ModelVersionRow[];
  effect: Array<{ time: string; actual: number; active: number; candidate: number; diff: number; data_origin?: string }>;
  error_trend: Array<{ date: string; mae: number; rmse: number; mape: number }>;
  admission: {
    rules: Array<{ label: string; passed: boolean; detail: string }>;
    passed: boolean;
    conclusion: string;
  };
  evaluation_summary: Array<{ metric: string; active: number; candidate: number; improvement: number }>;
  training: Record<string, any>;
  rollback: { default_version?: string; options: Array<{ model_version: string; label: string }> };
  events: Array<Record<string, any>>;
  data_lineage?: Record<string, unknown>;
}

export interface ModelVersionDetail {
  available: boolean;
  message?: string;
  version: ModelVersionRow & { metrics?: Record<string, any>; artifact_path?: string };
  latest_metric: Record<string, any>;
  metrics_history: Array<Record<string, any>>;
  events: Array<Record<string, any>>;
  prediction_samples: Array<Record<string, any>>;
  data_lineage?: Record<string, unknown>;
}

export async function getModelCenterData(params: Record<string, any> = {}) {
  return api.modelCenterOverview(params) as Promise<ModelCenterOverview>;
}

export async function getModelVersionDetail(version: string) {
  return api.modelCenterVersionDetail(version) as Promise<ModelVersionDetail>;
}

export async function startModelTraining(payload: Record<string, any>) {
  return api.modelTrainingStart(payload);
}

export async function activateModel(version: string, reason: string) {
  return api.modelActivate({ version, reason });
}

export async function rollbackModel(version: string, reason: string) {
  return api.modelRollback({ version, reason });
}

export async function exportModelCenterReport() {
  return api.modelCenterExport();
}

export async function getModelTrainingLogs(taskId: string) {
  return api.taskLogs(taskId, 1, 80);
}
