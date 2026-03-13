"""
Metric approval gate routes.
"""
import logging
import uuid
from datetime import datetime, timezone

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from auth.middleware import get_current_user
from database import get_db, get_session_factory
from models import Feature, FeatureStatus, Project, Session, User
from benchmark.generator import BenchmarkGenerator
from llm.client import LLMClient

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/requirements", tags=["requirements"])


class ApproveMetricRequest(BaseModel):
    feature_id: str
    approved: bool


@router.post("/metric-plan")
async def generate_metric_plan(
    body: dict,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    feature_id = body.get("feature_id")
    if not feature_id:
        raise HTTPException(status_code=400, detail="feature_id required")

    result = await db.execute(select(Feature).where(Feature.id == feature_id))
    feature = result.scalar_one_or_none()
    if not feature:
        raise HTTPException(status_code=404, detail="Feature not found")

    if not feature.module_spec:
        raise HTTPException(status_code=400, detail="Feature has no module spec yet")

    # Verify ownership
    proj_result = await db.execute(
        select(Project).where(Project.id == feature.project_id, Project.user_id == current_user.id)
    )
    if not proj_result.scalar_one_or_none():
        raise HTTPException(status_code=403, detail="Forbidden")

    llm = LLMClient()
    generator = BenchmarkGenerator(llm)
    plan = await generator.generate_metric_plan(feature.module_spec, {})

    feature.benchmark_plan = plan
    feature.status = FeatureStatus.AWAITING_METRIC_APPROVAL
    await db.commit()

    return plan


@router.post("/approve-metric")
async def approve_metric(
    body: ApproveMetricRequest,
    background_tasks: BackgroundTasks,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    result = await db.execute(select(Feature).where(Feature.id == body.feature_id))
    feature = result.scalar_one_or_none()
    if not feature:
        raise HTTPException(status_code=404, detail="Feature not found")

    if not body.approved:
        return {"status": "not_approved"}

    if not feature.module_spec:
        raise HTTPException(status_code=400, detail="Feature has no module spec")

    # Verify ownership
    proj_result = await db.execute(
        select(Project).where(Project.id == feature.project_id, Project.user_id == current_user.id)
    )
    project = proj_result.scalar_one_or_none()
    if not project:
        raise HTTPException(status_code=403, detail="Forbidden")

    # Create session
    session_id = str(uuid.uuid4())
    session = Session(
        id=session_id,
        module_name=feature.module_spec.get("module_name", "module"),
        requirement=feature.raw_requirement,
        feature_id=feature.id,
        project_id=feature.project_id,
        created_at=datetime.now(timezone.utc),
    )
    db.add(session)

    feature.approved_at = datetime.now(timezone.utc)
    feature.status = FeatureStatus.RUNNING
    feature.session_id = session_id
    await db.commit()

    # Launch loop in background
    background_tasks.add_task(_run_feature_loop, feature.id, session_id)

    branch_name = f"feature/{session_id[:8]}"
    return {"status": "RUNNING", "feature_branch": branch_name, "session_id": session_id}


async def _run_feature_loop(feature_id: str, session_id: str) -> None:
    """Background task to run the full iteration loop for a feature."""
    from runner.loop import run_feature_loop
    try:
        await run_feature_loop(feature_id, session_id)
    except Exception as exc:
        logger.error("Feature loop failed for %s: %s", feature_id, exc)
        factory = get_session_factory()
        async with factory() as db:
            result = await db.execute(select(Feature).where(Feature.id == feature_id))
            feature = result.scalar_one_or_none()
            if feature:
                feature.status = FeatureStatus.PARTIAL
                await db.commit()
