"""业务线 CRUD。"""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from sqlmodel import Session, select

from db import get_session
from models import BusinessLine, Goal
from schemas import BusinessLineIn, BusinessLineUpdate

router = APIRouter(prefix="/api/business-lines", tags=["business-lines"])


@router.get("")
def list_business_lines(session: Session = Depends(get_session)):
    rows = session.exec(select(BusinessLine).order_by(BusinessLine.id)).all()
    return rows


@router.get("/{bl_id}")
def get_business_line(bl_id: int, session: Session = Depends(get_session)):
    bl = session.get(BusinessLine, bl_id)
    if not bl:
        raise HTTPException(404, "业务线不存在")
    return bl


@router.post("", status_code=201)
def create_business_line(payload: BusinessLineIn, session: Session = Depends(get_session)):
    bl = BusinessLine(**payload.model_dump())
    session.add(bl)
    session.commit()
    session.refresh(bl)
    return bl


@router.patch("/{bl_id}")
def update_business_line(bl_id: int, payload: BusinessLineUpdate, session: Session = Depends(get_session)):
    bl = session.get(BusinessLine, bl_id)
    if not bl:
        raise HTTPException(404, "业务线不存在")
    for k, v in payload.model_dump(exclude_unset=True).items():
        setattr(bl, k, v)
    session.add(bl)
    session.commit()
    session.refresh(bl)
    return bl


@router.delete("/{bl_id}", status_code=204)
def delete_business_line(bl_id: int, session: Session = Depends(get_session)):
    bl = session.get(BusinessLine, bl_id)
    if not bl:
        raise HTTPException(404, "业务线不存在")
    if session.exec(select(Goal).where(Goal.business_line_id == bl_id)).first():
        raise HTTPException(400, "该业务线下还有目标，请先删除目标")
    session.delete(bl)
    session.commit()
