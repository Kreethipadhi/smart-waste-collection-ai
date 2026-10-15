import os
import secrets
import asyncio

import pytest
from alembic import command
from alembic.config import Config
from fastapi.testclient import TestClient

from app import api
from app.config import Settings
from app.models import Bin
from app.repository import Repository
from app.security import hash_password


def test_authentication_and_cors_protect_operational_api(tmp_path, monkeypatch):
    repo = Repository(str(tmp_path / 'auth.db'), initialize=True, seed_data=True)
    password = 'local-test-password-12'
    user_id = repo.create_user('operator@example.test', hash_password(password), 'admin')
    repo.create_user('viewer@example.test', hash_password(password), 'viewer')
    monkeypatch.setattr(api, 'repo', repo)

    with TestClient(api.app) as client:
        assert client.get('/health').status_code == 200
        assert client.get('/ready').status_code == 200
        assert client.get('/api/bins').status_code == 401
        assert client.post('/api/orchestrate').status_code == 401
        assert client.post('/api/auth/login', json={'username':'operator@example.test','password':'incorrect-password'}).status_code == 401
        login = client.post('/api/auth/login', json={'username': 'operator@example.test', 'password': password})
        assert login.status_code == 200
        token = login.json()['access_token']
        assert client.get('/api/bins', headers={'Authorization': f'Bearer {token}'}).status_code == 200
        assert client.get('/api/auth/me', headers={'Authorization': f'Bearer {token}'}).json()['id'] == user_id
        invalid_bin = client.post('/api/bins', headers={'Authorization': f'Bearer {token}'}, json={
            'id':'BIN-INVALID','zone':'Invalid coordinates','latitude':91,'longitude':72.8,
            'waste_type':'general','capacity_liters':500,'fill_percent':25,
        })
        assert invalid_bin.status_code == 422
        viewer_login = client.post('/api/auth/login', json={'username':'viewer@example.test','password':password})
        viewer_token = viewer_login.json()['access_token']
        assert client.get('/api/bins', headers={'Authorization': f'Bearer {viewer_token}'}).status_code == 200
        assert client.post('/api/orchestrate', headers={'Authorization': f'Bearer {viewer_token}'}).status_code == 403
        preflight = client.options('/api/bins', headers={
            'Origin': 'http://localhost:5173',
            'Access-Control-Request-Method': 'POST',
            'Access-Control-Request-Headers': 'authorization,content-type',
        })
        assert preflight.status_code == 200
        assert preflight.headers['access-control-allow-origin'] == 'http://localhost:5173'
    repo.dispose()


def test_startup_preserves_existing_operational_records(tmp_path, monkeypatch):
    repo = Repository(str(tmp_path / 'preserve.db'), initialize=True, seed_data=True)
    sentinel = Bin(id='BIN-PRESERVE', zone='Existing district', latitude=19.01, longitude=72.81,
                   waste_type='general', capacity_liters=500, fill_percent=25)
    repo.save_bin(sentinel)
    monkeypatch.setattr(api, 'repo', repo)

    with TestClient(api.app) as client:
        assert client.get('/health').status_code == 200
        assert repo.bin('BIN-PRESERVE').zone == 'Existing district'
        assert len(repo.bins()) == 6
    repo.dispose()


def test_migrations_are_repeatable_and_preserve_existing_bins(tmp_path, monkeypatch):
    database_url = 'sqlite:///' + (tmp_path / 'migration.db').as_posix()
    monkeypatch.setenv('APP_ENV', 'test')
    monkeypatch.setenv('DATABASE_URL', database_url)
    monkeypatch.setenv('AUTHENTICATION_SECRET', secrets.token_urlsafe(48))
    config_path = os.path.join(os.path.dirname(__file__), '..', 'alembic.ini')
    config = Config(os.path.abspath(config_path))

    command.upgrade(config, 'head')
    repo = Repository(database_url)
    sentinel = Bin(id='BIN-MIGRATION', zone='Migration district', latitude=19.02, longitude=72.82,
                   waste_type='organic', capacity_liters=400, fill_percent=15)
    repo.save_bin(sentinel)
    command.upgrade(config, 'head')

    assert repo.check_connection(require_migrations=True)
    assert repo.bin('BIN-MIGRATION').zone == 'Migration district'
    repo.dispose()


def test_production_refuses_sqlite_fallback_and_missing_database_url(monkeypatch):
    monkeypatch.setenv('APP_ENV', 'production')
    monkeypatch.delenv('DATABASE_URL', raising=False)
    with pytest.raises(RuntimeError, match='DATABASE_URL is required'):
        Settings.from_environment()

    monkeypatch.setenv('DATABASE_URL', 'sqlite:///./ecoroute.db')
    with pytest.raises(RuntimeError, match='must configure PostgreSQL'):
        Settings.from_environment()


def test_postgresql_url_defaults_to_production_without_app_env(monkeypatch):
    monkeypatch.delenv('APP_ENV', raising=False)
    monkeypatch.setenv('DATABASE_URL', 'postgresql+psycopg://')
    monkeypatch.delenv('AUTHENTICATION_SECRET', raising=False)

    with pytest.raises(RuntimeError, match='AUTHENTICATION_SECRET'):
        Settings.from_environment()


def test_development_postgresql_does_not_seed_by_default(monkeypatch):
    monkeypatch.setenv('APP_ENV', 'development')
    monkeypatch.setenv('DATABASE_URL', 'postgresql+psycopg://')
    monkeypatch.delenv('ECO_ROUTE_SEED_DATA', raising=False)

    assert Settings.from_environment().seed_development_data is False
    monkeypatch.setenv('ECO_ROUTE_SEED_DATA', 'true')
    with pytest.raises(RuntimeError, match='only for local SQLite'):
        Settings.from_environment()


def test_render_cannot_run_in_development_mode(monkeypatch):
    monkeypatch.setenv('RENDER', 'true')
    monkeypatch.setenv('APP_ENV', 'development')
    with pytest.raises(RuntimeError, match='APP_ENV must be production'):
        Settings.from_environment()


def test_production_lifespan_checks_migrations_without_seeding(monkeypatch):
    calls = []

    class RepositoryProbe:
        def check_connection(self, *, require_migrations=False):
            calls.append(('check', require_migrations))

        def initialize_schema(self):
            raise AssertionError('Production startup must not initialize schemas.')

        def seed(self):
            raise AssertionError('Production startup must not seed sample data.')

        def dispose(self):
            calls.append(('dispose',))

    production_settings = Settings(
        environment='production', database_url='postgresql+psycopg://',
        authentication_secret=secrets.token_urlsafe(48), frontend_origins=('https://frontend.example',),
        port=10000, seed_development_data=False,
    )
    monkeypatch.setattr(api, 'settings', production_settings)
    monkeypatch.setattr(api, 'repo', RepositoryProbe())

    async def run_lifespan():
        async with api.lifespan(api.app):
            pass

    asyncio.run(run_lifespan())

    assert calls == [('check', True), ('dispose',)]
