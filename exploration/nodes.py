import json
import re
from typing import Any, Dict

from llm import get_llm
from debug_utils import append_exploration_history_record
from tool.browser_tool import (
    detect_human_intervention,
    detect_interrupting_overlay,
    get_browser,
    sample_detail_pages,
    try_close_interrupting_overlay,
)
from tool.pageread_tool import build_page_snapshot, read_page_architecture

from .prompts import (
    EXPLORATION_SUMMARIZER_PROMPT,
    HUMAN_INTERVENTION_SUMMARIZER_PROMPT,
    TOOL_ARG_BUILDER_PROMPT,
    TOOL_SELECTOR_PROMPT,
)
from .state import ExplorationState
from .utils import load_tool_doc, load_tool_index, summarize_recent_failures


llm = get_llm()


def _ensure_metadata(state: ExplorationState) -> Dict[str, Any]:
    return state.setdefault("metadata", {})


def _clear_human_gate_state(state: ExplorationState) -> None:
    state["human_intervention_required"] = False
    state["human_intervention_reason"] = ""
    state["resume_from"] = ""


def _compact_tool_result(result: Dict[str, Any]) -> Dict[str, Any]:
    compact: Dict[str, Any] = {
        "success": bool(result.get("success", False)),
        "error": str(result.get("error", "") or ""),
    }
    if result.get("clicked_text"):
        compact["clicked_text"] = result.get("clicked_text", "")
    if result.get("clicked_href"):
        compact["clicked_href"] = result.get("clicked_href", "")
    if "count" in result:
        compact["count"] = result.get("count")
    if "matched_count" in result:
        compact["matched_count"] = result.get("matched_count")
    if "selector" in result and result.get("selector"):
        compact["selector"] = result.get("selector")
    if result.get("human_gate", {}).get("required"):
        compact["human_gate"] = {
            "required": True,
            "reason": result.get("human_gate", {}).get("reason", ""),
        }
    if result.get("snapshot"):
        snapshot = result["snapshot"]
        compact["page"] = {
            "url": snapshot.get("url", ""),
            "title": snapshot.get("title", ""),
        }
    elif isinstance(result.get("page"), dict):
        compact["page"] = {
            "url": result["page"].get("url", ""),
            "title": result["page"].get("title", ""),
        }
    if isinstance(result.get("items"), list):
        items = result["items"]
        compact_items = []
        for item in items[:3]:
            if isinstance(item, dict):
                compact_item = {
                    "success": bool(item.get("success", False)),
                    "href": item.get("href", ""),
                    "text": item.get("text", ""),
                    "title": item.get("title", ""),
                    "error": str(item.get("error", "") or ""),
                }
                compact_items.append(compact_item)
            else:
                compact_items.append(str(item))
        compact["items"] = compact_items
        compact["items_count"] = len(items)
    return compact


def _count_successful_detail_samples(state: ExplorationState) -> int:
    count = 0
    for item in state.get("exploration_history", []):
        if item.get("decision", {}).get("tool") != "sample_detail_pages":
            continue
        result = item.get("result", {})
        for sample in result.get("items", []):
            if isinstance(sample, dict) and sample.get("success"):
                count += 1
    return count


def extract_first_json_object(text: str) -> Dict[str, Any]:
    text = text.strip()
    try:
        obj = json.loads(text)
        if isinstance(obj, dict):
            return obj
    except Exception:
        pass

    match = re.search(r"\{[\s\S]*\}", text)
    if not match:
        raise ValueError(f"No JSON object found in model output:\n{text}")

    candidate = match.group(0).replace("```json", "").replace("```", "").strip()
    obj = json.loads(candidate)
    if not isinstance(obj, dict):
        raise ValueError("Could not parse JSON object")
    return obj


def _ask_llm_for_json(prompt_text: str, *, repair_once: bool = True):
    raw = llm.invoke(prompt_text).content.strip()
    try:
        return extract_first_json_object(raw)
    except Exception:
        if not repair_once:
            raise
        repair_prompt = f"""
You must repair the following output into one valid JSON object only.

Broken output:
{raw}

Return JSON only. No markdown fences. No explanations.
"""
        repaired = llm.invoke(repair_prompt).content.strip()
        return extract_first_json_object(repaired)


def _analyze_sampled_detail_page(state: ExplorationState, sampled_detail: Dict[str, Any]) -> Dict[str, Any]:
    tool_doc_content = load_tool_doc("read_page_architecture")
    recent_failure_summary = summarize_recent_failures(state.get("exploration_history", []))
    prompt = TOOL_ARG_BUILDER_PROMPT.format(
        user_request=state["user_request"],
        url=state["url"],
        selected_tool="read_page_architecture",
        current_page_architecture=sampled_detail.get("page_architecture", ""),
        exploration_history=json.dumps(state.get("exploration_history", []), ensure_ascii=False),
        recent_failure_summary=json.dumps(recent_failure_summary, ensure_ascii=False),
        selected_tool_context=json.dumps(
            {
                "analysis_target": "last_sampled_detail_page",
                "detail_page_url": sampled_detail.get("href", ""),
                "detail_page_title": sampled_detail.get("title", ""),
                "instruction": (
                    "Explain how the final scraper should extract the target information from this detail page. "
                    "Describe the likely container or pattern, the extraction steps, and the success signal. "
                    "Put that explanation in `reasoning`."
                ),
            },
            ensure_ascii=False,
            indent=2,
        ),
        tool_doc_content=tool_doc_content,
    )
    decision = _ask_llm_for_json(prompt)
    return {
        "reasoning": decision.get("reasoning", ""),
        "result": _compact_tool_result(read_page_architecture(sampled_detail)),
    }


def browser_bootstrap(state: ExplorationState) -> ExplorationState:
    browser = get_browser()
    browser.start(state["url"])

    snapshot = build_page_snapshot()
    state["current_url"] = snapshot["url"]
    state["current_page_snapshot"] = snapshot
    state["visited_urls"] = [snapshot["url"]]
    state["exploration_history"] = []
    state["tool_budget_used"] = 0
    state["resume_attempts"] = 0
    state["stop_reason"] = ""
    state["human_intervention_summary"] = {}
    meta = _ensure_metadata(state)
    meta["last_sampled_detail_page"] = {}
    _clear_human_gate_state(state)
    return state


def observer(state: ExplorationState) -> ExplorationState:
    snapshot = build_page_snapshot()
    state["current_url"] = snapshot["url"]
    state["current_page_snapshot"] = snapshot
    visited = state.setdefault("visited_urls", [])
    if snapshot["url"] not in visited:
        visited.append(snapshot["url"])
    return state


def human_gate_detector(state: ExplorationState) -> ExplorationState:
    browser = get_browser()
    detection = detect_human_intervention(browser.page)
    _ensure_metadata(state)["last_human_gate_detection"] = detection
    if detection.get("required"):
        state["human_intervention_required"] = True
        state["human_intervention_reason"] = detection.get("reason", "")
        state["resume_from"] = "observer"
        return state

    overlay_detection = detect_interrupting_overlay(browser.page)
    _ensure_metadata(state)["last_interrupt_detection"] = overlay_detection
    if overlay_detection.get("required"):
        auto_close = try_close_interrupting_overlay(browser.page)
        _ensure_metadata(state)["last_interrupt_handling"] = auto_close
        if auto_close.get("handled"):
            if auto_close.get("human_gate", {}).get("required"):
                state["human_intervention_required"] = True
                state["human_intervention_reason"] = auto_close["human_gate"].get("reason", "") or "verification_required"
                state["resume_from"] = "observer"
                _ensure_metadata(state)["last_human_gate_detection"] = auto_close["human_gate"]
                return state
            _clear_human_gate_state(state)
            return observer(state)
        state["human_intervention_required"] = True
        state["human_intervention_reason"] = "dismiss_overlay_required"
        state["resume_from"] = "observer"
        return state

    _clear_human_gate_state(state)
    return state


def human_gate_pause(state: ExplorationState) -> ExplorationState:
    browser = get_browser()
    pause_result = browser.wait_for_manual_resolution(state.get("human_intervention_reason", ""))
    if pause_result.get("aborted"):
        state["stop_reason"] = "human_intervention_aborted"
    return state


def human_gate_resume(state: ExplorationState) -> ExplorationState:
    browser = get_browser()
    detection = detect_human_intervention(browser.page)
    _ensure_metadata(state)["last_human_gate_detection"] = detection

    if detection.get("required"):
        state["resume_attempts"] = state.get("resume_attempts", 0) + 1
        state["human_intervention_required"] = True
        state["human_intervention_reason"] = detection.get("reason", "")
        if state.get("resume_attempts", 0) >= state.get("max_resume_attempts", 3):
            state["stop_reason"] = "human_intervention_unresolved"
        return state

    overlay_detection = detect_interrupting_overlay(browser.page)
    _ensure_metadata(state)["last_interrupt_detection"] = overlay_detection
    if overlay_detection.get("required"):
        auto_close = try_close_interrupting_overlay(browser.page)
        _ensure_metadata(state)["last_interrupt_handling"] = auto_close
        if auto_close.get("handled"):
            if auto_close.get("human_gate", {}).get("required"):
                state["resume_attempts"] = state.get("resume_attempts", 0) + 1
                state["human_intervention_required"] = True
                state["human_intervention_reason"] = auto_close["human_gate"].get("reason", "") or "verification_required"
                _ensure_metadata(state)["last_human_gate_detection"] = auto_close["human_gate"]
                if state.get("resume_attempts", 0) >= state.get("max_resume_attempts", 3):
                    state["stop_reason"] = "human_intervention_unresolved"
                return state
            _clear_human_gate_state(state)
            return observer(state)

        state["resume_attempts"] = state.get("resume_attempts", 0) + 1
        state["human_intervention_required"] = True
        state["human_intervention_reason"] = "dismiss_overlay_required"
        if state.get("resume_attempts", 0) >= state.get("max_resume_attempts", 3):
            state["stop_reason"] = "human_intervention_unresolved"
        return state

    _clear_human_gate_state(state)
    return observer(state)


def tool_selector(state: ExplorationState) -> ExplorationState:
    tool_index = load_tool_index()
    snapshot = state.get("current_page_snapshot", {})
    prompt = TOOL_SELECTOR_PROMPT.format(
        user_request=state["user_request"],
        url=state["url"],
        current_page_architecture=snapshot.get("page_architecture", ""),
        exploration_history=json.dumps(state.get("exploration_history", [])[-5:], ensure_ascii=False),
        tool_index=tool_index,
    )
    decision = _ask_llm_for_json(prompt)
    state["selected_tool"] = decision.get("tool", "finish")
    state["selected_tool_reasoning"] = decision.get("reasoning", "")
    return state


def tool_arg_builder(state: ExplorationState) -> ExplorationState:
    selected_tool = state.get("selected_tool", "finish")
    if selected_tool == "finish":
        state["tool_arg_reasoning"] = state.get("selected_tool_reasoning", "")
        state["tool_arg_draft"] = {
            "reasoning": state.get("selected_tool_reasoning", ""),
            "tool": "finish",
            "args": {},
        }
        return state

    tool_doc_content = load_tool_doc(selected_tool)
    recent_failure_summary = summarize_recent_failures(state.get("exploration_history", []))
    snapshot = state.get("current_page_snapshot", {})
    prompt = TOOL_ARG_BUILDER_PROMPT.format(
        user_request=state["user_request"],
        url=state["url"],
        selected_tool=selected_tool,
        current_page_architecture=snapshot.get("page_architecture", ""),
        exploration_history=json.dumps(state.get("exploration_history", []), ensure_ascii=False),
        recent_failure_summary=json.dumps(recent_failure_summary, ensure_ascii=False),
        selected_tool_context="",
        tool_doc_content=tool_doc_content,
    )
    decision = _ask_llm_for_json(prompt)
    if decision.get("tool", selected_tool) != selected_tool:
        raise ValueError(f"Tool arg builder changed tool from {selected_tool} to {decision['tool']}")
    state["recent_failure_summary"] = recent_failure_summary
    state["tool_arg_reasoning"] = decision.get("reasoning", "")
    state["tool_arg_draft"] = decision
    return state


def tool_executor(state: ExplorationState) -> ExplorationState:
    browser = get_browser()
    decision = state.get("tool_arg_draft", {}) or {"tool": "finish", "args": {}}
    tool = decision["tool"]
    args = dict(decision.get("args", {}))

    if tool == "finish":
        result = {"success": True, "finish": True}
    elif tool == "search_site":
        result = browser.search_site(
            query=args["query"],
            input_selector=args["input_selector"],
            submit_selector=args.get("submit_selector"),
            submit_text=args.get("submit_text"),
            scope_selector=args.get("scope_selector"),
            press_enter=args.get("press_enter", True),
            result_selector=args.get("result_selector"),
        )
    elif tool == "click_target":
        result = browser.click_target(
            scope_selector=args.get("scope_selector"),
            selector=args.get("selector"),
            element_selector=args.get("element_selector"),
            text=args.get("text"),
            exact=args.get("exact", False),
            index=args.get("index", 0),
        )
    elif tool == "goto":
        result = browser.safe_goto(args["url"])
    elif tool == "go_back":
        result = browser.safe_go_back()
    elif tool == "wait_for_selector":
        result = browser.safe_wait_for_selector(args["selector"])
    elif tool == "scroll_once":
        result = browser.safe_scroll_once()
    elif tool == "sample_detail_pages":
        links = args.get("links", [])
        result = {
            "success": bool(links),
            "items": sample_detail_pages(links, limit=args.get("limit", 2)) if links else [],
            **({"error": "sample_detail_pages requires non-empty links"} if not links else {}),
        }
    else:
        result = {"success": False, "error": f"Unknown tool: {tool}"}

    _ensure_metadata(state)["last_tool_execution"] = {
        "tool": tool,
        "args": args,
        "result": result,
    }
    return state


def post_tool_interrupt_handler(state: ExplorationState) -> ExplorationState:
    browser = get_browser()
    meta = _ensure_metadata(state)
    execution = meta.get("last_tool_execution", {})
    result = execution.get("result", {})

    result_human_gate = result.get("human_gate", {}) if isinstance(result, dict) else {}
    if result_human_gate.get("required"):
        state["human_intervention_required"] = True
        state["human_intervention_reason"] = result_human_gate.get("reason", "") or "verification_required"
        state["resume_from"] = "observer"
        meta["resume_pending_state_update"] = True
        meta["last_human_gate_detection"] = result_human_gate
        meta["last_interrupt_handling"] = {
            "type": "human_gate",
            "source": "tool_result",
            "success": False,
        }
        return state

    overlay_detection = detect_interrupting_overlay(browser.page)
    meta["last_interrupt_detection"] = overlay_detection
    if not overlay_detection.get("required"):
        meta["last_interrupt_handling"] = {"type": "none", "success": True}
        return state

    auto_close = try_close_interrupting_overlay(browser.page)
    meta["last_interrupt_handling"] = auto_close
    if auto_close.get("handled"):
        execution_result = execution.get("result", {})
        if auto_close.get("snapshot"):
            execution_result["snapshot"] = auto_close["snapshot"]
        execution_result["interrupt_handling"] = {
            "type": "auto_close",
            "reason": auto_close.get("reason", ""),
            "evidence": auto_close.get("evidence", []),
        }
        if auto_close.get("human_gate", {}).get("required"):
            state["human_intervention_required"] = True
            state["human_intervention_reason"] = auto_close["human_gate"].get("reason", "") or "verification_required"
            state["resume_from"] = "observer"
            meta["resume_pending_state_update"] = True
            meta["last_human_gate_detection"] = auto_close["human_gate"]
        return state

    state["human_intervention_required"] = True
    state["human_intervention_reason"] = "dismiss_overlay_required"
    state["resume_from"] = "observer"
    meta["resume_pending_state_update"] = True
    return state


def state_updater(state: ExplorationState) -> ExplorationState:
    meta = _ensure_metadata(state)
    execution = meta.get("last_tool_execution", {})
    tool = execution.get("tool", "")
    args = execution.get("args", {})
    result = execution.get("result", {})

    history_item = {
        "step": state.get("tool_budget_used", 0) + 1,
        "page_url": state.get("current_url", ""),
        "decision": {
            "reasoning": state.get("tool_arg_reasoning", state.get("selected_tool_reasoning", "")),
            "tool": tool,
            "args": args,
        },
        "result": _compact_tool_result(result),
    }

    if result.get("success") and result.get("snapshot"):
        snapshot = result["snapshot"]
        state["current_url"] = snapshot.get("url", state.get("current_url", ""))
        state["current_page_snapshot"] = snapshot

    if tool == "sample_detail_pages":
        successful_samples = [
            item for item in result.get("items", [])
            if isinstance(item, dict) and item.get("success")
        ]
        if successful_samples:
            meta["last_sampled_detail_page"] = successful_samples[0]
            history_item["detail_architecture_read"] = _analyze_sampled_detail_page(
                state,
                successful_samples[0],
            )

    meta["resume_pending_state_update"] = False
    state.setdefault("exploration_history", []).append(history_item)
    append_exploration_history_record(history_item)
    state["tool_budget_used"] = state.get("tool_budget_used", 0) + 1
    return state


def router(state: ExplorationState) -> str:
    max_steps = state.get("max_exploration_steps", 8)
    max_detail = state.get("max_detail_samples", 2)
    tool = _ensure_metadata(state).get("last_tool_execution", {}).get("tool", "")

    if state.get("stop_reason") in {"human_intervention_aborted", "human_intervention_unresolved"}:
        return "stop"
    if tool == "finish":
        state["stop_reason"] = "model_requested_finish"
        return "stop"
    if state.get("tool_budget_used", 0) >= max_steps:
        state["stop_reason"] = "tool_budget_exhausted"
        return "stop"
    if _count_successful_detail_samples(state) >= max_detail:
        state["stop_reason"] = "detail_samples_collected"
        return "stop"

    recent = state.get("exploration_history", [])[-3:]
    repeated = []
    for item in recent:
        decision = item.get("decision", {})
        repeated.append((decision.get("tool"), json.dumps(decision.get("args", {}), ensure_ascii=False, sort_keys=True)))
    if len(repeated) == 3 and len(set(repeated)) == 1:
        state["stop_reason"] = "repeated_same_action"
        return "stop"
    return "continue"


def summarizer(state: ExplorationState) -> Dict[str, Any]:
    prompt = EXPLORATION_SUMMARIZER_PROMPT.format(
        user_request=state["user_request"],
        exploration_history=json.dumps(state.get("exploration_history", []), ensure_ascii=False),
        stop_reason=state.get("stop_reason", ""),
    )
    summary = _ask_llm_for_json(prompt)
    return {
        "exploration_summary": summary.get("exploration_summary", ""),
        "exploration_stop_reason": state.get("stop_reason", ""),
    }


def human_intervention_summarizer(state: ExplorationState) -> Dict[str, Any]:
    detection = _ensure_metadata(state).get("last_human_gate_detection", {})
    status = "resolved"
    if state.get("stop_reason") == "human_intervention_aborted":
        status = "aborted"
    elif state.get("stop_reason") == "human_intervention_unresolved" or state.get("human_intervention_required"):
        status = "waiting"

    prompt = HUMAN_INTERVENTION_SUMMARIZER_PROMPT.format(
        user_request=state["user_request"],
        reason=state.get("human_intervention_reason", ""),
        status=status,
        evidence=json.dumps(detection.get("evidence", []), ensure_ascii=False),
        exploration_history=json.dumps(state.get("exploration_history", []), ensure_ascii=False),
        current_page_snapshot=json.dumps(state.get("current_page_snapshot", {}), ensure_ascii=False),
    )
    return _ask_llm_for_json(prompt)


def exploration_summary_node(state: ExplorationState) -> ExplorationState:
    state["exploration_summary_result"] = summarizer(state)
    return state


def human_intervention_summary_node(state: ExplorationState) -> ExplorationState:
    summary = human_intervention_summarizer(state)
    state["human_intervention_summary"] = summary
    return state
