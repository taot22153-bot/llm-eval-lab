import { TestCaseExecution } from "./testCaseExecutions";

export type EvaluationRunStatus = "pending" | "running" | "completed" | "failed";
export type VersionRole = "baseline" | "candidate";

export interface EvaluationRunExecution extends TestCaseExecution {
  version_role: VersionRole;
}

export interface EvaluationRun {
  id: string;
  baseline_version: { id: string; name: string };
  candidate_version: { id: string; name: string };
  evaluation_suite: { id: string; slug: string; version: number; name: string };
  status: EvaluationRunStatus;
  progress: {
    total: number;
    queued: number;
    running: number;
    completed: number;
    failed: number;
  };
  executions: EvaluationRunExecution[];
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

export async function listEvaluationRuns(): Promise<EvaluationRun[]> {
  return readResponse<EvaluationRun[]>(await fetch("/api/evaluation-runs?limit=1"));
}

export async function createEvaluationRun(
  baselineVersionId: string,
  candidateVersionId: string,
  evaluationSuiteId: string,
): Promise<EvaluationRun> {
  return readResponse<EvaluationRun>(
    await fetch("/api/evaluation-runs", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        baseline_version_id: baselineVersionId,
        candidate_version_id: candidateVersionId,
        evaluation_suite_id: evaluationSuiteId,
      }),
    }),
  );
}

export async function getEvaluationRun(id: string): Promise<EvaluationRun> {
  return readResponse<EvaluationRun>(await fetch(`/api/evaluation-runs/${id}`));
}
