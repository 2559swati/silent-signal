// Backend response shapes (mirror backend Pydantic schemas). No dummy data.

export type Phase2Status = 'healthy' | 'watch' | 'emerging' | 'critical';
export type FusionStatus = 'NORMAL' | 'WATCH' | 'EMERGING' | 'CRITICAL';
export type RiskLevel = 'LOW' | 'MEDIUM' | 'HIGH' | 'CRITICAL';
export type Severity = 'low' | 'medium' | 'high' | 'critical';

export interface Asset {
  id: string;
  external_code: string;
  criticality: number;
  public_exposure: number;
  status: Phase2Status;
}

export interface PaginatedAssets {
  total: number;
  page: number;
  page_size: number;
  items: Asset[];
}

export interface FusionResult {
  asset_id: string;
  asset_external_code: string;
  day: string;
  power_score: number;
  brightness_score: number;
  temperature_score: number;
  maintenance_score: number;
  neighbor_score: number;
  fusion_score: number;
  smoothed_fusion_score: number;
  status: FusionStatus;
  model_version: string;
}

export interface RiskResult {
  asset_id: string;
  asset_external_code: string;
  day: string;
  anomaly_score: number;
  fusion_score: number;
  smoothed_fusion_score: number;
  persistence_score: number;
  risk_score: number;
  risk_level: RiskLevel;
  model_version: string;
}

export interface ExplanationFactor {
  signal: string;
  score: number;
  severity: Severity;
  reason: string;
}

export interface ExplanationResult {
  asset_id: string;
  asset_external_code: string;
  day: string;
  risk_score: number;
  risk_level: RiskLevel;
  summary: string;
  factors: ExplanationFactor[];
  evidence: Record<string, unknown>;
  model_version: string;
}

export interface RecommendationItem {
  action: string;
  reason: string;
  evidence: Record<string, unknown>;
}

export interface RecommendationResult {
  asset_id: string;
  asset_external_code: string;
  day: string;
  risk_score: number;
  risk_level: RiskLevel;
  priority: string;
  urgency: string;
  recommendations: RecommendationItem[];
  evidence: Record<string, unknown>;
  model_version: string;
}

export interface AnomalyResult {
  id: string;
  asset_id: string;
  scored_at: string;
  score: number;
  model_version: string;
}

export interface HealthResponse {
  status: string;
}

export interface ResetResponse {
  status: string;
  assets: number;
  sensor_readings: number;
  maintenance_records: number;
}
