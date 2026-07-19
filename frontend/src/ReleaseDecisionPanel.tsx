import { useState } from "react";
import { FileCheck2, RefreshCw, Upload } from "lucide-react";

import {
  ReleaseDecision,
  ReleaseRule,
  ExternalSafetyEvidence,
  createReleaseDecision,
  importExternalSafetyEvidence,
  listExternalSafetyEvidence,
  listReleaseDecisions,
  listReleaseRules,
} from "./releaseDecisions";
import { formatCostUsd } from "./runtimeMetrics";

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

function externalEvidenceIds(
  reason: ReleaseDecision["reasons"][number],
): string[] {
  if (!reason.code.startsWith("external_safety_evidence_")) return [];
  if (!Array.isArray(reason.observed)) return [];
  return reason.observed.filter((value): value is string => typeof value === "string");
}

function latency(value: number | null): string {
  return value === null ? "Unavailable" : `${value} ms`;
}

function cost(value: number | null): string {
  return value === null ? "Unavailable" : formatCostUsd(value);
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
          : formatCostUsd(rule.maximum_candidate_total_cost_usd)}
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
  const externalSafety = decision.metrics.external_safety ?? {
    status: "not_present" as const,
    record_count: 0,
    records: [],
  };
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
        <div>
          <dt>External safety</dt>
          <dd className="release-metric-values">
            <span>
              {externalSafety.record_count} admitted report
              {externalSafety.record_count === 1 ? "" : "s"}
            </span>
          </dd>
          <small>
            {externalSafety.status.replaceAll("_", " ")}
          </small>
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
              {externalEvidenceIds(reason).map((evidenceId) => (
                <a
                  key={evidenceId}
                  href={`#external-safety-evidence-${evidenceId}`}
                >
                  External evidence
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

function ExternalSafetyEvidenceWorkspace({
  evidence,
  selectedFile,
  isImporting,
  isBusy,
  importNotice,
  onFileChange,
  onImport,
}: {
  evidence: ExternalSafetyEvidence[];
  selectedFile: File | null;
  isImporting: boolean;
  isBusy: boolean;
  importNotice: string | null;
  onFileChange: (file: File | null) => void;
  onImport: () => void;
}) {
  return (
    <section className="external-safety-workspace" aria-label="External Safety Evidence">
      <div className="external-safety-workspace__heading">
        <div>
          <strong>External Safety Evidence</strong>
          <p>
            Import an immutable Agent Incident Replay Lab Validation Report JSON.
          </p>
        </div>
        <span>{evidence.length} admitted</span>
      </div>
      <div className="external-safety-import">
        <label>
          <span>Validation Report JSON</span>
          <input
            aria-label="Validation Report JSON"
            type="file"
            accept="application/json,.json"
            disabled={isBusy}
            onChange={(event) => onFileChange(event.target.files?.[0] ?? null)}
          />
        </label>
        <button
          className="secondary-button"
          type="button"
          disabled={isBusy || selectedFile === null}
          onClick={onImport}
        >
          {isImporting ? (
            <RefreshCw className="spin" aria-hidden="true" size={15} />
          ) : (
            <Upload aria-hidden="true" size={15} />
          )}
          {isImporting ? "Importing safety evidence..." : "Import safety evidence"}
        </button>
      </div>
      <p className="external-safety-integrity">
        Content digest only; source fingerprints are producer claims, not signatures.
      </p>
      {importNotice ? <p className="external-safety-notice">{importNotice}</p> : null}
      {evidence.length === 0 ? (
        <p className="external-safety-empty">No external safety evidence admitted.</p>
      ) : (
        <ul className="external-safety-list">
          {evidence.map((item) => (
            <li
              key={item.id}
              id={`external-safety-evidence-${item.id}`}
              className={`external-safety-card--${item.candidate_verdict}`}
            >
              <div className="external-safety-card__heading">
                <div>
                  <code>{item.source_product}</code>
                  <strong>Candidate {item.candidate_verdict}</strong>
                </div>
                <span>Schema {item.schema_version}</span>
              </div>
              <p>{item.divergence_summary}</p>
              <dl>
                <div>
                  <dt>Record ID</dt>
                  <dd><code>{item.id}</code></dd>
                </div>
                <div>
                  <dt>Integration contract</dt>
                  <dd><code>{item.integration_contract}</code></dd>
                </div>
                <div>
                  <dt>Paired verdicts</dt>
                  <dd>
                    Baseline {item.baseline_verdict} / Candidate {item.candidate_verdict}
                  </dd>
                </div>
                <div>
                  <dt>Bundle / pair</dt>
                  <dd>{item.source_bundle_id} / {item.source_pair_id}</dd>
                </div>
                <div>
                  <dt>Baseline Agent Version</dt>
                  <dd><code>{item.baseline_agent_version_id}</code></dd>
                </div>
                <div>
                  <dt>Candidate Agent Version</dt>
                  <dd><code>{item.candidate_agent_version_id}</code></dd>
                </div>
                <div>
                  <dt>Local content digest</dt>
                  <dd><code>{item.source_digest}</code></dd>
                </div>
                <div>
                  <dt>Baseline source fingerprint</dt>
                  <dd><code>{item.baseline_evidence_fingerprint}</code></dd>
                </div>
                <div>
                  <dt>Candidate source fingerprint</dt>
                  <dd><code>{item.candidate_evidence_fingerprint}</code></dd>
                </div>
                <div>
                  <dt>Imported at</dt>
                  <dd><time dateTime={item.imported_at}>{item.imported_at}</time></dd>
                </div>
              </dl>
            </li>
          ))}
        </ul>
      )}
    </section>
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
  const [externalEvidence, setExternalEvidence] = useState<ExternalSafetyEvidence[]>([]);
  const [selectedEvidenceFile, setSelectedEvidenceFile] = useState<File | null>(null);
  const [importNotice, setImportNotice] = useState<string | null>(null);
  const [isLoaded, setIsLoaded] = useState(false);
  const [isLoading, setIsLoading] = useState(false);
  const [isProducing, setIsProducing] = useState(false);
  const [isImporting, setIsImporting] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function loadWorkspace() {
    setIsLoading(true);
    setError(null);
    try {
      const [loadedRules, loadedHistory, loadedEvidence] = await Promise.all([
        listReleaseRules(),
        listReleaseDecisions(evaluationRunId),
        listExternalSafetyEvidence(evaluationRunId),
      ]);
      const latest = loadedHistory[0] ?? null;
      setRules(loadedRules);
      setHistory(loadedHistory);
      setExternalEvidence(loadedEvidence);
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

  async function importEvidence() {
    if (selectedEvidenceFile === null || isProducing || isImporting) return;
    setIsImporting(true);
    setError(null);
    setImportNotice(null);
    try {
      const admitted = await importExternalSafetyEvidence(
        evaluationRunId,
        selectedEvidenceFile,
      );
      setExternalEvidence((current) => [
        admitted,
        ...current.filter((item) => item.id !== admitted.id),
      ]);
      setImportNotice(
        "Evidence admitted. Produce a new Release Decision to include this snapshot.",
      );
    } catch (reason) {
      setError(
        reason instanceof Error ? reason.message : "Unable to import safety evidence.",
      );
    } finally {
      setIsImporting(false);
    }
  }

  async function produceDecision() {
    if (!selectedRuleId || isProducing || isImporting) return;
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
                  disabled={isProducing || isImporting}
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
                disabled={isProducing || isImporting || !selectedRuleId}
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
          <ExternalSafetyEvidenceWorkspace
            evidence={externalEvidence}
            selectedFile={selectedEvidenceFile}
            isImporting={isImporting}
            isBusy={isImporting || isProducing}
            importNotice={importNotice}
            onFileChange={setSelectedEvidenceFile}
            onImport={() => void importEvidence()}
          />
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
