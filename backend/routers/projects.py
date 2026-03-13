"""
Project CRUD routes with background repo cloning.
"""
import logging
import uuid
from datetime import datetime, timezone
from typing import Optional

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from auth.github import decrypt_token
from auth.middleware import get_current_user
from database import get_db, get_session_factory
from git_manager import clone_repo, get_repo_file_tree, read_key_files
from agents.compose_agent import generate_compose
from models import (
    CloneStatus, Feature, Project, ProjectRepo, ProjectStatus,
    RepoRole, RepoStructure, User,
)

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/projects", tags=["projects"])


class CreateProjectRequest(BaseModel):
    name: str
    description: Optional[str] = ""
    github_urls: list[str]
    repo_structure: str = "MONO"


async def _update_clone_status(
    project_repo_id: str,
    status: str,
    default_branch: Optional[str] = None,
    cloned_at: Optional[datetime] = None,
    clone_error: Optional[str] = None,
) -> None:
    factory = get_session_factory()
    async with factory() as db:
        result = await db.execute(select(ProjectRepo).where(ProjectRepo.id == project_repo_id))
        repo = result.scalar_one_or_none()
        if repo:
            repo.clone_status = status
            if default_branch:
                repo.default_branch = default_branch
            if cloned_at:
                repo.cloned_at = cloned_at
            if clone_error:
                repo.clone_error = clone_error
            await db.commit()


async def _background_clone_and_compose(
    project_id: str,
    project_repo_id: str,
    github_url: str,
    local_path: str,
    access_token: str,
) -> None:
    """Background task: clone repo + generate compose."""
    try:
        await clone_repo(
            project_repo_id=project_repo_id,
            github_url=github_url,
            user_access_token=access_token,
            local_path=local_path,
            db_update_fn=_update_clone_status,
        )
    except Exception:
        return  # clone_repo already updated status to FAILED

    # Generate compose after successful clone
    factory = get_session_factory()
    async with factory() as db:
        try:
            file_tree = get_repo_file_tree(local_path)
            key_files = read_key_files(local_path)
            compose_result = await generate_compose(file_tree, key_files)

            result = await db.execute(select(Project).where(Project.id == project_id))
            project = result.scalar_one_or_none()
            if project:
                project.detected_stack = compose_result.get("detected_stack")
                project.generated_compose = compose_result.get("compose_yaml")
                await db.commit()
        except Exception as exc:
            logger.error("Compose generation failed for project %s: %s", project_id, exc)


@router.post("")
async def create_project(
    body: CreateProjectRequest,
    background_tasks: BackgroundTasks,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    # MVP: mono-repo only
    if len(body.github_urls) > 1 or body.repo_structure != "MONO":
        raise HTTPException(
            status_code=400,
            detail="Multi-repo coming soon. Use a single mono-repo for now.",
        )
    if not body.github_urls:
        raise HTTPException(status_code=400, detail="At least one GitHub URL required")

    from config import get_settings
    settings = get_settings()

    project_id = str(uuid.uuid4())
    project = Project(
        id=project_id,
        user_id=current_user.id,
        name=body.name,
        description=body.description,
        status=ProjectStatus.ACTIVE,
        repo_structure=RepoStructure.MONO,
        created_at=datetime.now(timezone.utc),
    )
    db.add(project)

    repos_out = []
    access_token = decrypt_token(current_user.github_access_token)

    for url in body.github_urls:
        repo_name = url.rstrip("/").split("/")[-1].removesuffix(".git")
        project_repo_id = str(uuid.uuid4())
        local_path = str(settings.workspace_base / project_id / repo_name)

        project_repo = ProjectRepo(
            id=project_repo_id,
            project_id=project_id,
            github_url=url,
            repo_name=repo_name,
            local_path=local_path,
            clone_status=CloneStatus.PENDING,
            role=RepoRole.PRIMARY,
        )
        db.add(project_repo)
        repos_out.append({"id": project_repo_id, "repo_name": repo_name, "status": "PENDING"})

        background_tasks.add_task(
            _background_clone_and_compose,
            project_id, project_repo_id, url, local_path, access_token,
        )

    await db.commit()

    return {"project_id": project_id, "status": "CLONING", "repos": repos_out}


@router.get("")
async def list_projects(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    result = await db.execute(
        select(Project).where(
            Project.user_id == current_user.id,
            Project.status == ProjectStatus.ACTIVE,
        )
    )
    projects = result.scalars().all()
    return [
        {
            "id": p.id,
            "name": p.name,
            "description": p.description,
            "created_at": p.created_at,
            "detected_stack": p.detected_stack,
        }
        for p in projects
    ]


@router.get("/{project_id}")
async def get_project(
    project_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    result = await db.execute(
        select(Project).where(Project.id == project_id, Project.user_id == current_user.id)
    )
    project = result.scalar_one_or_none()
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")

    repos_result = await db.execute(select(ProjectRepo).where(ProjectRepo.project_id == project_id))
    repos = repos_result.scalars().all()

    features_result = await db.execute(select(Feature).where(Feature.project_id == project_id))
    features = features_result.scalars().all()

    return {
        "id": project.id,
        "name": project.name,
        "description": project.description,
        "status": project.status,
        "detected_stack": project.detected_stack,
        "generated_compose": bool(project.generated_compose),
        "repos": [
            {
                "id": r.id,
                "github_url": r.github_url,
                "repo_name": r.repo_name,
                "clone_status": r.clone_status,
                "default_branch": r.default_branch,
                "cloned_at": r.cloned_at,
            }
            for r in repos
        ],
        "features": [
            {"id": f.id, "title": f.title, "status": f.status, "feature_branch": f.feature_branch}
            for f in features
        ],
    }


@router.delete("/{project_id}")
async def delete_project(
    project_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    result = await db.execute(
        select(Project).where(Project.id == project_id, Project.user_id == current_user.id)
    )
    project = result.scalar_one_or_none()
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")

    project.status = ProjectStatus.ARCHIVED
    await db.commit()
    return {"status": "archived"}
