"""旅行规划 API 路由"""

import asyncio
from datetime import date
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from ...agents.trip_planner_agent_langgraph import get_trip_planner_agent
from ...db.session import get_db
from ...models.schemas import TripPlan, TripPlanResponse, TripPlanUpdateRequest, TripRequest
from ...repositories.trip_repository import (
    create_trip_plan,
    create_trip_plan_version,
    get_trip_plan,
    save_new_trip_plan_version,
)

router = APIRouter(prefix="/trip", tags=["旅行规划"])


def _parse_iso_date(value: str) -> date:
    return date.fromisoformat(value)


@router.post(
    "/plan",
    response_model=TripPlanResponse,
    summary="生成旅行计划",
    description="根据用户输入的旅行需求生成详细的旅行计划",
)
async def plan_trip(request: TripRequest, db: Session = Depends(get_db)):
    """生成旅行计划并持久化到数据库。"""
    try:
        print(f"\n{'='*60}")
        print("收到旅行规划请求:")
        print(f"   城市: {request.city}")
        print(f"   日期: {request.start_date} - {request.end_date}")
        print(f"   天数: {request.travel_days}")
        print(f"{'='*60}\n")

        agent = get_trip_planner_agent()
        trip_plan = await asyncio.to_thread(agent.plan_trip, request)
        plan_payload = trip_plan.model_dump()
        request_payload = request.model_dump()

        trip_record = create_trip_plan(
            db,
            city=request.city,
            start_date=_parse_iso_date(request.start_date),
            end_date=_parse_iso_date(request.end_date),
            travel_days=request.travel_days,
            request_payload=request_payload,
            current_plan_payload=plan_payload,
        )
        create_trip_plan_version(
            db,
            trip_plan_id=trip_record.id,
            version_no=1,
            source="generated",
            plan_payload=plan_payload,
        )
        db.commit()

        return TripPlanResponse(
            success=True,
            message="旅行计划生成成功",
            plan_id=str(trip_record.id),
            data=trip_plan,
        )

    except Exception as e:
        db.rollback()
        print(f"生成旅行计划失败: {str(e)}")
        import traceback
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=f"生成旅行计划失败: {str(e)}")


@router.get(
    "/health",
    summary="健康检查",
    description="检查旅行规划服务是否正常",
)
async def health_check():
    """健康检查。"""
    try:
        agent = get_trip_planner_agent()
        return {
            "status": "healthy",
            "service": "trip-planner",
            "engine": "LangGraph",
            "graph_compiled": agent.app is not None,
        }
    except Exception as e:
        raise HTTPException(status_code=503, detail=f"服务不可用: {str(e)}")


@router.get(
    "/plans/{plan_id}",
    response_model=TripPlanResponse,
    summary="获取旅行计划",
    description="根据 plan_id 获取当前保存的旅行计划",
)
async def get_trip(plan_id: UUID, db: Session = Depends(get_db)):
    """获取已保存的旅行计划。"""
    trip_record = get_trip_plan(db, plan_id)
    if trip_record is None:
        raise HTTPException(status_code=404, detail="旅行计划不存在")

    try:
        trip_plan = TripPlan(**trip_record.current_plan_payload)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"旅行计划数据损坏: {str(e)}")

    return TripPlanResponse(
        success=True,
        message="旅行计划获取成功",
        plan_id=str(trip_record.id),
        data=trip_plan,
    )


@router.put(
    "/plans/{plan_id}",
    response_model=TripPlanResponse,
    summary="更新旅行计划",
    description="保存编辑后的旅行计划并生成新版本",
)
async def update_trip(plan_id: UUID, request: TripPlanUpdateRequest, db: Session = Depends(get_db)):
    """更新已保存的旅行计划。"""
    try:
        trip_record = get_trip_plan(db, plan_id)
        if trip_record is None:
            raise HTTPException(status_code=404, detail="旅行计划不存在")

        updated_payload = request.data.model_dump()
        save_new_trip_plan_version(
            db,
            trip_plan_id=plan_id,
            new_plan_payload=updated_payload,
            source="user_edit",
            note=request.note,
            status="edited",
        )
        db.commit()

        return TripPlanResponse(
            success=True,
            message="旅行计划保存成功",
            plan_id=str(plan_id),
            data=request.data,
        )
    except HTTPException:
        db.rollback()
        raise
    except Exception as e:
        db.rollback()
        raise HTTPException(status_code=500, detail=f"保存旅行计划失败: {str(e)}")
