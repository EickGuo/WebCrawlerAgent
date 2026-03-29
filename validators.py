import json
import re
from typing import Any, Dict, List

def extract_first_json_object(text: str) -> Dict[str, Any]:
    text = text.strip()

    try:
        obj = json.loads(text)
        if isinstance(obj, dict):
            return obj
    except Exception:
        pass

    match = re.search(r"\{[\s\S]*\}", text)
    if not match:
        raise ValueError(f"No JSON object found in model output:\n{text}")
    
    candidate = match.group(0).replace("```json","").replace("```","").strip()

    try:
        obj = json.loads(candidate)
        if isinstance(obj, dict):
            return obj
    except Exception as e:
        raise ValueError(f"Invalid JSON object:\n{candidate}\nError:{e}")
    
    raise ValueError("Could not parse JSON object")

def ensure_str(value: Any, default: str = "") -> str:
    return value if isinstance(value, str) else default

def ensure_bool(value: Any, default: bool = False) -> bool:
    return value if isinstance(value, bool) else default

def ensure_list(value: Any, default: List[Any] | None = None) -> List[Any]:
    if isinstance(value, list):
        return value
    return default if default is not None else []

def ensure_dict(value: Any, default: Dict[str, Any] | None = None) -> Dict[str, Any]:
    if isinstance(value, dict):
        return value
    return default if default is not None else {}

def ensure_int(value: Any, default: int | None = None) -> int | None:
    return value if isinstance(value, int) else default

def ensure_optional_bool(value: Any) -> bool | None:
    return value if isinstance(value, bool) else None

def normalize_link_items(value: Any) -> List[Dict[str, Any]]:
    items = ensure_list(value, [])
    normalized = []

    for item in items:
        if not isinstance(item, dict):
            continue
        href = ensure_str(item.get("href")).strip()
        if not href:
            continue

        normalized_item = {"href": href}
        text = ensure_str(item.get("text")).strip()
        if text:
            normalized_item["text"] = text

        for optional_key in ("kind", "detail_id", "page_no", "source_href", "resolver"):
            optional_value = ensure_str(item.get(optional_key)).strip()
            if optional_value:
                normalized_item[optional_key] = optional_value

        normalized.append(normalized_item)

    return normalized

def validate_strategy_decision(obj: Dict[str, Any]) -> Dict[str, Any]:
    strategy = ensure_str(obj.get("strategy"), "dynamic").lower()
    if strategy not in {"static", "dynamic"}:
        strategy = "dynamic"

    return {
        "strategy": strategy,
        "reason": ensure_str(obj.get("reason"), "")
    }

def validate_exploration_decision(obj: Dict[str, Any]) -> Dict[str, Any]:
    allowed_tools = {
        "finish",
        "get_page_snapshot",
        "list_links",
        "list_buttons",
        "search_site",
        "click_target",
        "click",
        "goto",
        "go_back",
        "wait_for_selector",
        "scroll_once",
        "extract_preview",
        "count_selector",
        "sample_detail_pages",
    }

    tool = ensure_str(obj.get("tool"), "finish")
    if tool not in allowed_tools:
        tool = "finish"

    args = ensure_dict(obj.get("args"), {})
    validated_args: Dict[str, Any] = {}

    if tool == "sample_detail_pages":
        links = normalize_link_items(args.get("links"))
        if not links:
            raise ValueError("sample_detail_pages requires non-empty args.links with href values")
        validated_args["links"] = links
        limit = ensure_int(args.get("limit"))
        if limit is not None and limit > 0:
            validated_args["limit"] = limit
    elif tool == "search_site":
        query = ensure_str(args.get("query")).strip()
        input_selector = ensure_str(args.get("input_selector")).strip()
        if not query or not input_selector:
            raise ValueError("search_site requires args.query and args.input_selector")
        validated_args["query"] = query
        validated_args["input_selector"] = input_selector
        for key in ("submit_selector", "submit_text", "scope_selector", "result_selector"):
            value = ensure_str(args.get(key)).strip()
            if value:
                validated_args[key] = value
        press_enter = ensure_optional_bool(args.get("press_enter"))
        if press_enter is not None:
            validated_args["press_enter"] = press_enter
    elif tool == "click_target":
        for key in ("scope_selector", "selector", "element_selector", "text"):
            value = ensure_str(args.get(key)).strip()
            if value:
                validated_args[key] = value
        exact = ensure_optional_bool(args.get("exact"))
        if exact is not None:
            validated_args["exact"] = exact
        index = ensure_int(args.get("index"))
        if index is not None and index >= 0:
            validated_args["index"] = index
        if not any(key in validated_args for key in ("scope_selector", "selector", "element_selector", "text")):
            raise ValueError("click_target requires at least one targeting argument")
    elif tool == "click":
        selector = ensure_str(args.get("selector")).strip()
        if not selector:
            raise ValueError("click requires args.selector")
        validated_args["selector"] = selector
    elif tool == "goto":
        url = ensure_str(args.get("url")).strip()
        if not url:
            raise ValueError("goto requires args.url")
        validated_args["url"] = url
    elif tool == "wait_for_selector":
        selector = ensure_str(args.get("selector")).strip()
        if not selector:
            raise ValueError("wait_for_selector requires args.selector")
        validated_args["selector"] = selector
    elif tool in {"list_links", "list_buttons", "extract_preview", "count_selector"}:
        limit = ensure_int(args.get("limit"))
        selector = ensure_str(args.get("selector")).strip()
        if selector:
            validated_args["selector"] = selector
        if limit is not None and limit > 0:
            validated_args["limit"] = limit

    return {
        "reasoning": ensure_str(obj.get("reasoning"), ""),
        "tool": tool,
        "args": validated_args,
    }

def validate_scraping_plan(obj: Dict[str, Any], fallback_url: str) -> Dict[str, Any]:
    mode = ensure_str(obj.get("mode"), "dynamic").lower()
    if mode not in {"static", "dynamic"}:
        mode = "dynamic"

    return {
        "mode": mode,
        "entry_url": ensure_str(obj.get("entry_url"), fallback_url),
        "page_pattern": ensure_str(obj.get("page_pattern"), "single_page"),
        "required_actions": ensure_list(obj.get("required_actions"), []),
        "list_page": ensure_dict(obj.get("list_page"), {}),
        "detail_page": ensure_dict(obj.get("detail_page"), {}),
        "reference_html_snippets": ensure_dict(obj.get("reference_html_snippets"), {}),
        "selectors": ensure_dict(obj.get("selectors"), {}),
        "validation": ensure_dict(obj.get("validation"), {}),
        "observations": ensure_list(obj.get("observations"), []),
        "notes": ensure_str(obj.get("notes"), ""),
    }

def validate_evaluation_decision(obj: Dict[str, Any]) -> Dict[str, Any]:
    return {
        "passed": ensure_bool(obj.get("passed"), False),
        "reason": ensure_str(obj.get("reason"), ""),
    }
