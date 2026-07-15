import { GroundingMaterial } from "./evaluationSuites";

export type ExecutionStatus = "pending" | "running" | "completed" | "failed";
export type DeterministicCheckType = "must_have_fact" | "forbidden_claim";
export type RegressionClassification = "new_regression" | "existing_failure";
export type SemanticOutcome = "pass" | "fail" | "insufficient_evidence";
export type HumanReviewReason =
  | "automatic_conflict"
  | "low_confidence"
  | "insufficient_evidence"
  | "test_case_requires_review"
  | "judge_failure";

export interface DeterministicCheckOutcome {
  check_type: DeterministicCheckType;
  position: number;
  rule: string;
  passed: boolean;
  matched_evidence: string | null;
}

export interface DeterministicEvaluation {
  scorer_version: string;
  passed: boolean;
  regression_classification: RegressionClassification | null;
  outcomes: DeterministicCheckOutcome[];
}

export interface SemanticEvaluation {
  judge_version: string;
  outcome: SemanticOutcome | null;
  rationale: string | null;
  confidence: number | null;
  judge_configuration: {
    judge_version: string;
    provider: string;
    model: string;
    generation_parameters: Record<string, unknown>;
    low_confidence_threshold: number;
  };
  error: { code: string; message: string } | null;
  created_at: string;
}

export interface HumanReviewItem {
  id: string;
  status: "pending" | "resolved";
  reasons: HumanReviewReason[];
  created_at: string;
  resolved_at: string | null;
}

export interface TestCaseExecution {
  id: string;
  application_version_id: string;
  application_version_name: string;
  test_case_id: string;
  test_case_key: string;
  test_case_title: string;
  test_case_severity: "normal" | "important" | "release_blocking";
  status: ExecutionStatus;
  prompt_context: {
    system_prompt: string;
    grounding_material: GroundingMaterial[];
    user_input: string;
  };
  model_response: string | null;
  usage: {
    prompt_tokens: number | null;
    completion_tokens: number | null;
    total_tokens: number | null;
  } | null;
  latency_ms: number | null;
  error: { code: string; message: string } | null;
  deterministic_evaluation: DeterministicEvaluation | null;
  semantic_evaluation: SemanticEvaluation | null;
  human_review_item: HumanReviewItem | null;
  created_at: string;
  started_at: string | null;
  completed_at: string | null;
}

async function readResponse<T>(response: Response): Promise<T> {
  if (response.ok) {
    return response.json() as Promise<T>;
  }

  let detail = `Request failed with status ${response.status}.`;
  try {
    const body = (await response.json()) as { detail?: string };
    detail = body.detail ?? detail;
  } catch {
    // The status message remains useful when the server does not return JSON.
  }
  throw new Error(detail);
}

export async function createTestCaseExecution(
  applicationVersionId: string,
  testCaseId: string,
): Promise<TestCaseExecution> {
  return readResponse<TestCaseExecution>(
    await fetch("/api/test-case-executions", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        application_version_id: applicationVersionId,
        test_case_id: testCaseId,
      }),
    }),
  );
}

export async function getTestCaseExecution(id: string): Promise<TestCaseExecution> {
  return readResponse<TestCaseExecution>(await fetch(`/api/test-case-executions/${id}`));
}
