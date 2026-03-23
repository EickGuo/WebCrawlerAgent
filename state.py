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
    available_links: List[Dict[str, Any]]

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

    # dynamic planning / unified planning
    scraping_plan: Dict[str, Any]

    # code pipeline
    code_raw: Optional[str]
    code: Optional[str]
    final_code: Optional[str]  # full-mode production code, generated after evaluation passes

    # execution
    result: Optional[str]
    error: Optional[str]
    execution_meta: Dict[str, Any]

    # execution evaluation
    evaluation_passed: bool
    evaluation_reason: str

    # streaming records
    trace: List[str]
    metadata: Dict[str, Any]
