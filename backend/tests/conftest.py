import atexit
import os
import secrets
import shutil
import tempfile
from pathlib import Path


_test_directory = Path(tempfile.mkdtemp(prefix='ecoroute-tests-'))
os.environ['APP_ENV'] = 'test'
os.environ['RENDER'] = 'false'
os.environ['DATABASE_URL'] = 'sqlite:///' + (_test_directory / 'api-import.db').as_posix()
os.environ['AUTHENTICATION_SECRET'] = secrets.token_urlsafe(48)
os.environ['FRONTEND_ORIGIN'] = 'http://localhost:5173,http://127.0.0.1:5173'
os.environ['ECO_ROUTE_SEED_DATA'] = 'false'
atexit.register(shutil.rmtree, _test_directory, ignore_errors=True)
