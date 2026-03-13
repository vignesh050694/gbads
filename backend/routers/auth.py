"""
GitHub OAuth routes.
"""
from fastapi import APIRouter, Depends
from fastapi.responses import RedirectResponse

from auth.github import (
    create_jwt,
    exchange_code_for_token,
    fetch_github_user,
    get_oauth_redirect_url,
    upsert_user,
)
from auth.middleware import get_current_user
from database import get_db
from models import User
from sqlalchemy.ext.asyncio import AsyncSession

router = APIRouter(prefix="/auth", tags=["auth"])


@router.get("/github")
async def github_login():
    """Redirect user to GitHub OAuth authorization page."""
    return RedirectResponse(url=get_oauth_redirect_url())


@router.get("/github/callback")
async def github_callback(code: str, db: AsyncSession = Depends(get_db)):
    """Exchange GitHub code for access token, upsert user, issue JWT."""
    access_token = await exchange_code_for_token(code)
    github_profile = await fetch_github_user(access_token)
    user = await upsert_user(db, github_profile, access_token)
    jwt_token = create_jwt(user.id)
    return RedirectResponse(url=f"http://localhost:3000?token={jwt_token}")


@router.get("/me")
async def get_me(current_user: User = Depends(get_current_user)):
    """Return current user profile."""
    return {
        "id": current_user.id,
        "github_username": current_user.github_username,
        "github_email": current_user.github_email,
        "avatar_url": current_user.avatar_url,
    }


@router.post("/logout")
async def logout():
    """Logout — client should discard JWT."""
    return {"status": "ok"}
