import { useEffect, useState } from "react";
import { AlertTriangle, CheckCircle2, Play, RefreshCw } from "lucide-react";

import { ApplicationVersion } from "./applicationVersions";
import ExecutionAssessment, { reviewReasonLabel } from "./ExecutionAssessment";
import { EvaluationSuiteSummary, listEvaluationSuites } from "./evaluationSuites";
import { HumanReviewQueueItem, listHumanReviewItems } from "./humanReviewItems";
import {
  EvaluationRun,
  EvaluationRunExecution,
  VersionDeterministicSummary,
  VersionRole,
  createEvaluationRun,
  getEvaluationRun,
  listEvaluationRuns,
} from "./evaluationRuns";

const POLL_INTERVAL_MS = 400;

function waitForNextPoll(): Promise<void> {
  return new Promise((resolve) => window.setTimeout(resolve, POLL_INTERVAL_MS));
}

function SeverityFailures({ summary }: { summary: VersionDeterministicSummary }) {
  return (
    <>
      <span>Normal: {summary.severity_failures.normal}</span>
      <span>Important: {summary.severity_failures.important}</span>
      <span>Release blocking: {summary.severity_failures.release_blocking}</span>
    </>
  );
}

function severityLabel(severity: EvaluationRunExecution["test_case_severity"]): string {
  return severity === "release_blocking"
    ? "Release blocking"
    : severity[0].toUpperCase() + severity.slice(1);
}

function ExecutionEvidence({ execution }: { execution: EvaluationRunExecution }) {
  return (
    <article className={`comparison-evidence comparison-evidence--${execution.status}`}>
      <div className="comparison-evidence__heading">
        <strong>{execution.test_case_title}</strong>
        <span>{execution.status}</span>
      </div>
      <p className="test-case-severity">
        Severity: {severityLabel(execution.test_case_severity)}
      </p>
      {execution.model_response ? <p>{execution.model_response}</p> : null}
      <ExecutionAssessment execution={execution} />
      {execution.error ? (
        <div className="comparison-error">
          <strong>{execution.error.code}</strong>
          <p>{execution.error.message}</p>
        </div>
      ) : null}
      {!execution.model_response && !execution.error ? (
        <p className="comparison-evidence__waiting">Waiting for persisted evidence.</p>
      ) : null}
    </article>
  );
}

function HumanReviewQueue({ items }: { items: HumanReviewQueueItem[] }) {
  if (items.length === 0) return null;
  return (
    <section className="human-review-queue" aria-label="Human Review queue">
      <div className="human-review-queue__heading">
        <div>
          <p className="eyebrow">Automatic evidence needs a person</p>
          <h3>Human Review queue</h3>
        </div>
        <strong>{items.length} unresolved</strong>
      </div>
      <ul>
        {items.map((item) => (
          <li key={item.id}>
            <div>
              <strong>{item.test_case_title}</strong>
              <span>{item.version_role ?? "single execution"}</span>
            </div>
            <p>{item.application_version_name}</p>
            <p>{item.reasons.map(reviewReasonLabel).join(" | ")}</p>
          </li>
        ))}
      </ul>
    </section>
  );
}

function VersionScoreSummary({
  label,
  summary,
}: {
  label: string;
  summary: VersionDeterministicSummary;
}) {
  return (
    <article className="score-summary-card">
      <div className="score-summary-card__heading">
        <strong>{label}</strong>
        <span>{summary.passed_test_cases}/{summary.scored_test_cases} test cases passed</span>
      </div>
      <dl>
        <div>
          <dt>Correctness</dt>
          <dd>{summary.correctness.passed}/{summary.correctness.total}</dd>
        </div>
        <div>
          <dt>Safety</dt>
          <dd>{summary.safety.passed}/{summary.safety.total}</dd>
        </div>
        <div>
          <dt>Failed test cases</dt>
          <dd>{summary.failed_test_cases}</dd>
        </div>
      </dl>
      <p className="severity-summary"><SeverityFailures summary={summary} /></p>
    </article>
  );
}

function VersionEvidence({ run, role }: { run: EvaluationRun; role: VersionRole }) {
  const version = role === "baseline" ? run.baseline_version : run.candidate_version;
  const summary = run.deterministic_summary[role];
  const executions = run.executions.filter((execution) => execution.version_role === role);
  return (
    <section className="comparison-column" aria-label={`${role} evidence`}>
      <p className="eyebrow">{role}</p>
      <h2>{version.name}</h2>
      <p className="comparison-column__severity"><SeverityFailures summary={summary} /></p>
      <div className="comparison-evidence-list">
        {executions.map((execution) => (
          <ExecutionEvidence key={execution.id} execution={execution} />
        ))}
      </div>
    </section>
  );
}

function EvaluationRunResult({
  run,
  reviewItems,
}: {
  run: EvaluationRun;
  reviewItems: HumanReviewQueueItem[];
}) {
  const progress = [
    ["Total", run.progress.total],
    ["Queued", run.progress.queued],
    ["Running", run.progress.running],
    ["Completed", run.progress.completed],
    ["Failed", run.progress.failed],
  ] as const;
  return (
    <section className="comparison-result">
      <div className="comparison-result__heading">
        <div>
          <p className="eyebrow">Latest persisted run</p>
          <h2>{run.evaluation_suite.name} v{run.evaluation_suite.version}</h2>
        </div>
        <span className={`execution-status comparison-status--${run.status}`}>
          {run.status === "pending" || run.status === "running" ? (
            <RefreshCw className="spin" aria-hidden="true" size={15} />
          ) : null}
          {run.status === "completed" ? <CheckCircle2 aria-hidden="true" size={15} /> : null}
          {run.status === "failed" ? <AlertTriangle aria-hidden="true" size={15} /> : null}
          {run.status}
        </span>
      </div>
      <dl className="comparison-progress" aria-label="Evaluation Run progress">
        {progress.map(([label, value]) => (
          <div className={`progress-card progress-card--${label.toLowerCase()}`} key={label}>
            <dt>{label}</dt>
            <dd className="progress-card__value">{value}</dd>
          </div>
        ))}
      </dl>
      <section className="deterministic-summary" aria-label="Deterministic score summary">
        <div className="regression-summary">
          <div>
            <strong>{run.deterministic_summary.new_regressions} new regression{run.deterministic_summary.new_regressions === 1 ? "" : "s"}</strong>
            <span>{run.deterministic_summary.existing_failures} existing failure{run.deterministic_summary.existing_failures === 1 ? "" : "s"}</span>
          </div>
          <div className="regression-severity-summary">
            <span>Normal regressions: {run.deterministic_summary.new_regressions_by_severity.normal}</span>
            <span>Important regressions: {run.deterministic_summary.new_regressions_by_severity.important}</span>
            <span>Release-blocking regressions: {run.deterministic_summary.new_regressions_by_severity.release_blocking}</span>
          </div>
        </div>
        <div className="score-summary-grid">
          <VersionScoreSummary label="Baseline" summary={run.deterministic_summary.baseline} />
          <VersionScoreSummary label="Candidate" summary={run.deterministic_summary.candidate} />
        </div>
      </section>
      <div className="comparison-columns">
        <VersionEvidence run={run} role="baseline" />
        <VersionEvidence run={run} role="candidate" />
      </div>
    </section>
  );
}

export default function EvaluationRunsWorkspace({ versions }: { versions: ApplicationVersion[] }) {
  const [suites, setSuites] = useState<EvaluationSuiteSummary[]>([]);
  const [baselineId, setBaselineId] = useState(versions[0]?.id ?? "");
  const [candidateId, setCandidateId] = useState(versions[1]?.id ?? "");
  const [suiteId, setSuiteId] = useState("");
  const [evaluationRun, setEvaluationRun] = useState<EvaluationRun | null>(null);
  const [reviewItems, setReviewItems] = useState<HumanReviewQueueItem[]>([]);
  const [isLoading, setIsLoading] = useState(true);
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (versions.length === 0) return;
    if (!versions.some((version) => version.id === baselineId)) {
      setBaselineId(versions[0]?.id ?? "");
    }
    if (!versions.some((version) => version.id === candidateId)) {
      setCandidateId(versions[1]?.id ?? "");
    }
  }, [baselineId, candidateId, versions]);

  useEffect(() => {
    let active = true;
    Promise.all([listEvaluationSuites(), listEvaluationRuns(), listHumanReviewItems()])
      .then(([loadedSuites, loadedRuns, loadedReviewItems]) => {
        if (!active) return;
        setSuites(loadedSuites);
        const latestRun = loadedRuns[0] ?? null;
        setEvaluationRun(latestRun);
        setReviewItems(loadedReviewItems);
        setBaselineId(latestRun?.baseline_version.id ?? "");
        setCandidateId(latestRun?.candidate_version.id ?? "");
        setSuiteId(latestRun?.evaluation_suite.id ?? loadedSuites[0]?.id ?? "");
      })
      .catch((reason: unknown) => {
        if (active) {
          setError(reason instanceof Error ? reason.message : "Unable to load Evaluation Runs.");
        }
      })
      .finally(() => {
        if (active) setIsLoading(false);
      });
    return () => {
      active = false;
    };
  }, []);

  useEffect(() => {
    if (evaluationRun?.status !== "pending" && evaluationRun?.status !== "running") return;
    let active = true;
    async function poll() {
      await waitForNextPoll();
      if (!active || evaluationRun === null) return;
      try {
        const current = await getEvaluationRun(evaluationRun.id);
        if (active) {
          setEvaluationRun(current);
          if (current.status === "completed" || current.status === "failed") {
            const currentReviewItems = await listHumanReviewItems();
            if (active) setReviewItems(currentReviewItems);
          }
          setError(null);
        }
      } catch (reason) {
        if (active) {
          setError(reason instanceof Error ? reason.message : "Unable to refresh the comparison.");
        }
      }
    }
    void poll();
    return () => {
      active = false;
    };
  }, [evaluationRun]);

  async function runComparison() {
    if (!baselineId || !candidateId || !suiteId || baselineId === candidateId) return;
    setIsSubmitting(true);
    setError(null);
    try {
      const current = await createEvaluationRun(baselineId, candidateId, suiteId);
      setEvaluationRun(current);
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "Unable to run the comparison.");
    } finally {
      setIsSubmitting(false);
    }
  }

  const invalidSelection = baselineId !== "" && baselineId === candidateId;
  const isActive = evaluationRun?.status === "pending" || evaluationRun?.status === "running";
  return (
    <>
      <div className="page-heading">
        <div>
          <p className="eyebrow">Paired, persisted evidence</p>
          <h1>Compare versions</h1>
        </div>
      </div>
      {error ? <div className="error-banner" role="alert">{error}</div> : null}
      <section className="comparison-controls" aria-label="Evaluation Run controls">
        <label>
          <span>Baseline</span>
          <select value={baselineId} onChange={(event) => setBaselineId(event.target.value)}>
            {versions.map((version) => <option key={version.id} value={version.id}>{version.name}</option>)}
          </select>
        </label>
        <label>
          <span>Candidate</span>
          <select value={candidateId} onChange={(event) => setCandidateId(event.target.value)}>
            {versions.map((version) => <option key={version.id} value={version.id}>{version.name}</option>)}
          </select>
        </label>
        <label>
          <span>Evaluation Suite</span>
          <select disabled={isLoading} value={suiteId} onChange={(event) => setSuiteId(event.target.value)}>
            {suites.map((suite) => <option key={suite.id} value={suite.id}>{suite.name} v{suite.version}</option>)}
          </select>
        </label>
        <button
          className="primary-button"
          type="button"
          disabled={isSubmitting || isActive || versions.length < 2 || !suiteId || invalidSelection}
          onClick={() => void runComparison()}
        >
          {isSubmitting || isActive ? <RefreshCw className="spin" aria-hidden="true" size={16} /> : <Play aria-hidden="true" size={16} />}
          {isSubmitting || isActive ? "Running comparison..." : "Run comparison"}
        </button>
      </section>
      {invalidSelection ? <div className="error-banner" role="alert">Choose two different Application Versions.</div> : null}
      {versions.length < 2 ? <p className="empty-state">Create two Application Versions before comparing them.</p> : null}
      <HumanReviewQueue items={reviewItems} />
      {evaluationRun ? (
        <EvaluationRunResult run={evaluationRun} reviewItems={reviewItems} />
      ) : null}
      {!evaluationRun && versions.length >= 2 ? <p className="empty-state">No persisted Evaluation Runs yet.</p> : null}
    </>
  );
}
