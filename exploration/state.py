from typing import Any, Dict, List, Optional, TypedDict


class ExplorationState(TypedDict, total=False):
    # task input
    url: str
    user_request: str

    # current page facts
    current_url: str
    current_page_snapshot: Optional[Dict[str, Any]]
    visited_urls: List[str]

    # exploration memory
    exploration_history: List[Dict[str, Any]]
    stop_reason: str
    tool_budget_used: int
    max_exploration_steps: int
    max_detail_samples: int
    max_resume_attempts: int

    # progressive disclosure
    selected_tool: str
    selected_tool_reasoning: str
    tool_arg_draft: Dict[str, Any]
    tool_arg_reasoning: str
    recent_failure_summary: List[Dict[str, Any]]

    # human intervention
    human_intervention_required: bool
    human_intervention_reason: str
    resume_from: str
    resume_attempts: int
    human_intervention_summary: Dict[str, Any]

    # summarized outputs
    exploration_summary_result: Dict[str, Any]

    # transient scratchpad
    metadata: Dict[str, Any]
