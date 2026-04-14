"""Page-reading tools."""

from __future__ import annotations

import os
import re

import requests
from bs4 import BeautifulSoup


def load_page(url: str, timeout: int = 20) -> str:
    headers = {
        "User-Agent": os.getenv("USER_AGENT"),
    }
    resp = requests.get(url, headers=headers, timeout=timeout)
    resp.raise_for_status()
    return resp.text


def clean_dom_for_llm(soup: BeautifulSoup):
    for tag in soup(["script", "style", "noscript", "svg", "path", "symbol", "use"]):
        tag.decompose()

    allowed_attrs = {"class", "id", "href", "name", "type", "placeholder"}
    for tag in soup.find_all(True):
        attrs = dict(tag.attrs)
        for attr in attrs:
            if attr not in allowed_attrs:
                del tag[attr]


def summarize_html_for_prompt(html: str) -> str:
    soup = BeautifulSoup(html, "html.parser")
    clean_dom_for_llm(soup)
    text = soup.prettify()
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text


def build_page_snapshot() -> dict[str, object]:
    from .browser_tool import get_browser

    browser = get_browser()
    html = browser.content()
    cleaned_architecture = summarize_html_for_prompt(html)

    return {
        "url": browser.url(),
        "title": browser.title(),
        "page_architecture": cleaned_architecture,
    }


def read_page_architecture(snapshot: dict[str, object] | None) -> dict[str, object]:
    snapshot = snapshot or {}
    return {
        "success": bool(snapshot),
        "page": {
            "url": snapshot.get("url", ""),
            "title": snapshot.get("title", ""),
        },
        "page_architecture": snapshot.get("page_architecture", ""),
        **({} if snapshot else {"error": "No page snapshot available for architecture reading"}),
    }


def heuristic_evaluate(result: str, error: str) -> tuple[bool, str]:
    if error and error.strip():
        return False, "stderr is non-empty"
    if not result or not result.strip():
        return False, "stdout is empty"

    low = result.lower()
    for signal in [
        "access denied",
        "forbidden",
        "captcha",
        "robot check",
        "please enable javascript",
        "sign in",
        "login",
    ]:
        if signal in low:
            return False, f"suspicious output: {signal}"

    return True, "heuristic check passed"
