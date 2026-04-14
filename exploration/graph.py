from typing import Any, Dict

from langgraph.graph import END, StateGraph

from tool.browser_tool import close_browser

from .nodes import (
    browser_bootstrap,
    exploration_summary_node,
    human_gate_detector,
    human_gate_pause,
    human_gate_resume,
    human_intervention_summary_node,
    observer,
    post_tool_interrupt_handler,
    router,
    state_updater,
    tool_arg_builder,
    tool_executor,
    tool_selector,
)
from .state import ExplorationState


def route_after_human_gate_detection(state: ExplorationState) -> str:
    if state.get("human_intervention_required"):
        return "pause"
    return "select"


def route_after_human_gate_resume(state: ExplorationState) -> str:
    if state.get("stop_reason") in {"human_intervention_aborted", "human_intervention_unresolved"}:
        return "summarize"
    if state.get("human_intervention_required"):
        return "pause"
    if state.get("metadata", {}).get("resume_pending_state_update"):
        return "update"
    return "select"


def route_after_state_update(state: ExplorationState) -> str:
    decision = router(state)
    if decision == "continue":
        return "observe"
    return "summarize"


def route_after_post_tool_interrupt(state: ExplorationState) -> str:
    if state.get("human_intervention_required"):
        return "pause"
    return "update"


def route_after_exploration_summary(state: ExplorationState) -> str:
    if state.get("human_intervention_required") or state.get("stop_reason", "").startswith("human_intervention"):
        return "human_summary"
    return "end"


def build_exploration_graph():
    builder = StateGraph(ExplorationState)

    builder.add_node("browser_bootstrap", browser_bootstrap)
    builder.add_node("observer", observer)
    builder.add_node("human_gate_detector", human_gate_detector)
    builder.add_node("human_gate_pause", human_gate_pause)
    builder.add_node("human_gate_resume", human_gate_resume)
    builder.add_node("tool_selector", tool_selector)
    builder.add_node("tool_arg_builder", tool_arg_builder)
    builder.add_node("tool_executor", tool_executor)
    builder.add_node("post_tool_interrupt_handler", post_tool_interrupt_handler)
    builder.add_node("state_updater", state_updater)
    builder.add_node("exploration_summary", exploration_summary_node)
    builder.add_node("human_intervention_summary", human_intervention_summary_node)

    builder.set_entry_point("browser_bootstrap")
    builder.add_edge("browser_bootstrap", "observer")
    builder.add_edge("observer", "human_gate_detector")
    builder.add_conditional_edges(
        "human_gate_detector",
        route_after_human_gate_detection,
        {
            "pause": "human_gate_pause",
            "select": "tool_selector",
        },
    )
    builder.add_edge("human_gate_pause", "human_gate_resume")
    builder.add_conditional_edges(
        "human_gate_resume",
        route_after_human_gate_resume,
        {
            "pause": "human_gate_pause",
            "select": "tool_selector",
            "update": "state_updater",
            "summarize": "exploration_summary",
        },
    )
    builder.add_edge("tool_selector", "tool_arg_builder")
    builder.add_edge("tool_arg_builder", "tool_executor")
    builder.add_edge("tool_executor", "post_tool_interrupt_handler")
    builder.add_conditional_edges(
        "post_tool_interrupt_handler",
        route_after_post_tool_interrupt,
        {
            "pause": "human_gate_pause",
            "update": "state_updater",
        },
    )
    builder.add_conditional_edges(
        "state_updater",
        route_after_state_update,
        {
            "observe": "observer",
            "summarize": "exploration_summary",
        },
    )
    builder.add_conditional_edges(
        "exploration_summary",
        route_after_exploration_summary,
        {
            "human_summary": "human_intervention_summary",
            "end": END,
        },
    )
    builder.add_edge("human_intervention_summary", END)

    return builder.compile()


exploration_graph = build_exploration_graph()


def run_exploration_subagent(main_state: Dict[str, Any]) -> Dict[str, Any]:
    state: ExplorationState = {
        "url": main_state["url"],
        "user_request": main_state["user_request"],
        "max_exploration_steps": main_state.get("max_exploration_steps", 8),
        "max_detail_samples": main_state.get("max_detail_samples", 2),
        "max_resume_attempts": main_state.get("max_resume_attempts", 3),
        "metadata": {},
    }

    try:
        final_state: Dict[str, Any] = dict(state)
        debug_steps = []
        for step in exploration_graph.stream(state):
            node, update = next(iter(step.items()))
            print(f"Executed exploration node: {node}", flush=True)
            debug_steps.append(
                {
                    "node": node,
                    "update": update,
                }
            )
            if isinstance(update, dict):
                final_state.update(update)
        exploration_summary = final_state.get("exploration_summary_result", {})
        human_summary = final_state.get("human_intervention_summary", {})

        return {
            "exploration_summary": exploration_summary.get("exploration_summary", ""),
            "exploration_stop_reason": exploration_summary.get(
                "exploration_stop_reason", final_state.get("stop_reason", "")
            ),
            "human_intervention_summary": human_summary,
            "exploration_debug_steps": debug_steps,
            "error": "Exploration stopped for human intervention" if human_summary else "",
        }
    finally:
        close_browser()
