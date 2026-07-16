from typing import Annotated, Any

from fastapi import APIRouter, Depends, HTTPException, Query, Response, status
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session, selectinload

from llm_eval_lab.database import get_session
from llm_eval_lab.evaluation_runs import load_evaluation_run
from llm_eval_lab.models import ReleaseDecision, ReleaseRule
from llm_eval_lab.release_decision_policy import evaluate_release
from llm_eval_lab.schemas import (
    ReleaseDecisionCreate,
    ReleaseDecisionRead,
    ReleaseRuleCreate,
    ReleaseRuleRead,
)

release_rules_router = APIRouter(prefix="/api/release-rules", tags=["release rules"])
release_decisions_router = APIRouter(
    prefix="/api/release-decisions",
    tags=["release decisions"],
)
DatabaseSession = Annotated[Session, Depends(get_session)]


def _decision_statement():
    return select(ReleaseDecision).options(selectinload(ReleaseDecision.release_rule))


def _serialize_decision(decision: ReleaseDecision) -> dict[str, Any]:
    return {
        "id": decision.id,
        "evaluation_run_id": decision.evaluation_run_id,
        "release_rule": {
            "id": decision.release_rule.id,
            "slug": decision.release_rule.slug,
            "version": decision.release_rule.version,
            "name": decision.release_rule.name,
        },
        "outcome": decision.outcome,
        "reasons": decision.reasons,
        "metrics": decision.metrics,
        "evidence_fingerprint": decision.evidence_fingerprint,
        "created_at": decision.created_at,
    }


@release_rules_router.post("", response_model=ReleaseRuleRead, status_code=201)
def create_release_rule(
    payload: ReleaseRuleCreate,
    session: DatabaseSession,
) -> ReleaseRule:
    release_rule = ReleaseRule(**payload.model_dump())
    session.add(release_rule)
    try:
        session.commit()
    except IntegrityError as error:
        session.rollback()
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Release Rule {payload.slug} v{payload.version} already exists.",
        ) from error
    session.refresh(release_rule)
    return release_rule


@release_rules_router.get("", response_model=list[ReleaseRuleRead])
def list_release_rules(session: DatabaseSession) -> list[ReleaseRule]:
    statement = select(ReleaseRule).order_by(ReleaseRule.slug, ReleaseRule.version.desc())
    return list(session.scalars(statement))


@release_decisions_router.post("", response_model=ReleaseDecisionRead, status_code=201)
def create_release_decision(
    payload: ReleaseDecisionCreate,
    response: Response,
    session: DatabaseSession,
) -> dict[str, Any]:
    evaluation_run = load_evaluation_run(session, payload.evaluation_run_id)
    release_rule = session.get(ReleaseRule, payload.release_rule_id)
    if evaluation_run is None or release_rule is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="The selected Evaluation Run or Release Rule was not found.",
        )
    if evaluation_run.status != "completed":
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="A Release Decision requires a completed Evaluation Run.",
        )

    result = evaluate_release(evaluation_run, release_rule)
    existing_statement = _decision_statement().where(
        ReleaseDecision.evaluation_run_id == evaluation_run.id,
        ReleaseDecision.release_rule_id == release_rule.id,
        ReleaseDecision.evidence_fingerprint == result.evidence_fingerprint,
    )
    existing = session.scalar(existing_statement)
    if existing is not None:
        response.status_code = status.HTTP_200_OK
        return _serialize_decision(existing)

    decision = ReleaseDecision(
        evaluation_run=evaluation_run,
        release_rule=release_rule,
        outcome=result.outcome,
        reasons=result.reasons,
        metrics=result.metrics,
        evidence_fingerprint=result.evidence_fingerprint,
    )
    session.add(decision)
    try:
        session.commit()
    except IntegrityError:
        session.rollback()
        concurrent_decision = session.scalar(existing_statement)
        if concurrent_decision is None:
            raise
        response.status_code = status.HTTP_200_OK
        return _serialize_decision(concurrent_decision)
    session.expire_all()
    decision = session.scalar(_decision_statement().where(ReleaseDecision.id == decision.id))
    if decision is None:
        raise RuntimeError("The Release Decision was not persisted.")
    return _serialize_decision(decision)


@release_decisions_router.get("", response_model=list[ReleaseDecisionRead])
def list_release_decisions(
    session: DatabaseSession,
    evaluation_run_id: str,
    limit: Annotated[int, Query(ge=1, le=100)] = 20,
) -> list[dict[str, Any]]:
    statement = (
        _decision_statement()
        .where(ReleaseDecision.evaluation_run_id == evaluation_run_id)
        .order_by(ReleaseDecision.created_at.desc(), ReleaseDecision.id.desc())
        .limit(limit)
    )
    return [_serialize_decision(decision) for decision in session.scalars(statement)]
