from typing import Any, Dict, List, Literal

from pydantic import BaseModel, Field


class ToolSelectionDecision(BaseModel):
    reasoning: str
    tool: Literal[
        "finish",
        "search_site",
        "click_target",
        "goto",
        "go_back",
        "wait_for_selector",
        "scroll_once",
        "sample_detail_pages",
    ]


class ToolArgDecision(BaseModel):
    reasoning: str
    tool: str
    args: Dict[str, Any] = Field(default_factory=dict)


class ExplorationSummary(BaseModel):
    exploration_summary: str
    exploration_stop_reason: str = ""


class HumanInterventionSummary(BaseModel):
    required: bool = False
    reason: str = ""
    status: str = ""
    evidence: List[str] = Field(default_factory=list)
    next_steps: List[str] = Field(default_factory=list)
    summary: str = ""
