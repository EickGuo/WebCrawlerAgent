from typing import TypedDict, Optional, List, Dict, Any

class CrawlerState(TypedDict, total = False):
    url: str
    user_request: str

    # deterministic setup
    html: Optional[str]
    html_summary: Optional[str]

    # router: static / dynamic
    strategy: str
    strategy_reason: str

    # browser session / current page
    current_url: str
    current_page_snapshot: Optional[Dict[str, Any]]
    last_successful_url: str
    last_successful_snapshot: Optional[Dict[str, Any]]

    # exploration memory
    exploration_history: List[Dict[str, Any]]
    visited_urls: List[str]
    detail_samples: List[Dict[str, Any]]
    stop_reason: str

    tool_budget_used: int
    page_visit_count: int
    max_exploration_steps: int
    max_detail_samples: int
    max_debug_rounds: int
    debug_count: int
    max_resume_attempts: int

    # dynamic planning / unified planning
    scraping_plan: Dict[str, Any]

    # runtime execution
    result_data: List[Dict[str, Any]]
    result: Optional[str]
    error: Optional[str]
    execution_meta: Dict[str, Any]
    final_result: Optional[str]
    final_code: Optional[str]

    # execution evaluation
    evaluation_passed: bool
    evaluation_reason: str

    # human gate
    human_intervention_required: bool
    human_intervention_reason: str
    human_intervention_evidence: List[str]
    human_intervention_status: str
    interrupted_phase: str
    resume_from: str
    resume_attempts: int

    # streaming records
    trace: List[str]
    metadata: Dict[str, Any]
