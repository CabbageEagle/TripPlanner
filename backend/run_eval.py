"""Local runner for lightweight eval pipeline.

Purpose:
- Read test requests from ``test_cases.json``.
- Validate request schema with ``TripRequest``.
- Generate plan from real planner agent (default) or mock plan.
- Call ``judge_trip_plan`` and print per-dimension scores.

This script is designed for practical quality tracking of real generated itineraries.
"""

from __future__ import annotations

import argparse
import json
import re
import shutil
import subprocess
import time
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any

from app.models.schemas import TripRequest
from app.services.judge import JudgeOptions, judge_trip_plan


def parse_args() -> argparse.Namespace:
    """Parse CLI arguments for evaluation run."""

    parser = argparse.ArgumentParser(description="Run local LLM-as-judge evaluation cases.")
    parser.add_argument(
        "--cases",
        type=str,
        default="test_cases.json",
        help="Path to test cases json file",
    )
    parser.add_argument(
        "--mode",
        choices=["auto", "llm", "heuristic"],
        default="auto",
        help="Judge mode: auto selects llm if key exists, else heuristic.",
    )
    parser.add_argument(
        "--model",
        type=str,
        default=None,
        help="Optional override model for llm mode.",
    )
    parser.add_argument(
        "--source",
        choices=["agent", "mock"],
        default="agent",
        help="Plan source: real langgraph agent or local mock generator.",
    )
    parser.add_argument(
        "--strict-llm-judge",
        action="store_true",
        help="Fail a case if judge falls back to heuristic in llm/auto mode.",
    )
    parser.add_argument(
        "--report",
        type=str,
        default="eval_reports/eval_report_latest.json",
        help="Latest JSON report path. Default keeps a fixed latest report file.",
    )
    parser.add_argument(
        "--report-history-dir",
        type=str,
        default="eval_reports/history",
        help="History archive directory. A timestamped snapshot is copied here after each run.",
    )
    parser.add_argument(
        "--report-tag",
        type=str,
        default="manual",
        help="Tag used in history filename for experiment comparison (e.g. baseline/p0_partialfix).",
    )
    return parser.parse_args()


def _sanitize_tag(value: str | None) -> str:
    """Normalize tag text for safe filename usage."""
    tag = (value or "").strip()
    if not tag:
        return "manual"
    cleaned = re.sub(r"[^0-9A-Za-z_-]+", "_", tag)
    cleaned = cleaned.strip("_")
    return cleaned or "manual"


def _git_short_sha(cwd: Path) -> str:
    """Return short git SHA for traceability; fallback to 'nogit' when unavailable."""
    try:
        proc = subprocess.run(
            ["git", "rev-parse", "--short", "HEAD"],
            cwd=str(cwd),
            capture_output=True,
            text=True,
            check=False,
        )
        sha = (proc.stdout or "").strip()
        return sha if sha else "nogit"
    except Exception:
        return "nogit"


def _write_latest_and_archive(
    *,
    payload: dict[str, Any],
    latest_path: Path,
    history_dir: Path,
    report_tag: str,
    git_cwd: Path,
) -> tuple[Path, Path]:
    """Write fixed latest report and archive a timestamped history copy."""
    latest_path.parent.mkdir(parents=True, exist_ok=True)
    latest_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")

    history_dir.mkdir(parents=True, exist_ok=True)
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    tag = _sanitize_tag(report_tag)
    commit = _git_short_sha(git_cwd)
    archive_name = f"eval_report_{ts}_{tag}_{commit}.json"
    archive_path = history_dir / archive_name
    shutil.copy2(latest_path, archive_path)
    return latest_path, archive_path


def load_cases(path: Path) -> list[dict[str, Any]]:
    """Load test case list from json file."""

    content = path.read_text(encoding="utf-8")
    data = json.loads(content)
    if not isinstance(data, list):
        raise ValueError("test cases file must be a list")
    return data


def build_mock_plan(case_id: str, request: TripRequest) -> dict[str, Any]:
    """Build a synthetic but structured plan for judge smoke-testing.

    Why mock data:
    - Phase-1 goal is pipeline run-through, not generation quality.
    - Avoid dependence on external planner/LLM availability.
    """

    start_date = datetime.strptime(request.start_date, "%Y-%m-%d")
    days: list[dict[str, Any]] = []

    # Generate day-level plan blocks based on requested travel days.
    for index in range(request.travel_days):
        current_date = (start_date + timedelta(days=index)).strftime("%Y-%m-%d")
        base_time = "09:30" if request.daily_start_time is None else request.daily_start_time

        # Default timeline keeps meals and two attractions with reasonable gaps.
        timeline = [
            {
                "start_time": base_time,
                "end_time": "10:10",
                "activity_type": "meal",
                "activity_name": "早餐",
                "duration": 40,
                "cost": 25,
            },
            {
                "start_time": "10:40",
                "end_time": "12:10",
                "activity_type": "attraction",
                "activity_name": f"{request.city}地标景点A{index + 1}",
                "duration": 90,
                "cost": 60,
            },
            {
                "start_time": "12:30",
                "end_time": "13:30",
                "activity_type": "meal",
                "activity_name": "午餐",
                "duration": 60,
                "cost": 50,
            },
            {
                "start_time": "14:10",
                "end_time": "15:40",
                "activity_type": "attraction",
                "activity_name": f"{request.city}地标景点B{index + 1}",
                "duration": 90,
                "cost": 80,
            },
            {
                "start_time": "18:00",
                "end_time": "19:00",
                "activity_type": "meal",
                "activity_name": "晚餐",
                "duration": 60,
                "cost": 80,
            },
        ]

        # Attraction objects include core fields used by completeness scorer.
        attractions = [
            {
                "name": f"{request.city}地标景点A{index + 1}",
                "address": f"{request.city}市中心区域A{index + 1}",
                "location": {"longitude": 116.40 + index * 0.01, "latitude": 39.90 + index * 0.01},
                "visit_duration": 90,
                "description": f"{request.city}代表性景点，适合拍照与参观。",
                "category": "历史文化" if index % 2 == 0 else "城市漫游",
                "ticket_price": 60,
                "visit_start_time": "10:40",
                "visit_end_time": "12:10",
            },
            {
                "name": f"{request.city}地标景点B{index + 1}",
                "address": f"{request.city}热门街区B{index + 1}",
                "location": {"longitude": 116.45 + index * 0.01, "latitude": 39.95 + index * 0.01},
                "visit_duration": 90,
                "description": f"{request.city}经典景点，周边餐饮丰富。",
                "category": "美食",
                "ticket_price": 80,
                "visit_start_time": "14:10",
                "visit_end_time": "15:40",
            },
        ]

        days.append(
            {
                "date": current_date,
                "day_index": index,
                "description": f"第{index + 1}天行程",
                "transportation": request.transportation,
                "accommodation": request.accommodation,
                "hotel": {
                    "name": f"{request.city}酒店{index + 1}",
                    "address": f"{request.city}中心酒店区",
                    "location": {"longitude": 116.41, "latitude": 39.91},
                    "price_range": "300-500元",
                    "rating": "4.5",
                    "distance": "距核心景点2公里",
                    "type": request.accommodation,
                    "estimated_cost": 400,
                },
                "attractions": attractions,
                "meals": [
                    {"type": "breakfast", "name": "早餐", "description": "本地早餐", "estimated_cost": 25},
                    {"type": "lunch", "name": "午餐", "description": "本地午餐", "estimated_cost": 50},
                    {"type": "dinner", "name": "晚餐", "description": "本地晚餐", "estimated_cost": 80},
                ],
                "timeline": timeline,
                "total_cost": 695,
                "total_duration": 340,
            }
        )

    plan = {
        "city": request.city,
        "start_date": request.start_date,
        "end_date": request.end_date,
        "days": days,
        "weather_info": [],
        "overall_suggestions": "行程已按节奏均衡安排，可根据天气微调。",
        "budget": {
            "total_attractions": request.travel_days * 140,
            "total_hotels": request.travel_days * 400,
            "total_meals": request.travel_days * 155,
            "total_transportation": request.travel_days * 80,
            "total": request.travel_days * 775,
        },
    }

    # Case-specific perturbations to trigger expected dimension behavior.
    if case_id == "TC05":
        # Low-budget boundary: remove hotel cost and reduce total spending.
        plan["budget"] = {
            "total_attractions": 80,
            "total_hotels": 0,
            "total_meals": 120,
            "total_transportation": 100,
            "total": 300,
        }
        plan["days"][0]["hotel"] = None
        plan["days"][0]["total_cost"] = 300

    if case_id == "TC06":
        # Time-conflict boundary: create overlap and overtime tendency.
        plan["days"][0]["timeline"] = [
            {
                "start_time": "10:30",
                "end_time": "11:30",
                "activity_type": "attraction",
                "activity_name": "历史景点A",
                "duration": 60,
                "cost": 80,
            },
            {
                "start_time": "11:20",
                "end_time": "12:40",
                "activity_type": "attraction",
                "activity_name": "历史景点B",
                "duration": 80,
                "cost": 80,
            },
            {
                "start_time": "12:45",
                "end_time": "13:20",
                "activity_type": "meal",
                "activity_name": "午餐",
                "duration": 35,
                "cost": 40,
            },
        ]
        plan["days"][0]["attractions"].append(
            {
                "name": "历史景点C",
                "address": f"{request.city}临近区域C",
                "location": {"longitude": 108.95, "latitude": 34.27},
                "visit_duration": 60,
                "description": "补充景点",
                "category": "历史文化",
                "ticket_price": 70,
                "visit_start_time": "12:20",
                "visit_end_time": "13:20",
            }
        )

    if case_id == "TC07":
        # Cold-start preference case: keep complete structure, generic categories.
        for day in plan["days"]:
            for attraction in day["attractions"]:
                attraction["category"] = "综合景点"

    return plan


def _generate_plan_with_agent(request: TripRequest) -> dict[str, Any]:
    """Generate plan using the real LangGraph planner in this repo."""
    from app.agents.trip_planner_agent_langgraph import get_trip_planner_agent

    planner = get_trip_planner_agent()
    trip_plan = planner.plan_trip(request)
    return trip_plan.model_dump()


def main() -> None:
    """CLI entrypoint: run all cases and print score table.

    Case lifecycle:
    1. Validate request.
    2. Generate plan (agent/mock).
    3. Run judge scoring.
    4. Print table + optional report JSON.
    """

    args = parse_args()
    case_path = Path(args.cases).resolve()
    cases = load_cases(case_path)

    print(f"Loaded {len(cases)} cases from: {case_path}")
    print(f"Judge mode: {args.mode}")
    print(f"Plan source: {args.source}")
    print("-" * 118)
    print(
        f"{'CASE':<6} {'STATUS':<18} {'SRC':<8} {'GEN(s)':>7} {'MODE':<10} {'OVERALL':>8} "
        f"{'SCH':>6} {'BUD':>6} {'DIV':>6} {'COM':>6} {'FIT':>6}"
    )
    print("-" * 118)

    report_rows: list[dict[str, Any]] = []
    overall_scores: list[float] = []
    stopped_early = False

    for case in cases:
        case_id = str(case.get("case_id", "UNKNOWN"))
        expected_status = str(case.get("expected_status", "ok"))
        request_payload = case.get("request", {})

        # Validate request upfront so invalid test case is reported clearly.
        try:
            validated_request = TripRequest(**request_payload)
        except Exception as exc:
            status = "request_invalid"
            print(f"{case_id:<6} {status:<18} {'-':<8} {'-':>7} {'-':<10} {'-':>8} {'-':>6} {'-':>6} {'-':>6} {'-':>6} {'-':>6}")
            print(f"  reason: {exc}")
            report_rows.append(
                {
                    "case_id": case_id,
                    "status": status,
                    "error": str(exc),
                }
            )
            continue

        # Negative case expected to fail request validation.
        if expected_status == "request_invalid":
            print(
                f"{case_id:<6} {'expected_invalid':<18} {'-':<8} {'-':>7} {'-':<10} "
                f"{'-':>8} {'-':>6} {'-':>6} {'-':>6} {'-':>6} {'-':>6}"
            )
            report_rows.append(
                {
                    "case_id": case_id,
                    "status": "expected_invalid",
                }
            )
            continue

        start_ts = time.perf_counter()
        if args.source == "agent":
            try:
                plan_payload = _generate_plan_with_agent(validated_request)
            except Exception as exc:
                gen_seconds = round(time.perf_counter() - start_ts, 2)
                print(
                    f"{case_id:<6} {'generation_failed':<18} {'agent':<8} {gen_seconds:>7.2f} "
                    f"{'-':<10} {'-':>8} {'-':>6} {'-':>6} {'-':>6} {'-':>6} {'-':>6}"
                )
                print(f"  reason: {exc}")
                report_rows.append(
                    {
                        "case_id": case_id,
                        "status": "generation_failed",
                        "source": args.source,
                        "generation_seconds": gen_seconds,
                        "error": str(exc),
                    }
                )
                continue
        else:
            plan_payload = build_mock_plan(case_id, validated_request)
        gen_seconds = round(time.perf_counter() - start_ts, 2)

        judge_options = JudgeOptions(
            force_mode=None if args.mode == "auto" else args.mode,
            model=args.model,
        )
        result = judge_trip_plan(
            request_payload=validated_request.model_dump(),
            plan_payload=plan_payload,
            options=judge_options,
        )

        status = "ok"
        if args.strict_llm_judge and result.evaluation_mode != "llm":
            status = "judge_not_llm"

        print(
            f"{case_id:<6} {status:<18} {args.source:<8} {gen_seconds:>7.2f} {result.evaluation_mode:<10} {result.overall_score:>8.2f} "
            f"{result.scores.schedule_quality:>6.2f} {result.scores.budget_match:>6.2f} "
            f"{result.scores.attraction_diversity:>6.2f} {result.scores.completeness:>6.2f} "
            f"{result.scores.requirement_fit:>6.2f}"
        )
        if status == "ok":
            overall_scores.append(result.overall_score)
        if status == "judge_not_llm":
            print(f"  reason: strict llm judge required but fallback mode={result.evaluation_mode}")

        report_rows.append(
            {
                "case_id": case_id,
                "status": status,
                "source": args.source,
                "generation_seconds": gen_seconds,
                "evaluation_mode": result.evaluation_mode,
                "overall_score": result.overall_score,
                "scores": result.scores.model_dump(),
                "summary": result.summary,
                "issues": [issue.model_dump() for issue in result.issues],
            }
        )

        # In strict mode, the first fallback means this run is invalid for LLM-only evaluation.
        if args.strict_llm_judge and status == "judge_not_llm":
            stopped_early = True
            print("Stopped early: first non-LLM judge result encountered in strict mode.")
            break

    print("-" * 118)
    if overall_scores:
        avg = sum(overall_scores) / len(overall_scores)
        print(f"Average overall score (status=ok): {avg:.2f} across {len(overall_scores)} cases")
    else:
        print("Average overall score: N/A (no successful scored cases)")

    if args.report:
        payload = {
            "judge_mode": args.mode,
            "source": args.source,
            "strict_llm_judge": args.strict_llm_judge,
            "stopped_early": stopped_early,
            "rows": report_rows,
        }
        latest_path = Path(args.report).resolve()
        history_dir = Path(args.report_history_dir).resolve()
        latest_written, history_written = _write_latest_and_archive(
            payload=payload,
            latest_path=latest_path,
            history_dir=history_dir,
            report_tag=args.report_tag,
            git_cwd=Path(__file__).resolve().parent,
        )
        print(f"Latest report written: {latest_written}")
        print(f"History report archived: {history_written}")

    print("Done.")


if __name__ == "__main__":
    main()
