"""LLM-as-judge core module with structured output guarantees.

This module exposes one public entrypoint: ``judge_trip_plan``.
It supports two modes:
1. ``llm``: use structured output from the model (Pydantic schema).
2. ``heuristic``: deterministic fallback when model call is unavailable.

Design goals:
- Output is always parseable and schema-validated.
- A score is always produced (fallback avoids pipeline interruption).
- Overall score is normalized by fixed rubric weights.
"""

from __future__ import annotations

import json
import os
from dataclasses import dataclass
from typing import Any

from langchain_core.messages import HumanMessage, SystemMessage
from langchain_openai import ChatOpenAI
from pydantic import BaseModel, Field
from pydantic import ValidationError

from ..config import get_settings

# Keep rubric version explicit so regression comparison remains reproducible.
RUBRIC_VERSION = "v1.0.0"

# Fixed weights must sum to 1.0.
RUBRIC_WEIGHTS = {
    "schedule_quality": 0.25,
    "budget_match": 0.20,
    "attraction_diversity": 0.20,
    "completeness": 0.20,
    "requirement_fit": 0.15,
}


class JudgeScores(BaseModel):
    """Per-dimension scores defined by the rubric.

    All dimensions are restricted to [0, 10] to keep data stable for storage and dashboards.
    """

    schedule_quality: float = Field(ge=0, le=10)
    budget_match: float = Field(ge=0, le=10)
    attraction_diversity: float = Field(ge=0, le=10)
    completeness: float = Field(ge=0, le=10)
    requirement_fit: float = Field(ge=0, le=10)


class JudgeIssue(BaseModel):
    """Single issue emitted by judge output for explainability."""

    dimension_key: str
    severity: str
    evidence: str
    suggestion: str


class JudgeResult(BaseModel):
    """Top-level structured judge output.

    ``overall_score`` is recalculated in code to avoid trusting model arithmetic.
    ``evaluation_mode`` indicates whether output came from LLM or heuristic fallback.
    """

    rubric_version: str = RUBRIC_VERSION
    scores: JudgeScores
    overall_score: float = Field(ge=0, le=10)
    summary: str
    issues: list[JudgeIssue] = Field(default_factory=list)
    confidence: float = Field(ge=0, le=1)
    evaluation_mode: str = "llm"


@dataclass(slots=True)
class JudgeOptions:
    """Runtime options for judge execution."""

    # "llm" | "heuristic" | None(auto detect)
    force_mode: str | None = None
    # Optional model override for LLM mode.
    model: str | None = None


def judge_trip_plan(
    *,
    request_payload: dict[str, Any],
    plan_payload: dict[str, Any],
    options: JudgeOptions | None = None,
) -> JudgeResult:
    """Evaluate a trip plan and always return a parseable ``JudgeResult``.

    Flow:
    1. Resolve mode (forced or auto).
    2. Try LLM structured output when in LLM mode.
    3. If LLM fails, transparently fall back to heuristic scoring.
    4. Normalize overall score and metadata.
    """

    opts = options or JudgeOptions()
    mode = _resolve_mode(opts.force_mode)

    if mode == "llm":
        try:
            result = _judge_with_llm(
                request_payload=request_payload,
                plan_payload=plan_payload,
                model=opts.model,
            )
            return _normalize_result(result, mode="llm")
        except Exception as exc:
            # Never break the pipeline because of transient model/network issues.
            fallback = _judge_with_heuristics(request_payload=request_payload, plan_payload=plan_payload)
            fallback.summary = f"{fallback.summary} (LLM failed, fallback used: {exc})"
            return _normalize_result(fallback, mode="heuristic")

    # Explicit heuristic mode, or auto mode without key.
    result = _judge_with_heuristics(request_payload=request_payload, plan_payload=plan_payload)
    return _normalize_result(result, mode="heuristic")


def _resolve_mode(force_mode: str | None) -> str:
    """Resolve effective mode.

    Rules:
    - If caller forces a valid mode, use it.
    - Otherwise auto-select LLM only when API key is available.
    """

    if force_mode in {"llm", "heuristic"}:
        return force_mode

    settings = get_settings()
    llm_api_key = settings.llm_api_key or os.getenv("LLM_API_KEY") or os.getenv("OPENAI_API_KEY")
    return "llm" if llm_api_key else "heuristic"


def _normalize_result(result: JudgeResult, *, mode: str) -> JudgeResult:
    """Recompute overall score from dimension scores and set output metadata."""

    result.rubric_version = RUBRIC_VERSION
    scores = result.scores
    weighted = (
        scores.schedule_quality * RUBRIC_WEIGHTS["schedule_quality"]
        + scores.budget_match * RUBRIC_WEIGHTS["budget_match"]
        + scores.attraction_diversity * RUBRIC_WEIGHTS["attraction_diversity"]
        + scores.completeness * RUBRIC_WEIGHTS["completeness"]
        + scores.requirement_fit * RUBRIC_WEIGHTS["requirement_fit"]
    )
    result.overall_score = round(max(0.0, min(10.0, weighted)), 2)
    result.evaluation_mode = mode
    return result


def _judge_with_llm(
    *,
    request_payload: dict[str, Any],
    plan_payload: dict[str, Any],
    model: str | None = None,
) -> JudgeResult:
    """Run model-based judging using strict structured output.

    Implementation detail:
    ``with_structured_output(JudgeResult)`` forces schema-shaped parsing.
    """

    settings = get_settings()
    api_key = settings.llm_api_key or os.getenv("LLM_API_KEY") or os.getenv("OPENAI_API_KEY")
    if not api_key:
        raise RuntimeError("Missing LLM API key")

    # Hard schema constraint passed to the model endpoint (when provider supports it).
    response_format = {
        "type": "json_schema",
        "json_schema": {
            "name": "judge_result",
            "strict": True,
            "schema": JudgeResult.model_json_schema(),
        },
    }
    llm = ChatOpenAI(
        # Use dedicated judge model instead of the main generation model.
        model=model or settings.judge_model,
        api_key=api_key,
        base_url=settings.llm_base_url,
        temperature=0,
        model_kwargs={"response_format": response_format},
    )

    # 使用中文提示词，和行程生成侧的语言保持一致，降低语义偏差。
    system_prompt = (
        "你是一个客观的旅行行程评审员（LLM-as-judge）。"
        "你必须只输出一个严格符合 JSON Schema 的 JSON 对象。\n"
        "不要输出任何解释性文本，不要添加多余字段，也不要缺少必填字段。\n"
        "评分标准版本：v1.0.0。\n"
        "评分维度（0-10）：schedule_quality、budget_match、attraction_diversity、completeness、requirement_fit。\n"
        "维度说明：\n"
        "- schedule_quality：时间线连贯性、交通/休息间隔、日程密度是否合理。\n"
        "- budget_match：预算约束匹配度与预算字段算术一致性。\n"
        "- attraction_diversity：兴趣标签覆盖度与景点类型多样性。\n"
        "- completeness：关键字段完整性与结构完整性。\n"
        "- requirement_fit：显式用户需求满足程度。\n"
        "issues 必须是对象数组，每个对象含 dimension_key、severity、evidence、suggestion。\n"
        "summary 必须是一句话中文总结。"
    )
    user_prompt = (
        "请根据上述评分标准评估下面的旅行计划。\n\n"
        "输出 JSON 结构（仅示意字段名，不得缺少）：\n"
        "{"
        "\"rubric_version\":\"v1.0.0\","
        "\"scores\":{"
        "\"schedule_quality\":0,"
        "\"budget_match\":0,"
        "\"attraction_diversity\":0,"
        "\"completeness\":0,"
        "\"requirement_fit\":0"
        "},"
        "\"overall_score\":0,"
        "\"summary\":\"...\","
        "\"issues\":[{\"dimension_key\":\"...\",\"severity\":\"...\",\"evidence\":\"...\",\"suggestion\":\"...\"}],"
        "\"confidence\":0,"
        "\"evaluation_mode\":\"llm\""
        "}\n\n"
        f"请求 JSON：\n{json.dumps(request_payload, ensure_ascii=False, indent=2)}\n\n"
        f"行程 JSON：\n{json.dumps(plan_payload, ensure_ascii=False, indent=2)}\n"
    )

    messages = [SystemMessage(content=system_prompt), HumanMessage(content=user_prompt)]
    last_error: Exception | None = None
    for attempt in range(2):
        try:
            response = llm.invoke(messages)
            payload = _extract_json_payload(response.content)
            validated = JudgeResult.model_validate(payload)
            return validated
        except (json.JSONDecodeError, ValidationError, TypeError, ValueError) as exc:
            last_error = exc
            # One repair round: force the model to correct format from previous invalid output.
            if attempt == 0:
                messages.append(
                    HumanMessage(
                        content=(
                            "你上一次输出未通过 JSON Schema 校验。\n"
                            f"校验错误如下：\n{exc}\n"
                            "请只返回一个修正后的 JSON 对象，必须严格匹配 schema，不能包含任何额外文本。"
                        )
                    )
                )
            else:
                break
    raise RuntimeError(f"Judge structured output validation failed: {last_error}")


def _extract_json_payload(content: Any) -> dict[str, Any]:
    """Extract JSON object payload from model response content.

    Handles common response formats:
    - plain JSON string
    - markdown fenced JSON
    - message content list chunks
    - already parsed dictionary
    """
    if isinstance(content, dict):
        return content

    if isinstance(content, list):
        text_parts: list[str] = []
        for item in content:
            if isinstance(item, str):
                text_parts.append(item)
            elif isinstance(item, dict):
                maybe_text = item.get("text")
                if isinstance(maybe_text, str):
                    text_parts.append(maybe_text)
        content = "".join(text_parts)

    if not isinstance(content, str):
        raise TypeError(f"Unsupported response content type: {type(content)!r}")

    text = content.strip()
    if text.startswith("```json"):
        text = text[7:]
    if text.startswith("```"):
        text = text[3:]
    if text.endswith("```"):
        text = text[:-3]
    text = text.strip()

    parsed = json.loads(text)
    if not isinstance(parsed, dict):
        raise TypeError(f"Expected JSON object, got: {type(parsed)!r}")
    return parsed


def _judge_with_heuristics(
    *,
    request_payload: dict[str, Any],
    plan_payload: dict[str, Any],
) -> JudgeResult:
    """Fallback scorer used when LLM cannot be called.

    This function intentionally mirrors the same five dimensions so downstream
    consumers do not need special-case logic.
    """

    days = plan_payload.get("days") if isinstance(plan_payload.get("days"), list) else []
    attractions = [a for d in days if isinstance(d, dict) for a in (d.get("attractions") or []) if isinstance(a, dict)]
    issues: list[JudgeIssue] = []

    schedule_score = _score_schedule(request_payload, days, issues)
    budget_score = _score_budget(request_payload, plan_payload, issues)
    diversity_score = _score_diversity(request_payload, attractions, issues)
    completeness_score = _score_completeness(plan_payload, days, attractions, issues)
    requirement_fit_score = _score_requirement_fit(request_payload, plan_payload, days, attractions, issues)

    scores = JudgeScores(
        schedule_quality=schedule_score,
        budget_match=budget_score,
        attraction_diversity=diversity_score,
        completeness=completeness_score,
        requirement_fit=requirement_fit_score,
    )
    return JudgeResult(
        scores=scores,
        overall_score=0,
        summary="Heuristic judge result generated without external LLM call.",
        # Keep only top-N issues so output stays concise.
        issues=issues[:8],
        confidence=0.62,
    )


def _score_schedule(request_payload: dict[str, Any], days: list[dict[str, Any]], issues: list[JudgeIssue]) -> float:
    """Score schedule quality based on timeline presence and conflict checks."""

    if not days:
        issues.append(
            JudgeIssue(
                dimension_key="schedule_quality",
                severity="high",
                evidence="days list is empty",
                suggestion="Provide day-level schedule with concrete activities.",
            )
        )
        return 0.0

    max_attractions = int(request_payload.get("max_attractions_per_day") or 4)
    has_timeline = False
    score = 8.8

    for day in days:
        timeline = day.get("timeline")
        if isinstance(timeline, list) and timeline:
            has_timeline = True

        # Penalty when attraction density exceeds user constraint.
        day_attr_count = len(day.get("attractions") or [])
        if day_attr_count > max_attractions:
            score -= 1.2
            issues.append(
                JudgeIssue(
                    dimension_key="schedule_quality",
                    severity="medium",
                    evidence=f"day {day.get('day_index', '?')} attractions={day_attr_count} exceeds limit={max_attractions}",
                    suggestion="Reduce attractions per day or expand available time window.",
                )
            )

    # Detect overlapping timeline entries and end-time overflow.
    conflicts = _plan_payload_conflicts(days, request_payload)
    score -= conflicts * 1.5
    if conflicts > 0:
        issues.append(
            JudgeIssue(
                dimension_key="schedule_quality",
                severity="high" if conflicts >= 2 else "medium",
                evidence=f"detected {conflicts} potential schedule conflicts",
                suggestion="Adjust activity sequence and add transport/rest buffer.",
            )
        )

    # Rubric requirement: no time arrangement -> zero.
    if not has_timeline:
        score = min(score, 0.0)
        issues.append(
            JudgeIssue(
                dimension_key="schedule_quality",
                severity="high",
                evidence="missing timeline/visit time fields",
                suggestion="Generate timeline or attraction-level visit_start/visit_end times.",
            )
        )
    return round(max(0.0, min(10.0, score)), 2)


def _score_budget(
    request_payload: dict[str, Any],
    plan_payload: dict[str, Any],
    issues: list[JudgeIssue],
) -> float:
    """Score budget match by availability, arithmetic consistency, and deviation."""

    budget = plan_payload.get("budget")
    budget_usage = plan_payload.get("budget_usage")
    max_budget = request_payload.get("max_budget")

    # Rubric requirement: no budget data -> zero.
    if not isinstance(budget, dict) and not isinstance(budget_usage, dict):
        issues.append(
            JudgeIssue(
                dimension_key="budget_match",
                severity="high",
                evidence="budget information is missing",
                suggestion="Provide budget summary with totals and category breakdown.",
            )
        )
        return 0.0

    total = None
    if isinstance(budget, dict):
        total = _safe_float(budget.get("total"))
        subtotal = sum(
            _safe_float(budget.get(name)) or 0.0
            for name in ("total_attractions", "total_hotels", "total_meals", "total_transportation")
        )
        # Add issue when category subtotal does not match the declared total.
        if total is not None and abs(total - subtotal) > 1:
            issues.append(
                JudgeIssue(
                    dimension_key="budget_match",
                    severity="medium",
                    evidence=f"budget total({total}) != subtotal({subtotal})",
                    suggestion="Reconcile budget arithmetic consistency.",
                )
            )
    if total is None and isinstance(budget_usage, dict):
        total = _safe_float(budget_usage.get("used_budget"))

    if total is None:
        return 0.0

    # Base score before user-budget deviation penalties.
    score = 8.0
    if max_budget:
        max_budget_f = float(max_budget)
        ratio = abs(total - max_budget_f) / max_budget_f if max_budget_f > 0 else 1.0
        if ratio <= 0.10:
            score = 10.0
        elif ratio <= 0.20:
            score = 8.0
        elif ratio <= 0.50:
            score = 5.0
        else:
            score = 2.0
            issues.append(
                JudgeIssue(
                    dimension_key="budget_match",
                    severity="high",
                    evidence=f"budget deviation too high (total={total}, max_budget={max_budget_f})",
                    suggestion="Reduce expensive items or adjust accommodation/transport strategy.",
                )
            )

    return round(max(0.0, min(10.0, score)), 2)


def _score_diversity(
    request_payload: dict[str, Any],
    attractions: list[dict[str, Any]],
    issues: list[JudgeIssue],
) -> float:
    """Score diversity by category variety and preference coverage."""

    if not attractions:
        issues.append(
            JudgeIssue(
                dimension_key="attraction_diversity",
                severity="high",
                evidence="no attractions found",
                suggestion="Add attractions aligned with user preferences.",
            )
        )
        return 0.0

    preferences = [str(x).strip().lower() for x in (request_payload.get("preferences") or []) if str(x).strip()]
    types = {str(a.get("category") or "").strip().lower() for a in attractions if str(a.get("category") or "").strip()}
    # Base score rewards type variety independent of preference matching.
    base = 6.0 + min(3.0, len(types) * 0.8)

    if not preferences:
        # Cold-start case: keep score moderate-high based on variety only.
        return round(min(9.0, base), 2)

    joined = " ".join(
        " ".join(
            [
                str(a.get("name") or ""),
                str(a.get("description") or ""),
                str(a.get("category") or ""),
            ]
        ).lower()
        for a in attractions
    )
    coverage = 0
    for pref in preferences:
        if pref and pref in joined:
            coverage += 1

    ratio = coverage / len(preferences)
    if ratio >= 1.0:
        score = 10.0
    elif ratio >= 0.7:
        score = 8.5
    elif ratio >= 0.4:
        score = 6.0
    else:
        score = 2.5
        issues.append(
            JudgeIssue(
                dimension_key="attraction_diversity",
                severity="medium",
                evidence=f"preference coverage low ({coverage}/{len(preferences)})",
                suggestion="Increase attractions explicitly matching user preference tags.",
            )
        )
    # Blend variety base and preference match.
    return round(max(0.0, min(10.0, (score + base) / 2.0)), 2)


def _score_completeness(
    plan_payload: dict[str, Any],
    days: list[dict[str, Any]],
    attractions: list[dict[str, Any]],
    issues: list[JudgeIssue],
) -> float:
    """Score structural completeness for top-level and attraction-level fields."""

    if not isinstance(plan_payload, dict) or not days:
        issues.append(
            JudgeIssue(
                dimension_key="completeness",
                severity="high",
                evidence="plan structure missing core fields",
                suggestion="Return complete plan schema with city/start/end/days.",
            )
        )
        return 0.0

    # Top-level mandatory fields.
    required_top = ["city", "start_date", "end_date", "days"]
    top_ok = sum(1 for field in required_top if field in plan_payload)

    # Attraction-level mandatory fields.
    required_attr = ["name", "address", "location", "visit_duration", "description", "ticket_price"]
    if attractions:
        total_checks = len(attractions) * len(required_attr)
        passed_checks = 0
        for attraction in attractions:
            for field in required_attr:
                value = attraction.get(field)
                if value is not None and value != "":
                    passed_checks += 1
        attr_ratio = passed_checks / total_checks if total_checks else 0
    else:
        attr_ratio = 0

    score = (top_ok / len(required_top)) * 4.0 + attr_ratio * 6.0
    if score < 6.0:
        issues.append(
            JudgeIssue(
                dimension_key="completeness",
                severity="medium",
                evidence=f"completeness score low ({score:.2f}/10)",
                suggestion="Fill missing attraction fields and day-level mandatory keys.",
            )
        )
    return round(max(0.0, min(10.0, score)), 2)


def _score_requirement_fit(
    request_payload: dict[str, Any],
    plan_payload: dict[str, Any],
    days: list[dict[str, Any]],
    attractions: list[dict[str, Any]],
    issues: list[JudgeIssue],
) -> float:
    """Score explicit requirement fit (days/transport/accommodation/free-text)."""

    if not days:
        return 0.0

    score = 8.0
    requested_days = int(request_payload.get("travel_days") or 0)
    if requested_days and requested_days != len(days):
        score -= 2.5
        issues.append(
            JudgeIssue(
                dimension_key="requirement_fit",
                severity="high",
                evidence=f"travel_days mismatch: request={requested_days}, plan={len(days)}",
                suggestion="Regenerate plan with exact requested day count.",
            )
        )

    transport_pref = str(request_payload.get("transportation") or "").strip()
    if transport_pref:
        day_transport = [str(day.get("transportation") or "") for day in days]
        if day_transport and not any(transport_pref in item for item in day_transport):
            score -= 1.0

    accommodation_pref = str(request_payload.get("accommodation") or "").strip()
    if accommodation_pref:
        day_acc = [str(day.get("accommodation") or "") for day in days]
        if day_acc and not any(accommodation_pref in item for item in day_acc):
            score -= 1.0

    free_text = str(request_payload.get("free_text_input") or "").strip().lower()
    if free_text:
        plan_text = json.dumps(plan_payload, ensure_ascii=False).lower()
        hit_count = sum(1 for token in _split_keywords(free_text) if token in plan_text)
        if hit_count == 0:
            score -= 2.0
            issues.append(
                JudgeIssue(
                    dimension_key="requirement_fit",
                    severity="medium",
                    evidence="free_text constraints not reflected",
                    suggestion="Inject user free-text constraints into planning prompt and validation rules.",
                )
            )

    if not attractions:
        score -= 2.0
    return round(max(0.0, min(10.0, score)), 2)


def _plan_payload_conflicts(days: list[dict[str, Any]], request_payload: dict[str, Any]) -> int:
    """Count schedule conflicts in timeline.

    Conflict types:
    - overlap: previous end time > current start time
    - overtime: day's final end time > requested daily_end_time
    """

    end_limit = str(request_payload.get("daily_end_time") or "")
    conflicts = 0
    for day in days:
        timeline = day.get("timeline")
        if not isinstance(timeline, list) or not timeline:
            continue

        previous_end = ""
        for item in timeline:
            if not isinstance(item, dict):
                continue
            start_time = str(item.get("start_time") or "")
            end_time = str(item.get("end_time") or "")
            if previous_end and start_time and previous_end > start_time:
                conflicts += 1
            previous_end = end_time or previous_end

        if end_limit and previous_end and previous_end > end_limit:
            conflicts += 1
    return conflicts


def _safe_float(value: Any) -> float | None:
    """Convert value to float; return None when conversion fails."""

    try:
        if value is None:
            return None
        return float(value)
    except (TypeError, ValueError):
        return None


def _split_keywords(text: str) -> list[str]:
    """Split free-text constraints into coarse tokens for quick matching."""

    separators = [",", "\uFF0C", "\u3002", " ", "\u3001", "\n", "\t"]
    tokens = [text]
    for sep in separators:
        next_tokens: list[str] = []
        for token in tokens:
            next_tokens.extend(token.split(sep))
        tokens = next_tokens
    return [token.strip() for token in tokens if len(token.strip()) >= 2]
