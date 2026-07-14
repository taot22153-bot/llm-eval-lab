from typing import Annotated, Any

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from llm_eval_lab.database import get_session
from llm_eval_lab.models import EvaluationSuite
from llm_eval_lab.schemas import EvaluationSuiteDetail, EvaluationSuiteSummary

router = APIRouter(prefix="/api/evaluation-suites", tags=["evaluation suites"])
DatabaseSession = Annotated[Session, Depends(get_session)]


def _suite_payload(suite: EvaluationSuite) -> dict[str, Any]:
    return {
        "id": suite.id,
        "slug": suite.slug,
        "version": suite.version,
        "name": suite.name,
        "description": suite.description,
        "test_case_count": len(suite.test_cases),
    }


@router.get("", response_model=list[EvaluationSuiteSummary])
def list_evaluation_suites(session: DatabaseSession) -> list[dict[str, Any]]:
    statement = (
        select(EvaluationSuite)
        .options(selectinload(EvaluationSuite.test_cases))
        .order_by(EvaluationSuite.slug, EvaluationSuite.version.desc())
    )
    return [_suite_payload(suite) for suite in session.scalars(statement)]


@router.get("/{evaluation_suite_id}", response_model=EvaluationSuiteDetail)
def get_evaluation_suite(
    evaluation_suite_id: str,
    session: DatabaseSession,
) -> dict[str, Any]:
    statement = (
        select(EvaluationSuite)
        .where(EvaluationSuite.id == evaluation_suite_id)
        .options(selectinload(EvaluationSuite.test_cases))
    )
    suite = session.scalar(statement)
    if suite is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Evaluation Suite {evaluation_suite_id} was not found.",
        )
    return {**_suite_payload(suite), "test_cases": suite.test_cases}
