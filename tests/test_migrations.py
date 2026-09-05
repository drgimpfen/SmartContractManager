import os
import tempfile
import pytest
from alembic.config import Config
from alembic import command
from sqlalchemy import create_engine, inspect


def test_alembic_migrations_lifecycle():
    """Verify that Alembic migrations run cleanly from base to head and can be downgraded."""
    with tempfile.NamedTemporaryFile(suffix=".db") as temp_db:
        db_url = f"sqlite:///{temp_db.name}"

        # Configure Alembic using project alembic.ini
        alembic_cfg = Config("alembic.ini")
        alembic_cfg.set_main_option("sqlalchemy.url", db_url)

        # 1. Upgrade from base to head
        command.upgrade(alembic_cfg, "head")

        engine = create_engine(db_url)
        inspector = inspect(engine)
        tables = set(inspector.get_table_names())

        expected_tables = {
            "alembic_version",
            "users",
            "providers",
            "tags",
            "contracts",
            "contract_tags",
            "documents",
            "price_entries",
            "exchange_rate_cache",
            "notes",
        }
        assert expected_tables.issubset(tables), f"Missing tables: {expected_tables - tables}"
        contract_cols = {c["name"] for c in inspector.get_columns("contracts")}
        assert "is_archived" in contract_cols, "is_archived column missing from contracts table"
        assert "title" in contract_cols, "title column missing from contracts table"

        # 2. Downgrade from head back to base
        command.downgrade(alembic_cfg, "base")

        engine.dispose()
        engine = create_engine(db_url)
        inspector = inspect(engine)
        remaining_tables = set(inspector.get_table_names()) - {"alembic_version"}
        assert len(remaining_tables) == 0, f"Remaining tables after downgrade: {remaining_tables}"

        # 3. Upgrade again to head
        command.upgrade(alembic_cfg, "head")
        inspector = inspect(engine)
        tables_reapplied = set(inspector.get_table_names())
        assert expected_tables.issubset(tables_reapplied)
        engine.dispose()
