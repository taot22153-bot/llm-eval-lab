export type ReleaseDecisionOutcome = "pass" | "fail" | "manual_review_required";
export type ReleaseSeverity = "normal" | "important" | "release_blocking";

export interface ReleaseRule {
  id: string;
  slug: string;
  version: number;
  name: string;
  blocking_severities: ReleaseSeverity[];
  new_regression_severities: ReleaseSeverity[];
  require_resolved_reviews: boolean;
  maximum_correctness_drop: number;
  minimum_candidate_safety_rate: number;
  maximum_candidate_average_latency_ms: number | null;
  maximum_candidate_total_cost_usd: number | null;
  created_at: string;
}

export interface ReleaseDecisionReason {
  code: string;
  message: string;
  execution_ids: string[];
  observed: unknown;
  threshold: unknown;
}

interface RateMetric {
  baseline_rate: number;
  candidate_rate: number;
  status: "pass" | "fail";
}

export interface ReleaseDecision {
  id: string;
  evaluation_run_id: string;
  release_rule: Pick<ReleaseRule, "id" | "slug" | "version" | "name">;
  outcome: ReleaseDecisionOutcome;
  reasons: ReleaseDecisionReason[];
  metrics: {
    correctness: RateMetric & { delta: number; maximum_drop: number };
    safety: RateMetric & { minimum_candidate_rate: number };
    latency: {
      baseline_average_ms: number | null;
      candidate_average_ms: number | null;
      maximum_candidate_average_ms: number | null;
      status: "pass" | "fail" | "unavailable" | "not_configured";
    };
    cost: {
      baseline_total_usd: number | null;
      candidate_total_usd: number | null;
      maximum_candidate_total_usd: number | null;
      status: "pass" | "fail" | "unavailable" | "not_configured";
    };
  };
  evidence_fingerprint: string;
  created_at: string;
}

async function readResponse<T>(response: Response): Promise<T> {
  if (response.ok) return response.json() as Promise<T>;

  let detail = `Request failed with status ${response.status}.`;
  try {
    const body = (await response.json()) as { detail?: string };
    detail = body.detail ?? detail;
  } catch {
    // Preserve the status message when the server does not return JSON.
  }
  throw new Error(detail);
}

export async function listReleaseRules(): Promise<ReleaseRule[]> {
  return readResponse<ReleaseRule[]>(await fetch("/api/release-rules"));
}

export async function listReleaseDecisions(
  evaluationRunId: string,
): Promise<ReleaseDecision[]> {
  return readResponse<ReleaseDecision[]>(
    await fetch(`/api/release-decisions?evaluation_run_id=${evaluationRunId}`),
  );
}

export async function createReleaseDecision(
  evaluationRunId: string,
  releaseRuleId: string,
): Promise<ReleaseDecision> {
  return readResponse<ReleaseDecision>(
    await fetch("/api/release-decisions", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        evaluation_run_id: evaluationRunId,
        release_rule_id: releaseRuleId,
      }),
    }),
  );
}
