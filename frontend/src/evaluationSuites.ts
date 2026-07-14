export type TestCaseType = "normal" | "hallucination" | "prompt_injection" | "jailbreak";
export type Severity = "normal" | "important" | "release_blocking";

export interface GroundingMaterial {
  kind: "product" | "shipping" | "return" | "warranty";
  title: string;
  content: string;
}

export interface EvaluationTestCase {
  id: string;
  key: string;
  position: number;
  title: string;
  user_input: string;
  grounding_material: GroundingMaterial[];
  must_have_facts: string[];
  forbidden_claims: string[];
  test_type: TestCaseType;
  severity: Severity;
  requires_human_review: boolean;
}

export interface EvaluationSuiteSummary {
  id: string;
  slug: string;
  version: number;
  name: string;
  description: string;
  test_case_count: number;
}

export interface EvaluationSuiteDetail extends EvaluationSuiteSummary {
  test_cases: EvaluationTestCase[];
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

export async function listEvaluationSuites(): Promise<EvaluationSuiteSummary[]> {
  return readResponse<EvaluationSuiteSummary[]>(await fetch("/api/evaluation-suites"));
}

export async function getEvaluationSuite(id: string): Promise<EvaluationSuiteDetail> {
  return readResponse<EvaluationSuiteDetail>(await fetch(`/api/evaluation-suites/${id}`));
}
