from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from llm_eval_lab.database import get_session
from llm_eval_lab.models import ApplicationVersion
from llm_eval_lab.schemas import ApplicationVersionCreate, ApplicationVersionRead

router = APIRouter(prefix="/api/application-versions", tags=["application versions"])
DatabaseSession = Annotated[Session, Depends(get_session)]


@router.post("", response_model=ApplicationVersionRead, status_code=status.HTTP_201_CREATED)
def create_application_version(
    payload: ApplicationVersionCreate,
    session: DatabaseSession,
) -> ApplicationVersion:
    application_version = ApplicationVersion(**payload.model_dump())
    session.add(application_version)
    session.commit()
    session.refresh(application_version)
    return application_version


@router.get("", response_model=list[ApplicationVersionRead])
def list_application_versions(session: DatabaseSession) -> list[ApplicationVersion]:
    statement = select(ApplicationVersion).order_by(
        ApplicationVersion.created_at.desc(),
        ApplicationVersion.id.desc(),
    )
    return list(session.scalars(statement))


@router.api_route("/{application_version_id}", methods=["PUT", "PATCH"], include_in_schema=False)
def reject_application_version_update(application_version_id: str) -> None:
    raise HTTPException(
        status_code=status.HTTP_405_METHOD_NOT_ALLOWED,
        detail=(
            f"Application Version {application_version_id} is immutable; "
            "create a new version instead."
        ),
    )
