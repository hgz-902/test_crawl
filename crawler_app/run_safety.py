from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from crawler_app.workflow import (
    DAUM_NEWS_API_FIXED_PAGE_LIMIT,
    DAUM_NEWS_API_MAX_LOOP_LIMIT,
    NAVER_NEWS_API_FIXED_PAGE_LIMIT,
    NAVER_NEWS_API_MAX_LOOP_LIMIT,
)


def read_config_for_safety(config_path: Path) -> dict[str, Any]:
    try:
        parsed = json.loads(config_path.read_text(encoding="utf-8"))
    except Exception:
        return {}
    return parsed if isinstance(parsed, dict) else {}


def run_safety_error(config: dict[str, Any], base_dir: Path) -> str | None:
    output_error = output_dir_safety_error(config, base_dir)
    if output_error:
        return output_error

    steps = config.get("steps") or []
    first_step = steps[0] if steps and isinstance(steps[0], dict) else {}
    parser_attr = str(first_step.get("attr") or "").strip().lower()
    if parser_attr == "naver":
        try:
            page_limit = int(first_step.get("page_limit") or NAVER_NEWS_API_FIXED_PAGE_LIMIT)
            loop_limit = int(first_step.get("loop_limit") or 0)
        except (TypeError, ValueError):
            return "Naver UI runs require numeric page_limit and loop_limit."
        if page_limit != NAVER_NEWS_API_FIXED_PAGE_LIMIT:
            return f"Naver UI runs require page_limit={NAVER_NEWS_API_FIXED_PAGE_LIMIT}."
        if loop_limit <= 0 or loop_limit > NAVER_NEWS_API_MAX_LOOP_LIMIT:
            return f"Naver UI runs require loop_limit between 1 and {NAVER_NEWS_API_MAX_LOOP_LIMIT}."
    if parser_attr == "daum":
        try:
            page_limit = int(first_step.get("page_limit") or DAUM_NEWS_API_FIXED_PAGE_LIMIT)
            loop_limit = int(first_step.get("loop_limit") or 0)
        except (TypeError, ValueError):
            return "Daum UI runs require numeric page_limit and loop_limit."
        if page_limit != DAUM_NEWS_API_FIXED_PAGE_LIMIT:
            return f"Daum UI runs require page_limit={DAUM_NEWS_API_FIXED_PAGE_LIMIT}."
        if loop_limit <= 0 or loop_limit > DAUM_NEWS_API_MAX_LOOP_LIMIT:
            return f"Daum UI runs require loop_limit between 1 and {DAUM_NEWS_API_MAX_LOOP_LIMIT}."
    return None


def output_dir_safety_error(config: dict[str, Any], base_dir: Path) -> str | None:
    raw_output_dir = str(config.get("output_dir") or "").strip()
    if not raw_output_dir:
        return None
    output_path = Path(raw_output_dir)
    if not output_path.is_absolute():
        output_path = base_dir / output_path
    try:
        resolved_output = output_path.resolve()
        resolved_base = base_dir.resolve()
    except OSError:
        return "UI runs require a valid output_dir path."
    if resolved_output == resolved_base or resolved_base in resolved_output.parents:
        return None
    return "UI runs require output_dir under the crawler project folder."
