import type {
  AnomalyResult,
  ExplanationResult,
  FusionResult,
  HealthResponse,
  PaginatedAssets,
  RecommendationResult,
  ResetResponse,
  RiskResult,
} from './types';

// Base URL for the FastAPI backend. The browser (host) talks to
// localhost:8000; override with VITE_API_URL for other environments.
export const API_BASE: string =
  import.meta.env.VITE_API_URL ?? 'http://localhost:8000';

export class ApiError extends Error {
  status: number;
  constructor(status: number, message: string) {
    super(message);
    this.name = 'ApiError';
    this.status = status;
  }
}

async function fetchJson<T>(path: string, init?: RequestInit): Promise<T> {
  const controller = new AbortController();
  const timer = window.setTimeout(() => controller.abort(), 120_000);
  let res: Response;
  try {
    res = await fetch(`${API_BASE}${path}`, {
      ...init,
      signal: controller.signal,
      headers: { 'Content-Type': 'application/json', ...(init?.headers ?? {}) },
    });
  } catch (err) {
    window.clearTimeout(timer);
    throw new ApiError(0, err instanceof Error ? err.message : 'Network error');
  }
  window.clearTimeout(timer);
  if (!res.ok) {
    let detail = res.statusText;
    try {
      const body = (await res.json()) as { detail?: string };
      if (typeof body.detail === 'string') detail = body.detail;
    } catch {
      // keep statusText
    }
    throw new ApiError(res.status, detail);
  }
  return (await res.json()) as T;
}

export function isNotFound(err: unknown): boolean {
  return err instanceof ApiError && err.status === 404;
}

export function isOffline(err: unknown): boolean {
  return err instanceof ApiError && err.status === 0;
}

export const api = {
  health: () => fetchJson<HealthResponse>('/api/health'),
  reset: () =>
    fetchJson<ResetResponse>('/api/demo/reset', { method: 'POST' }),
  assets: (page = 1, pageSize = 100, status?: string) =>
    fetchJson<PaginatedAssets>(
      `/api/assets?page=${page}&page_size=${pageSize}${status ? `&status=${status}` : ''}`,
    ),
  fusion: (assetId: string) =>
    fetchJson<FusionResult>(`/api/assets/${encodeURIComponent(assetId)}/fusion`),
  risk: (assetId: string) =>
    fetchJson<RiskResult>(`/api/assets/${encodeURIComponent(assetId)}/risk`),
  explanation: (assetId: string) =>
    fetchJson<ExplanationResult>(
      `/api/assets/${encodeURIComponent(assetId)}/explanation`,
    ),
  recommendations: (assetId: string) =>
    fetchJson<RecommendationResult>(
      `/api/assets/${encodeURIComponent(assetId)}/recommendations`,
    ),
  // NOTE: the anomaly endpoint requires the asset UUID (not the code).
  anomaly: (assetUuid: string) =>
    fetchJson<AnomalyResult>(
      `/api/assets/${encodeURIComponent(assetUuid)}/anomaly`,
    ),
};
