export type JsonObject = Record<string, unknown>;

export interface ApplicationVersionDraft {
  name: string;
  model_provider: string;
  model_name: string;
  system_prompt: string;
  generation_parameters: JsonObject;
  knowledge_config: JsonObject | null;
  tool_config: JsonObject | null;
}

export interface ApplicationVersion extends ApplicationVersionDraft {
  id: string;
  created_at: string;
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

export async function listApplicationVersions(): Promise<ApplicationVersion[]> {
  return readResponse<ApplicationVersion[]>(await fetch("/api/application-versions"));
}

export async function createApplicationVersion(
  draft: ApplicationVersionDraft,
): Promise<ApplicationVersion> {
  const response = await fetch("/api/application-versions", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(draft),
  });
  return readResponse<ApplicationVersion>(response);
}
