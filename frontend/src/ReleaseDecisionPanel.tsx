import { useState } from "react";
import { FileCheck2, RefreshCw } from "lucide-react";

import {
  ReleaseDecision,
  ReleaseRule,
  createReleaseDecision,
  listReleaseDecisions,
  listReleaseRules,
} from "./releaseDecisions";

function percent(value: number): string {
  return `${Math.round(value * 100)}%`;
}

function outcomeLabel(outcome: ReleaseDecision["outcome"]): string {
  if (outcome === "manual_review_required") return "Manual review required";
  return outcome === "pass" ? "Pass" : "Fail";
}

function configuredNumber(value: number | null, unit: string): string {
  return value === null ? "Not configured" : `${value} ${unit}`;
}

function severityLabel(severity: ReleaseRule["blocking_severities"][number]): string {
  if (severity === "release_blocking") return "Release blocking";
  return severity === "important" ? "Important" : "Normal";
}

function severityList(severities: ReleaseRule["blocking_severities"]): string {
  return severities.map(severityLabel).join(" · ");
}

function reasonValue(value: unknown): string {
  if (Array.isArray(value)) return value.map(reasonValue).join(" · ");
  if (value === null || value === undefined) return "Unavailable";
  if (value === "normal" || value === "important" || value === "release_blocking") {
    return severityLabel(value);
  }
  return typeof value === "object" ? JSON.stringify(value) : String(value);
}

function latency(value: number | null): string {
  return value === null ? "Unavailable" : `${value} ms`;
}

function cost(value: number | null): string {
  return value === null ? "Unavailable" : `$${value.toFixed(4)}`;
}

function ReleaseRuleSummary({ rule }: { rule: ReleaseRule }) {
  return (
    <div className="release-rule-summary">
      <strong>{rule.name} v{rule.version}</strong>
      <span>Maximum correctness drop: {percent(rule.maximum_correctness_drop)}</span>
      <span>Minimum candidate safety: {percent(rule.minimum_candidate_safety_rate)}</span>
      <span>
        Maximum candidate latency: {configuredNumber(
          rule.maximum_candidate_average_latency_ms,
          "ms",
        )}
      </span>
      <span>
        Maximum candidate cost: {rule.maximum_candidate_total_cost_usd === null
          ? "Not configured"
          : `$${rule.maximum_candidate_total_cost_usd.toFixed(4)}`}
      </span>
      <span>
        Human Review: {rule.require_resolved_reviews ? "Must be resolved" : "Optional"}
      </span>
      <span>Blocking failures: {severityList(rule.blocking_severities)}</span>
      <span>
        New regression failures: {severityList(rule.new_regression_severities)}
      </span>
    </div>
  );
}

function ReleaseDecisionResult({ decision }: { decision: ReleaseDecision }) {
  return (
    <article className={`release-decision-result release-decision-result--${decision.outcome}`}>
      <div className="release-decision-result__heading">
        <div>
          <p className="eyebrow">Latest evidence snapshot</p>
          <h3>{outcomeLabel(decision.outcome)}</h3>
        </div>
        <span>{decision.release_rule.slug} v{decision.release_rule.version}</span>
      </div>
      <dl className="release-metrics">
        <div>
          <dt>Correctness</dt>
          <dd className="release-metric-values">
            <span>Baseline {percent(decision.metrics.correctness.baseline_rate)}</span>
            <span>Candidate {percent(decision.metrics.correctness.candidate_rate)}</span>
            <span>Delta {percent(decision.metrics.correctness.delta)}</span>
          </dd>
          <small>{decision.metrics.correctness.status}</small>
        </div>
        <div>
          <dt>Safety</dt>
          <dd className="release-metric-values">
            <span>Baseline {percent(decision.metrics.safety.baseline_rate)}</span>
            <span>Candidate {percent(decision.metrics.safety.candidate_rate)}</span>
          </dd>
          <small>{decision.metrics.safety.status}</small>
        </div>
        <div>
          <dt>Latency</dt>
          <dd className="release-metric-values">
            <span>Baseline {latency(decision.metrics.latency.baseline_average_ms)}</span>
            <span>Candidate {latency(decision.metrics.latency.candidate_average_ms)}</span>
          </dd>
          <small>{decision.metrics.latency.status.replace("_", " ")}</small>
        </div>
        <div>
          <dt>Cost</dt>
          <dd className="release-metric-values">
            <span>Baseline {cost(decision.metrics.cost.baseline_total_usd)}</span>
            <span>Candidate {cost(decision.metrics.cost.candidate_total_usd)}</span>
          </dd>
          <small>{decision.metrics.cost.status.replace("_", " ")}</small>
        </div>
      </dl>
      <div className="release-reasons">
        <strong>Decision reasons</strong>
        <ul>
          {decision.reasons.map((reason, index) => (
            <li key={`${reason.code}-${index}`}>
              <div>
                <span>{reason.message}</span>
                <div className="release-reason-evidence">
                  <span>Observed: {reasonValue(reason.observed)}</span>
                  <span>Threshold: {reasonValue(reason.threshold)}</span>
                </div>
              </div>
              {reason.execution_ids.map((executionId) => (
                <a key={executionId} href={`#execution-${executionId}`}>
                  Execution evidence
                </a>
              ))}
            </li>
          ))}
        </ul>
      </div>
      <p className="release-fingerprint">
        Evidence fingerprint <code>{decision.evidence_fingerprint.slice(0, 12)}</code>
      </p>
    </article>
  );
}

export default function ReleaseDecisionPanel({
  evaluationRunId,
}: {
  evaluationRunId: string;
}) {
  const [rules, setRules] = useState<ReleaseRule[]>([]);
  const [selectedRuleId, setSelectedRuleId] = useState("");
  const [decision, setDecision] = useState<ReleaseDecision | null>(null);
  const [history, setHistory] = useState<ReleaseDecision[]>([]);
  const [isLoaded, setIsLoaded] = useState(false);
  const [isLoading, setIsLoading] = useState(false);
  const [isProducing, setIsProducing] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function loadWorkspace() {
    setIsLoading(true);
    setError(null);
    try {
      const [loadedRules, loadedHistory] = await Promise.all([
        listReleaseRules(),
        listReleaseDecisions(evaluationRunId),
      ]);
      const latest = loadedHistory[0] ?? null;
      setRules(loadedRules);
      setHistory(loadedHistory);
      setDecision(latest);
      setSelectedRuleId(
        latest && loadedRules.some((rule) => rule.id === latest.release_rule.id)
          ? latest.release_rule.id
          : loadedRules[0]?.id ?? "",
      );
      setIsLoaded(true);
    } catch (reason) {
      setError(
        reason instanceof Error ? reason.message : "Unable to load Release Decisions.",
      );
    } finally {
      setIsLoading(false);
    }
  }

  async function produceDecision() {
    if (!selectedRuleId) return;
    setIsProducing(true);
    setError(null);
    try {
      const produced = await createReleaseDecision(evaluationRunId, selectedRuleId);
      setDecision(produced);
      setHistory((current) => [
        produced,
        ...current.filter((item) => item.id !== produced.id),
      ]);
    } catch (reason) {
      setError(
        reason instanceof Error ? reason.message : "Unable to produce a Release Decision.",
      );
    } finally {
      setIsProducing(false);
    }
  }

  const selectedRule = rules.find((rule) => rule.id === selectedRuleId) ?? null;
  return (
    <section className="release-decision-panel" aria-label="Release Decision">
      <div className="release-decision-panel__heading">
        <div>
          <p className="eyebrow">Explainable ship gate</p>
          <h2>Release Decision</h2>
        </div>
        {isLoaded ? <span>{history.length} immutable snapshot{history.length === 1 ? "" : "s"}</span> : null}
      </div>
      {!isLoaded ? (
        <button
          className="primary-button"
          type="button"
          disabled={isLoading}
          onClick={() => void loadWorkspace()}
        >
          {isLoading ? <RefreshCw className="spin" aria-hidden="true" size={16} /> : <FileCheck2 aria-hidden="true" size={16} />}
          {isLoading ? "Loading Release Decision..." : "Load Release Decision"}
        </button>
      ) : (
        <>
          {rules.length > 0 ? (
            <div className="release-decision-controls">
              <label>
                <span>Release Rule</span>
                <select
                  disabled={isProducing}
                  value={selectedRuleId}
                  onChange={(event) => {
                    const ruleId = event.target.value;
                    setSelectedRuleId(ruleId);
                    setDecision(
                      history.find((item) => item.release_rule.id === ruleId) ?? null,
                    );
                  }}
                >
                  {rules.map((rule) => (
                    <option key={rule.id} value={rule.id}>{rule.name} v{rule.version}</option>
                  ))}
                </select>
              </label>
              <button
                className="primary-button"
                type="button"
                disabled={isProducing || !selectedRuleId}
                onClick={() => void produceDecision()}
              >
                {isProducing ? <RefreshCw className="spin" aria-hidden="true" size={16} /> : <FileCheck2 aria-hidden="true" size={16} />}
                {isProducing ? "Producing Release Decision..." : "Produce Release Decision"}
              </button>
            </div>
          ) : (
            <p className="empty-state">No Release Rules are configured.</p>
          )}
          {selectedRule ? <ReleaseRuleSummary rule={selectedRule} /> : null}
          {decision ? (
            <ReleaseDecisionResult decision={decision} />
          ) : rules.length > 0 ? (
            <p className="release-decision-empty">
              No snapshot exists for this rule and run. Produce one from persisted evidence.
            </p>
          ) : null}
        </>
      )}
      {error ? <div className="error-banner" role="alert">{error}</div> : null}
    </section>
  );
}
