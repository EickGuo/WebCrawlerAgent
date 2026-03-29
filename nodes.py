import json

from llm import get_llm
from prompts import (
    HTML_SUMMARIZER_PROMPT,
    STRATEGY_ROUTER_PROMPT,
    STATIC_PLAN_PROMPT,
    EXPLORATION_DECIDER_PROMPT,
    PLAN_SYNTHESIZER_PROMPT,
    RESULT_EVALUATOR_PROMPT,
    RUNTIME_DEBUG_PROMPT,
    CODE_EXPORTER_PROMPT,
)
from validators import (
    extract_first_json_object,
    validate_strategy_decision,
    validate_exploration_decision,
    validate_scraping_plan,
    validate_evaluation_decision,
)
from tools import (
    load_page,
    summarize_html_for_prompt,
    get_browser,
    close_browser,
    build_page_snapshot,
    absolutize_url,
    detect_human_intervention,
    sample_detail_pages,
    heuristic_evaluate,
)
from bs4 import BeautifulSoup

llm = get_llm()

STRUCTURAL_SELECTOR_KEYS = {
    "row_selector",
    "link_selector",
    "detail_link_selector",
    "detail_link_scope",
    "detail_link_text",
    "next_page_selector",
    "next_page_text",
    "pagination_scope_selector",
    "pagination_selector",
    "wait_selector",
    "container_selector",
    "item_selector",
    "list_selector",
}


def _trace(state, node_name: str):
    state.setdefault("trace", []).append(node_name)


def _clear_human_gate_state(state):
    state["human_intervention_required"] = False
    state["human_intervention_reason"] = ""
    state["human_intervention_evidence"] = []
    state["human_intervention_status"] = "idle"
    state["interrupted_phase"] = ""
    state["resume_from"] = ""


def _choose_first(*values):
    for value in values:
        if isinstance(value, str) and value.strip():
            return value.strip()
    return ""


def ask_llm_for_json(prompt_text: str, validator, *, repair_once: bool = True):
    raw = llm.invoke(prompt_text).content.strip()

    try:
        obj = extract_first_json_object(raw)
        return validator(obj)
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
        obj = extract_first_json_object(repaired)
        return validator(obj)


# ----------------------------
# A. Deterministic setup
# ----------------------------


def html_loader(state):
    _trace(state, "html_loader")
    state["html"] = load_page(state["url"])
    return state


def html_summarizer(state):
    _trace(state, "html_summarizer")
    html_snippet = summarize_html_for_prompt(state["html"])
    prompt = HTML_SUMMARIZER_PROMPT.format(
        user_request=state["user_request"],
        url=state["url"],
        html=html_snippet,
    )
    state["html_summary"] = llm.invoke(prompt).content.strip()
    return state


def strategy_router(state):
    _trace(state, "strategy_router")
    prompt = STRATEGY_ROUTER_PROMPT.format(
        user_request=state["user_request"],
        url=state["url"],
        html_summary=state["html_summary"],
    )
    decision = ask_llm_for_json(prompt, validate_strategy_decision)
    state["strategy"] = decision["strategy"]
    state["strategy_reason"] = decision["reason"]
    return state


def static_prepare(state):
    _trace(state, "static_prepare")
    prompt = STATIC_PLAN_PROMPT.format(
        user_request=state["user_request"],
        url=state["url"],
        html_summary=state["html_summary"],
    )
    state["scraping_plan"] = ask_llm_for_json(
        prompt,
        lambda obj: validate_scraping_plan(obj, fallback_url=state["url"]),
    )
    return state


# ----------------------------
# B. Dynamic exploration sub-agent
# ----------------------------


def browser_bootstrap(state):
    _trace(state, "browser_bootstrap")
    browser = get_browser()
    browser.start(state["url"])

    snapshot = build_page_snapshot()
    state["current_url"] = snapshot["url"]
    state["current_page_snapshot"] = snapshot
    state["last_successful_url"] = snapshot["url"]
    state["last_successful_snapshot"] = snapshot
    state["exploration_history"] = []
    state["visited_urls"] = [snapshot["url"]]
    state["detail_samples"] = []
    state["tool_budget_used"] = 0
    state["page_visit_count"] = 1
    state["resume_attempts"] = 0
    state.setdefault("metadata", {})
    state["metadata"]["last_listed_links"] = []
    _clear_human_gate_state(state)
    return state


def exploration_observer(state):
    _trace(state, "exploration_observer")
    snapshot = build_page_snapshot()
    state["current_url"] = snapshot["url"]
    state["current_page_snapshot"] = snapshot
    state["last_successful_url"] = snapshot["url"]
    state["last_successful_snapshot"] = snapshot
    state.setdefault("metadata", {})
    urls = state.setdefault("visited_urls", [])
    if snapshot["url"] not in urls:
        urls.append(snapshot["url"])
    return state


def human_gate_detector(state):
    _trace(state, "human_gate_detector")
    browser = get_browser()
    detection = detect_human_intervention(browser.page)
    state.setdefault("metadata", {})
    state["metadata"]["last_human_gate_detection"] = detection

    if detection.get("required"):
        state["human_intervention_required"] = True
        state["human_intervention_reason"] = detection.get("reason", "")
        state["human_intervention_evidence"] = detection.get("evidence", [])
        state["human_intervention_status"] = "detected"
        state["interrupted_phase"] = "exploration"
        state["resume_from"] = "exploration_observer"
        state["stop_reason"] = "human_intervention_required"
    elif state.get("human_intervention_status") != "resolved":
        _clear_human_gate_state(state)
        state["stop_reason"] = ""

    return state


def human_gate_pause(state):
    _trace(state, "human_gate_pause")
    browser = get_browser()
    state["human_intervention_status"] = "waiting"
    result = browser.wait_for_manual_resolution(state.get("human_intervention_reason", ""))
    state.setdefault("metadata", {})
    state["metadata"]["last_human_gate_pause_result"] = result
    if result.get("aborted"):
        state["human_intervention_status"] = "aborted"
        state["stop_reason"] = "human_intervention_aborted"
    else:
        state["human_intervention_status"] = "resuming"
    return state


def human_gate_resume(state):
    _trace(state, "human_gate_resume")
    browser = get_browser()
    detection = detect_human_intervention(browser.page)
    state.setdefault("metadata", {})
    state["metadata"]["last_human_gate_detection"] = detection

    if detection.get("required"):
        state["resume_attempts"] = state.get("resume_attempts", 0) + 1
        state["human_intervention_required"] = True
        state["human_intervention_reason"] = detection.get("reason", "")
        state["human_intervention_evidence"] = detection.get("evidence", [])
        state["human_intervention_status"] = "waiting"
        state["stop_reason"] = "human_intervention_required"
        return state

    snapshot = build_page_snapshot()
    state["current_url"] = snapshot["url"]
    state["current_page_snapshot"] = snapshot
    state["last_successful_url"] = snapshot["url"]
    state["last_successful_snapshot"] = snapshot
    state["human_intervention_status"] = "resolved"
    state["human_intervention_required"] = False
    state["human_intervention_reason"] = ""
    state["human_intervention_evidence"] = []
    state["stop_reason"] = ""
    return state


def human_gate_abort(state):
    _trace(state, "human_gate_abort")
    state["human_intervention_status"] = "aborted"
    state["error"] = f"Human intervention aborted: {state.get('human_intervention_reason', 'unknown')}"
    close_browser()
    return state


def exploration_decider(state):
    _trace(state, "exploration_decider")
    prompt = EXPLORATION_DECIDER_PROMPT.format(
        user_request=state["user_request"],
        url=state["url"],
        current_page_snapshot=json.dumps(state.get("current_page_snapshot", {}), ensure_ascii=False),
        visited_urls=json.dumps(state.get("visited_urls", []), ensure_ascii=False),
        detail_samples=json.dumps(state.get("detail_samples", []), ensure_ascii=False),
        exploration_history=json.dumps(state.get("exploration_history", [])[-5:], ensure_ascii=False),
        current_page_links=json.dumps(state.get("current_page_snapshot", {}).get("links", []), ensure_ascii=False),
        last_listed_links=json.dumps(state.get("metadata", {}).get("last_listed_links", []), ensure_ascii=False),
    )
    decision = ask_llm_for_json(prompt, validate_exploration_decision)
    state.setdefault("metadata", {})
    state["metadata"]["pending_exploration_decision"] = decision
    return state


def exploration_tool_executor(state):
    _trace(state, "exploration_tool_executor")
    browser = get_browser()
    decision = state["metadata"]["pending_exploration_decision"]
    tool = decision["tool"]
    args = dict(decision.get("args", {}))

    if tool == "finish":
        result = {"success": True, "finish": True}
    elif tool == "get_page_snapshot":
        result = {"success": True, "snapshot": build_page_snapshot()}
    elif tool == "list_links":
        result = browser.list_links(selector=args.get("selector", "a"), limit=args.get("limit", 20))
    elif tool == "list_buttons":
        result = {"success": True, "items": browser.list_buttons(limit=args.get("limit", 20))}
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
    elif tool == "click":
        result = browser.safe_click(args["selector"])
    elif tool == "goto":
        result = browser.safe_goto(args["url"])
    elif tool == "go_back":
        result = browser.safe_go_back()
    elif tool == "wait_for_selector":
        result = browser.safe_wait_for_selector(args["selector"])
    elif tool == "scroll_once":
        result = browser.safe_scroll_once()
    elif tool == "extract_preview":
        result = browser.extract_preview(args.get("selector", "body"), limit=args.get("limit"))
    elif tool == "count_selector":
        result = browser.count_selector(args.get("selector", "*"))
    elif tool == "sample_detail_pages":
        links = args.get("links", [])
        result = {
            "success": bool(links),
            "items": sample_detail_pages(links, limit=args.get("limit", 2)) if links else [],
            **({"error": "sample_detail_pages requires non-empty links"} if not links else {}),
        }
    else:
        result = {"success": False, "error": f"Unknown tool: {tool}"}

    state["metadata"]["last_tool_name"] = tool
    state["metadata"]["last_tool_args"] = args
    state["metadata"]["last_tool_result"] = result
    return state


def exploration_state_updater(state):
    _trace(state, "exploration_state_updater")
    decision = state["metadata"]["pending_exploration_decision"]
    tool = state["metadata"]["last_tool_name"]
    args = state["metadata"]["last_tool_args"]
    result = state["metadata"]["last_tool_result"]

    history_item = {
        "step": state.get("tool_budget_used", 0) + 1,
        "page_url": state.get("current_url", ""),
        "decision": {
            "reasoning": decision.get("reasoning", ""),
            "tool": tool,
            "args": args,
        },
        "result": result,
    }
    state.setdefault("exploration_history", []).append(history_item)
    state["tool_budget_used"] = state.get("tool_budget_used", 0) + 1

    if result.get("success") and result.get("snapshot"):
        snapshot = result["snapshot"]
        state["current_url"] = snapshot.get("url", state.get("current_url", ""))
        state["current_page_snapshot"] = snapshot
        state["last_successful_url"] = snapshot.get("url", state.get("last_successful_url", ""))
        state["last_successful_snapshot"] = snapshot

    if tool == "sample_detail_pages" and result.get("items"):
        state.setdefault("detail_samples", []).extend(result["items"])
        state["last_successful_url"] = state.get("current_url", "")
        state["last_successful_snapshot"] = state.get("current_page_snapshot")

    if tool == "list_links" and result.get("items"):
        state["metadata"]["last_listed_links"] = result["items"]

    return state


def exploration_router(state):
    _trace(state, "exploration_router")
    max_steps = state.get("max_exploration_steps", 8)
    max_detail = state.get("max_detail_samples", 2)
    decision = state["metadata"]["pending_exploration_decision"]
    tool = decision["tool"]

    if tool == "finish":
        state["stop_reason"] = "model_requested_finish"
        return state
    if state.get("tool_budget_used", 0) >= max_steps:
        state["stop_reason"] = "tool_budget_exhausted"
        return state
    if len(state.get("detail_samples", [])) >= max_detail:
        state["stop_reason"] = "detail_samples_collected"
        return state

    recent = state.get("exploration_history", [])[-3:]
    repeated = []
    for item in recent:
        d = item.get("decision", {})
        repeated.append((d.get("tool"), json.dumps(d.get("args", {}), sort_keys=True, ensure_ascii=False)))
    if len(repeated) >= 3 and len(set(repeated)) == 1:
        state["stop_reason"] = "repeated_same_action"
        return state

    state["stop_reason"] = ""
    return state


def plan_synthesizer(state):
    _trace(state, "plan_synthesizer")
    prompt = PLAN_SYNTHESIZER_PROMPT.format(
        user_request=state["user_request"],
        url=state["url"],
        current_page_snapshot=json.dumps(state.get("current_page_snapshot", {}), ensure_ascii=False),
        exploration_history=json.dumps(state.get("exploration_history", []), ensure_ascii=False),
        detail_samples=json.dumps(state.get("detail_samples", []), ensure_ascii=False),
        visited_urls=json.dumps(state.get("visited_urls", []), ensure_ascii=False),
    )
    state["scraping_plan"] = ask_llm_for_json(
        prompt,
        lambda obj: validate_scraping_plan(obj, fallback_url=state["url"]),
    )
    close_browser()
    return state


# ----------------------------
# C. Unified runtime pipeline
# ----------------------------


def _normalize_field_rules(plan, section_name: str) -> list[dict]:
    section = plan.get(section_name, {}) or {}
    selectors = plan.get("selectors", {}) or {}
    candidates = []

    for source in (section.get("fields"), selectors.get("fields")):
        if isinstance(source, list):
            candidates.extend(source)
        elif isinstance(source, dict):
            for field_name, field_rule in source.items():
                if isinstance(field_rule, str):
                    candidates.append({"name": field_name, "selector": field_rule})
                elif isinstance(field_rule, dict):
                    item = dict(field_rule)
                    item.setdefault("name", field_name)
                    candidates.append(item)

    if not candidates:
        for field_name, field_rule in selectors.items():
            if field_name in STRUCTURAL_SELECTOR_KEYS:
                continue
            if isinstance(field_rule, str):
                candidates.append({"name": field_name, "selector": field_rule})
            elif isinstance(field_rule, dict) and any(
                isinstance(field_rule.get(key), str) for key in ("selector", "container_selector", "match_text", "label")
            ):
                item = dict(field_rule)
                item.setdefault("name", field_name)
                candidates.append(item)

    normalized = []
    for item in candidates:
        if not isinstance(item, dict):
            continue
        field_name = str(item.get("name") or item.get("field") or item.get("label") or "").strip()
        if not field_name:
            continue
        rule = dict(item)
        rule["name"] = field_name
        normalized.append(rule)
    return normalized


def _pick_value_from_cells(cells: list[str], match_text: str, field_name: str) -> str:
    normalized_match = (match_text or field_name or "").strip().rstrip(":")
    cleaned_cells = [str(cell or "").strip() for cell in cells if str(cell or "").strip()]

    for cell in cleaned_cells:
        bare = cell.rstrip(":").strip()
        if not bare:
            continue
        if bare == normalized_match:
            continue
        if normalized_match and bare.startswith(normalized_match):
            suffix = bare[len(normalized_match):].lstrip(": ").strip()
            if suffix:
                return suffix
        return bare

    if cleaned_cells:
        row_text = " ".join(cleaned_cells)
        if normalized_match and row_text.startswith(normalized_match):
            suffix = row_text[len(normalized_match):].lstrip(": ").strip()
            if suffix:
                return suffix
        return row_text
    return ""


def _extract_field_from_page(browser, rule: dict) -> str:
    selector = str(rule.get("selector") or "").strip()
    if selector:
        text_result = browser.extract_text(selector, limit=1)
        if text_result.get("success") and text_result.get("items"):
            return text_result["items"][0]

    row_selector = _choose_first(rule.get("container_selector"), rule.get("row_selector"))
    match_text = _choose_first(rule.get("match_text"), rule.get("label"), rule.get("text"), rule.get("name"))
    if not row_selector or not match_text:
        return ""

    try:
        rows = browser.page.locator(row_selector)
        count = min(rows.count(), 30)
    except Exception:
        return ""

    for i in range(count):
        row = rows.nth(i)
        try:
            row_text = row.inner_text().strip()
        except Exception:
            row_text = ""
        if match_text not in row_text:
            continue

        try:
            cell_texts = row.locator("th, td").all_inner_texts()
        except Exception:
            cell_texts = []

        value = _pick_value_from_cells(cell_texts, match_text, str(rule.get("name", "")))
        if value:
            return value

        stripped = row_text.replace(match_text, "", 1).lstrip(": ").strip()
        if stripped:
            return stripped

    return ""


def _extract_fields_for_section(browser, plan: dict, section_name: str) -> dict:
    data = {}
    for rule in _normalize_field_rules(plan, section_name):
        value = _extract_field_from_page(browser, rule)
        if value:
            data[rule["name"]] = value
    return data


def _extract_list_rows(browser, plan: dict) -> list[dict]:
    list_page = plan.get("list_page", {}) or {}
    selectors = plan.get("selectors", {}) or {}
    row_selector = _choose_first(
        list_page.get("row_selector"),
        selectors.get("row_selector"),
        selectors.get("item_selector"),
        selectors.get("list_selector"),
    )
    if not row_selector:
        return []

    link_selector = _choose_first(
        list_page.get("link_selector"),
        selectors.get("link_selector"),
        selectors.get("detail_link_selector"),
        "a",
    )
    row_field_rules = _normalize_field_rules(plan, "list_page")
    items = []

    try:
        rows = browser.page.locator(row_selector)
        row_count = min(rows.count(), 50)
    except Exception:
        return []

    current_url = browser.page.url
    for i in range(row_count):
        row = rows.nth(i)
        try:
            row_text = row.inner_text().strip()
        except Exception:
            row_text = ""
        if not row_text:
            continue

        item = {"row_text": row_text}
        for rule in row_field_rules:
            selector = str(rule.get("selector") or "").strip()
            if not selector:
                continue
            try:
                value = row.locator(selector).first.inner_text().strip()
            except Exception:
                value = ""
            if value:
                item[rule["name"]] = value

        try:
            link = row.locator(link_selector).first
            href = (link.get_attribute("href") or "").strip()
            try:
                link_text = link.inner_text().strip()
            except Exception:
                link_text = ""
        except Exception:
            href = ""
            link_text = ""

        if href:
            item["href"] = absolutize_url(href, current_url)
        if link_text:
            item["link_text"] = link_text
        items.append(item)

    return items


def _handle_runtime_human_gate(state, browser, stage: str) -> str | None:
    while True:
        detection = detect_human_intervention(browser.page)
        if not detection.get("required"):
            state["human_intervention_required"] = False
            state["human_intervention_reason"] = ""
            state["human_intervention_evidence"] = []
            state["human_intervention_status"] = "resolved"
            return None

        state["human_intervention_required"] = True
        state["human_intervention_reason"] = detection.get("reason", "")
        state["human_intervention_evidence"] = detection.get("evidence", [])
        state["human_intervention_status"] = "waiting"
        state["interrupted_phase"] = "runtime_scraping"
        state["resume_from"] = stage

        pause_result = browser.wait_for_manual_resolution(detection.get("reason", ""))
        if pause_result.get("aborted"):
            state["human_intervention_status"] = "aborted"
            return "Human intervention aborted during runtime scraping"

        state["human_intervention_status"] = "resuming"


def _apply_required_actions(state, browser, plan: dict) -> str:
    for action in plan.get("required_actions", []):
        if not isinstance(action, dict):
            continue
        action_type = str(action.get("type") or action.get("action") or "").strip().lower()
        if action_type != "search":
            continue

        query = str(action.get("query") or action.get("keyword") or "").strip()
        input_selector = str(action.get("input_selector") or action.get("selector") or "").strip()
        if not query or not input_selector:
            return "Search action requires query and input_selector"

        result = browser.search_site(
            query=query,
            input_selector=input_selector,
            submit_selector=action.get("submit_selector"),
            submit_text=action.get("submit_text"),
            scope_selector=action.get("scope_selector"),
            press_enter=bool(action.get("press_enter", True)),
            result_selector=action.get("result_selector"),
        )
        if not result.get("success"):
            return result.get("error", "Search action failed")

        search_gate_error = _handle_runtime_human_gate(state, browser, "runtime_search")
        if search_gate_error:
            return search_gate_error

        state["current_url"] = result.get("url_after", state.get("current_url", ""))
        if result.get("snapshot"):
            state["current_page_snapshot"] = result["snapshot"]
            state["last_successful_url"] = result["snapshot"].get("url", state.get("last_successful_url", ""))
            state["last_successful_snapshot"] = result["snapshot"]

    return ""


def _extract_detail_record(browser, state, plan: dict, href: str) -> tuple[dict, str]:
    detail_url = absolutize_url(href, browser.page.url)
    goto_result = browser.safe_goto(detail_url)
    if not goto_result.get("success"):
        return {}, goto_result.get("error", f"Failed to open detail page: {detail_url}")

    human_gate_error = _handle_runtime_human_gate(state, browser, "runtime_detail")
    if human_gate_error:
        return {}, human_gate_error

    wait_selector = _choose_first(
        plan.get("detail_page", {}).get("wait_selector"),
        plan.get("validation", {}).get("detail_wait_selector"),
    )
    if wait_selector:
        wait_result = browser.safe_wait_for_selector(wait_selector)
        if not wait_result.get("success"):
            return {}, wait_result.get("error", "")

    detail_data = _extract_fields_for_section(browser, plan, "detail_page")
    go_back_result = browser.safe_go_back()
    if not go_back_result.get("success"):
        return detail_data, go_back_result.get("error", "")
    return detail_data, ""


def _advance_runtime_pagination(browser, plan: dict, current_page_index: int) -> dict:
    list_page = plan.get("list_page", {}) or {}
    selectors = plan.get("selectors", {}) or {}
    validation = plan.get("validation", {}) or {}
    max_pages = int(validation.get("max_pages", 20))

    if current_page_index + 1 >= max_pages:
        return {"advanced": False, "reason": "max_pages_reached"}

    next_page_selector = _choose_first(list_page.get("next_page_selector"), selectors.get("next_page_selector"))
    pagination_scope_selector = _choose_first(
        list_page.get("pagination_scope_selector"),
        selectors.get("pagination_scope_selector"),
    )
    pagination_selector = _choose_first(
        list_page.get("pagination_selector"),
        selectors.get("pagination_selector"),
    )
    next_page_text = _choose_first(
        list_page.get("next_page_text"),
        selectors.get("next_page_text"),
        str(current_page_index + 2),
    )

    if next_page_selector:
        click_result = browser.safe_click(next_page_selector)
    elif pagination_scope_selector or pagination_selector or next_page_text:
        click_result = browser.click_target(
            scope_selector=pagination_scope_selector or None,
            selector=pagination_selector or None,
            element_selector="a",
            text=next_page_text or None,
            exact=True,
            index=0,
        )
    else:
        return {"advanced": False, "reason": "no_pagination_rule"}

    if not click_result.get("success"):
        return {"advanced": False, "reason": click_result.get("error", "pagination_failed")}

    return {"advanced": True, "result": click_result}


def _run_dynamic_runtime(state) -> tuple[list[dict], str, dict]:
    plan = state["scraping_plan"]
    browser = get_browser()
    browser.start(plan.get("entry_url", state["url"]))

    error = _handle_runtime_human_gate(state, browser, "runtime_entry")
    if error:
        close_browser()
        return [], error, {"mode": "dynamic", "pages_visited": 0}

    error = _apply_required_actions(state, browser, plan)
    if error:
        close_browser()
        return [], error, {"mode": "dynamic", "pages_visited": 0, "stopped_reason": "required_action_failed"}

    records = []
    visited_signatures = set()
    pages_visited = 0
    detail_errors = 0

    while True:
        snapshot = build_page_snapshot()
        state["current_url"] = snapshot["url"]
        state["current_page_snapshot"] = snapshot
        state["last_successful_url"] = snapshot["url"]
        state["last_successful_snapshot"] = snapshot

        signature = f"{snapshot['url']}|{snapshot['local_snippet'][:400]}"
        if signature in visited_signatures:
            break
        visited_signatures.add(signature)
        pages_visited += 1

        list_items = _extract_list_rows(browser, plan)
        if list_items:
            for item in list_items:
                record = dict(item)
                href = item.get("href", "")
                needs_detail = bool(_normalize_field_rules(plan, "detail_page")) or plan.get("page_pattern") == "list_to_detail"
                if href and needs_detail:
                    detail_data, detail_error = _extract_detail_record(browser, state, plan, href)
                    if detail_data:
                        record.update(detail_data)
                    if detail_error:
                        detail_errors += 1
                        record["_detail_error"] = detail_error
                records.append(record)
        else:
            page_record = _extract_fields_for_section(browser, plan, "detail_page") or _extract_fields_for_section(browser, plan, "list_page")
            if page_record:
                page_record.setdefault("source_url", snapshot["url"])
                records.append(page_record)

        pagination_result = _advance_runtime_pagination(browser, plan, pages_visited - 1)
        if not pagination_result.get("advanced"):
            break

        error = _handle_runtime_human_gate(state, browser, "runtime_pagination")
        if error:
            close_browser()
            return records, error, {
                "mode": "dynamic",
                "pages_visited": pages_visited,
                "detail_errors": detail_errors,
                "stopped_reason": "human_gate_abort",
                "records_collected": len(records),
            }

    close_browser()
    return records, "", {
        "mode": "dynamic",
        "pages_visited": pages_visited,
        "detail_errors": detail_errors,
        "records_collected": len(records),
    }


def _run_static_runtime(state) -> tuple[list[dict], str, dict]:
    plan = state["scraping_plan"]
    html = load_page(plan.get("entry_url", state["url"]))
    state["html"] = html

    soup = BeautifulSoup(html, "html.parser")
    selectors = plan.get("selectors", {}) or {}
    records = []
    row_selector = _choose_first(plan.get("list_page", {}).get("row_selector"), selectors.get("row_selector"))

    if row_selector:
        rows = soup.select(row_selector)
        for row in rows[:50]:
            item = {"row_text": row.get_text(" ", strip=True)}
            for rule in _normalize_field_rules(plan, "list_page"):
                selector = str(rule.get("selector") or "").strip()
                if not selector:
                    continue
                node = row.select_one(selector)
                if node:
                    item[rule["name"]] = node.get_text(" ", strip=True)
            records.append(item)
    else:
        item = {}
        for rule in _normalize_field_rules(plan, "detail_page") or _normalize_field_rules(plan, "list_page"):
            selector = str(rule.get("selector") or "").strip()
            if not selector:
                continue
            node = soup.select_one(selector)
            if node:
                item[rule["name"]] = node.get_text(" ", strip=True)
        if item:
            records.append(item)

    return records, "", {"mode": "static", "records_collected": len(records)}


def runtime_executor(state):
    _trace(state, "runtime_executor")
    mode = state["scraping_plan"].get("mode", "dynamic")
    if mode == "static":
        records, error, meta = _run_static_runtime(state)
    else:
        records, error, meta = _run_dynamic_runtime(state)

    state["result_data"] = records
    state["result"] = json.dumps(records[:3], ensure_ascii=False, indent=2) if records else ""
    state["error"] = error
    state["execution_meta"] = meta
    return state


def result_evaluator(state):
    _trace(state, "result_evaluator")
    ok, reason = heuristic_evaluate(state.get("result", ""), state.get("error", ""))
    if not ok:
        state["evaluation_passed"] = False
        state["evaluation_reason"] = reason
        return state

    prompt = RESULT_EVALUATOR_PROMPT.format(
        user_request=state["user_request"],
        scraping_plan=json.dumps(state["scraping_plan"], ensure_ascii=False, indent=2),
        result=state.get("result", "")[:2000],
        error=state.get("error", ""),
        execution_meta=json.dumps(state.get("execution_meta", {}), ensure_ascii=False),
    )
    decision = ask_llm_for_json(prompt, validate_evaluation_decision)
    state["evaluation_passed"] = decision["passed"]
    state["evaluation_reason"] = decision["reason"]
    return state


def runtime_debug_agent(state):
    _trace(state, "runtime_debug_agent")
    prompt = RUNTIME_DEBUG_PROMPT.format(
        user_request=state["user_request"],
        scraping_plan=json.dumps(state["scraping_plan"], ensure_ascii=False, indent=2),
        result=state.get("result", ""),
        error=state.get("error", ""),
        execution_meta=json.dumps(state.get("execution_meta", {}), ensure_ascii=False),
        evaluation_reason=state.get("evaluation_reason", ""),
    )
    state["scraping_plan"] = ask_llm_for_json(
        prompt,
        lambda obj: validate_scraping_plan(obj, fallback_url=state["url"]),
    )
    state["debug_count"] = state.get("debug_count", 0) + 1
    return state


def runtime_finalizer(state):
    _trace(state, "runtime_finalizer")
    state["final_result"] = state.get("result", "")
    return state


def code_exporter(state):
    _trace(state, "code_exporter")
    prompt = CODE_EXPORTER_PROMPT.format(
        user_request=state["user_request"],
        scraping_plan=json.dumps(state["scraping_plan"], ensure_ascii=False, indent=2),
        result=state.get("result", ""),
    )
    state["final_code"] = llm.invoke(prompt).content.strip()
    return state
