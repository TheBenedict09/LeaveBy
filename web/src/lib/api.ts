import type { Envelope, Meta, RecommendationData, RecommendationRequest, RescoreRequest } from "@/lib/types"

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
    res = await fetch(path, { headers: { "content-type": "application/json" }, ...init })
  } catch {
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
