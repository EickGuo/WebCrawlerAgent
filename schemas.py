from typing import Any, Dict, List, Literal, Optional
from pydantic import BaseModel, Field

class StrategyDecision(BaseModel):
    strategy: Literal["static", "dynamic"]
    reason: str

class ExplorationDecision(BaseModel):
    reasoning: str
    tool: Literal[
        "finish",
        "search_site",
        "click_target",
        "goto",
        "go_back",
        "wait_for_selector",
        "scroll_once",
        "sample_detail_pages"
    ]
    args: Dict[str, Any] = Field(default_factory=dict)

class ScrapingPlan(BaseModel):
    mode: Literal["static", "dynamic"]
    entry_url: str
    page_pattern: str
    required_actions: List[Dict[str, Any]] = Field(default_factory=list)
    list_page: Dict[str, Any] = Field(default_factory=dict)
    detail_page: Dict[str, Any] = Field(default_factory=dict)
    reference_html_snippets: Dict[str, Any] = Field(default_factory=dict)
    selectors: Dict[str, Any] = Field(default_factory=dict)
    validation: Dict[str, Any] = Field(default_factory=dict)
    observations: List[Any] = Field(default_factory=list)
    notes: str = ""

class EvaluationDecision(BaseModel):
    passed: bool
    reason: str
