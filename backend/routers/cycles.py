"""周期 CRUD。"""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from sqlmodel import Session, select

from db import get_session
from models import Cycle, Goal
from schemas import CycleIn, CycleUpdate

router = APIRouter(prefix="/api/cycles", tags=["cycles"])


@router.get("")
def list_cycles(session: Session = Depends(get_session)):
    return session.exec(select(Cycle).order_by(Cycle.start_date.desc(), Cycle.id.desc())).all()


@router.post("", status_code=201)
def create_cycle(payload: CycleIn, session: Session = Depends(get_session)):
    c = Cycle(**payload.model_dump())
    session.add(c)
    session.commit()
    session.refresh(c)
    return c


@router.patch("/{cycle_id}")
def update_cycle(cycle_id: int, payload: CycleUpdate, session: Session = Depends(get_session)):
    c = session.get(Cycle, cycle_id)
    if not c:
        raise HTTPException(404, "周期不存在")
    for k, v in payload.model_dump(exclude_unset=True).items():
        setattr(c, k, v)
    session.add(c)
    session.commit()
    session.refresh(c)
    return c


@router.delete("/{cycle_id}", status_code=204)
def delete_cycle(cycle_id: int, session: Session = Depends(get_session)):
    c = session.get(Cycle, cycle_id)
    if not c:
        raise HTTPException(404, "周期不存在")
    if session.exec(select(Goal).where(Goal.cycle_id == cycle_id)).first():
        raise HTTPException(400, "该周期下还有目标，不能删除")
    session.delete(c)
    session.commit()
