import { useEffect, useState } from "react";
import {
  AlertTriangle,
  BookOpen,
  ChevronRight,
  ClipboardCheck,
  RefreshCw,
  ShieldAlert,
} from "lucide-react";

import {
  EvaluationSuiteDetail,
  EvaluationSuiteSummary,
  EvaluationTestCase,
  getEvaluationSuite,
  listEvaluationSuites,
} from "./evaluationSuites";

function formatLabel(value: string): string {
  const label = value.replaceAll("_", " ");
  return label.charAt(0).toUpperCase() + label.slice(1);
}

function TestCaseDetail({ testCase }: { testCase: EvaluationTestCase }) {
  return (
    <article className="test-case-detail">
      <div className="test-case-detail__heading">
        <div>
          <p className="eyebrow">Test Case {testCase.position}</p>
          <h2>{testCase.title}</h2>
        </div>
        <div className="test-case-badges">
          <span className={`badge badge--${testCase.severity}`}>
            {formatLabel(testCase.severity)}
          </span>
          <span className="badge">{formatLabel(testCase.test_type)}</span>
        </div>
      </div>

      <div className="review-requirement">
        <ShieldAlert aria-hidden="true" size={17} />
        {testCase.requires_human_review
          ? "Human review required"
          : "Human review not pre-required"}
      </div>

      <section className="evidence-section">
        <h3>User input</h3>
        <blockquote>{testCase.user_input}</blockquote>
      </section>

      <section className="evidence-section">
        <h3>
          <BookOpen aria-hidden="true" size={17} />
          Grounding material
        </h3>
        <div className="grounding-list">
          {testCase.grounding_material.map((material) => (
            <article className="grounding-card" key={`${material.kind}-${material.title}`}>
              <span>{material.kind}</span>
              <h4>{material.title}</h4>
              <p>{material.content}</p>
            </article>
          ))}
        </div>
      </section>

      <div className="evidence-grid">
        <section className="evidence-section evidence-section--positive">
          <h3>
            <ClipboardCheck aria-hidden="true" size={17} />
            Must-have facts
          </h3>
          <ul>
            {testCase.must_have_facts.map((fact) => (
              <li key={fact}>{fact}</li>
            ))}
          </ul>
        </section>
        <section className="evidence-section evidence-section--negative">
          <h3>
            <AlertTriangle aria-hidden="true" size={17} />
            Forbidden claims
          </h3>
          <ul>
            {testCase.forbidden_claims.map((claim) => (
              <li key={claim}>{claim}</li>
            ))}
          </ul>
        </section>
      </div>
    </article>
  );
}

export default function EvaluationSuitesWorkspace() {
  const [suites, setSuites] = useState<EvaluationSuiteSummary[]>([]);
  const [selectedSuite, setSelectedSuite] = useState<EvaluationSuiteDetail | null>(null);
  const [selectedTestCase, setSelectedTestCase] = useState<EvaluationTestCase | null>(null);
  const [isLoading, setIsLoading] = useState(true);
  const [isLoadingDetail, setIsLoadingDetail] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let active = true;
    listEvaluationSuites()
      .then((loadedSuites) => {
        if (active) {
          setSuites(loadedSuites);
          setError(null);
        }
      })
      .catch((reason: unknown) => {
        if (active) {
          setError(reason instanceof Error ? reason.message : "Unable to load Evaluation Suites.");
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

  async function browseSuite(suiteId: string) {
    setIsLoadingDetail(true);
    setError(null);
    try {
      const detail = await getEvaluationSuite(suiteId);
      setSelectedSuite(detail);
      setSelectedTestCase(detail.test_cases[0] ?? null);
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "Unable to load the Evaluation Suite.");
    } finally {
      setIsLoadingDetail(false);
    }
  }

  return (
    <>
      <div className="page-heading">
        <div>
          <p className="eyebrow">Versioned evaluation evidence</p>
          <h1>Evaluation Suites</h1>
        </div>
        <span className="record-count">{suites.length} total</span>
      </div>

      {error ? (
        <div className="error-banner" role="alert">
          {error}
        </div>
      ) : null}

      <section className="suite-catalog" aria-label="Saved Evaluation Suites">
        {isLoading ? <p className="empty-state">Loading Evaluation Suites...</p> : null}
        {!isLoading && suites.length === 0 ? (
          <p className="empty-state">No Evaluation Suites yet.</p>
        ) : null}
        {suites.map((suite) => (
          <article className="suite-card" key={suite.id}>
            <div>
              <div className="suite-card__title">
                <h2>{suite.name}</h2>
                <span>v{suite.version}</span>
              </div>
              <p>{suite.description}</p>
            </div>
            <button
              className="secondary-button"
              type="button"
              onClick={() => browseSuite(suite.id)}
              disabled={isLoadingDetail}
            >
              {isLoadingDetail ? (
                <RefreshCw className="spin" aria-hidden="true" size={16} />
              ) : (
                <ChevronRight aria-hidden="true" size={16} />
              )}
              Browse {suite.test_case_count} Test Cases
            </button>
          </article>
        ))}
      </section>

      {selectedSuite ? (
        <section className="suite-browser" aria-label={`${selectedSuite.name} Test Cases`}>
          <aside className="test-case-list">
            <div className="test-case-list__heading">
              <span>{selectedSuite.name}</span>
              <strong>{selectedSuite.test_case_count} cases</strong>
            </div>
            {selectedSuite.test_cases.map((testCase) => (
              <button
                aria-label={testCase.title}
                className={testCase.id === selectedTestCase?.id ? "is-selected" : ""}
                key={testCase.id}
                type="button"
                onClick={() => setSelectedTestCase(testCase)}
              >
                <span>{testCase.position}</span>
                <strong>{testCase.title}</strong>
              </button>
            ))}
          </aside>
          {selectedTestCase ? <TestCaseDetail testCase={selectedTestCase} /> : null}
        </section>
      ) : null}
    </>
  );
}
