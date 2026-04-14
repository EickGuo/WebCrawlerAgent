from typing import Any, Dict, List, Optional, TypedDict


class CrawlerState(TypedDict, total=False):
    url: str
    user_request: str

    # task-level configuration
    max_exploration_steps: int
    max_detail_samples: int
    max_resume_attempts: int

    # deterministic setup
    html: Optional[str]

    # router
    strategy: str
    strategy_reason: str

    # outputs shared across top-level stages
    scraping_plan: Any
    final_code: Optional[str]
    final_code_path: Optional[str]
    error: Optional[str]

    # exploration summaries returned to the main graph
    exploration_summary: str
    exploration_stop_reason: str
    human_intervention_summary: Dict[str, Any]
    exploration_debug_steps: List[Dict[str, Any]]

    # tracing
    trace: List[str]
