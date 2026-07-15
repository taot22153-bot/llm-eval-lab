import { HumanReviewReason, TestCaseExecution } from "./testCaseExecutions";

export interface HumanReviewQueueItem {
  id: string;
  test_case_execution_id: string;
  test_case_title: string;
  application_version_name: string;
  evaluation_run_id: string | null;
  version_role: "baseline" | "candidate" | null;
  status: "pending" | "resolved";
  reasons: HumanReviewReason[];
  outcome: "pass" | "fail" | null;
  rationale: string | null;
  created_at: string;
  resolved_at: string | null;
}

export interface HumanReviewDetail extends HumanReviewQueueItem {
  execution: TestCaseExecution;
}

async function readResponse<T>(response: Response): Promise<T> {
  if (response.ok) return response.json() as Promise<T>;

  let detail = `Human Review request failed with status ${response.status}.`;
  try {
    const body = (await response.json()) as { detail?: string };
    detail = body.detail ?? detail;
  } catch {
    // The status message remains useful when the server does not return JSON.
  }
  throw new Error(detail);
}

export async function listHumanReviewItems(
  status: "pending" | "resolved" = "pending",
): Promise<HumanReviewQueueItem[]> {
  return readResponse<HumanReviewQueueItem[]>(
    await fetch(`/api/human-review-items?status=${status}&limit=100`),
  );
}

export async function getHumanReviewItem(id: string): Promise<HumanReviewDetail> {
  return readResponse<HumanReviewDetail>(await fetch(`/api/human-review-items/${id}`));
}

export async function resolveHumanReviewItem(
  id: string,
  outcome: "pass" | "fail",
  rationale: string,
): Promise<HumanReviewDetail> {
  return readResponse<HumanReviewDetail>(
    await fetch(`/api/human-review-items/${id}`, {
      method: "PATCH",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ outcome, rationale }),
    }),
  );
}
