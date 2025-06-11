from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from typing import List
from pydantic import BaseModel, ConfigDict
from uuid import UUID
from datetime import datetime

from app.core.database import get_db
from app.models.database import Project

router = APIRouter(prefix="/api")


class ProjectCreate(BaseModel):
    name: str
    description: str | None = None
    query: str
    filters: dict


class ProjectResponse(BaseModel):
    id: UUID
    name: str
    description: str | None
    query: str
    filters: dict
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)

    def model_dump(self, **kwargs):
        data = super().model_dump(**kwargs)
        # Convert datetime objects to ISO format strings
        data["created_at"] = data["created_at"].isoformat()
        data["updated_at"] = data["updated_at"].isoformat()
        return data


@router.post("/projects/", response_model=ProjectResponse)
async def create_project(
    project: ProjectCreate,
    clerk_user_id: str = Query(..., description="Clerk user ID"),
    db: AsyncSession = Depends(get_db),
):
    # Check if project with same name exists
    result = await db.execute(
        select(Project).where(
            Project.clerk_user_id == clerk_user_id, Project.name == project.name
        )
    )
    existing_project = result.scalar_one_or_none()

    if existing_project:
        # Update existing project
        existing_project.description = project.description
        existing_project.query = project.query
        existing_project.filters = project.filters
        await db.commit()
        await db.refresh(existing_project)
        return existing_project

    # Create new project
    db_project = Project(
        clerk_user_id=clerk_user_id,
        name=project.name,
        description=project.description,
        query=project.query,
        filters=project.filters,
    )
    db.add(db_project)
    await db.commit()
    await db.refresh(db_project)
    return db_project


@router.get("/projects/", response_model=List[ProjectResponse])
async def list_projects(
    clerk_user_id: str = Query(..., description="Clerk user ID"),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(Project)
        .where(Project.clerk_user_id == clerk_user_id)
        .order_by(Project.created_at.desc())
    )
    projects = result.scalars().all()
    return projects


@router.get("/projects/{project_id}", response_model=ProjectResponse)
async def get_project(
    project_id: UUID,
    clerk_user_id: str = Query(..., description="Clerk user ID"),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(Project).where(
            Project.id == project_id, Project.clerk_user_id == clerk_user_id
        )
    )
    project = result.scalar_one_or_none()
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")
    return project
