# ruff: noqa: E402

import json
import os
from datetime import UTC, datetime
from pathlib import Path

import pytest
from dotenv import load_dotenv
from fastapi.testclient import TestClient
from sqlalchemy import event

load_dotenv(Path(__file__).parents[2] / ".env")
os.environ["DATABASE_URL"] = os.environ["TEST_DATABASE_URL"]

from llm_eval_lab.database import Base, SessionLocal, engine
from llm_eval_lab.main import app
from llm_eval_lab.models import (
    ApplicationVersion,
    EvaluationRun,
    EvaluationSuite,
    ExternalSafetyEvidence,
)

REPORT_PATH = Path(__file__).parent / "fixtures" / "agent-incident-validation-report.json"


@pytest.fixture(autouse=True)
def reset_database():
    Base.metadata.drop_all(bind=engine)
    Base.metadata.create_all(bind=engine)
    app.dependency_overrides.clear()
    yield
    app.dependency_overrides.clear()
    Base.metadata.drop_all(bind=engine)


def seed_run(status: str = "completed") -> str:
    now = datetime.now(UTC)
    with SessionLocal() as session:
        baseline = ApplicationVersion(
            name="External evidence baseline",
            model_provider="fixture",
            model_name="deterministic",
            system_prompt="Answer from evidence.",
            generation_parameters={},
            knowledge_config=None,
            tool_config=None,
        )
        candidate = ApplicationVersion(
            name="External evidence candidate",
            model_provider="fixture",
            model_name="deterministic",
            system_prompt="Answer safely from evidence.",
            generation_parameters={},
            knowledge_config=None,
            tool_config=None,
        )
        suite = EvaluationSuite(
            slug="external-evidence-fixture",
            version=1,
            name="External Evidence Fixture",
            description="A completed run used to attach external safety evidence.",
            test_cases=[],
        )
        evaluation_run = EvaluationRun(
            baseline_version=baseline,
            candidate_version=candidate,
            evaluation_suite=suite,
            status=status,
            started_at=now,
            completed_at=now if status == "completed" else None,
        )
        session.add(evaluation_run)
        session.commit()
        return evaluation_run.id


def test_imports_lists_and_idempotently_reuses_agent_validation_report():
    run_id = seed_run()
    report_bytes = REPORT_PATH.read_bytes()

    with TestClient(app) as client:
        imported = client.post(
            f"/api/evaluation-runs/{run_id}/external-safety-evidence",
            content=report_bytes,
            headers={"Content-Type": "application/json"},
        )
        repeated = client.post(
            f"/api/evaluation-runs/{run_id}/external-safety-evidence",
            content=report_bytes,
            headers={"Content-Type": "application/json"},
        )
        listed = client.get(
            f"/api/evaluation-runs/{run_id}/external-safety-evidence"
        )

    assert imported.status_code == 201
    assert repeated.status_code == 200
    expected = {
        "evaluation_run_id": run_id,
        "source_product": "agent_incident_replay_lab",
        "integration_contract": "validation_report_json_file_only",
        "schema_version": "1.0",
        "source_digest": (
            "7c08115da895d46ab54168a16fb800799ea9a1b418783d5cfc035851fbba3ecd"
        ),
        "source_bundle_id": "support-ticket-exfiltration-v1",
        "source_pair_id": "vp-cce933bc36914efaa38fb2e5a19ced44",
        "baseline_agent_version_id": "baseline-support-ticket-validation-pair-v1",
        "candidate_agent_version_id": "candidate-support-ticket-approval-v1",
        "baseline_evidence_fingerprint": (
            "44943513e48b94fcfd7cabbfdd315c7df7914b716021310dfbc81af770701ed3"
        ),
        "candidate_evidence_fingerprint": (
            "8aee734da3ddaca1841ea4f8cb859640541369424deb2df905ca8d0472b36a48"
        ),
        "baseline_verdict": "ineffective",
        "candidate_verdict": "effective",
        "divergence_summary": (
            "Baseline permitted the external email; Candidate required an exact "
            "Approval Request."
        ),
    }
    imported_body = imported.json()
    assert imported_body.pop("id")
    assert imported_body.pop("imported_at").endswith("Z")
    assert imported_body == expected
    assert repeated.json()["id"] == listed.json()[0]["id"]
    assert repeated.json()["id"] == imported.json()["id"]
    assert listed.status_code == 200
    assert len(listed.json()) == 1
    assert "canonical_json" not in listed.json()[0]
    with SessionLocal() as session:
        stored = session.get(ExternalSafetyEvidence, imported.json()["id"])
        assert stored is not None
        assert json.loads(stored.canonical_json) == json.loads(report_bytes)


def test_evidence_list_does_not_reload_canonical_report_json():
    run_id = seed_run()
    statements: list[str] = []

    def capture_statement(_connection, _cursor, statement, _parameters, _context, _many):
        statements.append(statement)

    with TestClient(app) as client:
        imported = client.post(
            f"/api/evaluation-runs/{run_id}/external-safety-evidence",
            content=REPORT_PATH.read_bytes(),
            headers={"Content-Type": "application/json"},
        )
        assert imported.status_code == 201
        event.listen(engine, "before_cursor_execute", capture_statement)
        try:
            listed = client.get(
                f"/api/evaluation-runs/{run_id}/external-safety-evidence"
            )
        finally:
            event.remove(engine, "before_cursor_execute", capture_statement)

    assert listed.status_code == 200
    evidence_queries = [
        statement
        for statement in statements
        if "external_safety_evidence" in statement.lower()
    ]
    assert evidence_queries
    assert all("canonical_json" not in statement.lower() for statement in evidence_queries)


def test_rejects_non_json_media_type_without_persisting_evidence():
    run_id = seed_run()

    with TestClient(app) as client:
        response = client.post(
            f"/api/evaluation-runs/{run_id}/external-safety-evidence",
            content=REPORT_PATH.read_bytes(),
            headers={"Content-Type": "text/plain"},
        )
        listed = client.get(
            f"/api/evaluation-runs/{run_id}/external-safety-evidence"
        )

    assert response.status_code == 415
    assert response.json() == {
        "detail": "External Safety Evidence must be application/json."
    }
    assert listed.json() == []


@pytest.mark.parametrize(
    ("body", "expected_detail"),
    [
        (b"not-json", "The file is not a supported Validation Report."),
        (b"[]", "The file is not a supported Validation Report."),
        (
            b"{" + b" " * (1024 * 1024),
            "The report exceeds the 1 MiB import limit.",
        ),
        (
            b"[" * 10_000 + b"]" * 10_000,
            "The file is not a supported Validation Report.",
        ),
    ],
    ids=["malformed", "non-object", "oversized", "deeply-nested"],
)
def test_rejects_invalid_or_oversized_reports(body: bytes, expected_detail: str):
    run_id = seed_run()

    with TestClient(app) as client:
        response = client.post(
            f"/api/evaluation-runs/{run_id}/external-safety-evidence",
            content=body,
            headers={"Content-Type": "application/json"},
        )

    assert response.status_code == 422
    assert response.json() == {"detail": expected_detail}
    with SessionLocal() as session:
        assert session.query(ExternalSafetyEvidence).count() == 0


def test_rejects_duplicate_root_json_members_without_persisting_evidence():
    run_id = seed_run()
    ambiguous_report = REPORT_PATH.read_bytes().replace(
        b"{",
        b'{"schema_version":"999",',
        1,
    )

    with TestClient(app) as client:
        response = client.post(
            f"/api/evaluation-runs/{run_id}/external-safety-evidence",
            content=ambiguous_report,
            headers={"Content-Type": "application/json"},
        )

    assert response.status_code == 422
    assert response.json() == {
        "detail": "The file is not a supported Validation Report."
    }
    with SessionLocal() as session:
        assert session.query(ExternalSafetyEvidence).count() == 0


def test_rejects_duplicate_nested_json_members_without_persisting_evidence():
    run_id = seed_run()
    report_text = REPORT_PATH.read_text(encoding="utf-8")
    prefix, candidate = report_text.split('  "candidate": {', 1)
    ambiguous_candidate = candidate.replace(
        '"status": "effective"',
        '"status": "ineffective",\n          "status": "effective"',
        1,
    )
    ambiguous_report = (prefix + '  "candidate": {' + ambiguous_candidate).encode()

    with TestClient(app) as client:
        response = client.post(
            f"/api/evaluation-runs/{run_id}/external-safety-evidence",
            content=ambiguous_report,
            headers={"Content-Type": "application/json"},
        )

    assert response.status_code == 422
    assert response.json() == {
        "detail": "The file is not a supported Validation Report."
    }
    with SessionLocal() as session:
        assert session.query(ExternalSafetyEvidence).count() == 0


def test_rejects_events_after_the_terminal_validation_verdict():
    run_id = seed_run()
    report = json.loads(REPORT_PATH.read_bytes())
    candidate = report["candidate"]
    candidate["evidence_timeline"].append(
        {
            "sequence": len(candidate["evidence_timeline"]) + 1,
            "kind": "task_outcome",
            "causal_id": "post-verdict-event",
            "caused_by": [],
            "content": {
                "status": "completed",
                "summary": "Occurred after the declared terminal verdict.",
            },
        }
    )
    candidate["normalized_timeline"].append(
        {
            "alignment_key": "post-verdict-event",
            "kind": "task_outcome",
            "causal_role": "post_verdict",
            "caused_by": [],
            "content": {
                "status": "completed",
                "summary": "Occurred after the declared terminal verdict.",
            },
        }
    )

    with TestClient(app) as client:
        response = client.post(
            f"/api/evaluation-runs/{run_id}/external-safety-evidence",
            json=report,
        )

    assert response.status_code == 422
    assert response.json() == {
        "detail": "The file is not a supported Validation Report."
    }
    with SessionLocal() as session:
        assert session.query(ExternalSafetyEvidence).count() == 0


@pytest.mark.parametrize(
    ("field", "value", "expected_detail"),
    [
        (
            "schema_version",
            "2.0",
            "The Validation Report schema version is not supported.",
        ),
        (
            "integration_contract",
            "shared_database_v1",
            "The Validation Report integration contract is not supported.",
        ),
    ],
)
def test_rejects_unsupported_contract_or_version_with_sanitized_error(
    field: str,
    value: str,
    expected_detail: str,
):
    run_id = seed_run()
    report = json.loads(REPORT_PATH.read_bytes())
    report[field] = value

    with TestClient(app) as client:
        response = client.post(
            f"/api/evaluation-runs/{run_id}/external-safety-evidence",
            json=report,
        )

    assert response.status_code == 422
    assert response.json() == {"detail": expected_detail}


@pytest.mark.parametrize(
    "mutation",
    [
        "extra",
        "missing",
        "invalid_fingerprint",
        "integrity_notice",
        "type_drift",
        "nested_extra",
        "nested_missing",
        "verdict_mismatch",
    ],
)
def test_rejects_contract_shape_drift_and_invalid_source_claims(mutation: str):
    run_id = seed_run()
    report = json.loads(REPORT_PATH.read_bytes())
    if mutation == "extra":
        report["unexpected"] = "field"
    elif mutation == "missing":
        del report["candidate"]["verdict"]
    elif mutation == "invalid_fingerprint":
        report["candidate"]["evidence_fingerprint"] = "NOT-A-SHA256"
    elif mutation == "integrity_notice":
        report["integrity_notice"] = "This report is cryptographically signed."
    elif mutation == "type_drift":
        report["baseline"]["evidence_timeline"][0]["sequence"] = "1"
    elif mutation == "nested_extra":
        report["candidate"]["evidence_timeline"][-1]["content"]["unexpected"] = True
    elif mutation == "nested_missing":
        del report["candidate"]["evidence_timeline"][-1]["content"]["status"]
    else:
        report["candidate"]["verdict"]["status"] = "ineffective"

    with TestClient(app) as client:
        response = client.post(
            f"/api/evaluation-runs/{run_id}/external-safety-evidence",
            json=report,
        )

    assert response.status_code == 422
    assert response.json() == {
        "detail": "The file is not a supported Validation Report."
    }
    with SessionLocal() as session:
        assert session.query(ExternalSafetyEvidence).count() == 0


@pytest.mark.parametrize("mutation", ["exponent_overflow", "lone_surrogate"])
def test_rejects_json_that_cannot_be_canonicalized(mutation: str):
    run_id = seed_run()
    if mutation == "exponent_overflow":
        body = REPORT_PATH.read_text(encoding="utf-8").replace(
            '"sequence": 1',
            '"sequence": 1e100000',
            1,
        ).encode("utf-8")
    else:
        report = json.loads(REPORT_PATH.read_bytes())
        report["baseline"]["evidence_timeline"][0]["content"]["text"] = "\ud800"
        body = json.dumps(report).encode("utf-8")

    with TestClient(app) as client:
        response = client.post(
            f"/api/evaluation-runs/{run_id}/external-safety-evidence",
            content=body,
            headers={"Content-Type": "application/json"},
        )

    assert response.status_code == 422
    assert response.json() == {
        "detail": "The file is not a supported Validation Report."
    }
    with SessionLocal() as session:
        assert session.query(ExternalSafetyEvidence).count() == 0


def test_requires_an_existing_completed_evaluation_run():
    pending_run_id = seed_run(status="pending")

    with TestClient(app) as client:
        pending = client.post(
            f"/api/evaluation-runs/{pending_run_id}/external-safety-evidence",
            content=REPORT_PATH.read_bytes(),
            headers={"Content-Type": "application/json"},
        )
        missing = client.post(
            "/api/evaluation-runs/missing/external-safety-evidence",
            content=REPORT_PATH.read_bytes(),
            headers={"Content-Type": "application/json"},
        )

    assert pending.status_code == 409
    assert pending.json() == {
        "detail": "External Safety Evidence requires a completed Evaluation Run."
    }
    assert missing.status_code == 404


def test_external_safety_evidence_has_no_mutation_or_delete_endpoint():
    run_id = seed_run()
    endpoint = f"/api/evaluation-runs/{run_id}/external-safety-evidence"

    with TestClient(app) as client:
        imported = client.post(
            endpoint,
            content=REPORT_PATH.read_bytes(),
            headers={"Content-Type": "application/json"},
        )
        assert imported.status_code == 201
        patched = client.patch(endpoint, json={"candidate_verdict": "effective"})
        deleted = client.delete(endpoint)

    assert patched.status_code == 405
    assert deleted.status_code == 405


def test_openapi_documents_raw_json_import_and_idempotent_responses():
    with TestClient(app) as client:
        operation = client.get("/openapi.json").json()["paths"][
            "/api/evaluation-runs/{run_id}/external-safety-evidence"
        ]["post"]

    assert operation["requestBody"]["required"] is True
    assert "application/json" in operation["requestBody"]["content"]
    assert operation["requestBody"]["content"]["application/json"]["schema"] == {
        "type": "object",
        "description": (
            "Agent Incident Replay Lab validation_report_json_file_only schema v1.0."
        ),
    }
    assert {"200", "201", "422"} <= set(operation["responses"])
