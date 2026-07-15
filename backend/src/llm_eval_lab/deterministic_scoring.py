import re
from dataclasses import dataclass
from typing import Literal

DETERMINISTIC_SCORER_VERSION = "exact-phrase-v1"
CheckType = Literal["must_have_fact", "forbidden_claim"]
RegressionClassification = Literal["new_regression", "existing_failure"]


@dataclass(frozen=True)
class DeterministicRuleOutcome:
    check_type: CheckType
    position: int
    rule: str
    passed: bool
    matched_evidence: str | None


@dataclass(frozen=True)
class DeterministicScore:
    scorer_version: str
    passed: bool
    outcomes: tuple[DeterministicRuleOutcome, ...]


def _matched_evidence(response: str, rule: str) -> str | None:
    match = re.search(re.escape(rule), response, flags=re.IGNORECASE)
    return match.group(0) if match is not None else None


class VersionedDeterministicScorer:
    version = DETERMINISTIC_SCORER_VERSION

    def score(
        self,
        *,
        response: str,
        must_have_facts: list[str],
        forbidden_claims: list[str],
    ) -> DeterministicScore:
        outcomes: list[DeterministicRuleOutcome] = []
        for rule in must_have_facts:
            evidence = _matched_evidence(response, rule)
            outcomes.append(
                DeterministicRuleOutcome(
                    check_type="must_have_fact",
                    position=len(outcomes) + 1,
                    rule=rule,
                    passed=evidence is not None,
                    matched_evidence=evidence,
                )
            )
        for rule in forbidden_claims:
            evidence = _matched_evidence(response, rule)
            outcomes.append(
                DeterministicRuleOutcome(
                    check_type="forbidden_claim",
                    position=len(outcomes) + 1,
                    rule=rule,
                    passed=evidence is None,
                    matched_evidence=evidence,
                )
            )
        return DeterministicScore(
            scorer_version=self.version,
            passed=all(outcome.passed for outcome in outcomes),
            outcomes=tuple(outcomes),
        )


def classify_candidate_regression(
    baseline_passed: bool,
    candidate_passed: bool,
) -> RegressionClassification | None:
    if candidate_passed:
        return None
    return "new_regression" if baseline_passed else "existing_failure"
