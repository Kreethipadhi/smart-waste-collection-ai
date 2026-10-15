import base64
import hashlib
import hmac
import secrets
from datetime import datetime, timedelta, timezone

import jwt

from .config import Settings


PASSWORD_SCRYPT_N = 2**14
PASSWORD_SCRYPT_R = 8
PASSWORD_SCRYPT_P = 1
ACCESS_TOKEN_TTL = timedelta(hours=8)
TOKEN_ISSUER = 'ecoroute-api'


def hash_password(password: str) -> str:
    if len(password) < 12:
        raise ValueError('Administrator passwords must be at least 12 characters long.')
    salt = secrets.token_bytes(16)
    digest = hashlib.scrypt(password.encode('utf-8'), salt=salt, n=PASSWORD_SCRYPT_N, r=PASSWORD_SCRYPT_R, p=PASSWORD_SCRYPT_P, dklen=64)
    encode = lambda value: base64.urlsafe_b64encode(value).decode('ascii').rstrip('=')
    return f'scrypt${PASSWORD_SCRYPT_N}${PASSWORD_SCRYPT_R}${PASSWORD_SCRYPT_P}${encode(salt)}${encode(digest)}'


def verify_password(password: str, encoded: str) -> bool:
    try:
        algorithm, n, r, p, salt_value, digest_value = encoded.split('$')
        if algorithm != 'scrypt' or int(n) != PASSWORD_SCRYPT_N or int(r) != PASSWORD_SCRYPT_R or int(p) != PASSWORD_SCRYPT_P:
            return False
        decode = lambda value: base64.urlsafe_b64decode(value + '=' * (-len(value) % 4))
        salt, expected = decode(salt_value), decode(digest_value)
        actual = hashlib.scrypt(password.encode('utf-8'), salt=salt, n=int(n), r=int(r), p=int(p), dklen=len(expected))
        return hmac.compare_digest(actual, expected)
    except (ValueError, TypeError):
        return False


DUMMY_PASSWORD_HASH = hash_password('nonexistent-account-password')


def create_access_token(user_id: int, role: str, settings: Settings) -> str:
    now = datetime.now(timezone.utc)
    return jwt.encode(
        {'sub': str(user_id), 'role': role, 'iss': TOKEN_ISSUER, 'iat': now, 'exp': now + ACCESS_TOKEN_TTL},
        settings.authentication_secret,
        algorithm='HS256',
    )
