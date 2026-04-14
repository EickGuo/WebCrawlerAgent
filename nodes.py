import json
import re
from pathlib import Path
from typing import Any, Dict

from llm import get_llm
from prompts import (
    CODE_EXPORTER_PROMPT,
    PLAN_SYNTHESIZER_PROMPT,
    STATIC_PLAN_PROMPT,
    STRATEGY_ROUTER_PROMPT,
)
from tool.pageread_tool import load_page, summarize_html_for_prompt

from exploration import run_exploration_subagent


llm = get_llm()
EXPORTS_DIR = Path(__file__).resolve().parent / "exports"
FINAL_CODE_PATH = EXPORTS_DIR / "final_code.py"


def _trace(state, node_name: str):
    state.setdefault("trace", []).append(node_name)


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


def ask_llm_for_json(prompt_text: str, *, repair_once: bool = True):
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


def strip_python_fence(text: str) -> str:
    cleaned = text.strip()
    cleaned = re.sub(r"^```python\s*", "", cleaned, flags=re.IGNORECASE)
    cleaned = re.sub(r"^```\s*", "", cleaned)
    cleaned = re.sub(r"\s*```$", "", cleaned)
    return cleaned.strip()


def html_loader(state):
    _trace(state, "html_loader")
    state["html"] = load_page(state["url"])
    return state


def strategy_router(state):
    _trace(state, "strategy_router")
    cleaned_html = summarize_html_for_prompt(state["html"])
    prompt = STRATEGY_ROUTER_PROMPT.format(
        user_request=state["user_request"],
        url=state["url"],
        html=cleaned_html,
    )
    decision = ask_llm_for_json(prompt)
    state["strategy"] = decision["strategy"]
    state["strategy_reason"] = decision.get("reason", "")
    return state


def static_prepare(state):
    _trace(state, "static_prepare")
    cleaned_html = summarize_html_for_prompt(state["html"])
    prompt = STATIC_PLAN_PROMPT.format(
        user_request=state["user_request"],
        url=state["url"],
        html=cleaned_html,
    )
    state["scraping_plan"] = ask_llm_for_json(prompt)
    return state


def exploration_subagent(state):
    _trace(state, "exploration_subagent")
    update = run_exploration_subagent(state)
    state.update(update)
    return state


def plan_synthesizer(state):
    _trace(state, "plan_synthesizer")
    prompt = PLAN_SYNTHESIZER_PROMPT.format(
        user_request=state["user_request"],
        url=state["url"],
        exploration_summary=state.get("exploration_summary", ""),
        human_intervention_summary=json.dumps(state.get("human_intervention_summary", {}), ensure_ascii=False, indent=2),
    )
    state["scraping_plan"] = llm.invoke(prompt).content.strip()
    return state


def code_exporter(state):
    _trace(state, "code_exporter")
    scraping_plan = state["scraping_plan"]
    scraping_plan_text = (
        json.dumps(scraping_plan, ensure_ascii=False, indent=2)
        if isinstance(scraping_plan, dict)
        else str(scraping_plan)
    )
    prompt = CODE_EXPORTER_PROMPT.format(
        user_request=state["user_request"],
        entry_url=state["url"],
        scraping_plan=scraping_plan_text,
    )
    final_code = strip_python_fence(llm.invoke(prompt).content.strip())
    EXPORTS_DIR.mkdir(parents=True, exist_ok=True)
    FINAL_CODE_PATH.write_text(final_code, encoding="utf-8")
    state["final_code"] = final_code
    state["final_code_path"] = str(FINAL_CODE_PATH)
    return state
