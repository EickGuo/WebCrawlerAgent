from langgraph.graph import StateGraph, END

from state import CrawlerState
from nodes import (
    html_loader,
    html_summarizer,
    strategy_router,
    static_prepare,
    browser_bootstrap,
    exploration_observer,
    exploration_decider,
    exploration_tool_executor,
    exploration_state_updater,
    exploration_router,
    plan_synthesizer,
    code_generator,
    code_cleaner,
    code_executor,
    result_evaluator,
    debug_agent,
    code_finalizer,
)


def route_by_strategy(state: CrawlerState):
    return state.get("strategy", "static")


def route_after_exploration(state: CrawlerState):
    if state.get("stop_reason"):
        return "stop"
    return "continue"


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
builder.add_node("exploration_decider", exploration_decider)
builder.add_node("exploration_tool_executor", exploration_tool_executor)
builder.add_node("exploration_state_updater", exploration_state_updater)
builder.add_node("exploration_router", exploration_router)
builder.add_node("plan_synthesizer", plan_synthesizer)

builder.add_node("code_generator", code_generator)
builder.add_node("code_cleaner", code_cleaner)
builder.add_node("code_executor", code_executor)
builder.add_node("result_evaluator", result_evaluator)
builder.add_node("debug_agent", debug_agent)
builder.add_node("code_finalizer", code_finalizer)

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

builder.add_edge("static_prepare", "code_generator")

builder.add_edge("browser_bootstrap", "exploration_observer")
builder.add_edge("exploration_observer", "exploration_decider")
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

builder.add_edge("plan_synthesizer", "code_generator")

builder.add_edge("code_generator", "code_cleaner")
builder.add_edge("code_cleaner", "code_executor")
builder.add_edge("code_executor", "result_evaluator")

builder.add_conditional_edges(
    "result_evaluator",
    route_after_evaluation,
    {
        "debug": "debug_agent",
        "finish": "code_finalizer",
    },
)

builder.add_edge("debug_agent", "code_executor")
builder.add_edge("code_finalizer", END)

graph = builder.compile()

if __name__ == "__main__":
    init_state: CrawlerState = {
        "url": "http://221.229.125.247:18080/tard/outside!getYajy.do?_r=0.27991238734356816&type=1&conId=9124",
        "user_request": "提取市九届人大四次会议的所有建议案信息。这只是第一页，后面还有很多页。同时，我不仅需要首页的信息，我还希望获取建议案和答复的具体文本内容。我希望你用动态页面的方式提取信息，最终结果按照json模式存储文件。",
        "max_exploration_steps": 10,
        "max_detail_samples": 3,
        "max_debug_rounds": 2,
        "debug_count": 0,
        "trace": [],
        "metadata": {},
    }

import json

with open("debug_log.json", "w", encoding="utf-8") as f:
    for step in graph.stream(init_state):
        node, update = next(iter(step.items()))
        print(f"✅ 执行完节点: {node}")
        
        f.write(f"\n--- NODE: {node} ---\n")
        
        # Filter out huge strings for better readability in the log file
        safe_update = {}
        for k, v in update.items():
            if k in ["html", "DOM snippet", "code_raw", "code"]:
                safe_update[k] = str(v)[:200] + "... [TRUNCATED]" if v else v
            else:
                safe_update[k] = v
                
        f.write(json.dumps(safe_update, ensure_ascii=False, indent=2, default=str))

# print("=========Result==========")
# print(result["result"])
