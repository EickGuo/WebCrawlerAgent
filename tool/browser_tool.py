"""Browser interaction tools and browser-session utilities."""

from __future__ import annotations

import random
from typing import Any
from urllib.parse import urljoin

from dotenv import load_dotenv
from playwright.sync_api import sync_playwright


load_dotenv()

BROWSER_TOOL_NAMES = [
    "finish",
    "search_site",
    "click_target",
    "goto",
    "go_back",
    "wait_for_selector",
    "scroll_once",
    "sample_detail_pages",
]

HUMAN_GATE_KEYWORDS = {
    "login_required": [
        "登录",
        "登陆",
        "sign in",
        "log in",
        "账号登录",
        "用户登录",
        "请输入用户名",
        "请输入密码",
    ],
    "captcha_required": [
        "验证码",
        "captcha",
        "请输入验证码",
        "图形验证码",
        "滑块",
        "请完成验证",
        "安全验证",
    ],
    "2fa_required": [
        "短信验证码",
        "手机验证码",
        "动态码",
        "二次验证",
        "双重验证",
        "2fa",
        "otp",
    ],
    "verification_required": [
        "人机验证",
        "verify",
        "verification",
        "身份验证",
        "安全校验",
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

INTERRUPT_OVERLAY_SELECTORS = [
    "[role='dialog']",
    "[aria-modal='true']",
    "[class*='modal']",
    "[class*='dialog']",
    "[class*='popup']",
    "[class*='overlay']",
    "[class*='mask']",
]

INTERRUPT_CLOSE_SELECTORS = [
    "button[aria-label='Close']",
    "button[aria-label='close']",
    "[aria-label='Close']",
    "[aria-label='close']",
    ".close",
    ".btn-close",
    ".modal-close",
    ".dialog-close",
    ".popup-close",
    "[class*='close']",
    "[id*='close']",
    "[data-testid*='close']",
]

INTERRUPT_CLOSE_TEXTS = [
    "关闭",
    "关闭弹窗",
    "跳过",
    "稍后",
    "我知道了",
    "以后再说",
    "暂不",
    "not now",
    "skip",
    "close",
    "dismiss",
    "maybe later",
    "no thanks",
    "cancel",
]


def list_browser_tools() -> list[str]:
    return list(BROWSER_TOOL_NAMES)


def _tool_result(action: str, success: bool, **kwargs) -> dict[str, Any]:
    result = {
        "action": action,
        "success": success,
        "error": "",
        "human_gate": {"required": False, "reason": "", "evidence": []},
    }
    result.update(kwargs)
    return result


def _wait_random_for_page(page, min_ms: int, max_ms: int) -> None:
    if page is None:
        return
    page.wait_for_timeout(random.randint(min_ms, max_ms))


class BrowserSession:
    def __init__(self):
        self.play = None
        self.browser = None
        self.page = None

    def _wait_random(self, min_ms: int, max_ms: int) -> None:
        if not self.page:
            return
        self.page.wait_for_timeout(random.randint(min_ms, max_ms))

    def _humanized_pre_action_pause(self) -> None:
        self._wait_random(180, 650)

    def _humanized_post_action_pause(self, base_ms: int) -> None:
        jitter = random.randint(150, 900)
        self.page.wait_for_timeout(base_ms + jitter)

    def start(self, url: str, wait_ms: int = 3000):
        self.play = sync_playwright().start()
        self.browser = self.play.chromium.launch(headless=False)
        self.page = self.browser.new_page()
        self._wait_random(250, 900)
        self.page.goto(url, wait_until="domcontentloaded", timeout=30000)
        self._humanized_post_action_pause(wait_ms)

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

    def snapshot_human_gate(self) -> dict[str, Any]:
        return detect_human_intervention(self.page)

    def current_snapshot(self) -> dict[str, Any]:
        from .pageread_tool import build_page_snapshot

        return build_page_snapshot()

    def wait_for_manual_resolution(self, reason: str = "", timeout_seconds: int = 600) -> dict[str, Any]:
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
    ) -> dict[str, Any]:
        try:
            scope = self.page.locator(scope_selector) if scope_selector else self.page
            input_box = scope.locator(input_selector).first if scope_selector else self.page.locator(input_selector).first
            self._humanized_pre_action_pause()
            input_box.click(timeout=5000)
            self._wait_random(120, 420)
            input_box.fill("")
            self._wait_random(120, 360)
            input_box.fill(query)
            self._wait_random(220, 720)

            if submit_selector:
                submit = scope.locator(submit_selector).first if scope_selector else self.page.locator(submit_selector).first
                self._humanized_pre_action_pause()
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
                        error=target.get("error", "search submit failed"),
                    )
            elif press_enter:
                input_box.press("Enter")

            try:
                self.page.wait_for_load_state("domcontentloaded", timeout=30000)
            except Exception:
                pass
            self._humanized_post_action_pause(1500)
        except Exception as e:
            return _tool_result("search_site", False, error=str(e))

        selector_error = ""
        if result_selector:
            try:
                self.page.wait_for_selector(result_selector, timeout=5000)
            except Exception as e:
                selector_error = str(e)

        return _tool_result(
            "search_site",
            True,
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
    ) -> dict[str, Any]:
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

            self._humanized_pre_action_pause()
            target.click(timeout=5000)
            try:
                self.page.wait_for_load_state("domcontentloaded", timeout=30000)
            except Exception:
                pass
            self._humanized_post_action_pause(1200)

            selector_error = ""
            if known_selector:
                selector_result = self.safe_wait_for_selector(known_selector)
                if not selector_result.get("success"):
                    selector_error = selector_result.get("error", "")

            human_gate = self.snapshot_human_gate()
            return _tool_result(
                "click_target",
                True,
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
                error=str(e),
            )

    def safe_goto(self, url: str, known_selector: str | None = None) -> dict[str, Any]:
        try:
            self._wait_random(220, 850)
            self.page.goto(url, wait_until="domcontentloaded", timeout=30000)
            self._humanized_post_action_pause(3000)
        except Exception as e:
            return _tool_result("safe_goto", False, error=str(e))

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
            human_gate=human_gate,
            snapshot=self.current_snapshot(),
            selector_error=selector_error,
        )

    def safe_go_back(self, known_selector: str | None = None) -> dict[str, Any]:
        try:
            self._wait_random(180, 700)
            self.page.go_back(wait_until="domcontentloaded", timeout=30000)
            self._humanized_post_action_pause(3000)
        except Exception as e:
            return _tool_result("safe_go_back", False, error=str(e))

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
            human_gate=human_gate,
            snapshot=self.current_snapshot(),
            selector_error=selector_error,
        )

    def safe_click(self, selector: str, known_selector: str | None = None) -> dict[str, Any]:
        try:
            self._humanized_pre_action_pause()
            self.page.locator(selector).first.click(timeout=5000)
            try:
                self.page.wait_for_load_state("domcontentloaded", timeout=30000)
            except Exception:
                pass
            self._humanized_post_action_pause(1200)
        except Exception as e:
            return _tool_result("safe_click", False, error=str(e))

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
            human_gate=human_gate,
            snapshot=self.current_snapshot(),
            selector=selector,
            selector_error=selector_error,
        )

    def safe_wait_for_selector(self, selector: str) -> dict[str, Any]:
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

    def safe_scroll_once(self) -> dict[str, Any]:
        try:
            self._humanized_pre_action_pause()
            self.page.evaluate("window.scrollBy(0, document.body.scrollHeight * 0.8)")
            self._humanized_post_action_pause(1500)
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

    def extract_text(self, selector: str, limit: int | None = 1) -> dict[str, Any]:
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
    ) -> dict[str, Any]:
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


def detect_human_intervention(page) -> dict[str, Any]:
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
        body_text = page.locator("body").inner_text(timeout=3000)
    except Exception:
        try:
            body_text = page.content()
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
        "evidence": evidence,
        "url": current_url,
        "title": title,
    }


def _collect_visible_selector_candidates(page, selectors: list[str]) -> list[dict[str, str]]:
    candidates: list[dict[str, str]] = []
    for selector in selectors:
        try:
            locator = page.locator(selector)
            count = min(locator.count(), 3)
        except Exception:
            continue
        for i in range(count):
            try:
                node = locator.nth(i)
                if not node.is_visible():
                    continue
                candidates.append({"kind": "selector", "value": selector, "index": str(i)})
                break
            except Exception:
                continue
    return candidates


def _collect_visible_text_candidates(page, texts: list[str]) -> list[dict[str, str]]:
    candidates: list[dict[str, str]] = []
    for text in texts:
        try:
            locator = page.get_by_text(text, exact=False)
            count = min(locator.count(), 3)
        except Exception:
            continue
        for i in range(count):
            try:
                node = locator.nth(i)
                if not node.is_visible():
                    continue
                candidates.append({"kind": "text", "value": text, "index": str(i)})
                break
            except Exception:
                continue
    return candidates


def detect_interrupting_overlay(page) -> dict[str, Any]:
    if page is None:
        return {"required": False, "reason": "", "evidence": [], "close_candidates": []}

    evidence: list[str] = []
    close_candidates: list[dict[str, str]] = []

    for selector in INTERRUPT_OVERLAY_SELECTORS:
        try:
            locator = page.locator(selector)
            count = min(locator.count(), 3)
        except Exception:
            count = 0
        visible_count = 0
        for i in range(count):
            try:
                if locator.nth(i).is_visible():
                    visible_count += 1
            except Exception:
                continue
        if visible_count:
            evidence.append(f"visible overlay selector: {selector} x{visible_count}")

    close_candidates.extend(_collect_visible_selector_candidates(page, INTERRUPT_CLOSE_SELECTORS))
    close_candidates.extend(_collect_visible_text_candidates(page, INTERRUPT_CLOSE_TEXTS))

    required = bool(evidence and close_candidates)
    return {
        "required": required,
        "reason": "dismissible_overlay" if required else "",
        "evidence": evidence,
        "close_candidates": close_candidates,
    }


def try_close_interrupting_overlay(page) -> dict[str, Any]:
    detection = detect_interrupting_overlay(page)
    if not detection.get("required"):
        return {"handled": False, "success": False, "reason": "", "evidence": [], "snapshot": {}}

    for candidate in detection.get("close_candidates", []):
        try:
            if candidate.get("kind") == "selector":
                locator = page.locator(candidate["value"]).nth(int(candidate.get("index", "0")))
            else:
                locator = page.get_by_text(candidate["value"], exact=False).nth(int(candidate.get("index", "0")))
            _wait_random_for_page(page, 180, 650)
            locator.click(timeout=3000)
            try:
                page.wait_for_load_state("domcontentloaded", timeout=5000)
            except Exception:
                pass
            _wait_random_for_page(page, 900, 1600)
        except Exception:
            continue

        remaining_overlay = detect_interrupting_overlay(page)
        human_gate = detect_human_intervention(page)
        if not remaining_overlay.get("required"):
            try:
                from .pageread_tool import build_page_snapshot

                snapshot = build_page_snapshot()
            except Exception:
                snapshot = {}
            return {
                "handled": True,
                "success": True,
                "reason": "dismissible_overlay_closed",
                "evidence": detection.get("evidence", []),
                "close_candidate": candidate,
                "human_gate": human_gate,
                "snapshot": snapshot,
            }

    return {
        "handled": False,
        "success": False,
        "reason": "dismissible_overlay_unresolved",
        "evidence": detection.get("evidence", []),
        "snapshot": {},
    }


def absolutize_url(url: str, base_url: str) -> str:
    if not url:
        return ""
    return urljoin(base_url, url)


def sample_detail_pages(links: list[dict[str, Any]], limit: int = 2) -> list[dict[str, Any]]:
    from .pageread_tool import build_page_snapshot

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
        normalized_links.append(
            {
                "href": href,
                "source_href": str(item.get("source_href") or href).strip(),
                "text": str(item.get("text") or "").strip(),
                "kind": str(item.get("kind") or "").strip(),
                "detail_id": str(item.get("detail_id") or "").strip(),
                "resolver": str(item.get("resolver") or "").strip(),
            }
        )

    for item in normalized_links[:limit]:
        href = absolutize_url(item.get("href"), origin_url)
        if not href:
            continue

        result = browser.safe_goto(href)
        if not result.get("success"):
            samples.append(
                {
                    "href": href,
                    "source_href": item.get("source_href", href),
                    "text": item.get("text", ""),
                    "kind": item.get("kind", ""),
                    "detail_id": item.get("detail_id", ""),
                    "resolver": item.get("resolver", ""),
                    "success": False,
                    "error": result.get("error", ""),
                }
            )
            continue

        snapshot = build_page_snapshot()
        samples.append(
            {
                "href": browser.url(),
                "source_href": item.get("source_href", href),
                "text": item.get("text", ""),
                "kind": item.get("kind", ""),
                "detail_id": item.get("detail_id", ""),
                "resolver": item.get("resolver", ""),
                "success": True,
                "title": snapshot["title"],
                "page_architecture": snapshot.get("page_architecture", ""),
                "snapshot": snapshot,
            }
        )

    browser.safe_goto(origin_url)
    return samples
