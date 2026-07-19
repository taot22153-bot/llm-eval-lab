from __future__ import annotations

import hashlib
import json
import math
from dataclasses import dataclass
from typing import Annotated, Literal

from fastapi import APIRouter, Depends, HTTPException, Request, Response, status
from pydantic import BaseModel, ConfigDict, Field, JsonValue, ValidationError, model_validator
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session, defer

from llm_eval_lab.database import get_session
from llm_eval_lab.models import EvaluationRun, ExternalSafetyEvidence
from llm_eval_lab.schemas import ExternalSafetyEvidenceRead

MAX_REPORT_BYTES = 1024 * 1024
SOURCE_PRODUCT = "agent_incident_replay_lab"
SHA256_PATTERN = r"^[0-9a-f]{64}$"

router = APIRouter(
    prefix="/api/evaluation-runs/{run_id}/external-safety-evidence",
    tags=["external safety evidence"],
)
DatabaseSession = Annotated[Session, Depends(get_session)]


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)


class SourceAgentPolicy(StrictModel):
    external_email: Literal["allow", "require_approval", "block"]


class SourceAgentVersion(StrictModel):
    agent_version_id: str = Field(min_length=1, max_length=160)
    role: Literal["baseline", "candidate"]
    instructions: list[str]
    deterministic_model_behavior: Literal["follow_ticket_instruction"]
    tool_grants: list[Literal["virtual.email.send", "virtual.case_note.create"]]
    policy: SourceAgentPolicy
    approval_requirements: list[Literal["virtual.email.send"]]


class SourceValidationPair(StrictModel):
    pair_id: str = Field(min_length=1, max_length=80)
    bundle_id: str = Field(min_length=1, max_length=160)
    bundle_digest: str = Field(pattern=SHA256_PATTERN)
    baseline_run_id: str = Field(min_length=1)
    candidate_run_id: str = Field(min_length=1)
    declared_repair: Literal["external_email_policy:allow->require_approval"]
    baseline_agent_version: SourceAgentVersion
    candidate_agent_version: SourceAgentVersion


class SourceEvidenceReference(StrictModel):
    sequence: int = Field(ge=1)
    kind: str = Field(min_length=1)
    causal_id: str = Field(min_length=1)


class SourceDivergencePoint(StrictModel):
    summary: str = Field(min_length=1)
    baseline_evidence: list[SourceEvidenceReference]
    candidate_evidence: list[SourceEvidenceReference]


class SourceValidationVerdict(StrictModel):
    status: Literal["effective", "ineffective", "inconclusive"]
    explanation: str = Field(min_length=1)


class SourceTextContent(StrictModel):
    text: str = Field(min_length=1)


class SourceEmailToolRequest(StrictModel):
    tool_name: Literal["virtual.email.send"]
    recipient: str = Field(min_length=3, max_length=320)
    body: str


class SourceCaseNoteToolRequest(StrictModel):
    tool_name: Literal["virtual.case_note.create"]
    ticket_id: str = Field(min_length=1, max_length=100)
    body: str


class SourcePolicyEvaluation(StrictModel):
    action: Literal["virtual.case_note.create", "virtual.email.send"]
    decision: Literal["allowed", "blocked", "approval_required"]
    rationale: str = Field(min_length=1)


class SourceVirtualEffect(StrictModel):
    tool_name: Literal["virtual.case_note.create", "virtual.email.send"]
    status: Literal["applied", "not_applied", "failed"]
    summary: str = Field(min_length=1)


class SourceApprovalRequest(StrictModel):
    approval_request_id: str = Field(min_length=1)
    action: Literal["virtual.email.send"]
    recipient: str = Field(min_length=3, max_length=320)
    payload_sha256: str = Field(pattern=SHA256_PATTERN)
    status: Literal["pending"]
    reason: str = Field(min_length=1)


class SourceLegacyApprovalRequest(StrictModel):
    approval_request_id: str = Field(min_length=1)
    action: Literal["virtual.email.send"]
    status: Literal["pending"]
    reason: str = Field(min_length=1)


class SourceNormalizedApprovalRequest(StrictModel):
    action: Literal["virtual.email.send"]
    recipient: str = Field(min_length=3, max_length=320)
    payload_sha256: str = Field(pattern=SHA256_PATTERN)
    status: Literal["pending"]
    reason: str = Field(min_length=1)


class SourceNormalizedLegacyApprovalRequest(StrictModel):
    action: Literal["virtual.email.send"]
    status: Literal["pending"]
    reason: str = Field(min_length=1)


class SourceApprovalDecision(StrictModel):
    approval_request_id: str = Field(min_length=1)
    action: Literal["virtual.email.send"]
    recipient: str = Field(min_length=3, max_length=320)
    payload_sha256: str = Field(pattern=SHA256_PATTERN)
    decision: Literal["approve", "deny"]
    decided_by: Literal["operator", "deterministic_approval_script"]


class SourceNormalizedApprovalDecision(StrictModel):
    action: Literal["virtual.email.send"]
    recipient: str = Field(min_length=3, max_length=320)
    payload_sha256: str = Field(pattern=SHA256_PATTERN)
    decision: Literal["approve", "deny"]
    decided_by: Literal["operator", "deterministic_approval_script"]


class SourceTaskOutcome(StrictModel):
    status: Literal["completed", "failed", "pending"]
    summary: str = Field(min_length=1)


class SourceSafetyViolation(StrictModel):
    action: str = Field(min_length=1)
    condition: str = Field(min_length=1)
    evidence_causal_id: str = Field(min_length=1)


class SourceSafetyOutcome(StrictModel):
    status: Literal["satisfied", "violated", "inconclusive"]
    violations: list[SourceSafetyViolation]


def _validate_event_content(
    kind: str,
    content: dict[str, JsonValue],
    *,
    normalized: bool,
) -> None:
    content_model: type[StrictModel]
    if kind == "tool_requested":
        content_model = (
            SourceEmailToolRequest
            if content.get("tool_name") == "virtual.email.send"
            else SourceCaseNoteToolRequest
        )
    elif kind == "approval_requested":
        has_binding = "recipient" in content or "payload_sha256" in content
        if normalized:
            content_model = (
                SourceNormalizedApprovalRequest
                if has_binding
                else SourceNormalizedLegacyApprovalRequest
            )
        else:
            content_model = SourceApprovalRequest if has_binding else SourceLegacyApprovalRequest
    elif kind == "approval_decided":
        content_model = (
            SourceNormalizedApprovalDecision if normalized else SourceApprovalDecision
        )
    else:
        content_models: dict[str, type[StrictModel]] = {
            "task_received": SourceTextContent,
            "model_output": SourceTextContent,
            "policy_evaluated": SourcePolicyEvaluation,
            "virtual_effect": SourceVirtualEffect,
            "task_outcome": SourceTaskOutcome,
            "safety_evaluated": SourceSafetyOutcome,
            "validation_paused": SourceValidationVerdict,
            "validation_verdict": SourceValidationVerdict,
        }
        content_model = content_models.get(kind)  # type: ignore[assignment]
        if content_model is None:
            raise ValueError("The timeline contains an unsupported event kind.")
    content_model.model_validate(content)


class SourceEvidenceEvent(StrictModel):
    sequence: int = Field(ge=1)
    kind: str = Field(min_length=1)
    causal_id: str = Field(min_length=1)
    caused_by: list[str]
    content: dict[str, JsonValue]

    @model_validator(mode="after")
    def validate_content(self) -> SourceEvidenceEvent:
        _validate_event_content(self.kind, self.content, normalized=False)
        return self


class SourceNormalizedEvent(StrictModel):
    alignment_key: str = Field(min_length=1)
    kind: str = Field(min_length=1)
    causal_role: str = Field(min_length=1)
    caused_by: list[str]
    content: dict[str, JsonValue]

    @model_validator(mode="after")
    def validate_content(self) -> SourceNormalizedEvent:
        _validate_event_content(self.kind, self.content, normalized=True)
        return self


class SourceRunEvidence(StrictModel):
    agent_version: SourceAgentVersion
    verdict: SourceValidationVerdict
    verdict_evidence: list[SourceEvidenceReference] = Field(min_length=1)
    evidence_fingerprint: str = Field(pattern=SHA256_PATTERN)
    evidence_timeline: list[SourceEvidenceEvent] = Field(min_length=1)
    normalized_timeline: list[SourceNormalizedEvent] = Field(min_length=1)

    @model_validator(mode="after")
    def validate_timeline_consistency(self) -> SourceRunEvidence:
        sequences = [event.sequence for event in self.evidence_timeline]
        if sequences != list(range(1, len(self.evidence_timeline) + 1)):
            raise ValueError("Evidence timeline sequences must be contiguous and ordered.")
        if [event.kind for event in self.evidence_timeline] != [
            event.kind for event in self.normalized_timeline
        ]:
            raise ValueError("Normalized timeline does not align with source evidence.")
        terminal_events = [
            event for event in self.evidence_timeline if event.kind == "validation_verdict"
        ]
        normalized_terminal_events = [
            event for event in self.normalized_timeline if event.kind == "validation_verdict"
        ]
        if len(terminal_events) != 1 or len(normalized_terminal_events) != 1:
            raise ValueError("Validation evidence must contain one terminal verdict.")
        terminal_verdict = SourceValidationVerdict.model_validate(terminal_events[0].content)
        normalized_verdict = SourceValidationVerdict.model_validate(
            normalized_terminal_events[0].content
        )
        if terminal_verdict != self.verdict or normalized_verdict != self.verdict:
            raise ValueError("Declared verdict does not match terminal evidence.")
        if [reference.kind for reference in self.verdict_evidence] != [
            "task_outcome",
            "safety_evaluated",
            "validation_verdict",
        ]:
            raise ValueError("Verdict evidence is incomplete or out of order.")
        timeline_references = {
            (event.sequence, event.kind, event.causal_id) for event in self.evidence_timeline
        }
        if any(
            (reference.sequence, reference.kind, reference.causal_id)
            not in timeline_references
            for reference in self.verdict_evidence
        ):
            raise ValueError("Verdict evidence does not reference the source timeline.")
        return self


class SourceValidationReport(StrictModel):
    schema_version: Literal["1.0"]
    validation_pair: SourceValidationPair
    divergence_point: SourceDivergencePoint
    baseline: SourceRunEvidence
    candidate: SourceRunEvidence
    integrity_notice: Literal[
        "SHA-256 fingerprints support integrity comparison only; they do not provide "
        "encryption, signer identity, or non-repudiation."
    ]
    integration_contract: Literal["validation_report_json_file_only"]

    @model_validator(mode="after")
    def validate_pair_consistency(self) -> SourceValidationReport:
        pair = self.validation_pair
        if pair.baseline_agent_version != self.baseline.agent_version:
            raise ValueError("Baseline Agent Version does not match the Validation Pair.")
        if pair.candidate_agent_version != self.candidate.agent_version:
            raise ValueError("Candidate Agent Version does not match the Validation Pair.")
        if self.baseline.agent_version.role != "baseline":
            raise ValueError("Baseline evidence has the wrong role.")
        if self.candidate.agent_version.role != "candidate":
            raise ValueError("Candidate evidence has the wrong role.")
        for references, evidence in (
            (self.divergence_point.baseline_evidence, self.baseline),
            (self.divergence_point.candidate_evidence, self.candidate),
        ):
            timeline_references = {
                (event.sequence, event.kind, event.causal_id)
                for event in evidence.evidence_timeline
            }
            if any(
                (reference.sequence, reference.kind, reference.causal_id)
                not in timeline_references
                for reference in references
            ):
                raise ValueError("Divergence evidence does not reference the source timeline.")
        return self


class AdmissionError(ValueError):
    pass


@dataclass(frozen=True)
class AdmittedReport:
    report: SourceValidationReport
    canonical_json: str
    source_digest: str


def admit_report(raw: bytes) -> AdmittedReport:
    if len(raw) > MAX_REPORT_BYTES:
        raise AdmissionError("The report exceeds the 1 MiB import limit.")
    try:
        decoded = raw.decode("utf-8")
        source = json.loads(
            decoded,
            object_pairs_hook=_reject_duplicate_object_members,
            parse_constant=_reject_nonstandard_json_constant,
            parse_float=_parse_finite_float,
        )
        if not isinstance(source, dict):
            raise ValueError
        if (
            "integration_contract" in source
            and source["integration_contract"] != "validation_report_json_file_only"
        ):
            raise AdmissionError(
                "The Validation Report integration contract is not supported."
            )
        if "schema_version" in source and source["schema_version"] != "1.0":
            raise AdmissionError(
                "The Validation Report schema version is not supported."
            )
        report = SourceValidationReport.model_validate(source)
        canonical_json = json.dumps(
            source,
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=False,
            allow_nan=False,
        )
        canonical_bytes = canonical_json.encode("utf-8")
    except AdmissionError:
        raise
    except (
        UnicodeDecodeError,
        UnicodeEncodeError,
        json.JSONDecodeError,
        ValidationError,
        ValueError,
        RecursionError,
    ) as error:
        raise AdmissionError("The file is not a supported Validation Report.") from error
    return AdmittedReport(
        report=report,
        canonical_json=canonical_json,
        source_digest=hashlib.sha256(canonical_bytes).hexdigest(),
    )


def _reject_nonstandard_json_constant(_: str) -> None:
    raise ValueError


def _reject_duplicate_object_members(
    members: list[tuple[str, JsonValue]],
) -> dict[str, JsonValue]:
    parsed: dict[str, JsonValue] = {}
    for name, value in members:
        if name in parsed:
            raise ValueError
        parsed[name] = value
    return parsed


def _parse_finite_float(value: str) -> float:
    parsed = float(value)
    if not math.isfinite(parsed):
        raise ValueError
    return parsed


async def _read_report_bytes(request: Request) -> bytes:
    body = bytearray()
    async for chunk in request.stream():
        if len(body) + len(chunk) > MAX_REPORT_BYTES:
            raise AdmissionError("The report exceeds the 1 MiB import limit.")
        body.extend(chunk)
    return bytes(body)


def _find_run(session: Session, run_id: str) -> EvaluationRun:
    evaluation_run = session.get(EvaluationRun, run_id)
    if evaluation_run is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Evaluation Run {run_id} was not found.",
        )
    if evaluation_run.status != "completed":
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="External Safety Evidence requires a completed Evaluation Run.",
        )
    return evaluation_run


def _evidence_summary_statement():
    return select(ExternalSafetyEvidence).options(
        defer(ExternalSafetyEvidence.canonical_json)
    )


@router.post(
    "",
    response_model=ExternalSafetyEvidenceRead,
    status_code=status.HTTP_201_CREATED,
    responses={
        status.HTTP_200_OK: {
            "model": ExternalSafetyEvidenceRead,
            "description": "The identical report was already admitted for this run.",
        }
    },
    openapi_extra={
        "requestBody": {
            "required": True,
            "content": {
                "application/json": {
                    "schema": {
                        "type": "object",
                        "description": (
                            "Agent Incident Replay Lab "
                            "validation_report_json_file_only schema v1.0."
                        ),
                    }
                }
            },
        }
    },
)
async def import_external_safety_evidence(
    run_id: str,
    request: Request,
    response: Response,
    session: DatabaseSession,
) -> ExternalSafetyEvidence:
    evaluation_run = _find_run(session, run_id)
    if request.headers.get("content-type", "").split(";", 1)[0].strip().lower() != (
        "application/json"
    ):
        raise HTTPException(
            status_code=status.HTTP_415_UNSUPPORTED_MEDIA_TYPE,
            detail="External Safety Evidence must be application/json.",
        )
    try:
        admitted = admit_report(await _read_report_bytes(request))
    except AdmissionError as error:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail=str(error),
        ) from error

    existing_statement = _evidence_summary_statement().where(
        ExternalSafetyEvidence.evaluation_run_id == run_id,
        ExternalSafetyEvidence.source_digest == admitted.source_digest,
    )
    existing = session.scalar(existing_statement)
    if existing is not None:
        response.status_code = status.HTTP_200_OK
        return existing

    report = admitted.report
    evidence = ExternalSafetyEvidence(
        evaluation_run=evaluation_run,
        source_product=SOURCE_PRODUCT,
        integration_contract=report.integration_contract,
        schema_version=report.schema_version,
        source_digest=admitted.source_digest,
        source_bundle_id=report.validation_pair.bundle_id,
        source_pair_id=report.validation_pair.pair_id,
        baseline_agent_version_id=report.baseline.agent_version.agent_version_id,
        candidate_agent_version_id=report.candidate.agent_version.agent_version_id,
        baseline_evidence_fingerprint=report.baseline.evidence_fingerprint,
        candidate_evidence_fingerprint=report.candidate.evidence_fingerprint,
        baseline_verdict=report.baseline.verdict.status,
        candidate_verdict=report.candidate.verdict.status,
        divergence_summary=report.divergence_point.summary,
        canonical_json=admitted.canonical_json,
    )
    session.add(evidence)
    try:
        session.commit()
    except IntegrityError:
        session.rollback()
        concurrent_evidence = session.scalar(existing_statement)
        if concurrent_evidence is None:
            raise
        response.status_code = status.HTTP_200_OK
        return concurrent_evidence
    session.refresh(evidence)
    response.status_code = status.HTTP_201_CREATED
    return evidence


@router.get("", response_model=list[ExternalSafetyEvidenceRead])
def list_external_safety_evidence(
    run_id: str,
    session: DatabaseSession,
) -> list[ExternalSafetyEvidence]:
    _find_run(session, run_id)
    statement = (
        _evidence_summary_statement()
        .where(ExternalSafetyEvidence.evaluation_run_id == run_id)
        .order_by(ExternalSafetyEvidence.imported_at.desc(), ExternalSafetyEvidence.id)
    )
    return list(session.scalars(statement))
