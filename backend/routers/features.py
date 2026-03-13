"""
Feature lifecycle routes.
"""
import logging
import uuid
from datetime import datetime, timezone
from typing import Optional

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from auth.middleware import get_current_user
from database import get_db, get_session_factory
from git_manager import get_repo_file_tree, read_key_files
from interceptor.agent import InterceptorAgent
from llm.client import LLMClient
from models import Feature, FeatureStatus, Project, ProjectRepo, Session, User
from time_utils import utc_now_naive

logger = logging.getLogger(__name__)
router = APIRouter(tags=["features"])


class CreateFeatureRequest(BaseModel):
    title: str
    raw_requirement: str


class ClarifyRequest(BaseModel):
    answers: dict


async def _intercept_requirement(
    feature_id: str,
    raw_requirement: str,
    repo_local_path: Optional[str],
) -> None:
    factory = get_session_factory()
    async with factory() as db:
        try:
            llm = LLMClient()
            agent = InterceptorAgent(llm)

            repo_context = None
            if repo_local_path:
                file_tree = get_repo_file_tree(repo_local_path)
                key_files = read_key_files(repo_local_path)
                repo_context = {"file_tree": file_tree, "key_files": key_files}

            spec = await agent.parse(raw_requirement, repo_context=repo_context)

            result = await db.execute(select(Feature).where(Feature.id == feature_id))
            feature = result.scalar_one_or_none()
            if feature:
                feature.module_spec = spec
                if spec.get("clarifying_questions"):
                    feature.status = FeatureStatus.AWAITING_CLARIFICATION
                else:
                    feature.status = FeatureStatus.AWAITING_METRIC_APPROVAL
                await db.commit()
        except Exception as exc:
            logger.error("Intercept failed for feature %s: %s", feature_id, exc)
            result = await db.execute(select(Feature).where(Feature.id == feature_id))
            feature = result.scalar_one_or_none()
            if feature:
                feature.status = FeatureStatus.CANCELLED
                await db.commit()


@router.post("/projects/{project_id}/features")
async def create_feature(
    project_id: str,
    body: CreateFeatureRequest,
    background_tasks: BackgroundTasks,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    result = await db.execute(
        select(Project).where(Project.id == project_id, Project.user_id == current_user.id)
    )
    project = result.scalar_one_or_none()
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")

    # Get primary repo local path
    repo_result = await db.execute(
        select(ProjectRepo).where(
            ProjectRepo.project_id == project_id,
            ProjectRepo.clone_status == "DONE",
        )
    )
    repo = repo_result.scalar_one_or_none()
    repo_local_path = repo.local_path if repo else None

    feature_id = str(uuid.uuid4())
    feature = Feature(
        id=feature_id,
        project_id=project_id,
        title=body.title,
        raw_requirement=body.raw_requirement,
        status=FeatureStatus.INTERCEPTING,
        created_at=utc_now_naive(),
    )
    db.add(feature)
    await db.commit()

    background_tasks.add_task(_intercept_requirement, feature_id, body.raw_requirement, repo_local_path)

    return {"feature_id": feature_id, "status": "INTERCEPTING"}


@router.get("/projects/{project_id}/features")
async def list_features(
    project_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    result = await db.execute(
        select(Project).where(Project.id == project_id, Project.user_id == current_user.id)
    )
    if not result.scalar_one_or_none():
        raise HTTPException(status_code=404, detail="Project not found")

    features_result = await db.execute(
        select(Feature).where(Feature.project_id == project_id)
    )
    features = features_result.scalars().all()
    return [
        {
            "id": f.id,
            "title": f.title,
            "status": f.status,
            "feature_branch": f.feature_branch,
            "created_at": f.created_at,
        }
        for f in features
    ]


@router.get("/features/{feature_id}")
async def get_feature(
    feature_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    result = await db.execute(select(Feature).where(Feature.id == feature_id))
    feature = result.scalar_one_or_none()
    if not feature:
        raise HTTPException(status_code=404, detail="Feature not found")

    # Verify ownership
    proj_result = await db.execute(
        select(Project).where(Project.id == feature.project_id, Project.user_id == current_user.id)
    )
    if not proj_result.scalar_one_or_none():
        raise HTTPException(status_code=403, detail="Forbidden")

    return {
        "id": feature.id,
        "title": feature.title,
        "raw_requirement": feature.raw_requirement,
        "status": feature.status,
        "module_spec": feature.module_spec,
        "benchmark_plan": feature.benchmark_plan,
        "approved_at": feature.approved_at,
        "feature_branch": feature.feature_branch,
        "pr_url": feature.pr_url,
        "created_at": feature.created_at,
        "session_id": feature.session_id,
    }


@router.post("/features/{feature_id}/clarify")
async def clarify_feature(
    feature_id: str,
    body: ClarifyRequest,
    background_tasks: BackgroundTasks,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    result = await db.execute(select(Feature).where(Feature.id == feature_id))
    feature = result.scalar_one_or_none()
    if not feature:
        raise HTTPException(status_code=404, detail="Feature not found")

    # Re-run interceptor with clarification answers
    async def _re_intercept():
        factory = get_session_factory()
        async with factory() as inner_db:
            try:
                llm = LLMClient()
                agent = InterceptorAgent(llm)
                spec = await agent.parse(feature.raw_requirement, clarifications=body.answers)

                inner_result = await inner_db.execute(select(Feature).where(Feature.id == feature_id))
                feat = inner_result.scalar_one_or_none()
                if feat:
                    feat.module_spec = spec
                    feat.status = FeatureStatus.AWAITING_METRIC_APPROVAL
                    await inner_db.commit()
            except Exception as exc:
                logger.error("Re-intercept failed: %s", exc)

    background_tasks.add_task(_re_intercept)
    return {"status": "processing"}
