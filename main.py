from langgraph.graph import END, StateGraph

from debug_utils import append_debug_event, reset_debug_log
from nodes import (
    code_exporter,
    exploration_subagent,
    html_loader,
    plan_synthesizer,
    static_prepare,
    strategy_router,
)
from state import CrawlerState
from user_information import user_information


def route_by_strategy(state: CrawlerState):
    return state.get("strategy", "static")


def route_after_exploration(state: CrawlerState):
    human_summary = state.get("human_intervention_summary") or {}
    if human_summary.get("required") or state.get("exploration_stop_reason", "").startswith("human_intervention"):
        return "blocked"
    return "plan"


builder = StateGraph(CrawlerState)

builder.add_node("html_loader", html_loader)
builder.add_node("strategy_router", strategy_router)
builder.add_node("static_prepare", static_prepare)
builder.add_node("exploration_subagent", exploration_subagent)
builder.add_node("plan_synthesizer", plan_synthesizer)
builder.add_node("code_exporter", code_exporter)

builder.set_entry_point("html_loader")

builder.add_edge("html_loader", "strategy_router")
builder.add_conditional_edges(
    "strategy_router",
    route_by_strategy,
    {
        "static": "static_prepare",
        "dynamic": "exploration_subagent",
    },
)
builder.add_edge("static_prepare", "code_exporter")
builder.add_conditional_edges(
    "exploration_subagent",
    route_after_exploration,
    {
        "blocked": END,
        "plan": "plan_synthesizer",
    },
)
builder.add_edge("plan_synthesizer", "code_exporter")
builder.add_edge("code_exporter", END)

graph = builder.compile()


if __name__ == "__main__":
    info = user_information()
    init_state: CrawlerState = {
        "url": info["url"],
        "user_request": info["user_request"],
        "max_exploration_steps": info["max_exploration_steps"],
        "max_detail_samples": info["max_detail_samples"],
        "max_resume_attempts": info.get("max_resume_attempts", 3),
        "trace": [],
    }

    reset_debug_log()
    for step in graph.stream(init_state):
        node, update = next(iter(step.items()))
        print(f"Executed node: {node}", flush=True)
        append_debug_event("main", node, update)
