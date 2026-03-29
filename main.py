from langgraph.graph import StateGraph, END

from state import CrawlerState
from nodes import (
    html_loader,
    html_summarizer,
    strategy_router,
    static_prepare,
    browser_bootstrap,
    exploration_observer,
    human_gate_detector,
    human_gate_pause,
    human_gate_resume,
    human_gate_abort,
    exploration_decider,
    exploration_tool_executor,
    exploration_state_updater,
    exploration_router,
    plan_synthesizer,
    runtime_executor,
    result_evaluator,
    runtime_debug_agent,
    runtime_finalizer,
    code_exporter,
)

from user_information import user_information
import json


def route_by_strategy(state: CrawlerState):
    return state.get("strategy", "static")


def route_after_exploration(state: CrawlerState):
    if state.get("stop_reason"):
        return "stop"
    return "continue"


def route_after_human_gate_detection(state: CrawlerState):
    if state.get("human_intervention_required"):
        return "pause"
    return "continue"


def route_after_human_gate_resume(state: CrawlerState):
    if state.get("human_intervention_status") == "resolved":
        return "continue"
    if state.get("human_intervention_status") == "aborted":
        return "abort"
    if state.get("resume_attempts", 0) >= state.get("max_resume_attempts", 3):
        return "abort"
    return "pause"


def route_after_evaluation(state: CrawlerState):
    has_error = bool(state.get("error"))
    passed = bool(state.get("evaluation_passed"))
    debug_count = state.get("debug_count", 0)
    max_debug_rounds = state.get("max_debug_rounds", 2)

    if (has_error or not passed) and debug_count < max_debug_rounds:
        return "debug"
    return "finish"


builder = StateGraph(CrawlerState)

builder.add_node("html_loader", html_loader)
builder.add_node("html_summarizer", html_summarizer)
builder.add_node("strategy_router", strategy_router)
builder.add_node("static_prepare", static_prepare)

builder.add_node("browser_bootstrap", browser_bootstrap)
builder.add_node("exploration_observer", exploration_observer)
builder.add_node("human_gate_detector", human_gate_detector)
builder.add_node("human_gate_pause", human_gate_pause)
builder.add_node("human_gate_resume", human_gate_resume)
builder.add_node("human_gate_abort", human_gate_abort)
builder.add_node("exploration_decider", exploration_decider)
builder.add_node("exploration_tool_executor", exploration_tool_executor)
builder.add_node("exploration_state_updater", exploration_state_updater)
builder.add_node("exploration_router", exploration_router)
builder.add_node("plan_synthesizer", plan_synthesizer)

builder.add_node("runtime_executor", runtime_executor)
builder.add_node("result_evaluator", result_evaluator)
builder.add_node("runtime_debug_agent", runtime_debug_agent)
builder.add_node("runtime_finalizer", runtime_finalizer)
builder.add_node("code_exporter", code_exporter)

builder.set_entry_point("html_loader")

builder.add_edge("html_loader", "html_summarizer")
builder.add_edge("html_summarizer", "strategy_router")

builder.add_conditional_edges(
    "strategy_router",
    route_by_strategy,
    {
        "static": "static_prepare",
        "dynamic": "browser_bootstrap",
    },
)

builder.add_edge("static_prepare", "runtime_executor")

builder.add_edge("browser_bootstrap", "exploration_observer")
builder.add_edge("exploration_observer", "human_gate_detector")
builder.add_conditional_edges(
    "human_gate_detector",
    route_after_human_gate_detection,
    {
        "pause": "human_gate_pause",
        "continue": "exploration_decider",
    },
)
builder.add_edge("human_gate_pause", "human_gate_resume")
builder.add_conditional_edges(
    "human_gate_resume",
    route_after_human_gate_resume,
    {
        "continue": "exploration_observer",
        "pause": "human_gate_pause",
        "abort": "human_gate_abort",
    },
)
builder.add_edge("exploration_decider", "exploration_tool_executor")
builder.add_edge("exploration_tool_executor", "exploration_state_updater")
builder.add_edge("exploration_state_updater", "exploration_router")

builder.add_conditional_edges(
    "exploration_router",
    route_after_exploration,
    {
        "continue": "exploration_observer",
        "stop": "plan_synthesizer",
    },
)

builder.add_edge("plan_synthesizer", "runtime_executor")
builder.add_edge("runtime_executor", "result_evaluator")

builder.add_conditional_edges(
    "result_evaluator",
    route_after_evaluation,
    {
        "debug": "runtime_debug_agent",
        "finish": "runtime_finalizer",
    },
)

builder.add_edge("runtime_debug_agent", "runtime_executor")
builder.add_edge("runtime_finalizer", "code_exporter")
builder.add_edge("human_gate_abort", END)
builder.add_edge("code_exporter", END)

graph = builder.compile()

if __name__ == "__main__":
    user_information = user_information()
    init_state: CrawlerState = {
        "url": user_information["url"],
        "user_request": user_information["user_request"],
        "max_exploration_steps": user_information["max_exploration_steps"],
        "max_detail_samples": user_information["max_detail_samples"],
        "max_debug_rounds": user_information["max_debug_rounds"],
        "max_resume_attempts": user_information.get("max_resume_attempts", 3),
        "debug_count": 0,
        "trace": [],
        "metadata": {},
    }
    with open("debug_log.json", "w", encoding="utf-8") as f:
        for step in graph.stream(init_state):
            node, update = next(iter(step.items()))
            print(f"✅ 执行完节点: {node}")

            f.write(f"\n--- NODE: {node} ---\n")

            # Filter out huge strings for better readability in the log file
            safe_update = {}
            for k, v in update.items():
                if k in ["html", "DOM snippet", "result", "final_result", "final_code"]:
                    safe_update[k] = str(v)[:200] + "... [TRUNCATED]" if v else v
                else:
                    safe_update[k] = v

            f.write(json.dumps(safe_update, ensure_ascii=False, indent=2, default=str))
