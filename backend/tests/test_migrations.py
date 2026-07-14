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
