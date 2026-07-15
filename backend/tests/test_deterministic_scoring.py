from llm_eval_lab.deterministic_scoring import (
    DETERMINISTIC_SCORER_VERSION,
    VersionedDeterministicScorer,
    classify_candidate_regression,
)


def test_passing_answer_preserves_exact_rule_evidence():
    result = VersionedDeterministicScorer().score(
        response="The PRICE is $79. The available colors are black and silver.",
        must_have_facts=[
            "The price is $79.",
            "The available colors are black and silver.",
        ],
        forbidden_claims=["The EchoBud X1 costs $99."],
    )

    assert result.scorer_version == DETERMINISTIC_SCORER_VERSION == "exact-phrase-v1"
    assert result.passed is True
    assert [outcome.passed for outcome in result.outcomes] == [True, True, True]
    assert result.outcomes[0].matched_evidence == "The PRICE is $79."
    assert result.outcomes[1].matched_evidence == (
        "The available colors are black and silver."
    )
    assert result.outcomes[2].matched_evidence is None


def test_missing_must_have_fact_is_an_explainable_failure():
    result = VersionedDeterministicScorer().score(
        response="The EchoBud X1 is available in black and silver.",
        must_have_facts=["The price is $79."],
        forbidden_claims=[],
    )

    assert result.passed is False
    assert result.outcomes[0].check_type == "must_have_fact"
    assert result.outcomes[0].rule == "The price is $79."
    assert result.outcomes[0].passed is False
    assert result.outcomes[0].matched_evidence is None


def test_forbidden_claim_failure_preserves_the_matched_response_text():
    result = VersionedDeterministicScorer().score(
        response="The EchoBud X1 costs $99.",
        must_have_facts=[],
        forbidden_claims=["The EchoBud X1 costs $99."],
    )

    assert result.passed is False
    assert result.outcomes[0].check_type == "forbidden_claim"
    assert result.outcomes[0].passed is False
    assert result.outcomes[0].matched_evidence == "The EchoBud X1 costs $99."


def test_evidence_span_stays_aligned_after_unicode_case_expansion():
    result = VersionedDeterministicScorer().score(
        response="AßForbidden",
        must_have_facts=[],
        forbidden_claims=["Forbidden"],
    )

    assert result.passed is False
    assert result.outcomes[0].matched_evidence == "Forbidden"


def test_multiple_rule_failures_remain_individually_inspectable():
    result = VersionedDeterministicScorer().score(
        response="A lifetime warranty is included.",
        must_have_facts=[
            "The warranty lasts 12 months.",
            "Water damage is excluded.",
        ],
        forbidden_claims=["A lifetime warranty is included."],
    )

    assert result.passed is False
    assert [outcome.passed for outcome in result.outcomes] == [False, False, False]
    assert [outcome.position for outcome in result.outcomes] == [1, 2, 3]


def test_candidate_failure_is_classified_against_the_baseline():
    assert classify_candidate_regression(True, False) == "new_regression"
    assert classify_candidate_regression(False, False) == "existing_failure"
    assert classify_candidate_regression(False, True) is None
    assert classify_candidate_regression(True, True) is None
