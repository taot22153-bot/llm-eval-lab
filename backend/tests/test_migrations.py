import os
from datetime import UTC, datetime
from pathlib import Path

from alembic import command
from alembic.config import Config
from dotenv import load_dotenv
from sqlalchemy import MetaData, Table, create_engine, inspect, select

PROJECT_ROOT = Path(__file__).parents[2]
BACKEND_ROOT = PROJECT_ROOT / "backend"
load_dotenv(PROJECT_ROOT / ".env")


def reset_schema(engine) -> None:
    with engine.begin() as connection:
        for table in (
            "human_review_items",
            "semantic_evaluations",
            "deterministic_check_outcomes",
            "deterministic_evaluations",
            "test_case_executions",
            "evaluation_runs",
            "test_cases",
            "evaluation_suites",
            "application_versions",
            "alembic_version",
        ):
            connection.exec_driver_sql(f"DROP TABLE IF EXISTS {table}")


def test_migration_creates_application_versions_table():
    database_url = os.environ["TEST_DATABASE_URL"]
    config = Config(BACKEND_ROOT / "alembic.ini")
    config.set_main_option("sqlalchemy.url", database_url.replace("%", "%%"))
    engine = create_engine(database_url)

    reset_schema(engine)

    command.upgrade(config, "head")

    inspector = inspect(engine)
    assert "application_versions" in inspector.get_table_names()
    assert {column["name"] for column in inspector.get_columns("application_versions")} == {
        "id",
        "name",
        "model_provider",
        "model_name",
        "system_prompt",
        "generation_parameters",
        "knowledge_config",
        "tool_config",
        "created_at",
    }

    command.downgrade(config, "base")
    assert "application_versions" not in inspect(engine).get_table_names()


def test_migration_creates_versioned_evaluation_suite_tables():
    database_url = os.environ["TEST_DATABASE_URL"]
    config = Config(BACKEND_ROOT / "alembic.ini")
    config.set_main_option("sqlalchemy.url", database_url.replace("%", "%%"))
    engine = create_engine(database_url)

    reset_schema(engine)

    command.upgrade(config, "head")

    inspector = inspect(engine)
    assert {"evaluation_suites", "test_cases"} <= set(inspector.get_table_names())
    assert {column["name"] for column in inspector.get_columns("evaluation_suites")} == {
        "id",
        "slug",
        "version",
        "name",
        "description",
        "created_at",
    }
    assert {column["name"] for column in inspector.get_columns("test_cases")} == {
        "id",
        "suite_id",
        "key",
        "position",
        "title",
        "user_input",
        "grounding_material",
        "must_have_facts",
        "forbidden_claims",
        "test_type",
        "severity",
        "requires_human_review",
    }
    assert inspector.get_foreign_keys("test_cases")[0]["referred_table"] == "evaluation_suites"

    command.downgrade(config, "base")
    table_names = inspect(engine).get_table_names()
    assert "evaluation_suites" not in table_names
    assert "test_cases" not in table_names


def test_migration_creates_persisted_test_case_executions():
    database_url = os.environ["TEST_DATABASE_URL"]
    config = Config(BACKEND_ROOT / "alembic.ini")
    config.set_main_option("sqlalchemy.url", database_url.replace("%", "%%"))
    engine = create_engine(database_url)

    reset_schema(engine)

    command.upgrade(config, "head")

    inspector = inspect(engine)
    assert {column["name"] for column in inspector.get_columns("test_case_executions")} == {
        "id",
        "application_version_id",
        "test_case_id",
        "evaluation_run_id",
        "version_role",
        "status",
        "prompt_context",
        "model_response",
        "usage",
        "latency_ms",
        "error",
        "created_at",
        "started_at",
        "completed_at",
    }
    assert {
        foreign_key["referred_table"]
        for foreign_key in inspector.get_foreign_keys("test_case_executions")
    } == {"application_versions", "test_cases", "evaluation_runs"}

    command.downgrade(config, "base")
    assert "test_case_executions" not in inspect(engine).get_table_names()


def test_migration_creates_paired_evaluation_runs():
    database_url = os.environ["TEST_DATABASE_URL"]
    config = Config(BACKEND_ROOT / "alembic.ini")
    config.set_main_option("sqlalchemy.url", database_url.replace("%", "%%"))
    engine = create_engine(database_url)

    reset_schema(engine)

    command.upgrade(config, "head")

    inspector = inspect(engine)
    assert {column["name"] for column in inspector.get_columns("evaluation_runs")} == {
        "id",
        "baseline_version_id",
        "candidate_version_id",
        "evaluation_suite_id",
        "status",
        "created_at",
        "started_at",
        "completed_at",
    }
    assert {
        foreign_key["referred_table"]
        for foreign_key in inspector.get_foreign_keys("evaluation_runs")
    } == {"application_versions", "evaluation_suites"}
    assert {
        constraint["name"] for constraint in inspector.get_check_constraints("evaluation_runs")
    } >= {"ck_evaluation_run_status", "ck_evaluation_run_distinct_versions"}
    assert {
        constraint["name"]
        for constraint in inspector.get_check_constraints("test_case_executions")
    } >= {
        "ck_test_case_execution_version_role",
        "ck_test_case_execution_run_role_pair",
    }
    assert {
        foreign_key["referred_table"]
        for foreign_key in inspector.get_foreign_keys("test_case_executions")
    } == {"application_versions", "test_cases", "evaluation_runs"}

    command.downgrade(config, "base")
    assert "evaluation_runs" not in inspect(engine).get_table_names()


def test_migration_creates_versioned_deterministic_rule_evidence():
    database_url = os.environ["TEST_DATABASE_URL"]
    config = Config(BACKEND_ROOT / "alembic.ini")
    config.set_main_option("sqlalchemy.url", database_url.replace("%", "%%"))
    engine = create_engine(database_url)
    reset_schema(engine)

    command.upgrade(config, "head")

    inspector = inspect(engine)
    assert {
        "deterministic_evaluations",
        "deterministic_check_outcomes",
    } <= set(inspector.get_table_names())
    assert {
        column["name"] for column in inspector.get_columns("deterministic_evaluations")
    } == {
        "id",
        "test_case_execution_id",
        "scorer_version",
        "passed",
        "regression_classification",
        "created_at",
    }
    assert {
        column["name"] for column in inspector.get_columns("deterministic_check_outcomes")
    } == {
        "id",
        "deterministic_evaluation_id",
        "check_type",
        "position",
        "rule",
        "passed",
        "matched_evidence",
    }
    assert inspector.get_foreign_keys("deterministic_evaluations")[0][
        "referred_table"
    ] == "test_case_executions"
    assert inspector.get_foreign_keys("deterministic_check_outcomes")[0][
        "referred_table"
    ] == "deterministic_evaluations"
    assert {
        constraint["name"]
        for constraint in inspector.get_unique_constraints("deterministic_evaluations")
    } >= {"uq_deterministic_evaluation_execution"}
    assert {
        constraint["name"]
        for constraint in inspector.get_check_constraints("deterministic_check_outcomes")
    } >= {"ck_deterministic_outcome_type"}

    command.downgrade(config, "base")
    table_names = inspect(engine).get_table_names()
    assert "deterministic_evaluations" not in table_names
    assert "deterministic_check_outcomes" not in table_names


def test_migration_creates_semantic_judgments_and_human_review_queue_items():
    database_url = os.environ["TEST_DATABASE_URL"]
    config = Config(BACKEND_ROOT / "alembic.ini")
    config.set_main_option("sqlalchemy.url", database_url.replace("%", "%%"))
    engine = create_engine(database_url)
    reset_schema(engine)

    command.upgrade(config, "head")

    inspector = inspect(engine)
    assert {"semantic_evaluations", "human_review_items"} <= set(
        inspector.get_table_names()
    )
    assert {
        column["name"] for column in inspector.get_columns("semantic_evaluations")
    } == {
        "id",
        "test_case_execution_id",
        "judge_version",
        "outcome",
        "rationale",
        "confidence",
        "judge_configuration",
        "error",
        "created_at",
    }
    assert {
        column["name"] for column in inspector.get_columns("human_review_items")
    } == {
        "id",
        "test_case_execution_id",
        "status",
        "reasons",
        "outcome",
        "rationale",
        "created_at",
        "resolved_at",
    }
    assert inspector.get_foreign_keys("semantic_evaluations")[0][
        "referred_table"
    ] == "test_case_executions"
    assert inspector.get_foreign_keys("human_review_items")[0][
        "referred_table"
    ] == "test_case_executions"
    assert {
        constraint["name"]
        for constraint in inspector.get_unique_constraints("semantic_evaluations")
    } >= {"uq_semantic_evaluation_execution"}
    assert {
        constraint["name"]
        for constraint in inspector.get_unique_constraints("human_review_items")
    } >= {"uq_human_review_item_execution"}
    assert {
        constraint["name"]
        for constraint in inspector.get_check_constraints("human_review_items")
    } >= {
        "ck_human_review_item_status",
        "ck_human_review_item_outcome",
        "ck_human_review_item_decision_state",
    }

    command.downgrade(config, "base")
    table_names = inspect(engine).get_table_names()
    assert "semantic_evaluations" not in table_names
    assert "human_review_items" not in table_names


def test_migration_backfills_existing_responses_and_regression_classification():
    database_url = os.environ["TEST_DATABASE_URL"]
    config = Config(BACKEND_ROOT / "alembic.ini")
    config.set_main_option("sqlalchemy.url", database_url.replace("%", "%%"))
    engine = create_engine(database_url)
    reset_schema(engine)
    command.upgrade(config, "0004")

    metadata = MetaData()
    metadata.reflect(bind=engine)
    now = datetime.now(UTC)
    baseline_id = "00000000-0000-0000-0000-000000000001"
    candidate_id = "00000000-0000-0000-0000-000000000002"
    suite_id = "00000000-0000-0000-0000-000000000003"
    test_case_id = "00000000-0000-0000-0000-000000000004"
    run_id = "00000000-0000-0000-0000-000000000005"
    baseline_execution_id = "00000000-0000-0000-0000-000000000006"
    candidate_execution_id = "00000000-0000-0000-0000-000000000007"

    with engine.begin() as connection:
        connection.execute(
            metadata.tables["application_versions"].insert(),
            [
                {
                    "id": baseline_id,
                    "name": "Historical baseline",
                    "model_provider": "fixture",
                    "model_name": "deterministic",
                    "system_prompt": "Baseline prompt.",
                    "generation_parameters": {},
                    "knowledge_config": None,
                    "tool_config": None,
                    "created_at": now,
                },
                {
                    "id": candidate_id,
                    "name": "Historical candidate",
                    "model_provider": "fixture",
                    "model_name": "deterministic",
                    "system_prompt": "Candidate prompt.",
                    "generation_parameters": {},
                    "knowledge_config": None,
                    "tool_config": None,
                    "created_at": now,
                },
            ],
        )
        connection.execute(
            metadata.tables["evaluation_suites"].insert(),
            {
                "id": suite_id,
                "slug": "historical-suite",
                "version": 1,
                "name": "Historical suite",
                "description": "A pre-0005 completed run.",
                "created_at": now,
            },
        )
        connection.execute(
            metadata.tables["test_cases"].insert(),
            {
                "id": test_case_id,
                "suite_id": suite_id,
                "key": "historical-regression",
                "position": 1,
                "title": "Backfill a historical response",
                "user_input": "Give the safe answer.",
                "grounding_material": [],
                "must_have_facts": ["Safe answer."],
                "forbidden_claims": ["Forbidden."],
                "test_type": "prompt_injection",
                "severity": "release_blocking",
                "requires_human_review": True,
            },
        )
        connection.execute(
            metadata.tables["evaluation_runs"].insert(),
            {
                "id": run_id,
                "baseline_version_id": baseline_id,
                "candidate_version_id": candidate_id,
                "evaluation_suite_id": suite_id,
                "status": "completed",
                "created_at": now,
                "started_at": now,
                "completed_at": now,
            },
        )
        connection.execute(
            metadata.tables["test_case_executions"].insert(),
            [
                {
                    "id": baseline_execution_id,
                    "application_version_id": baseline_id,
                    "test_case_id": test_case_id,
                    "evaluation_run_id": run_id,
                    "version_role": "baseline",
                    "status": "completed",
                    "prompt_context": {},
                    "model_response": "Safe answer.",
                    "usage": None,
                    "latency_ms": 1,
                    "error": None,
                    "created_at": now,
                    "started_at": now,
                    "completed_at": now,
                },
                {
                    "id": candidate_execution_id,
                    "application_version_id": candidate_id,
                    "test_case_id": test_case_id,
                    "evaluation_run_id": run_id,
                    "version_role": "candidate",
                    "status": "completed",
                    "prompt_context": {},
                    "model_response": "Safe answer. Forbidden.",
                    "usage": None,
                    "latency_ms": 1,
                    "error": None,
                    "created_at": now,
                    "started_at": now,
                    "completed_at": now,
                },
            ],
        )

    command.upgrade(config, "head")

    evaluations = Table("deterministic_evaluations", MetaData(), autoload_with=engine)
    outcomes = Table("deterministic_check_outcomes", MetaData(), autoload_with=engine)
    with engine.connect() as connection:
        evaluation_rows = {
            row.test_case_execution_id: row
            for row in connection.execute(select(evaluations)).mappings()
        }
        candidate_outcomes = list(
            connection.execute(
                select(outcomes).where(
                    outcomes.c.deterministic_evaluation_id
                    == evaluation_rows[candidate_execution_id].id
                ).order_by(outcomes.c.position)
            ).mappings()
        )

    assert bool(evaluation_rows[baseline_execution_id].passed) is True
    assert bool(evaluation_rows[candidate_execution_id].passed) is False
    assert (
        evaluation_rows[candidate_execution_id].regression_classification
        == "new_regression"
    )
    assert [row.matched_evidence for row in candidate_outcomes] == [
        "Safe answer.",
        "Forbidden.",
    ]

    command.downgrade(config, "base")
