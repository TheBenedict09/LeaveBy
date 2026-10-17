export type Mode = "walk" | "bike" | "drive" | "train"

export interface Place {
  label: string
  lat: number
  lon: number
}

export interface GeocodeData {
  places: Place[]
}

export interface Weights {
  time: number
  cost: number
  carbon: number
  accessibility: number
}

export interface Constraints {
  step_free: boolean
  max_walk_m: number
  max_bike_m: number
  has_luggage: boolean
  has_car: boolean
}

export interface RecommendationRequest {
  origin: Place
  destination: Place
  arrive_by: string
  confidence: number
  weights?: Weights
  constraints?: Constraints
  options?: { simulate_incident?: boolean }
}

/** Any field left out keeps the value from the original request. */
export interface RescoreRequest {
  confidence?: number
  weights?: Weights
  constraints?: Constraints
}

export interface Headline {
  mode: Mode
  leave_at: string
  p_on_time: number
  on_time_scenarios: number
  total_scenarios: number
}

export interface Option {
  mode: Mode
  rank: number | null
  score: number | null
  feasible: boolean
  infeasible_reason: string | null
  leave_by: string | null
  p_on_time: number
  on_time_scenarios: number
  total_scenarios: number
  arrival: { p05: string; p50: string; p95: string }
  journey_at_risk_min: number
  cost_gbp: number
  co2e_kg: number
  accessibility: { feasible: boolean; score: number }
  cliff: { leave: string; p_on_time: number }[]
  scenario_arrivals: string[]
  provenance: string[]
  service?: TrainService | null
}

/** The real train behind a leave-by time, when the timetable covers the trip. */
export interface TrainService {
  depart_at: string
  arrive_at: string
  operator: string
  headsign: string
  from_station: string
  to_station: string
}

export interface Hedge {
  backup_mode: Mode
  leave_at: string
  p_both_late: number
  both_late_scenarios: number
  total_scenarios: number
  reason: string | null
}

export interface Explanation {
  mode: "template"
  because: string[]
  tradeoffs: string[]
  flip_points: string[]
}

export interface RecommendationData {
  recommendation_id: string
  headline: Headline | null
  options: Option[]
  hedge: Hedge | null
  explanation: Explanation
  traffic?: Traffic | null
  assumptions_ref: string
}

export interface Traffic {
  basis: "live" | "predicted" | "free-flow"
  car_min: number
  free_flow_min: number
  incidents: { count: number; worst_delay_min: number; description: string | null; simulated: boolean } | null
}

export interface Warning {
  code: string
  message: string
}

export interface SourceMeta {
  id: string
  kind: "live" | "static" | "mock" | "cached" | "estimated"
  fetched_at: string
  age_s: number
  latency_ms?: number | null
  licence: string
  attribution?: string | null
}

export interface Meta {
  request_id: string
  generated_at: string
  seed: number | null
  degraded: boolean
  warnings: Warning[]
  sources: SourceMeta[]
}

export interface ApiErrorBody {
  type: string
  title: string
  status: number
  code: string
  detail: string
  fields: { path: string; message: string }[]
}

export type Envelope<T> = { ok: true; data: T; meta: Meta } | { ok: false; error: ApiErrorBody; meta: Meta }

export interface ComposerValue {
  origin: Place
  destination: Place
  dayOffset: number
  time: string
  hasCar: boolean
  simulateIncident: boolean // demo only
}
