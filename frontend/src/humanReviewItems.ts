import { HumanReviewReason } from "./testCaseExecutions";

export interface HumanReviewQueueItem {
  id: string;
  test_case_execution_id: string;
  test_case_title: string;
  application_version_name: string;
  evaluation_run_id: string | null;
  version_role: "baseline" | "candidate" | null;
  status: "pending" | "resolved";
  reasons: HumanReviewReason[];
  created_at: string;
  resolved_at: string | null;
}

async function readResponse<T>(response: Response): Promise<T> {
  if (response.ok) return response.json() as Promise<T>;
  throw new Error(`Unable to load Human Review queue (status ${response.status}).`);
}

export async function listHumanReviewItems(): Promise<HumanReviewQueueItem[]> {
  return readResponse<HumanReviewQueueItem[]>(
    await fetch("/api/human-review-items?status=pending&limit=100"),
  );
}
