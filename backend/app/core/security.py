from __future__ import annotations

import secrets
from datetime import datetime, timedelta, timezone
from typing import Any

import bcrypt
import jwt

from app.core.config import settings

JWT_ALGORITHM = "HS256"

ACCESS_TOKEN_TYPE = "access"
REFRESH_TOKEN_TYPE = "refresh"

CUSTOMER_ACCESS_TOKEN_TYPE = "customer_access"
CUSTOMER_REFRESH_TOKEN_TYPE = "customer_refresh"
CUSTOMER_TOKEN_AUDIENCE = "customer-portal"
CUSTOMER_TOKEN_SCOPE = "customer"


def _password_bytes(password: str) -> bytes:
    return password.encode("utf-8")[:72]


def hash_password(password: str) -> str:
    hashed = bcrypt.hashpw(
        _password_bytes(password),
        bcrypt.gensalt(rounds=settings.bcrypt_rounds),
    )
    return hashed.decode("utf-8")


def verify_password(password: str, password_hash: str) -> bool:
    try:
        return bcrypt.checkpw(_password_bytes(password), password_hash.encode("utf-8"))
    except (TypeError, ValueError):
        return False


def _encode_token(
    *,
    user_id: int,
    email: str,
    username: str,
    role: str,
    token_type: str,
    expires_in: timedelta,
) -> str:
    now = datetime.now(timezone.utc)
    payload: dict[str, Any] = {
        "id": user_id,
        "email": email,
        "username": username,
        "role": role,
        "type": token_type,
        "jti": secrets.token_urlsafe(16),
        "iat": now,
        "exp": now + expires_in,
    }
    return jwt.encode(
        payload,
        settings.jwt_secret.get_secret_value(),
        algorithm=JWT_ALGORITHM,
    )


def create_access_token(
    *,
    user_id: int,
    email: str,
    username: str,
    role: str,
) -> str:
    return _encode_token(
        user_id=user_id,
        email=email,
        username=username,
        role=role,
        token_type=ACCESS_TOKEN_TYPE,
        expires_in=timedelta(minutes=settings.access_token_expire_minutes),
    )


def create_refresh_token(
    *,
    user_id: int,
    email: str,
    username: str,
    role: str,
) -> str:
    return _encode_token(
        user_id=user_id,
        email=email,
        username=username,
        role=role,
        token_type=REFRESH_TOKEN_TYPE,
        expires_in=timedelta(minutes=settings.refresh_token_expire_minutes),
    )


def decode_token(token: str, *, expected_type: str) -> dict[str, Any]:
    payload = jwt.decode(
        token,
        settings.jwt_secret.get_secret_value(),
        algorithms=[JWT_ALGORITHM],
    )
    if payload.get("type") != expected_type:
        raise jwt.InvalidTokenError(f"Expected a {expected_type} token")
    return payload


def decode_access_token(token: str) -> dict[str, Any]:
    return decode_token(token, expected_type=ACCESS_TOKEN_TYPE)


def decode_refresh_token(token: str) -> dict[str, Any]:
    return decode_token(token, expected_type=REFRESH_TOKEN_TYPE)


def _encode_customer_token(
    *,
    account_id: int,
    customer_id: int,
    email: str,
    token_type: str,
    expires_in: timedelta,
) -> str:
    now = datetime.now(timezone.utc)
    payload: dict[str, Any] = {
        "account_id": account_id,
        "customer_id": customer_id,
        "email": email,
        "scope": CUSTOMER_TOKEN_SCOPE,
        "aud": CUSTOMER_TOKEN_AUDIENCE,
        "type": token_type,
        "jti": secrets.token_urlsafe(16),
        "iat": now,
        "exp": now + expires_in,
    }
    return jwt.encode(
        payload,
        settings.customer_jwt_secret_value,
        algorithm=JWT_ALGORITHM,
    )


def create_customer_access_token(
    *,
    account_id: int,
    customer_id: int,
    email: str,
) -> str:
    return _encode_customer_token(
        account_id=account_id,
        customer_id=customer_id,
        email=email,
        token_type=CUSTOMER_ACCESS_TOKEN_TYPE,
        expires_in=timedelta(minutes=settings.access_token_expire_minutes),
    )


def create_customer_refresh_token(
    *,
    account_id: int,
    customer_id: int,
    email: str,
) -> str:
    return _encode_customer_token(
        account_id=account_id,
        customer_id=customer_id,
        email=email,
        token_type=CUSTOMER_REFRESH_TOKEN_TYPE,
        expires_in=timedelta(minutes=settings.refresh_token_expire_minutes),
    )


def decode_customer_token(token: str, *, expected_type: str) -> dict[str, Any]:
    payload = jwt.decode(
        token,
        settings.customer_jwt_secret_value,
        algorithms=[JWT_ALGORITHM],
        audience=CUSTOMER_TOKEN_AUDIENCE,
    )
    if payload.get("type") != expected_type:
        raise jwt.InvalidTokenError(f"Expected a {expected_type} token")
    if payload.get("scope") != CUSTOMER_TOKEN_SCOPE:
        raise jwt.InvalidTokenError("Invalid token scope")
    return payload


def decode_customer_access_token(token: str) -> dict[str, Any]:
    return decode_customer_token(token, expected_type=CUSTOMER_ACCESS_TOKEN_TYPE)


def decode_customer_refresh_token(token: str) -> dict[str, Any]:
    return decode_customer_token(token, expected_type=CUSTOMER_REFRESH_TOKEN_TYPE)
