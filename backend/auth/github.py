"""
GitHub OAuth flow + JWT auth for GBADS v2.
"""
import base64
import hashlib
import logging
import uuid
from datetime import datetime, timedelta, timezone
from typing import Optional

import httpx
import jwt as pyjwt
from cryptography.fernet import Fernet
from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from config import get_settings
from models import User

logger = logging.getLogger(__name__)

GITHUB_SCOPES = "read:user user:email repo"
GITHUB_AUTHORIZE_URL = "https://github.com/login/oauth/authorize"
GITHUB_TOKEN_URL = "https://github.com/login/oauth/access_token"
GITHUB_API_URL = "https://api.github.com"


def _get_fernet() -> Fernet:
    settings = get_settings()
    key_bytes = hashlib.sha256(settings.jwt_secret_key.encode()).digest()
    fernet_key = base64.urlsafe_b64encode(key_bytes)
    return Fernet(fernet_key)


def encrypt_token(token: str) -> str:
    return _get_fernet().encrypt(token.encode()).decode()


def decrypt_token(encrypted: str) -> str:
    return _get_fernet().decrypt(encrypted.encode()).decode()


def get_oauth_redirect_url() -> str:
    settings = get_settings()
    return (
        f"{GITHUB_AUTHORIZE_URL}"
        f"?client_id={settings.github_client_id}"
        f"&redirect_uri={settings.github_redirect_uri}"
        f"&scope={GITHUB_SCOPES.replace(' ', '%20')}"
    )


async def exchange_code_for_token(code: str) -> str:
    settings = get_settings()
    async with httpx.AsyncClient() as client:
        resp = await client.post(
            GITHUB_TOKEN_URL,
            data={
                "client_id": settings.github_client_id,
                "client_secret": settings.github_client_secret,
                "code": code,
                "redirect_uri": settings.github_redirect_uri,
            },
            headers={"Accept": "application/json"},
        )
        resp.raise_for_status()
        data = resp.json()

    access_token = data.get("access_token")
    if not access_token:
        raise HTTPException(status_code=400, detail=f"GitHub OAuth error: {data.get('error_description', 'unknown')}")
    return access_token


async def fetch_github_user(access_token: str) -> dict:
    async with httpx.AsyncClient() as client:
        resp = await client.get(
            f"{GITHUB_API_URL}/user",
            headers={
                "Authorization": f"Bearer {access_token}",
                "Accept": "application/vnd.github+json",
            },
        )
        resp.raise_for_status()
        profile = resp.json()

        # Fetch primary email if not in profile
        if not profile.get("email"):
            email_resp = await client.get(
                f"{GITHUB_API_URL}/user/emails",
                headers={
                    "Authorization": f"Bearer {access_token}",
                    "Accept": "application/vnd.github+json",
                },
            )
            if email_resp.status_code == 200:
                emails = email_resp.json()
                primary = next((e["email"] for e in emails if e.get("primary")), None)
                profile["email"] = primary

    return profile


async def upsert_user(db: AsyncSession, github_profile: dict, access_token: str) -> User:
    github_id = str(github_profile["id"])
    encrypted_token = encrypt_token(access_token)

    result = await db.execute(select(User).where(User.github_id == github_id))
    user = result.scalar_one_or_none()

    if user:
        user.github_username = github_profile.get("login", "")
        user.github_email = github_profile.get("email", "")
        user.github_access_token = encrypted_token
        user.avatar_url = github_profile.get("avatar_url", "")
        user.last_login = datetime.now(timezone.utc)
    else:
        user = User(
            id=str(uuid.uuid4()),
            github_id=github_id,
            github_username=github_profile.get("login", ""),
            github_email=github_profile.get("email", ""),
            github_access_token=encrypted_token,
            avatar_url=github_profile.get("avatar_url", ""),
            created_at=datetime.now(timezone.utc),
            last_login=datetime.now(timezone.utc),
        )
        db.add(user)

    await db.commit()
    await db.refresh(user)
    return user


def create_jwt(user_id: str) -> str:
    settings = get_settings()
    expire = datetime.now(timezone.utc) + timedelta(hours=settings.jwt_expire_hours)
    payload = {"sub": user_id, "exp": expire, "iat": datetime.now(timezone.utc)}
    return pyjwt.encode(payload, settings.jwt_secret_key, algorithm="HS256")


def verify_jwt(token: str) -> dict:
    settings = get_settings()
    try:
        return pyjwt.decode(token, settings.jwt_secret_key, algorithms=["HS256"])
    except pyjwt.ExpiredSignatureError:
        raise HTTPException(status_code=401, detail="Token expired")
    except pyjwt.InvalidTokenError:
        raise HTTPException(status_code=401, detail="Invalid token")
