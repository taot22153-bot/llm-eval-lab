import { useEffect, useState } from "react";
import { AlertTriangle, CheckCircle2, Clock3, Play, RefreshCw } from "lucide-react";

import { ApplicationVersion } from "./applicationVersions";
import ExecutionAssessment from "./ExecutionAssessment";
import {
  EvaluationSuiteDetail,
  EvaluationSuiteSummary,
  getEvaluationSuite,
  listEvaluationSuites,
} from "./evaluationSuites";
import {
  TestCaseExecution,
  createTestCaseExecution,
  getTestCaseExecution,
} from "./testCaseExecutions";
import { formatCostUsd } from "./runtimeMetrics";

const POLL_INTERVAL_MS = 400;

function waitForNextPoll(): Promise<void> {
  return new Promise((resolve) => window.setTimeout(resolve, POLL_INTERVAL_MS));
}

function statusLabel(status: TestCaseExecution["status"]): string {
  return status.charAt(0).toUpperCase() + status.slice(1);
}

function tokenUsageLabel(usage: TestCaseExecution["usage"]): string {
  if (usage === null) return "Unknown";
  return [
    `Prompt ${usage.prompt_tokens ?? "Unknown"}`,
    `Completion ${usage.completion_tokens ?? "Unknown"}`,
    `Total ${usage.total_tokens ?? "Unknown"}`,
  ].join(" · ");
}

function ExecutionResult({ execution }: { execution: TestCaseExecution }) {
  const isActive = execution.status === "pending" || execution.status === "running";

  return (
    <section className={`execution-result execution-result--${execution.status}`}>
      <div className="execution-result__heading">
        <div>
          <p className="eyebrow">Persisted execution</p>
          <h2>{execution.test_case_title}</h2>
        </div>
        <span className="execution-status">
          {isActive ? <RefreshCw className="spin" aria-hidden="true" size={15} /> : null}
          {execution.status === "completed" ? (
            <CheckCircle2 aria-hidden="true" size={15} />
          ) : null}
          {execution.status === "failed" ? (
            <AlertTriangle aria-hidden="true" size={15} />
          ) : null}
          {statusLabel(execution.status)}
        </span>
      </div>

      {execution.model_response ? (
        <div className="model-response">
          <span>Model response</span>
          <p>{execution.model_response}</p>
        </div>
      ) : null}

      {execution.error ? (
        <div className="error-banner" role="alert">
          <strong>{execution.error.code}</strong>{" "}
          {execution.error.message}
        </div>
      ) : null}

      <ExecutionAssessment execution={execution} />

      <dl className="execution-metrics">
        <div>
          <dt>Application Version</dt>
          <dd>{execution.application_version_name}</dd>
        </div>
        <div>
          <dt>Latency</dt>
          <dd>
            <Clock3 aria-hidden="true" size={14} />
            {execution.latency_ms === null ? "Pending" : `${execution.latency_ms} ms`}
          </dd>
        </div>
        <div>
          <dt>Usage</dt>
          <dd>{tokenUsageLabel(execution.usage)}</dd>
        </div>
        <div>
          <dt>Cost</dt>
          <dd>{formatCostUsd(execution.usage?.cost_usd)}</dd>
        </div>
      </dl>
    </section>
  );
}

export default function TestExecutionWorkspace({
  versions,
}: {
  versions: ApplicationVersion[];
}) {
  const [suites, setSuites] = useState<EvaluationSuiteSummary[]>([]);
  const [suite, setSuite] = useState<EvaluationSuiteDetail | null>(null);
  const [applicationVersionId, setApplicationVersionId] = useState(versions[0]?.id ?? "");
  const [testCaseId, setTestCaseId] = useState("");
  const [execution, setExecution] = useState<TestCaseExecution | null>(null);
  const [isLoading, setIsLoading] = useState(true);
  const [isRunning, setIsRunning] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (versions.length === 0) {
      setApplicationVersionId("");
      return;
    }
    if (!versions.some((version) => version.id === applicationVersionId)) {
      setApplicationVersionId(versions[0].id);
    }
  }, [applicationVersionId, versions]);

  useEffect(() => {
    let active = true;
    listEvaluationSuites()
      .then(async (loadedSuites) => {
        if (!active) return;
        setSuites(loadedSuites);
        if (loadedSuites.length > 0) {
          const detail = await getEvaluationSuite(loadedSuites[0].id);
          if (active) {
            setSuite(detail);
            setTestCaseId(detail.test_cases[0]?.id ?? "");
          }
        }
      })
      .catch((reason: unknown) => {
        if (active) {
          setError(reason instanceof Error ? reason.message : "Unable to load Test Cases.");
        }
      })
      .finally(() => {
        if (active) setIsLoading(false);
      });

    return () => {
      active = false;
    };
  }, []);

  async function selectSuite(suiteId: string) {
    setError(null);
    setExecution(null);
    try {
      const detail = await getEvaluationSuite(suiteId);
      setSuite(detail);
      setTestCaseId(detail.test_cases[0]?.id ?? "");
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "Unable to load the Evaluation Suite.");
    }
  }

  async function runTestCase() {
    if (!applicationVersionId || !testCaseId) return;
    setIsRunning(true);
    setError(null);
    try {
      let current = await createTestCaseExecution(applicationVersionId, testCaseId);
      setExecution(current);
      while (current.status === "pending" || current.status === "running") {
        current = await getTestCaseExecution(current.id);
        setExecution(current);
        if (current.status === "pending" || current.status === "running") {
          await waitForNextPoll();
        }
      }
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "Unable to run the Test Case.");
    } finally {
      setIsRunning(false);
    }
  }

  return (
    <>
      <div className="page-heading">
        <div>
          <p className="eyebrow">Provider-neutral execution</p>
          <h1>Run one Test Case</h1>
        </div>
      </div>

      {error ? <div className="error-banner" role="alert">{error}</div> : null}

      <div className="execution-workspace">
        <section className="execution-form" aria-label="Test Case execution controls">
          <label>
            <span>Application Version</span>
            <select
              value={applicationVersionId}
              onChange={(event) => setApplicationVersionId(event.target.value)}
            >
              {versions.map((version) => (
                <option key={version.id} value={version.id}>{version.name}</option>
              ))}
            </select>
          </label>

          <label>
            <span>Evaluation Suite</span>
            <select
              disabled={isLoading}
              value={suite?.id ?? ""}
              onChange={(event) => void selectSuite(event.target.value)}
            >
              {suites.map((item) => (
                <option key={item.id} value={item.id}>{item.name} v{item.version}</option>
              ))}
            </select>
          </label>

          <label>
            <span>Test Case</span>
            <select
              disabled={!suite}
              value={testCaseId}
              onChange={(event) => setTestCaseId(event.target.value)}
            >
              {suite?.test_cases.map((testCase) => (
                <option key={testCase.id} value={testCase.id}>{testCase.title}</option>
              ))}
            </select>
          </label>

          <button
            className="primary-button"
            type="button"
            disabled={isRunning || !applicationVersionId || !testCaseId}
            onClick={() => void runTestCase()}
          >
            {isRunning ? (
              <RefreshCw className="spin" aria-hidden="true" size={16} />
            ) : (
              <Play aria-hidden="true" size={16} />
            )}
            {isRunning ? "Running..." : "Run Test Case"}
          </button>
        </section>

        {versions.length === 0 ? (
          <p className="empty-state">Create an Application Version before running a Test Case.</p>
        ) : null}
        {execution ? <ExecutionResult execution={execution} /> : null}
        {!execution && versions.length > 0 ? (
          <p className="empty-state">Select evidence and run one Test Case.</p>
        ) : null}
      </div>
    </>
  );
}
