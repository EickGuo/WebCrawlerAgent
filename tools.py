import re
import subprocess
import tempfile
from collections import Counter
from typing import Any, Dict, List, Tuple
import os
from dotenv import load_dotenv

import requests
from bs4 import BeautifulSoup
from playwright.sync_api import sync_playwright


# ----------------------------
# initial page load
# ----------------------------

def load_page(url: str, timeout: int = 20) -> str:
    headers = {
        "User-Agent": os.getenv("USER_AGENT")
    }
    resp = requests.get(url, headers=headers, timeout=timeout)
    resp.raise_for_status()
    return resp.text


def clean_dom_for_llm(soup: BeautifulSoup):
    for tag in soup(["script", "style", "noscript", "svg", "path", "symbol", "use"]):
        tag.decompose()
        
    allowed_attrs = {"class", "id", "href"}
    for tag in soup.find_all(True):
        attrs = dict(tag.attrs)
        for attr in attrs:
            if attr not in allowed_attrs:
                del tag[attr]

def summarize_html_for_prompt(html: str, max_len: int = 5000) -> str:
    soup = BeautifulSoup(html, "html.parser")
    clean_dom_for_llm(soup)

    text = soup.prettify()
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text[:max_len]

# ----------------------------
# DOM summary
# ----------------------------

def summarize_rendered_dom(html: str, max_len: int = 5000) -> Dict[str, Any]:
    soup = BeautifulSoup(html, "html.parser")
    clean_dom_for_llm(soup)

    links = []
    for a in soup.find_all("a", href=True):
        links.append({
            "text": a.get_text(" ", strip=True)[:80],
            "href": a.get("href"),
        })

    buttons = []
    for b in soup.find_all("button"):
        buttons.append({
            "text": b.get_text(" ", strip=True)[:80],
            "class": " ".join(b.get("class", []))[:120],
        })

    candidate_blocks = []
    for selector_name in ["div", "li", "article", "tr"]:
        nodes = soup.find_all(selector_name)
        if len(nodes) >= 5:
            candidate_blocks.append({
                "tag": selector_name,
                "count": len(nodes),
            })

    script_snippets = []
    raw_soup = BeautifulSoup(html, "html.parser")
    for script in raw_soup.find_all("script"):
        script_text = script.get_text(" ", strip=True)
        if script_text:
            script_snippets.append(script_text[:500])

    return {
        "local_snippet": soup.prettify()[:max_len],
        "links": links,
        "buttons": buttons,
        "candidate_blocks": candidate_blocks[:10],
        "script_snippets": script_snippets[:10],
    }


# ----------------------------
# Browser session
# ----------------------------

class BrowserSession:
    def __init__(self):
        self.play = None
        self.browser = None
        self.page = None

    def start(self, url: str, wait_ms: int = 3000):
        self.play = sync_playwright().start()
        self.browser = self.play.chromium.launch(headless=False)
        self.page = self.browser.new_page()
        self.page.goto(url, wait_until="domcontentloaded", timeout=30000)
        self.page.wait_for_timeout(wait_ms)

    def close(self):
        try:
            if self.browser:
                self.browser.close()
        finally:
            if self.play:
                self.play.stop()

    def content(self) -> str:
        for _ in range(5):
            try:
                return self.page.content()
            except Exception as e:
                if "navigating" in str(e).lower() or "changing the content" in str(e).lower():
                    try:
                        self.page.wait_for_load_state("domcontentloaded", timeout=30000)
                    except Exception:
                        self.page.wait_for_timeout(1000)
                else:
                    raise
        return self.page.content()

    def url(self) -> str:
        return self.page.url

    def title(self) -> str:
        return self.page.title()

    def list_buttons(self, limit: int = 20) -> List[str]:
        try:
            return [x.strip() for x in self.page.locator("button").all_text_contents()[:limit] if x.strip()]
        except Exception:
            return []

    def list_links(self, selector: str = "a", limit: int | None = 20) -> Dict[str, Any]:
        try:
            loc = self.page.locator(selector)
            count = loc.count()
            n = count if limit is None else min(count, limit)
            items = []
            for i in range(n):
                link = loc.nth(i)
                href = link.get_attribute("href")
                text = ""
                try:
                    text = link.inner_text().strip()[:200]
                except Exception:
                    pass
                items.append({"text": text, "href": href})
            return {"success": True, "items": items}
        except Exception as e:
            return {"success": False, "error": str(e)}

    def click_target(
        self,
        *,
        scope_selector: str | None = None,
        selector: str | None = None,
        element_selector: str | None = None,
        text: str | None = None,
        exact: bool = False,
        index: int = 0,
    ) -> Dict[str, Any]:
        try:
            if selector:
                locator = self.page.locator(selector)
            else:
                scope = self.page.locator(scope_selector) if scope_selector else self.page
                if element_selector:
                    locator = scope.locator(element_selector)
                elif scope_selector:
                    locator = scope
                else:
                    locator = self.page.locator("a, button, [role='button'], input[type='button'], input[type='submit']")

            matched_indexes = []
            candidate_count = locator.count()
            normalized_text = (text or "").strip()

            for i in range(candidate_count):
                candidate = locator.nth(i)
                candidate_text = ""
                try:
                    candidate_text = candidate.inner_text().strip()
                except Exception:
                    try:
                        candidate_text = (candidate.get_attribute("value") or "").strip()
                    except Exception:
                        candidate_text = ""

                if not normalized_text:
                    matched_indexes.append(i)
                    continue

                if exact:
                    if candidate_text == normalized_text:
                        matched_indexes.append(i)
                elif normalized_text in candidate_text:
                    matched_indexes.append(i)

            if not matched_indexes:
                return {
                    "success": False,
                    "error": "No matching element found",
                    "selector": selector or element_selector or scope_selector or "",
                    "text": normalized_text,
                }

            target_pos = index if 0 <= index < len(matched_indexes) else 0
            target = locator.nth(matched_indexes[target_pos])
            url_before = self.page.url
            clicked_text = ""
            clicked_href = None
            try:
                clicked_text = target.inner_text().strip()
            except Exception:
                pass
            try:
                clicked_href = target.get_attribute("href")
            except Exception:
                clicked_href = None

            target.click(timeout=5000)
            try:
                self.page.wait_for_load_state("domcontentloaded", timeout=30000)
            except Exception:
                pass
            self.page.wait_for_timeout(1200)
            return {
                "success": True,
                "clicked_text": clicked_text,
                "clicked_href": clicked_href,
                "url_before": url_before,
                "url_after": self.page.url,
                "matched_count": len(matched_indexes),
                "used_index": target_pos,
            }
        except Exception as e:
            return {"success": False, "error": str(e)}

    def click(self, selector: str) -> Dict[str, Any]:
        try:
            self.page.locator(selector).first.click(timeout=5000)
            try:
                self.page.wait_for_load_state("domcontentloaded", timeout=30000)
            except Exception:
                pass
            self.page.wait_for_timeout(1200)
            return {"success": True}
        except Exception as e:
            return {"success": False, "error": str(e)}

    def goto(self, url: str) -> Dict[str, Any]:
        try:
            self.page.goto(url, wait_until="domcontentloaded", timeout=30000)
            self.page.wait_for_timeout(3000)
            return {"success": True, "url": self.page.url}
        except Exception as e:
            return {"success": False, "error": str(e)}

    def go_back(self) -> Dict[str, Any]:
        try:
            self.page.go_back(wait_until="domcontentloaded", timeout=30000)
            self.page.wait_for_timeout(3000)
            return {"success": True, "url": self.page.url}
        except Exception as e:
            return {"success": False, "error": str(e)}

    def wait_for_selector(self, selector: str) -> Dict[str, Any]:
        try:
            self.page.wait_for_selector(selector, timeout=5000)
            return {"success": True}
        except Exception as e:
            return {"success": False, "error": str(e)}

    def scroll_once(self) -> Dict[str, Any]:
        try:
            self.page.evaluate("window.scrollBy(0, document.body.scrollHeight * 0.8)")
            self.page.wait_for_timeout(1500)
            return {"success": True}
        except Exception as e:
            return {"success": False, "error": str(e)}

    def count_selector(self, selector: str) -> Dict[str, Any]:
        try:
            return {"success": True, "count": self.page.locator(selector).count()}
        except Exception as e:
            return {"success": False, "error": str(e)}

    def extract_preview(self, selector: str, limit: int = None) -> Dict[str, Any]:
        try:
            loc = self.page.locator(selector)
            n = loc.count() if limit is None else min(loc.count(), limit)
            items = []
            for i in range(n):
                txt = loc.nth(i).inner_text()
                items.append(txt.strip()[:300] if txt else "")
            return {"success": True, "items": items}
        except Exception as e:
            return {"success": False, "error": str(e)}

GLOBAL_BROWSER: BrowserSession | None = None


def get_browser() -> BrowserSession:
    global GLOBAL_BROWSER
    if GLOBAL_BROWSER is None:
        GLOBAL_BROWSER = BrowserSession()
    return GLOBAL_BROWSER


def close_browser():
    global GLOBAL_BROWSER
    if GLOBAL_BROWSER is not None:
        GLOBAL_BROWSER.close()
        GLOBAL_BROWSER = None


# ----------------------------
# Understanding pages
# ----------------------------

def build_page_snapshot() -> Dict[str, Any]:
    browser = get_browser()
    html = browser.content()
    dom = summarize_rendered_dom(html)

    return {
        "url": browser.url(),
        "title": browser.title(),
        "local_snippet": dom["local_snippet"],
        "links": dom["links"],
        "buttons": dom["buttons"],
        "candidate_blocks": dom["candidate_blocks"],
        "script_snippets": dom["script_snippets"],
    }


def sample_detail_pages(links: List[Dict[str, Any]], limit: int = 2) -> List[Dict[str, Any]]:
    browser = get_browser()
    origin_url = browser.url()
    samples = []
    normalized_links = []

    for item in links:
        if not isinstance(item, dict):
            continue
        href = str(item.get("href") or "").strip()
        if not href:
            continue
        normalized_links.append({
            "href": href,
            "source_href": str(item.get("source_href") or href).strip(),
            "text": str(item.get("text") or "").strip(),
            "kind": str(item.get("kind") or "").strip(),
            "detail_id": str(item.get("detail_id") or "").strip(),
            "resolver": str(item.get("resolver") or "").strip(),
        })

    for item in normalized_links[:limit]:
        href = item.get("href")
        if not href:
            continue

        result = browser.goto(href)
        if not result.get("success"):
            samples.append({
                "href": href,
                "source_href": item.get("source_href", href),
                "text": item.get("text", ""),
                "kind": item.get("kind", ""),
                "detail_id": item.get("detail_id", ""),
                "resolver": item.get("resolver", ""),
                "success": False,
                "error": result.get("error", ""),
            })
            continue

        snapshot = build_page_snapshot()
        samples.append({
            "href": browser.url(),
            "source_href": item.get("source_href", href),
            "text": item.get("text", ""),
            "kind": item.get("kind", ""),
            "detail_id": item.get("detail_id", ""),
            "resolver": item.get("resolver", ""),
            "success": True,
            "title": snapshot["title"],
            "local_snippet": snapshot["local_snippet"],
        })

    browser.goto(origin_url)
    return samples


# ----------------------------
# Unified code pipeline
# ----------------------------

def clean_code_block(text: str) -> str:
    text = text.strip()
    pattern = r"^```(?:python)?\s*([\s\S]*?)\s*```$"
    match = re.match(pattern, text, flags=re.IGNORECASE)
    if match:
        return match.group(1).strip()
    return text.replace("```python", "").replace("```", "").strip()


def ensure_utf8_preamble(code: str) -> str:
    preamble = (
        "import sys\n"
        "if hasattr(sys.stdout, 'reconfigure'):\n"
        "    sys.stdout.reconfigure(encoding='utf-8')\n"
        "if hasattr(sys.stderr, 'reconfigure'):\n"
        "    sys.stderr.reconfigure(encoding='utf-8')\n\n"
    )
    if "sys.stdout.reconfigure" in code:
        return code
    return preamble + code


def run_code(code: str, timeout: int = 60) -> Tuple[str, str]:
    with tempfile.NamedTemporaryFile(mode="w", suffix=".py", delete=False, encoding="utf-8") as f:
        f.write(code)
        filename = f.name

    try:
        result = subprocess.run(
            ["python", "-X", "utf8", filename],
            capture_output=True,
            text=True,
            timeout=timeout,
            encoding="utf-8",
            errors="replace",
        )
        stdout = result.stdout.strip()
        stderr = result.stderr.strip()
        if result.returncode == 0:
            return stdout, ""
        return stdout, stderr or f"Process exited with code {result.returncode}"
    except Exception as e:
        return "", str(e)


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
