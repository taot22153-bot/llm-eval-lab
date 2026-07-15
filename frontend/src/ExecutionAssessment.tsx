import { HumanReviewReason, TestCaseExecution } from "./testCaseExecutions";

export function reviewReasonLabel(reason: HumanReviewReason): string {
  const labels: Record<HumanReviewReason, string> = {
    automatic_conflict: "Automatic score conflict",
    low_confidence: "Low semantic confidence",
    insufficient_evidence: "Insufficient evidence",
    test_case_requires_review: "Test Case requires review",
    judge_failure: "Semantic judge failure",
  };
  return labels[reason];
}

export default function ExecutionAssessment({ execution }: { execution: TestCaseExecution }) {
  const deterministicEvaluation = execution.deterministic_evaluation ?? null;
  const semanticEvaluation = execution.semantic_evaluation ?? null;
  const humanReviewItem = execution.human_review_item ?? null;
  const regressionLabel = deterministicEvaluation?.regression_classification === "new_regression"
    ? "New regression"
    : deterministicEvaluation?.regression_classification === "existing_failure"
      ? "Existing failure"
      : null;

  return (
    <div className="automatic-assessment" aria-label="Automatic and Human Review evidence">
      {deterministicEvaluation ? (
        <div className="deterministic-evaluation">
          <div className="deterministic-evaluation__status">
            <span className={deterministicEvaluation.passed ? "rule-pass" : "rule-fail"}>
              {deterministicEvaluation.passed ? "Deterministic pass" : "Deterministic failure"}
            </span>
            {regressionLabel ? <strong>{regressionLabel}</strong> : null}
          </div>
          {!deterministicEvaluation.passed || regressionLabel ? (
            <details className="rule-evidence">
              <summary>Inspect rule evidence</summary>
              <p className="rule-evidence__version">
                Scorer {deterministicEvaluation.scorer_version}
              </p>
              <ol>
                {deterministicEvaluation.outcomes.map((outcome) => (
                  <li key={`${outcome.check_type}-${outcome.position}`}>
                    <div>
                      <strong>
                        {outcome.check_type === "must_have_fact" ? "Must-have fact" : "Forbidden claim"}
                      </strong>
                      <span className={outcome.passed ? "rule-pass" : "rule-fail"}>
                        {outcome.passed ? "Pass" : "Fail"}
                      </span>
                    </div>
                    <p>{outcome.rule}</p>
                    <small>
                      {outcome.matched_evidence
                        ? `Matched response: ${outcome.matched_evidence}`
                        : "No matching evidence found."}
                    </small>
                  </li>
                ))}
              </ol>
            </details>
          ) : null}
        </div>
      ) : null}
      {semanticEvaluation ? (
        <div className="semantic-evaluation">
          <div className="semantic-evaluation__status">
            <strong>Semantic judgment</strong>
            <span className={semanticEvaluation.outcome === "pass" ? "rule-pass" : "rule-fail"}>
              {semanticEvaluation.error
                ? "Semantic judge failed"
                : semanticEvaluation.outcome === "insufficient_evidence"
                  ? "Semantic evidence insufficient"
                  : `Semantic ${semanticEvaluation.outcome}`}
            </span>
          </div>
          {semanticEvaluation.rationale ? <p>{semanticEvaluation.rationale}</p> : null}
          {semanticEvaluation.confidence !== null ? (
            <p className="semantic-evaluation__confidence">
              {Math.round(semanticEvaluation.confidence * 100)}% confidence
            </p>
          ) : null}
          <p className="semantic-evaluation__configuration">
            {semanticEvaluation.judge_configuration.provider} / {semanticEvaluation.judge_configuration.model}
            <span> · {semanticEvaluation.judge_version}</span>
          </p>
          {semanticEvaluation.error ? (
            <div className="semantic-evaluation__error">
              <strong>{semanticEvaluation.error.code}</strong>
              <p>{semanticEvaluation.error.message}</p>
            </div>
          ) : null}
        </div>
      ) : null}
      {humanReviewItem ? (
        <div className={`human-review-state human-review-state--${humanReviewItem.status}`}>
          <strong>
            {humanReviewItem.status === "pending" ? "Pending human review" : "Human review resolved"}
          </strong>
          <span>{humanReviewItem.reasons.map(reviewReasonLabel).join(" · ")}</span>
        </div>
      ) : null}
    </div>
  );
}
