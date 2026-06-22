from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any
import json
import re

from crawler_app.workflow import (
    _config_filter_terms,
    _config_search_terms,
    load_workflow_config,
    normalize_workflow_config,
    safe_name,
    validate_workflow_config,
)


CONFIG_DIR = Path("configs")


# 설정 summary 정보를 담는 데이터 객체다.
@dataclass(slots=True)
class ConfigSummary:
    name: str
    path: Path
    start_url: str
    output_dir: str
    search_terms: list[str]
    filter_terms: list[str]
    notes: str
    created_at: str


# 설정 디렉터리의 JSON config 목록을 UI 표시용으로 읽는다.
def list_configs(config_dir: str | Path = CONFIG_DIR) -> list[ConfigSummary]:
    root = Path(config_dir)
    if not root.exists():
        return []

    configs: list[ConfigSummary] = []
    for path in sorted(root.glob("*.json")):
        try:
            config = load_workflow_config(path)
        except Exception:
            continue
        configs.append(
            ConfigSummary(
                name=str(config["name"]),
                path=path,
                start_url=str(config.get("start_url") or ""),
                output_dir=str(config.get("output_dir") or ""),
                search_terms=list(_config_search_terms(config)),
                filter_terms=list(_config_filter_terms(config)),
                notes=str(config.get("notes") or ""),
                created_at=str(config.get("created_at") or ""),
            )
        )
    return sorted(
        configs,
        key=lambda item: (item.created_at or "", item.name),
        reverse=True,
    )


# 설정 이름에 해당하는 JSON config 내용을 읽는다.
def get_config(name: str, config_dir: str | Path = CONFIG_DIR) -> dict[str, Any]:
    return load_workflow_config(config_name_to_path(name, config_dir))


# config payload를 기존 이름 기준으로 저장한다.
def save_config(config: dict[str, Any], config_dir: str | Path = CONFIG_DIR) -> Path:
    config = normalize_workflow_config(config)
    validate_workflow_config(config)
    path = config_name_to_path(str(config["name"]), config_dir)
    write_config_file(config, path)
    return path


# config payload를 지정한 새 이름으로 저장한다.
def save_config_as(config: dict[str, Any], name: str, config_dir: str | Path = CONFIG_DIR) -> Path:
    config = normalize_workflow_config(config)
    validate_workflow_config(config)
    path = config_name_to_path(name, config_dir)
    write_config_file(config, path)
    return path


# 정규화된 config 내용을 JSON 파일로 기록한다.
def write_config_file(config: dict[str, Any], path: str | Path) -> None:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = dict(config)
    now = _timestamp_now()
    existing_created_at = _read_existing_created_at(path)
    payload["created_at"] = str(payload.get("created_at") or existing_created_at or now)
    payload["updated_at"] = now
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


# 설정 이름에 해당하는 JSON config 파일을 삭제한다.
def delete_config(name: str, config_dir: str | Path = CONFIG_DIR) -> None:
    path = config_name_to_path(name, config_dir)
    if path.exists():
        path.unlink()


# 설정 이름을 실제 config 파일 경로로 변환한다.
def config_name_to_path(name: str, config_dir: str | Path = CONFIG_DIR) -> Path:
    root = Path(config_dir)
    raw_name = str(name).strip()
    exact_stem = Path(raw_name).name
    if exact_stem and exact_stem == raw_name:
        exact_path = root / f"{exact_stem}.json"
        if exact_path.exists():
            return exact_path
    cleaned = config_file_stem(name)
    return root / f"{cleaned}.json"


# config 이름을 안전한 파일 stem 값으로 변환한다.
def config_file_stem(name: str) -> str:
    normalized = re.sub(r"\s+", "_", name.strip())
    return safe_name(normalized).lower()


# 현재 시각을 config 메타데이터용 ISO 문자열로 만든다.
def _timestamp_now() -> str:
    return datetime.now().astimezone().isoformat(timespec="seconds")


# 기존 config 파일의 created_at 값을 보존용으로 읽는다.
def _read_existing_created_at(path: Path) -> str | None:
    if not path.exists():
        return None

    try:
        existing = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None

    if not isinstance(existing, dict):
        return None

    created_at = existing.get("created_at")
    return str(created_at) if created_at else None
