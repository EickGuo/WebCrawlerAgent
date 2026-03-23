from typing import Any, Dict, List, Literal, Optional
from pydantic import BaseModel, Field

class StrategyDecision(BaseModel):
    strategy: Literal["static", "dynamic"]
    reason: str

class ExplorationDecision(BaseModel):
    reasoning: str
    tool: Literal[
        "finish",
        "get_page_snapshot",
        "list_links",
        "list_buttons",
        "click_target",
        "click",
        "goto",
        "go_back",
        "wait_for_selector",
        "scroll_once",
        "extract_preview",
        "count_selector",
        "sample_detail_pages"
    ]
    args: Dict[str, Any] = Field(default_factory=dict)

class ScrapingPlan(BaseModel):
    model: Literal["static", "dynamic"]
    entry_url: str
    page_pattern: str
    required_actions: List[Dict[str, Any]] = Field(default_factory=dict)
    list_page: Dict[str, Any] = Field(default_factory=dict)
    detail_page: Dict[str, Any] = Field(default_factory=dict)
    selectors: Dict[str, Any] = Field(default_factory=dict)
    validation: Dict[str, Any] = Field(default_factory=dict)
    notes: str = ""

class EvaluationDecision(BaseModel):
    passed: bool
    reason: str
