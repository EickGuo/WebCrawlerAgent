from pathlib import Path
from typing import Any, Dict, List

from tool.browser_tool import list_browser_tools

TOOL_ROOT_DIR = Path(__file__).resolve().parent.parent / "tool"
TOOL_DOCS_DIR = TOOL_ROOT_DIR / "browser_tool_explanation"


def load_tool_doc(tool_name: str) -> str:
    path = TOOL_DOCS_DIR / f"{tool_name}.md"
    if not path.exists():
        return f"- `{tool_name}`\n  Purpose: see code implementation.\n  Usage: use only with evidence-backed args."
    return path.read_text(encoding="utf-8").strip()


def load_tool_index() -> str:
    index_path = TOOL_DOCS_DIR / "index.md"
    if index_path.exists():
        return index_path.read_text(encoding="utf-8").strip()

    tool_names = list_browser_tools()
    lines = []
    for name in tool_names:
        doc = load_tool_doc(name).splitlines()
        first_line = doc[0] if doc else f"- `{name}`"
        lines.append(first_line)
    return "\n".join(lines)

def summarize_recent_failures(exploration_history: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    failures: List[Dict[str, Any]] = []
    for item in exploration_history[-6:]:
        result = item.get("result", {})
        if result.get("success"):
            continue
        failures.append(
            {
                "tool": item.get("decision", {}).get("tool", ""),
                "args": item.get("decision", {}).get("args", {}),
                "error": str(result.get("error") or ""),
            }
        )
    return failures[-4:]
