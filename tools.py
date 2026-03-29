import re
from collections import Counter
from typing import Any, Dict, List
import os
from urllib.parse import urljoin
from dotenv import load_dotenv

import requests
from bs4 import BeautifulSoup
from playwright.sync_api import sync_playwright


HUMAN_GATE_KEYWORDS = {
    "login_required": [
        "登录", "登陆", "sign in", "log in", "账号登录", "用户登录", "请输入用户名", "请输入密码",
    ],
    "captcha_required": [
        "验证码", "captcha", "请输入验证码", "图形验证码", "滑块", "请完成验证", "安全验证",
    ],
    "2fa_required": [
        "短信验证码", "手机验证码", "动态码", "二次验证", "双重验证", "2fa", "otp",
    ],
    "verification_required": [
        "人机验证", "verify", "verification", "身份验证", "安全校验",
    ],
}

HUMAN_GATE_SELECTORS = {
    "login_required": [
        "input[type='password']",
        "input[name*='password']",
        "form input[type='password']",
    ],
    "captcha_required": [
        "input[name*='captcha']",
        "input[id*='captcha']",
        "img[src*='captcha']",
        "iframe[src*='captcha']",
    ],
    "verification_required": [
        "iframe[src*='verify']",
        "iframe[src*='captcha']",
        "[class*='captcha']",
        "[id*='captcha']",
        "[class*='verify']",
    ],
}


def _tool_result(action: str, success: bool, **kwargs) -> Dict[str, Any]:
    result = {
        "action": action,
        "success": success,
        "error": "",
        "human_gate": {"required": False, "reason": "", "evidence": []},
    }
    result.update(kwargs)
    return result


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

    inputs = []
    for node in soup.find_all(["input", "textarea"]):
        inputs.append({
            "type": (node.get("type") or node.name or "")[:40],
            "name": (node.get("name") or "")[:80],
            "id": (node.get("id") or "")[:80],
            "placeholder": (node.get("placeholder") or "")[:120],
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
        "inputs": inputs[:20],
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

    def snapshot_human_gate(self) -> Dict[str, Any]:
        return detect_human_intervention(self.page)

    def current_snapshot(self) -> Dict[str, Any]:
        return build_page_snapshot()

    def wait_for_manual_resolution(self, reason: str = "", timeout_seconds: int = 600) -> Dict[str, Any]:
        prompt = (
            "\n[Human Gate] Detected a page requiring manual action."
            f"\nReason: {reason or 'unknown'}"
            "\nPlease use the opened browser window to complete login / captcha / verification."
            "\nAfter finishing, press Enter here to continue. Type 'abort' to stop.\n> "
        )
        user_input = input(prompt).strip().lower()
        if user_input == "abort":
            return {"success": False, "aborted": True}
        return {"success": True}

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

    def search_site(
        self,
        *,
        query: str,
        input_selector: str,
        submit_selector: str | None = None,
        submit_text: str | None = None,
        scope_selector: str | None = None,
        press_enter: bool = True,
        result_selector: str | None = None,
    ) -> Dict[str, Any]:
        url_before = self.page.url if self.page else ""
        try:
            scope = self.page.locator(scope_selector) if scope_selector else self.page
            input_box = scope.locator(input_selector).first if scope_selector else self.page.locator(input_selector).first
            input_box.click(timeout=5000)
            input_box.fill("")
            input_box.fill(query)

            if submit_selector:
                submit = scope.locator(submit_selector).first if scope_selector else self.page.locator(submit_selector).first
                submit.click(timeout=5000)
            elif submit_text:
                target = self.click_target(
                    scope_selector=scope_selector,
                    element_selector="button, input[type='submit'], input[type='button'], a",
                    text=submit_text,
                    exact=False,
                    index=0,
                )
                if not target.get("success"):
                    return _tool_result(
                        "search_site",
                        False,
                        url_before=url_before,
                        url_after=url_before,
                        error=target.get("error", "search submit failed"),
                    )
            elif press_enter:
                input_box.press("Enter")

            try:
                self.page.wait_for_load_state("domcontentloaded", timeout=30000)
            except Exception:
                pass
            self.page.wait_for_timeout(1500)
        except Exception as e:
            return _tool_result("search_site", False, url_before=url_before, url_after=url_before, error=str(e))

        selector_error = ""
        if result_selector:
            try:
                self.page.wait_for_selector(result_selector, timeout=5000)
            except Exception as e:
                selector_error = str(e)

        return _tool_result(
            "search_site",
            True,
            url_before=url_before,
            url_after=self.page.url,
            query=query,
            input_selector=input_selector,
            submit_selector=submit_selector or "",
            submit_text=submit_text or "",
            human_gate=self.snapshot_human_gate(),
            snapshot=self.current_snapshot(),
            selector_error=selector_error,
        )

    def click_target(
        self,
        *,
        scope_selector: str | None = None,
        selector: str | None = None,
        element_selector: str | None = None,
        text: str | None = None,
        exact: bool = False,
        index: int = 0,
        known_selector: str | None = None,
    ) -> Dict[str, Any]:
        url_before = self.page.url if self.page else ""
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
                return _tool_result(
                    "click_target",
                    False,
                    url_before=url_before,
                    url_after=url_before,
                    error="No matching element found",
                    selector=selector or element_selector or scope_selector or "",
                    text=normalized_text,
                )

            target_pos = index if 0 <= index < len(matched_indexes) else 0
            target = locator.nth(matched_indexes[target_pos])
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

            selector_error = ""
            if known_selector:
                selector_result = self.safe_wait_for_selector(known_selector)
                if not selector_result.get("success"):
                    selector_error = selector_result.get("error", "")

            human_gate = self.snapshot_human_gate()
            return _tool_result(
                "click_target",
                True,
                url_before=url_before,
                url_after=self.page.url,
                human_gate=human_gate,
                snapshot=self.current_snapshot(),
                clicked_text=clicked_text,
                clicked_href=clicked_href,
                matched_count=len(matched_indexes),
                used_index=target_pos,
                selector=selector or "",
                scope_selector=scope_selector or "",
                element_selector=element_selector or "",
                text=normalized_text,
                selector_error=selector_error,
            )
        except Exception as e:
            return _tool_result(
                "click_target",
                False,
                url_before=url_before,
                url_after=url_before,
                error=str(e),
            )

    def safe_goto(self, url: str, known_selector: str | None = None) -> Dict[str, Any]:
        url_before = self.page.url if self.page else ""
        try:
            self.page.goto(url, wait_until="domcontentloaded", timeout=30000)
            self.page.wait_for_timeout(3000)
        except Exception as e:
            return _tool_result("safe_goto", False, url_before=url_before, url_after=url_before, error=str(e))

        if known_selector:
            try:
                self.page.wait_for_selector(known_selector, timeout=5000)
                selector_error = ""
            except Exception as e:
                selector_error = str(e)
        else:
            selector_error = ""

        human_gate = self.snapshot_human_gate()
        return _tool_result(
            "safe_goto",
            True,
            url_before=url_before,
            url_after=self.page.url,
            human_gate=human_gate,
            snapshot=self.current_snapshot(),
            selector_error=selector_error,
        )

    def safe_go_back(self, known_selector: str | None = None) -> Dict[str, Any]:
        url_before = self.page.url if self.page else ""
        try:
            self.page.go_back(wait_until="domcontentloaded", timeout=30000)
            self.page.wait_for_timeout(3000)
        except Exception as e:
            return _tool_result("safe_go_back", False, url_before=url_before, url_after=url_before, error=str(e))

        if known_selector:
            try:
                self.page.wait_for_selector(known_selector, timeout=5000)
                selector_error = ""
            except Exception as e:
                selector_error = str(e)
        else:
            selector_error = ""

        human_gate = self.snapshot_human_gate()
        return _tool_result(
            "safe_go_back",
            True,
            url_before=url_before,
            url_after=self.page.url,
            human_gate=human_gate,
            snapshot=self.current_snapshot(),
            selector_error=selector_error,
        )

    def safe_click(self, selector: str, known_selector: str | None = None) -> Dict[str, Any]:
        url_before = self.page.url if self.page else ""
        try:
            self.page.locator(selector).first.click(timeout=5000)
            try:
                self.page.wait_for_load_state("domcontentloaded", timeout=30000)
            except Exception:
                pass
            self.page.wait_for_timeout(1200)
        except Exception as e:
            return _tool_result("safe_click", False, url_before=url_before, url_after=url_before, error=str(e))

        if known_selector:
            try:
                self.page.wait_for_selector(known_selector, timeout=5000)
                selector_error = ""
            except Exception as e:
                selector_error = str(e)
        else:
            selector_error = ""

        human_gate = self.snapshot_human_gate()
        return _tool_result(
            "safe_click",
            True,
            url_before=url_before,
            url_after=self.page.url,
            human_gate=human_gate,
            snapshot=self.current_snapshot(),
            selector=selector,
            selector_error=selector_error,
        )

    def safe_wait_for_selector(self, selector: str) -> Dict[str, Any]:
        try:
            self.page.wait_for_selector(selector, timeout=5000)
            result = {"success": True}
        except Exception as e:
            result = {"success": False, "error": str(e)}
        human_gate = self.snapshot_human_gate()
        return _tool_result(
            "safe_wait_for_selector",
            bool(result.get("success")),
            selector=selector,
            error=result.get("error", ""),
            human_gate=human_gate,
        )

    def safe_scroll_once(self) -> Dict[str, Any]:
        try:
            self.page.evaluate("window.scrollBy(0, document.body.scrollHeight * 0.8)")
            self.page.wait_for_timeout(1500)
            result = {"success": True}
        except Exception as e:
            result = {"success": False, "error": str(e)}
        human_gate = self.snapshot_human_gate()
        return _tool_result(
            "safe_scroll_once",
            bool(result.get("success")),
            error=result.get("error", ""),
            human_gate=human_gate,
            snapshot=self.current_snapshot() if result.get("success") else {},
        )

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

    def extract_text(self, selector: str, limit: int | None = 1) -> Dict[str, Any]:
        try:
            loc = self.page.locator(selector)
            count = loc.count()
            n = count if limit is None else min(count, limit)
            items = []
            for i in range(n):
                text = loc.nth(i).inner_text().strip()
                if text:
                    items.append(text)
            return {"success": True, "items": items}
        except Exception as e:
            return {"success": False, "error": str(e)}

    def extract_structured_rows(
        self,
        row_selector: str,
        *,
        cell_selector: str = "th, td",
        limit: int | None = None,
    ) -> Dict[str, Any]:
        try:
            rows = self.page.locator(row_selector)
            count = rows.count()
            n = count if limit is None else min(count, limit)
            items = []
            for i in range(n):
                row = rows.nth(i)
                row_text = ""
                try:
                    row_text = row.inner_text().strip()
                except Exception:
                    pass
                cells = []
                cell_loc = row.locator(cell_selector)
                cell_count = cell_loc.count()
                for j in range(cell_count):
                    try:
                        cell_text = cell_loc.nth(j).inner_text().strip()
                    except Exception:
                        cell_text = ""
                    cells.append(cell_text)
                items.append({"row_text": row_text, "cells": cells})
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


def detect_human_intervention(page) -> Dict[str, Any]:
    if page is None:
        return {"required": False, "reason": "", "evidence": []}

    evidence = []
    reason = ""

    try:
        current_url = page.url or ""
    except Exception:
        current_url = ""

    try:
        title = (page.title() or "").strip()
    except Exception:
        title = ""

    body_text = ""
    try:
        body_text = page.locator("body").inner_text(timeout=3000)[:4000]
    except Exception:
        try:
            body_text = page.content()[:4000]
        except Exception:
            body_text = ""

    low_text = f"{title}\n{body_text}".lower()
    low_url = current_url.lower()

    if any(token in low_url for token in ("/login", "login?", "signin", "passport", "auth")):
        reason = "login_required"
        evidence.append(f"url indicates login page: {current_url}")

    for candidate_reason, keywords in HUMAN_GATE_KEYWORDS.items():
        for keyword in keywords:
            if keyword.lower() in low_text:
                if not reason:
                    reason = candidate_reason
                evidence.append(f"text matched keyword: {keyword}")
                break

    for candidate_reason, selectors in HUMAN_GATE_SELECTORS.items():
        for selector in selectors:
            try:
                count = page.locator(selector).count()
            except Exception:
                count = 0
            if count > 0:
                if not reason:
                    reason = candidate_reason
                evidence.append(f"selector matched: {selector} x{count}")
                break

    return {
        "required": bool(reason),
        "reason": reason,
        "evidence": evidence[:8],
        "url": current_url,
        "title": title,
    }


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
        "inputs": dom["inputs"],
        "candidate_blocks": dom["candidate_blocks"],
        "script_snippets": dom["script_snippets"],
    }


def absolutize_url(url: str, base_url: str) -> str:
    if not url:
        return ""
    return urljoin(base_url, url)


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
        href = absolutize_url(item.get("href"), origin_url)
        if not href:
            continue

        result = browser.safe_goto(href)
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

    browser.safe_goto(origin_url)
    return samples


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
