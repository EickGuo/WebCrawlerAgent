import json
from datetime import datetime
from pathlib import Path
from typing import Any


DEBUG_DIR = Path(__file__).resolve().parent / "debug"
DEBUG_LOG_PATH = DEBUG_DIR / "debug_log.json"
EXPLORATION_RECORD_PATH = DEBUG_DIR / "exploration_record.json"


def reset_debug_log() -> None:
    DEBUG_DIR.mkdir(parents=True, exist_ok=True)
    DEBUG_LOG_PATH.write_text(
        json.dumps({"events": []}, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    EXPLORATION_RECORD_PATH.write_text(
        json.dumps({"history": []}, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )


def _summarize_snapshot(snapshot: dict[str, Any]) -> dict[str, Any]:
    return {
        "url": snapshot.get("url", ""),
        "title": snapshot.get("title", ""),
        "page_architecture": snapshot.get("page_architecture", ""),
    }


def _summarize_tool_result(result: dict[str, Any]) -> dict[str, Any]:
    summary = {
        "success": result.get("success", False),
        "error": result.get("error", ""),
        "human_gate_required": result.get("human_gate", {}).get("required", False),
        "human_gate_reason": result.get("human_gate", {}).get("reason", ""),
    }
    if "count" in result:
        summary["count"] = result.get("count")
    if "matched_count" in result:
        summary["matched_count"] = result.get("matched_count")
    if "clicked_text" in result:
        summary["clicked_text"] = result.get("clicked_text", "")
    if "clicked_href" in result:
        summary["clicked_href"] = result.get("clicked_href", "")
    if "page" in result and isinstance(result.get("page"), dict):
        summary["page"] = {
            "url": result["page"].get("url", ""),
            "title": result["page"].get("title", ""),
        }
    if "items" in result and isinstance(result.get("items"), list):
        summary["items_count"] = len(result["items"])
    if result.get("snapshot"):
        summary["snapshot"] = _summarize_snapshot(result["snapshot"])
    return summary


def _summarize_metadata(metadata: dict[str, Any]) -> dict[str, Any]:
    summary: dict[str, Any] = {"keys": sorted(metadata.keys())}
    if "last_tool_execution" in metadata and isinstance(metadata["last_tool_execution"], dict):
        execution = metadata["last_tool_execution"]
        summary["last_tool_execution"] = {
            "tool": execution.get("tool", ""),
            "args": execution.get("args", {}),
            "result": _summarize_tool_result(execution.get("result", {}))
            if isinstance(execution.get("result"), dict)
            else str(execution.get("result", "")),
        }
    if "last_human_gate_detection" in metadata and isinstance(metadata["last_human_gate_detection"], dict):
        detection = metadata["last_human_gate_detection"]
        summary["last_human_gate_detection"] = {
            "required": detection.get("required", False),
            "reason": detection.get("reason", ""),
            "evidence_count": len(detection.get("evidence", [])),
        }
    if metadata.get("resume_pending_state_update"):
        summary["resume_pending_state_update"] = True
    if "last_sampled_detail_page" in metadata and isinstance(metadata["last_sampled_detail_page"], dict):
        sample = metadata["last_sampled_detail_page"]
        summary["last_sampled_detail_page"] = {
            "href": sample.get("href", ""),
            "title": sample.get("title", ""),
            "success": sample.get("success", False),
        }
    return summary


def _summarize_scraping_plan(plan: dict[str, Any]) -> dict[str, Any]:
    return {
        "keys": sorted(plan.keys()),
        "field_count": len(plan.get("fields", [])) if isinstance(plan.get("fields"), list) else 0,
        "required_actions_count": len(plan.get("required_actions", []))
        if isinstance(plan.get("required_actions"), list)
        else 0,
    }


def summarize_debug_update(update: Any, *, phase: str = "") -> Any:
    if isinstance(update, dict):
        summary: dict[str, Any] = {}
        for key, value in update.items():
            if key == "html":
                summary[key] = {"length": len(value) if isinstance(value, str) else 0}
            elif key == "current_page_snapshot" and isinstance(value, dict):
                summary[key] = _summarize_snapshot(value)
            elif key == "metadata" and isinstance(value, dict):
                summary[key] = _summarize_metadata(value)
            elif key == "scraping_plan" and isinstance(value, dict):
                if phase == "main":
                    summary[key] = value
                else:
                    summary[key] = _summarize_scraping_plan(value)
            elif key == "exploration_debug_steps" and isinstance(value, list):
                summary[key] = {"count": len(value)}
            elif key == "trace" and isinstance(value, list):
                summary[key] = {"count": len(value), "tail": value[-6:]}
            elif key == "visited_urls" and isinstance(value, list):
                summary[key] = {"count": len(value), "tail": value[-5:]}
            elif key == "exploration_history" and isinstance(value, list):
                summary[key] = {"count": len(value)}
            elif key == "recent_failure_summary" and isinstance(value, list):
                summary[key] = {"count": len(value), "items": value[:3]}
            elif isinstance(value, str):
                summary[key] = value
            elif isinstance(value, list):
                summary[key] = {"count": len(value), "sample": value[:3]}
            elif isinstance(value, dict):
                summary[key] = summarize_debug_update(value, phase=phase)
            else:
                summary[key] = value
        return summary
    return update


def append_debug_event(phase: str, node: str, update: Any) -> None:
    event = {
        "ts": datetime.now().astimezone().isoformat(timespec="seconds"),
        "phase": phase,
        "node": node,
        "summary": summarize_debug_update(update, phase=phase),
    }
    if DEBUG_LOG_PATH.exists():
        try:
            payload = json.loads(DEBUG_LOG_PATH.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            payload = {"events": []}
    else:
        payload = {"events": []}

    events = payload.get("events")
    if not isinstance(events, list):
        events = []
    events.append(event)
    payload["events"] = events
    DEBUG_LOG_PATH.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2, default=str),
        encoding="utf-8",
    )


def append_exploration_history_record(item: dict[str, Any]) -> None:
    if EXPLORATION_RECORD_PATH.exists():
        try:
            record = json.loads(EXPLORATION_RECORD_PATH.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            record = {"history": []}
    else:
        record = {"history": []}

    history = record.get("history")
    if not isinstance(history, list):
        history = []

    entry = {
        "index": len(history) + 1,
        "ts": datetime.now().astimezone().isoformat(timespec="seconds"),
        "step": item.get("step"),
        "page_url": item.get("page_url", ""),
        "decision": summarize_debug_update(item.get("decision", {}), phase="exploration"),
        "result": summarize_debug_update(item.get("result", {}), phase="exploration"),
    }
    if "detail_architecture_read" in item:
        entry["detail_architecture_read"] = summarize_debug_update(
            item.get("detail_architecture_read", {}),
            phase="exploration",
        )
    history.append(entry)
    record["history"] = history
    EXPLORATION_RECORD_PATH.write_text(
        json.dumps(record, ensure_ascii=False, indent=2, default=str),
        encoding="utf-8",
    )
