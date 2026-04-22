"""
UrjaRakshak — Grid Management API
====================================
GET  /api/v1/grid/               — List grid sections
POST /api/v1/grid/               — Create grid section
GET  /api/v1/grid/{id}           — Get grid section with components
POST /api/v1/grid/{id}/components — Add component to section

Author: Vipin Baniya
"""

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from pydantic import BaseModel, Field
from typing import Optional, List, Dict, Any

from app.database import get_db
from app.models.db_models import GridSection, Component
from app.auth import get_current_active_user, require_analyst
from app.models.db_models import User

router = APIRouter()


class GridSectionCreate(BaseModel):
    substation_id: str
    name: Optional[str] = None
    region: Optional[str] = None
    capacity_mva: Optional[float] = None
    voltage_kv: Optional[float] = None
    location_lat: Optional[float] = None
    location_lng: Optional[float] = None


class ComponentCreate(BaseModel):
    component_id: str
    component_type: str = Field(..., description="transformer | line | meter")
    rated_capacity_kva: Optional[float] = None
    efficiency_rating: Optional[float] = Field(None, ge=0.0, le=1.0)
    age_years: Optional[float] = None
    resistance_ohms: Optional[float] = None
    length_km: Optional[float] = None
    voltage_kv: Optional[float] = None
    load_factor: Optional[float] = Field(None, ge=0.0, le=1.0)


@router.get("/")
async def list_grids(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
) -> Dict[str, Any]:
    result = await db.execute(select(GridSection).where(GridSection.status == "active"))
    sections = result.scalars().all()
    return {
        "total": len(sections),
        "grids": [
            {
                "id": s.id, "substation_id": s.substation_id,
                "name": s.name, "region": s.region,
                "status": s.status, "capacity_mva": s.capacity_mva,
            }
            for s in sections
        ],
    }


@router.post("/", status_code=201)
async def create_grid_section(
    data: GridSectionCreate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_analyst),
) -> Dict[str, Any]:
    existing = await db.execute(
        select(GridSection).where(GridSection.substation_id == data.substation_id)
    )
    if existing.scalar_one_or_none():
        raise HTTPException(status_code=400, detail="Substation ID already exists")

    section = GridSection(**data.model_dump())
    db.add(section)
    await db.commit()
    await db.refresh(section)
    return {"id": section.id, "substation_id": section.substation_id, "status": "created"}


@router.get("/{section_id}")
async def get_grid_section(
    section_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
) -> Dict[str, Any]:
    result = await db.execute(select(GridSection).where(GridSection.id == section_id))
    section = result.scalar_one_or_none()
    if not section:
        raise HTTPException(status_code=404, detail="Grid section not found")

    comp_result = await db.execute(
        select(Component).where(Component.grid_section_id == section_id)
    )
    components = comp_result.scalars().all()

    return {
        "id": section.id, "substation_id": section.substation_id,
        "name": section.name, "region": section.region,
        "capacity_mva": section.capacity_mva, "voltage_kv": section.voltage_kv,
        "status": section.status,
        "components": [
            {
                "id": c.id, "component_id": c.component_id,
                "type": c.component_type, "capacity_kva": c.rated_capacity_kva,
                "efficiency": c.efficiency_rating, "age_years": c.age_years,
            }
            for c in components
        ],
    }


@router.post("/{section_id}/components", status_code=201)
async def add_component(
    section_id: str,
    data: ComponentCreate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_analyst),
) -> Dict[str, Any]:
    result = await db.execute(select(GridSection).where(GridSection.id == section_id))
    section = result.scalar_one_or_none()
    if not section:
        raise HTTPException(status_code=404, detail="Grid section not found")

    component = Component(grid_section_id=section_id, **data.model_dump())
    db.add(component)
    await db.commit()
    await db.refresh(component)
    return {"id": component.id, "component_id": component.component_id, "status": "created"}
