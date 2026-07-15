import { FormEvent, useEffect, useState } from "react";
import {
  Box,
  Check,
  Clock3,
  GitCompareArrows,
  Layers3,
  ListChecks,
  Plus,
  Play,
  RefreshCw,
  ShieldCheck,
} from "lucide-react";

import EvaluationSuitesWorkspace from "./EvaluationSuitesWorkspace";
import EvaluationRunsWorkspace from "./EvaluationRunsWorkspace";
import TestExecutionWorkspace from "./TestExecutionWorkspace";
import {
  ApplicationVersion,
  ApplicationVersionDraft,
  JsonObject,
  createApplicationVersion,
  listApplicationVersions,
} from "./applicationVersions";
import "./styles.css";

interface FormState {
  name: string;
  modelProvider: string;
  modelName: string;
  systemPrompt: string;
  generationParameters: string;
  knowledgeConfig: string;
  toolConfig: string;
}

const initialForm: FormState = {
  name: "",
  modelProvider: "",
  modelName: "",
  systemPrompt: "",
  generationParameters: '{"temperature": 0.1}',
  knowledgeConfig: "",
  toolConfig: "",
};

function parseObject(value: string, label: string, optional = false): JsonObject | null {
  if (optional && !value.trim()) {
    return null;
  }

  let parsed: unknown;
  try {
    parsed = JSON.parse(value);
  } catch {
    throw new Error(`${label} must be valid JSON.`);
  }

  if (parsed === null || Array.isArray(parsed) || typeof parsed !== "object") {
    throw new Error(`${label} must be a JSON object.`);
  }
  return parsed as JsonObject;
}

function formatCreatedAt(value: string): string {
  return new Intl.DateTimeFormat(undefined, {
    dateStyle: "medium",
    timeStyle: "short",
  }).format(new Date(value));
}

function ConfigurationValue({
  label,
  value,
}: {
  label: string;
  value: JsonObject | null;
}) {
  return (
    <div className="configuration-value">
      <span>{label}</span>
      {value === null ? (
        <p>Not configured</p>
      ) : (
        <pre>{JSON.stringify(value, null, 2)}</pre>
      )}
    </div>
  );
}

function VersionCard({ version }: { version: ApplicationVersion }) {
  return (
    <article className="version-card">
      <div className="version-card__topline">
        <div>
          <h3>{version.name}</h3>
          <p className="model-name">{version.model_name}</p>
        </div>
        <span className="immutable-badge">
          <ShieldCheck aria-hidden="true" size={14} />
          Immutable
        </span>
      </div>

      <dl className="version-metadata">
        <div>
          <dt>Provider</dt>
          <dd>{version.model_provider}</dd>
        </div>
        <div>
          <dt>Created</dt>
          <dd>
            <Clock3 aria-hidden="true" size={14} />
            {formatCreatedAt(version.created_at)}
          </dd>
        </div>
      </dl>

      <div className="prompt-preview">
        <span>System prompt</span>
        <p>{version.system_prompt}</p>
      </div>

      <details>
        <summary>Configuration</summary>
        <div className="configuration-list">
          <ConfigurationValue
            label="Generation parameters"
            value={version.generation_parameters}
          />
          <ConfigurationValue label="Knowledge config" value={version.knowledge_config} />
          <ConfigurationValue label="Tool config" value={version.tool_config} />
        </div>
      </details>
    </article>
  );
}

export default function App() {
  const [workspace, setWorkspace] = useState<
    "versions" | "suites" | "execution" | "runs"
  >("versions");
  const [versions, setVersions] = useState<ApplicationVersion[]>([]);
  const [form, setForm] = useState<FormState>(initialForm);
  const [isLoading, setIsLoading] = useState(true);
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let active = true;
    listApplicationVersions()
      .then((loadedVersions) => {
        if (active) {
          setVersions(loadedVersions);
          setError(null);
        }
      })
      .catch((reason: unknown) => {
        if (active) {
          setError(reason instanceof Error ? reason.message : "Unable to load versions.");
        }
      })
      .finally(() => {
        if (active) {
          setIsLoading(false);
        }
      });

    return () => {
      active = false;
    };
  }, []);

  function updateField(field: keyof FormState, value: string) {
    setForm((current) => ({ ...current, [field]: value }));
  }

  async function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setError(null);

    let draft: ApplicationVersionDraft;
    try {
      draft = {
        name: form.name.trim(),
        model_provider: form.modelProvider.trim(),
        model_name: form.modelName.trim(),
        system_prompt: form.systemPrompt.trim(),
        generation_parameters: parseObject(
          form.generationParameters,
          "Generation parameters",
        ) as JsonObject,
        knowledge_config: parseObject(form.knowledgeConfig, "Knowledge config", true),
        tool_config: parseObject(form.toolConfig, "Tool config", true),
      };
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "Invalid configuration.");
      return;
    }

    setIsSubmitting(true);
    try {
      const created = await createApplicationVersion(draft);
      setVersions((current) => [created, ...current]);
      setForm(initialForm);
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "Unable to create version.");
    } finally {
      setIsSubmitting(false);
    }
  }

  return (
    <div className="app-shell">
      <header className="app-header">
        <a className="brand" href="/" aria-label="LLM Eval Lab home">
          <span className="brand-mark">
            <Box aria-hidden="true" size={19} />
          </span>
          <span>LLM Eval Lab</span>
        </a>
        <nav className="primary-navigation" aria-label="Primary">
          <button
            aria-current={workspace === "versions" ? "page" : undefined}
            type="button"
            onClick={() => setWorkspace("versions")}
          >
            <Layers3 aria-hidden="true" size={16} />
            Application Versions
          </button>
          <button
            aria-current={workspace === "suites" ? "page" : undefined}
            type="button"
            onClick={() => setWorkspace("suites")}
          >
            <ListChecks aria-hidden="true" size={16} />
            Evaluation Suites
          </button>
          <button
            aria-current={workspace === "execution" ? "page" : undefined}
            type="button"
            onClick={() => setWorkspace("execution")}
          >
            <Play aria-hidden="true" size={16} />
            Test Case Execution
          </button>
          <button
            aria-current={workspace === "runs" ? "page" : undefined}
            type="button"
            onClick={() => setWorkspace("runs")}
          >
            <GitCompareArrows aria-hidden="true" size={16} />
            Evaluation Runs
          </button>
        </nav>
        <div className="workspace-status">
          <span className="status-dot" />
          Local workspace
        </div>
      </header>

      <main>
        {workspace === "suites" ? <EvaluationSuitesWorkspace /> : null}
        {workspace === "execution" ? <TestExecutionWorkspace versions={versions} /> : null}
        {workspace === "runs" ? <EvaluationRunsWorkspace versions={versions} /> : null}
        {workspace === "versions" ? (
          <>
        <div className="page-heading">
          <div>
            <p className="eyebrow">Configuration registry</p>
            <h1>Application Versions</h1>
          </div>
          <span className="record-count">{versions.length} total</span>
        </div>

        {error ? (
          <div className="error-banner" role="alert">
            {error}
          </div>
        ) : null}

        <div className="workspace-grid">
          <section className="form-panel" aria-labelledby="create-version-heading">
            <div className="panel-heading">
              <Plus aria-hidden="true" size={18} />
              <h2 id="create-version-heading">Create version</h2>
            </div>

            <form onSubmit={handleSubmit}>
              <label>
                <span>Version name</span>
                <input
                  required
                  maxLength={120}
                  value={form.name}
                  onChange={(event) => updateField("name", event.target.value)}
                  placeholder="Store support baseline"
                />
              </label>

              <div className="field-row">
                <label>
                  <span>Model provider</span>
                  <input
                    required
                    maxLength={80}
                    value={form.modelProvider}
                    onChange={(event) => updateField("modelProvider", event.target.value)}
                    placeholder="ollama"
                  />
                </label>
                <label>
                  <span>Model name</span>
                  <input
                    required
                    maxLength={160}
                    value={form.modelName}
                    onChange={(event) => updateField("modelName", event.target.value)}
                    placeholder="qwen3:8b"
                  />
                </label>
              </div>

              <label>
                <span>System prompt</span>
                <textarea
                  required
                  rows={5}
                  value={form.systemPrompt}
                  onChange={(event) => updateField("systemPrompt", event.target.value)}
                />
              </label>

              <label>
                <span>Generation parameters (JSON)</span>
                <textarea
                  required
                  className="code-input"
                  rows={3}
                  value={form.generationParameters}
                  onChange={(event) => updateField("generationParameters", event.target.value)}
                  spellCheck={false}
                />
              </label>

              <details className="optional-config">
                <summary>Optional configuration</summary>
                <label>
                  <span>Knowledge config (JSON)</span>
                  <textarea
                    className="code-input"
                    rows={3}
                    value={form.knowledgeConfig}
                    onChange={(event) => updateField("knowledgeConfig", event.target.value)}
                    spellCheck={false}
                  />
                </label>
                <label>
                  <span>Tool config (JSON)</span>
                  <textarea
                    className="code-input"
                    rows={3}
                    value={form.toolConfig}
                    onChange={(event) => updateField("toolConfig", event.target.value)}
                    spellCheck={false}
                  />
                </label>
              </details>

              <button className="primary-button" type="submit" disabled={isSubmitting}>
                {isSubmitting ? (
                  <RefreshCw className="spin" aria-hidden="true" size={16} />
                ) : (
                  <Check aria-hidden="true" size={16} />
                )}
                {isSubmitting ? "Creating..." : "Create version"}
              </button>
            </form>
          </section>

          <section className="version-list" aria-label="Saved Application Versions">
            {isLoading ? <p className="empty-state">Loading Application Versions...</p> : null}
            {!isLoading && versions.length === 0 ? (
              <p className="empty-state">No Application Versions yet.</p>
            ) : null}
            {versions.map((version) => (
              <VersionCard key={version.id} version={version} />
            ))}
          </section>
        </div>
          </>
        ) : null}
      </main>
    </div>
  );
}
