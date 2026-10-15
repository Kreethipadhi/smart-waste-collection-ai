import os
import secrets
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import urlsplit

from dotenv import load_dotenv


load_dotenv(Path(__file__).resolve().parents[1] / '.env', override=False)


def _frontend_origins(value: str | None, environment: str) -> tuple[str, ...]:
    if not value:
        if environment == 'production':
            raise RuntimeError('FRONTEND_ORIGIN must be configured in production.')
        return ('http://localhost:5173', 'http://127.0.0.1:5173')

    origins = tuple(origin.strip().rstrip('/') for origin in value.split(',') if origin.strip())
    if not origins:
        raise RuntimeError('FRONTEND_ORIGIN must contain at least one valid origin.')
    for origin in origins:
        parsed = urlsplit(origin)
        if parsed.scheme not in ('http', 'https') or not parsed.netloc or parsed.path or parsed.query or parsed.fragment:
            raise RuntimeError('FRONTEND_ORIGIN values must be bare http(s) origins without paths.')
        if environment == 'production' and parsed.scheme != 'https':
            raise RuntimeError('Production FRONTEND_ORIGIN values must use HTTPS.')
    return origins


@dataclass(frozen=True)
class Settings:
    environment: str
    database_url: str
    authentication_secret: str
    frontend_origins: tuple[str, ...]
    port: int
    seed_development_data: bool

    @classmethod
    def from_environment(cls) -> 'Settings':
        configured_database_url = os.getenv('DATABASE_URL', '').strip()
        production_database = configured_database_url.startswith(('postgres://', 'postgresql://', 'postgresql+'))
        render_runtime = os.getenv('RENDER', '').strip().lower() in {'true', '1', 'yes'}
        default_environment = 'production' if production_database or render_runtime else 'development'
        environment = os.getenv('APP_ENV', default_environment).strip().lower()
        if environment not in {'development', 'test', 'production'}:
            raise RuntimeError('APP_ENV must be development, test, or production.')
        if render_runtime and environment != 'production':
            raise RuntimeError('APP_ENV must be production when running on Render.')

        database_url = configured_database_url
        if not database_url:
            if environment == 'production':
                raise RuntimeError('DATABASE_URL is required in production; refusing to fall back to SQLite.')
            database_url = 'sqlite:///./ecoroute.db'
        if database_url.startswith('postgres://'):
            database_url = 'postgresql+psycopg://' + database_url.removeprefix('postgres://')
        elif database_url.startswith('postgresql://'):
            database_url = 'postgresql+psycopg://' + database_url.removeprefix('postgresql://')
        if environment == 'production' and not database_url.startswith('postgresql+psycopg://'):
            raise RuntimeError('Production DATABASE_URL must configure PostgreSQL through psycopg.')

        authentication_secret = os.getenv('AUTHENTICATION_SECRET', '').strip()
        if environment == 'production' and len(authentication_secret) < 32:
            raise RuntimeError('AUTHENTICATION_SECRET must contain at least 32 characters in production.')
        if not authentication_secret:
            authentication_secret = secrets.token_urlsafe(48)

        try:
            port = int(os.getenv('PORT', '8000'))
        except ValueError as exc:
            raise RuntimeError('PORT must be an integer from 1 to 65535.') from exc
        if not 1 <= port <= 65535:
            raise RuntimeError('PORT must be an integer from 1 to 65535.')

        default_seed = environment == 'development' and database_url.startswith('sqlite:')
        seed_value = os.getenv('ECO_ROUTE_SEED_DATA', 'true' if default_seed else 'false').lower()
        if seed_value not in {'true', 'false', '1', '0', 'yes', 'no'}:
            raise RuntimeError('ECO_ROUTE_SEED_DATA must be a boolean value.')
        seed_development_data = seed_value in {'true', '1', 'yes'}
        if environment == 'production' and seed_development_data:
            raise RuntimeError('ECO_ROUTE_SEED_DATA cannot be enabled in production.')
        if seed_development_data and not database_url.startswith('sqlite:'):
            raise RuntimeError('ECO_ROUTE_SEED_DATA is supported only for local SQLite development.')

        return cls(
            environment=environment,
            database_url=database_url,
            authentication_secret=authentication_secret,
            frontend_origins=_frontend_origins(os.getenv('FRONTEND_ORIGIN'), environment),
            port=port,
            seed_development_data=seed_development_data,
        )