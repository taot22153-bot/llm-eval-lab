from typing import Annotated, Literal

from fastapi import APIRouter, Depends, Query
from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from llm_eval_lab.database import get_session
from llm_eval_lab.models import HumanReviewItem, TestCaseExecution
from llm_eval_lab.schemas import HumanReviewQueueItemRead

router = APIRouter(prefix="/api/human-review-items", tags=["human review"])
DatabaseSession = Annotated[Session, Depends(get_session)]


@router.get("", response_model=list[HumanReviewQueueItemRead])
def list_human_review_items(
    session: DatabaseSession,
    status: Literal["pending", "resolved"] = "pending",
    limit: Annotated[int, Query(ge=1, le=200)] = 100,
) -> list[dict[str, object]]:
    statement = (
        select(HumanReviewItem)
        .where(HumanReviewItem.status == status)
        .options(
            selectinload(HumanReviewItem.execution).selectinload(
                TestCaseExecution.test_case
            ),
            selectinload(HumanReviewItem.execution).selectinload(
                TestCaseExecution.application_version
            ),
        )
        .order_by(HumanReviewItem.created_at.asc())
        .limit(limit)
    )
    return [
        {
            "id": item.id,
            "test_case_execution_id": item.test_case_execution_id,
            "test_case_title": item.execution.test_case.title,
            "application_version_name": item.execution.application_version.name,
            "evaluation_run_id": item.execution.evaluation_run_id,
            "version_role": item.execution.version_role,
            "status": item.status,
            "reasons": item.reasons,
            "created_at": item.created_at,
            "resolved_at": item.resolved_at,
        }
        for item in session.scalars(statement)
    ]
