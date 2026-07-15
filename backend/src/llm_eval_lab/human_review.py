from datetime import UTC, datetime
from typing import Annotated, Literal

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from llm_eval_lab.database import get_session
from llm_eval_lab.models import DeterministicEvaluation, HumanReviewItem, TestCaseExecution
from llm_eval_lab.schemas import (
    HumanReviewDecisionCreate,
    HumanReviewDetailRead,
    HumanReviewQueueItemRead,
)
from llm_eval_lab.test_case_executions import serialize_test_case_execution

router = APIRouter(prefix="/api/human-review-items", tags=["human review"])
DatabaseSession = Annotated[Session, Depends(get_session)]


def _review_statement():
    return select(HumanReviewItem).options(
        selectinload(HumanReviewItem.execution).selectinload(
            TestCaseExecution.test_case
        ),
        selectinload(HumanReviewItem.execution).selectinload(
            TestCaseExecution.application_version
        ),
        selectinload(HumanReviewItem.execution)
        .selectinload(TestCaseExecution.deterministic_evaluation)
        .selectinload(DeterministicEvaluation.outcomes),
        selectinload(HumanReviewItem.execution).selectinload(
            TestCaseExecution.semantic_evaluation
        ),
        selectinload(HumanReviewItem.execution).selectinload(
            TestCaseExecution.human_review_item
        ),
    )


def _serialize_item(item: HumanReviewItem) -> dict[str, object]:
    return {
        "id": item.id,
        "test_case_execution_id": item.test_case_execution_id,
        "test_case_title": item.execution.test_case.title,
        "application_version_name": item.execution.application_version.name,
        "evaluation_run_id": item.execution.evaluation_run_id,
        "version_role": item.execution.version_role,
        "status": item.status,
        "reasons": item.reasons,
        "outcome": item.outcome,
        "rationale": item.rationale,
        "created_at": item.created_at,
        "resolved_at": item.resolved_at,
    }


def _load_item(
    session: Session,
    item_id: str,
    *,
    for_update: bool = False,
) -> HumanReviewItem | None:
    statement = _review_statement().where(HumanReviewItem.id == item_id)
    if for_update:
        statement = statement.with_for_update()
    return session.scalar(statement)


@router.get("", response_model=list[HumanReviewQueueItemRead])
def list_human_review_items(
    session: DatabaseSession,
    status: Literal["pending", "resolved"] = "pending",
    limit: Annotated[int, Query(ge=1, le=200)] = 100,
) -> list[dict[str, object]]:
    statement = (
        _review_statement()
        .where(HumanReviewItem.status == status)
        .order_by(HumanReviewItem.created_at.asc())
        .limit(limit)
    )
    return [_serialize_item(item) for item in session.scalars(statement)]


@router.get("/{item_id}", response_model=HumanReviewDetailRead)
def get_human_review_item(
    item_id: str,
    session: DatabaseSession,
) -> dict[str, object]:
    item = _load_item(session, item_id)
    if item is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Human Review item {item_id} was not found.",
        )
    return {**_serialize_item(item), "execution": serialize_test_case_execution(item.execution)}


@router.patch("/{item_id}", response_model=HumanReviewDetailRead)
def resolve_human_review_item(
    item_id: str,
    payload: HumanReviewDecisionCreate,
    session: DatabaseSession,
) -> dict[str, object]:
    item = _load_item(session, item_id, for_update=True)
    if item is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Human Review item {item_id} was not found.",
        )
    if item.status == "resolved":
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="This Human Review item has already been resolved.",
        )

    item.status = "resolved"
    item.outcome = payload.outcome
    item.rationale = payload.rationale
    item.resolved_at = datetime.now(UTC)
    session.commit()
    item = _load_item(session, item_id)
    if item is None:
        raise RuntimeError("The Human Review item was not persisted.")
    return {**_serialize_item(item), "execution": serialize_test_case_execution(item.execution)}
