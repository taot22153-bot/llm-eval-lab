from __future__ import annotations

from datetime import UTC, datetime
from time import perf_counter
from typing import Annotated, Any

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from llm_eval_lab.database import SessionLocal, get_session
from llm_eval_lab.model_provider import (
    ModelProviderFailure,
    ModelProviderRegistry,
    ModelRequest,
    get_model_provider_registry,
)
from llm_eval_lab.models import ApplicationVersion, EvaluationRun, TestCase, TestCaseExecution
from llm_eval_lab.schemas import TestCaseExecutionCreate, TestCaseExecutionRead

router = APIRouter(prefix="/api/test-case-executions", tags=["test case executions"])
DatabaseSession = Annotated[Session, Depends(get_session)]
ProviderRegistry = Annotated[ModelProviderRegistry, Depends(get_model_provider_registry)]


def _build_user_prompt(test_case: TestCase) -> str:
    grounding = "\n".join(
        f"- {material['title']}: {material['content']}"
        for material in test_case.grounding_material
    )
    return f"Grounding material:\n{grounding}\n\nUser input:\n{test_case.user_input}"


def _load_execution(session: Session, execution_id: str) -> TestCaseExecution | None:
    statement = (
        select(TestCaseExecution)
        .where(TestCaseExecution.id == execution_id)
        .options(
            selectinload(TestCaseExecution.application_version),
            selectinload(TestCaseExecution.test_case),
        )
    )
    return session.scalar(statement)


def serialize_test_case_execution(execution: TestCaseExecution) -> dict[str, Any]:
    return {
        "id": execution.id,
        "application_version_id": execution.application_version_id,
        "application_version_name": execution.application_version.name,
        "test_case_id": execution.test_case_id,
        "test_case_key": execution.test_case.key,
        "test_case_title": execution.test_case.title,
        "status": execution.status,
        "prompt_context": execution.prompt_context,
        "model_response": execution.model_response,
        "usage": execution.usage,
        "latency_ms": execution.latency_ms,
        "error": execution.error,
        "created_at": execution.created_at,
        "started_at": execution.started_at,
        "completed_at": execution.completed_at,
    }


def new_test_case_execution(
    application_version: ApplicationVersion,
    test_case: TestCase,
    *,
    evaluation_run: EvaluationRun | None = None,
    version_role: str | None = None,
) -> TestCaseExecution:
    user_prompt = _build_user_prompt(test_case)
    return TestCaseExecution(
        application_version=application_version,
        test_case=test_case,
        evaluation_run=evaluation_run,
        version_role=version_role,
        status="pending",
        prompt_context={
            "model_provider": application_version.model_provider,
            "model_name": application_version.model_name,
            "system_prompt": application_version.system_prompt,
            "generation_parameters": application_version.generation_parameters,
            "grounding_material": test_case.grounding_material,
            "user_input": test_case.user_input,
            "user_prompt": user_prompt,
        },
    )


def run_test_case_execution(
    execution_id: str,
    provider_registry: ModelProviderRegistry,
) -> None:
    with SessionLocal() as session:
        execution = _load_execution(session, execution_id)
        if execution is None or execution.status != "pending":
            return

        execution.status = "running"
        execution.started_at = datetime.now(UTC)
        session.commit()

        started = perf_counter()
        try:
            prompt_context = execution.prompt_context
            request = ModelRequest(
                model=str(prompt_context["model_name"]),
                system_prompt=str(prompt_context["system_prompt"]),
                user_prompt=str(prompt_context["user_prompt"]),
                generation_parameters=dict(prompt_context["generation_parameters"]),
            )
            provider = provider_registry.get(str(prompt_context["model_provider"]))
            response = provider.generate(request)
        except ModelProviderFailure as failure:
            execution.status = "failed"
            execution.error = {"code": failure.code, "message": failure.message}
        except Exception:
            execution.status = "failed"
            execution.error = {
                "code": "provider_failure",
                "message": "The model provider failed unexpectedly. Check the local provider logs.",
            }
        else:
            execution.status = "completed"
            execution.model_response = response.content
            execution.usage = {
                "prompt_tokens": response.usage.prompt_tokens,
                "completion_tokens": response.usage.completion_tokens,
                "total_tokens": response.usage.total_tokens,
            }
        finally:
            execution.latency_ms = round((perf_counter() - started) * 1000)
            execution.completed_at = datetime.now(UTC)
            session.commit()


def reconcile_interrupted_test_case_executions() -> None:
    with SessionLocal() as session:
        statement = select(TestCaseExecution).where(
            TestCaseExecution.status.in_(("pending", "running"))
        )
        interrupted = list(session.scalars(statement))
        if not interrupted:
            return

        completed_at = datetime.now(UTC)
        for execution in interrupted:
            execution.status = "failed"
            execution.error = {
                "code": "execution_interrupted",
                "message": (
                    "Execution was interrupted by an application restart. Run the Test Case again."
                ),
            }
            execution.completed_at = completed_at
        session.commit()


@router.post("", response_model=TestCaseExecutionRead, status_code=status.HTTP_201_CREATED)
def create_test_case_execution(
    payload: TestCaseExecutionCreate,
    background_tasks: BackgroundTasks,
    session: DatabaseSession,
    provider_registry: ProviderRegistry,
) -> dict[str, Any]:
    application_version = session.get(ApplicationVersion, payload.application_version_id)
    if application_version is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Application Version {payload.application_version_id} was not found.",
        )
    test_case = session.get(TestCase, payload.test_case_id)
    if test_case is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Test Case {payload.test_case_id} was not found.",
        )

    execution = new_test_case_execution(application_version, test_case)
    session.add(execution)
    session.commit()
    session.refresh(execution)

    response = serialize_test_case_execution(execution)
    background_tasks.add_task(run_test_case_execution, execution.id, provider_registry)
    return response


@router.get("/{execution_id}", response_model=TestCaseExecutionRead)
def get_test_case_execution(
    execution_id: str,
    session: DatabaseSession,
) -> dict[str, Any]:
    execution = _load_execution(session, execution_id)
    if execution is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Test Case Execution {execution_id} was not found.",
        )
    return serialize_test_case_execution(execution)
