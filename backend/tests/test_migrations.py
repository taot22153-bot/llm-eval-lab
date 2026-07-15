import os
from pathlib import Path

from alembic import command
from alembic.config import Config
from dotenv import load_dotenv
from sqlalchemy import create_engine, inspect

PROJECT_ROOT = Path(__file__).parents[2]
BACKEND_ROOT = PROJECT_ROOT / "backend"
load_dotenv(PROJECT_ROOT / ".env")


def test_migration_creates_application_versions_table():
    database_url = os.environ["TEST_DATABASE_URL"]
    config = Config(BACKEND_ROOT / "alembic.ini")
    config.set_main_option("sqlalchemy.url", database_url.replace("%", "%%"))
    engine = create_engine(database_url)

    with engine.begin() as connection:
        connection.exec_driver_sql("DROP TABLE IF EXISTS test_case_executions")
        connection.exec_driver_sql("DROP TABLE IF EXISTS evaluation_runs")
        connection.exec_driver_sql("DROP TABLE IF EXISTS test_cases")
        connection.exec_driver_sql("DROP TABLE IF EXISTS evaluation_suites")
        connection.exec_driver_sql("DROP TABLE IF EXISTS application_versions")
        connection.exec_driver_sql("DROP TABLE IF EXISTS alembic_version")

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

    with engine.begin() as connection:
        connection.exec_driver_sql("DROP TABLE IF EXISTS test_case_executions")
        connection.exec_driver_sql("DROP TABLE IF EXISTS evaluation_runs")
        connection.exec_driver_sql("DROP TABLE IF EXISTS test_cases")
        connection.exec_driver_sql("DROP TABLE IF EXISTS evaluation_suites")
        connection.exec_driver_sql("DROP TABLE IF EXISTS application_versions")
        connection.exec_driver_sql("DROP TABLE IF EXISTS alembic_version")

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

    with engine.begin() as connection:
        connection.exec_driver_sql("DROP TABLE IF EXISTS test_case_executions")
        connection.exec_driver_sql("DROP TABLE IF EXISTS evaluation_runs")
        connection.exec_driver_sql("DROP TABLE IF EXISTS test_cases")
        connection.exec_driver_sql("DROP TABLE IF EXISTS evaluation_suites")
        connection.exec_driver_sql("DROP TABLE IF EXISTS application_versions")
        connection.exec_driver_sql("DROP TABLE IF EXISTS alembic_version")

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

    with engine.begin() as connection:
        connection.exec_driver_sql("DROP TABLE IF EXISTS test_case_executions")
        connection.exec_driver_sql("DROP TABLE IF EXISTS evaluation_runs")
        connection.exec_driver_sql("DROP TABLE IF EXISTS test_cases")
        connection.exec_driver_sql("DROP TABLE IF EXISTS evaluation_suites")
        connection.exec_driver_sql("DROP TABLE IF EXISTS application_versions")
        connection.exec_driver_sql("DROP TABLE IF EXISTS alembic_version")

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
