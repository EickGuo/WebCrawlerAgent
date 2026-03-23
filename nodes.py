import json
import re

from llm import get_llm
from prompts import (
    HTML_SUMMARIZER_PROMPT,
    STRATEGY_ROUTER_PROMPT,
    STATIC_PLAN_PROMPT,
    EXPLORATION_DECIDER_PROMPT,
    PLAN_SYNTHESIZER_PROMPT,
    CODE_GENERATOR_PROMPT,
    RESULT_EVALUATOR_PROMPT,
    DEBUG_PROMPT,
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
    sample_detail_pages,
    clean_code_block,
    ensure_utf8_preamble,
    run_code,
    heuristic_evaluate,
)

llm = get_llm()


def _trace(state, node_name: str):
    state.setdefault("trace", []).append(node_name)

def _refresh_available_links(state, snapshot):
    state["available_links"] = snapshot.get("links", [])


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
    html = load_page(state["url"])
    state["html"] = html
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
    plan = ask_llm_for_json(
        prompt,
        lambda obj: validate_scraping_plan(obj, fallback_url=state["url"])
    )
    state["scraping_plan"] = plan
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
    state["exploration_history"] = []
    state["visited_urls"] = [snapshot["url"]]
    state["detail_samples"] = []
    state["tool_budget_used"] = 0
    state["page_visit_count"] = 1
    state.setdefault("metadata", {})
    state["metadata"]["last_listed_links"] = []
    _refresh_available_links(state, snapshot)
    return state


def exploration_observer(state):
    _trace(state, "exploration_observer")

    browser = get_browser()
    snapshot = build_page_snapshot()

    state["current_url"] = snapshot["url"]
    state["current_page_snapshot"] = snapshot
    state.setdefault("metadata", {})
    _refresh_available_links(state, snapshot)

    urls = state.setdefault("visited_urls", [])
    if snapshot["url"] not in urls:
        urls.append(snapshot["url"])

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
        available_links=json.dumps(state.get("available_links", []), ensure_ascii=False),
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
        result = browser.click(args["selector"])

    elif tool == "goto":
        result = browser.goto(args["url"])

    elif tool == "go_back":
        result = browser.go_back()

    elif tool == "wait_for_selector":
        result = browser.wait_for_selector(args["selector"])

    elif tool == "scroll_once":
        result = browser.scroll_once()

    elif tool == "extract_preview":
        result = browser.extract_preview(args.get("selector", "body"), limit=args.get("limit"))

    elif tool == "count_selector":
        result = browser.count_selector(args.get("selector", "*"))

    elif tool == "sample_detail_pages":
        result = {
            "success": bool(args.get("links")),
            "items": sample_detail_pages(args.get("links", []), limit=args.get("limit", 2)) if args.get("links") else [],
            **({"error": "sample_detail_pages requires non-empty links"} if not args.get("links") else {}),
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

    if tool == "sample_detail_pages" and result.get("items"):
        state.setdefault("detail_samples", []).extend(result["items"])

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
    plan = ask_llm_for_json(
        prompt,
        lambda obj: validate_scraping_plan(obj, fallback_url=state["url"])
    )
    state["scraping_plan"] = plan

    close_browser()
    return state


# ----------------------------
# C. Unified code pipeline
# ----------------------------

def code_generator(state):
    _trace(state, "code_generator")

    prompt = CODE_GENERATOR_PROMPT.format(
        user_request=state["user_request"],
        scraping_plan=json.dumps(state["scraping_plan"], ensure_ascii=False, indent=2),
    )
    state["code_raw"] = llm.invoke(prompt).content.strip()
    return state


def code_cleaner(state):
    _trace(state, "code_cleaner")
    code = clean_code_block(state["code_raw"])
    code = ensure_utf8_preamble(code)
    state["code"] = code
    return state


def code_executor(state):
    _trace(state, "code_executor")

    code_to_run = state["code"]
    stdout, stderr = run_code(code_to_run)

    state["result"] = stdout
    state["error"] = stderr
    state["execution_meta"] = {
        "mode": state["scraping_plan"].get("mode", ""),
        "stdout_len": len(stdout),
        "stderr_len": len(stderr),
    }
    return state


def result_evaluator(state):
    _trace(state, "result_evaluator")

    ok, reason = heuristic_evaluate(
        state.get("result", ""),
        state.get("error", "")
    )
    if not ok:
        state["evaluation_passed"] = False
        state["evaluation_reason"] = reason
        return state

    # Truncate result to avoid token waste - structural eval only needs a sample
    truncated_result = state.get("result", "")[:2000]

    prompt = RESULT_EVALUATOR_PROMPT.format(
        user_request=state["user_request"],
        scraping_plan=json.dumps(state["scraping_plan"], ensure_ascii=False, indent=2),
        result=truncated_result,
        error=state.get("error", ""),
        execution_meta=json.dumps(state.get("execution_meta", {}), ensure_ascii=False),
    )
    decision = ask_llm_for_json(prompt, validate_evaluation_decision)

    state["evaluation_passed"] = decision["passed"]
    state["evaluation_reason"] = decision["reason"]
    return state


def debug_agent(state):
    _trace(state, "debug_agent")

    prompt = DEBUG_PROMPT.format(
        user_request=state["user_request"],
        scraping_plan=json.dumps(state["scraping_plan"], ensure_ascii=False, indent=2),
        code=state.get("code", ""),
        result=state.get("result", ""),
        error=state.get("error", ""),
        execution_meta=json.dumps(state.get("execution_meta", {}), ensure_ascii=False),
        evaluation_reason=state.get("evaluation_reason", ""),
    )
    fixed = llm.invoke(prompt).content.strip()

    state["code_raw"] = fixed
    state["code"] = ensure_utf8_preamble(clean_code_block(fixed))
    state["debug_count"] = state.get("debug_count", 0) + 1
    return state


def code_finalizer(state):
    _trace(state, "code_finalizer")

    code = state.get("code", "")

    # Rule 1: remove the SAMPLE_LIMIT definition line entirely
    code = re.sub(r"^SAMPLE_LIMIT\s*=\s*\d+[^\n]*\n?", "", code, flags=re.MULTILINE)

    # Rule 2: replace [:SAMPLE_LIMIT] -> [:] (keep all items)
    # SAMPLE_LIMIT is only allowed in slice notation per CODE_GENERATOR_PROMPT rules,
    # so these two rules are exhaustive and safe.
    code = re.sub(r"\[:SAMPLE_LIMIT\]", "[:]", code)

    state["final_code"] = code
    return state
