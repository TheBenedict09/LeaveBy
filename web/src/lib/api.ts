import type {
  Envelope,
  GeocodeData,
  Meta,
  RecommendationData,
  RecommendationRequest,
  RescoreRequest,
} from "@/lib/types"

export class ApiFailure extends Error {
  code: string

  constructor(message: string, code: string) {
    super(message)
    this.code = code
  }
}

async function call<T>(path: string, init?: RequestInit): Promise<{ data: T; meta: Meta }> {
  let res: Response
  try {
    // 20 s covers a cold forecast and routing fetch; longer means something upstream is stuck
    res = await fetch(path, {
      headers: { "content-type": "application/json" },
      signal: AbortSignal.timeout(20_000),
      ...init,
    })
  } catch (e) {
    if (e instanceof DOMException && e.name === "TimeoutError")
      throw new ApiFailure("The LeaveBy API took too long to answer.", "TIMEOUT")
    throw new ApiFailure("Can't reach the LeaveBy API. Is it running?", "NETWORK")
  }
  const body = (await res.json().catch(() => null)) as Envelope<T> | null
  if (!body) throw new ApiFailure(`Unexpected response from the API (${res.status})`, "BAD_RESPONSE")
  if (!body.ok) throw new ApiFailure(body.error.detail, body.error.code)
  return { data: body.data, meta: body.meta }
}

export function createRecommendation(req: RecommendationRequest) {
  return call<RecommendationData>("/v1/recommendations", { method: "POST", body: JSON.stringify(req) })
}

/** Re-decide a stored recommendation with new settings. No weather or routing call is made. */
export function rescore(id: string, req: RescoreRequest) {
  return call<RecommendationData>(`/v1/recommendations/${encodeURIComponent(id)}/rescore`, {
    method: "POST",
    body: JSON.stringify(req),
  })
}

/** Place search. Falls back to a built-in UK list on the server when the geocoder is down (meta.degraded). */
export function searchPlaces(q: string, limit: number) {
  return call<GeocodeData>(`/v1/geocode?${new URLSearchParams({ q, limit: String(limit) })}`)
}

export interface SourceInfo {
  id: string
  kind: string
  role: string
  licence: string
  attribution?: string | null
}

export function getSources() {
  return call<{ sources: SourceInfo[] }>("/v1/sources")
}

/** The parts of /v1/assumptions the UI reads (the endpoint serves every coefficient). */
export interface Assumptions {
  model: {
    noise: { n_draws: number }
    rail: { station_radius_m: number; calm_within_5min_target: number; calm_target_sources: string[] }
    emissions: { source: string }
  }
  rail_timetable: { source: string; release: string; valid_from: string; valid_to: string } | null
}

export function getAssumptions() {
  return call<Assumptions>("/v1/assumptions")
}
