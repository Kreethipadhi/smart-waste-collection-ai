import os
from uuid import uuid4

import pytest
from sqlalchemy import delete
from sqlalchemy.engine import make_url

from app.database import bins as bins_table
from app.models import Bin
from app.repository import Repository


postgres_url = os.getenv('TEST_DATABASE_URL', '').strip()
run_postgres_tests = os.getenv('RUN_POSTGRES_INTEGRATION_TESTS') == '1' and bool(postgres_url)


@pytest.mark.skipif(not run_postgres_tests, reason='Set RUN_POSTGRES_INTEGRATION_TESTS=1 and a dedicated TEST_DATABASE_URL to opt in.')
def test_dedicated_postgresql_repository_round_trip():
    if not postgres_url.startswith(('postgresql://', 'postgresql+psycopg://', 'postgres://')):
        pytest.fail('TEST_DATABASE_URL must point to a dedicated PostgreSQL test database.')
    database_name = make_url(postgres_url).database or ''
    if 'test' not in database_name.lower():
        pytest.fail('The TEST_DATABASE_URL database name must include "test"; refusing a non-test database.')

    repo = Repository(postgres_url)
    test_bin_id = f'PG-TEST-{uuid4().hex}'
    try:
        assert repo.check_connection(require_migrations=True)
        test_bin = Bin(
            id=test_bin_id, zone='PostgreSQL integration test', latitude=19.0, longitude=72.8,
            waste_type='general', capacity_liters=500, fill_percent=25,
        )
        repo.save_bin(test_bin)
        assert repo.bin(test_bin_id).zone == test_bin.zone
    finally:
        with repo.engine.begin() as connection:
            connection.execute(delete(bins_table).where(bins_table.c.id == test_bin_id))
        repo.dispose()
