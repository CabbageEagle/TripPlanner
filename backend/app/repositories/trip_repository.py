from __future__ import annotations

import uuid
from datetime import date
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from ..db.models import TripPlanRecord, TripPlanVersion


def create_trip_plan(
    db: Session,
    *,
    city: str,
    start_date: date,
    end_date: date,
    travel_days: int,
    request_payload: dict[str, Any],
    current_plan_payload: dict[str, Any],
    status: str = "generated",
) -> TripPlanRecord:
    trip_plan = TripPlanRecord(
        city=city,
        start_date=start_date,
        end_date=end_date,
        travel_days=travel_days,
        request_payload=request_payload,
        current_plan_payload=current_plan_payload,
        status=status,
    )
    db.add(trip_plan)
    db.flush()
    return trip_plan


def create_trip_plan_version(
    db: Session,
    *,
    trip_plan_id: uuid.UUID,
    version_no: int,
    source: str,
    plan_payload: dict[str, Any],
    note: str | None = None,
) -> TripPlanVersion:
    version = TripPlanVersion(
        trip_plan_id=trip_plan_id,
        version_no=version_no,
        source=source,
        plan_payload=plan_payload,
        note=note,
    )
    db.add(version)
    db.flush()
    return version


def get_trip_plan(db: Session, trip_plan_id: uuid.UUID) -> TripPlanRecord | None:
    return db.get(TripPlanRecord, trip_plan_id)


def get_trip_plan_or_raise(db: Session, trip_plan_id: uuid.UUID) -> TripPlanRecord:
    trip_plan = get_trip_plan(db, trip_plan_id)
    if trip_plan is None:
        raise ValueError(f"Trip plan {trip_plan_id} not found")
    return trip_plan


def list_trip_plan_versions(db: Session, trip_plan_id: uuid.UUID) -> list[TripPlanVersion]:
    stmt = (
        select(TripPlanVersion)
        .where(TripPlanVersion.trip_plan_id == trip_plan_id)
        .order_by(TripPlanVersion.version_no.desc())
    )
    return list(db.scalars(stmt))


def get_next_version_no(db: Session, trip_plan_id: uuid.UUID) -> int:
    stmt = select(func.max(TripPlanVersion.version_no)).where(TripPlanVersion.trip_plan_id == trip_plan_id)
    current_max = db.execute(stmt).scalar_one_or_none()
    return 1 if current_max is None else current_max + 1


def update_trip_plan_payload(
    db: Session,
    *,
    trip_plan_id: uuid.UUID,
    new_plan_payload: dict[str, Any],
    status: str | None = None,
) -> TripPlanRecord:
    trip_plan = get_trip_plan_or_raise(db, trip_plan_id)
    trip_plan.current_plan_payload = new_plan_payload
    if status is not None:
        trip_plan.status = status
    db.flush()
    return trip_plan


def save_new_trip_plan_version(
    db: Session,
    *,
    trip_plan_id: uuid.UUID,
    new_plan_payload: dict[str, Any],
    source: str,
    note: str | None = None,
    status: str | None = None,
) -> TripPlanVersion:
    update_trip_plan_payload(
        db,
        trip_plan_id=trip_plan_id,
        new_plan_payload=new_plan_payload,
        status=status,
    )
    version_no = get_next_version_no(db, trip_plan_id)
    return create_trip_plan_version(
        db,
        trip_plan_id=trip_plan_id,
        version_no=version_no,
        source=source,
        plan_payload=new_plan_payload,
        note=note,
    )
