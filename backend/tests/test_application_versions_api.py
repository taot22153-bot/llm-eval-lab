import os
from pathlib import Path

import pytest
from dotenv import load_dotenv
from fastapi.testclient import TestClient

load_dotenv(Path(__file__).parents[2] / ".env")
os.environ["DATABASE_URL"] = os.environ["TEST_DATABASE_URL"]

from llm_eval_lab.database import Base, engine  # noqa: E402
from llm_eval_lab.main import app  # noqa: E402


@pytest.fixture(autouse=True)
def reset_database():
    Base.metadata.drop_all(bind=engine)
    Base.metadata.create_all(bind=engine)
    yield
    Base.metadata.drop_all(bind=engine)


def test_evaluation_user_can_create_and_list_an_application_version():
    payload = {
        "name": "Store support baseline",
        "model_provider": "ollama",
        "model_name": "qwen3:8b",
        "system_prompt": "Answer only from the supplied store policies.",
        "generation_parameters": {"temperature": 0.1, "top_p": 0.9},
        "knowledge_config": {"source": "sample-store-policies-v1"},
        "tool_config": None,
    }

    with TestClient(app) as client:
        create_response = client.post("/api/application-versions", json=payload)

    with TestClient(app) as restarted_client:
        list_response = restarted_client.get("/api/application-versions")

    assert create_response.status_code == 201
    created = create_response.json()
    assert created == {
        "id": created["id"],
        **payload,
        "created_at": created["created_at"],
    }
    assert created["id"]
    assert created["created_at"].endswith("Z")

    assert list_response.status_code == 200
    assert list_response.json() == [created]


def test_published_application_version_cannot_be_edited_in_place():
    payload = {
        "name": "Store support baseline",
        "model_provider": "ollama",
        "model_name": "qwen3:8b",
        "system_prompt": "Answer only from the supplied store policies.",
        "generation_parameters": {"temperature": 0.1},
        "knowledge_config": None,
        "tool_config": None,
    }

    with TestClient(app) as client:
        created = client.post("/api/application-versions", json=payload).json()
        patch_response = client.patch(
            f"/api/application-versions/{created['id']}",
            json={"name": "Changed in place"},
        )
        put_response = client.put(
            f"/api/application-versions/{created['id']}",
            json={**payload, "name": "Changed in place"},
        )
        stored_versions = client.get("/api/application-versions").json()

    assert patch_response.status_code == 405
    assert put_response.status_code == 405
    assert stored_versions == [created]
