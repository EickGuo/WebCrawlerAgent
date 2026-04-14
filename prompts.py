from langchain_core.prompts import ChatPromptTemplate


STRATEGY_ROUTER_PROMPT = ChatPromptTemplate.from_template(
    """
You are deciding scraping strategy.

User request:
{user_request}

Target URL:
{url}

Cleaned HTML architecture:
{html}

Return EXACTLY one JSON object with this schema:
{{
  "strategy": "static" or "dynamic",
  "reason": "short explanation"
}}

Rules:
1. Use "static" if requests + BeautifulSoup is likely enough.
2. Use "dynamic" if browser rendering or interaction is likely needed.
3. Output JSON only. No markdown fences. No extra text.
"""
)


STATIC_PLAN_PROMPT = ChatPromptTemplate.from_template(
    """
You are creating a scraping plan for a static page.

User request:
{user_request}

Target URL:
{url}

Cleaned HTML architecture:
{html}

Return EXACTLY one JSON object with this schema:
{{
  "mode": "static",
  "entry_url": "{url}",
  "page_pattern": "single_page or list_to_detail",
  "required_actions": [],
  "list_page": {{}},
  "detail_page": {{}},
  "reference_html_snippets": {{"selector_name": "raw html string from the provided snippet"}},
  "selectors": {{}},
  "validation": {{}},
  "observations": ["important insights from static analysis"],
  "notes": "short explanation"
}}

Rules:
1. Before providing CSS selectors, extract the exact raw HTML snippet containing the target data into `reference_html_snippets`.
2. Do not hallucinate class names.
3. Output JSON only.
"""
)


PLAN_SYNTHESIZER_PROMPT = ChatPromptTemplate.from_template(
    """
You are synthesizing a final executable scraping plan from exploration evidence.

User request:
{user_request}

Entry URL:
{url}

Exploration summary:
{exploration_summary}

Human intervention summary:
{human_intervention_summary}

Write a concrete step-by-step scraping plan in plain text.

The plan must clearly describe:
1. Which page should be opened first.
2. Which page should be reached next, in order.
3. What action should be executed on each page.
4. What result should be observed after each action.
5. How the code should detect that the step succeeded.
6. How list pages, detail pages, pagination, search, and extraction should be implemented if they are needed.
7. How human intervention should be handled if login / captcha / verification appears.

Rules:
1. Use only exploration-backed evidence. Do not invent runtime verification.
2. Base the entire plan on `exploration_summary` and `human_intervention_summary`.
3. Make the plan specific enough that a coding model can implement runnable code directly from it.
4. Explicitly state what code should do to confirm success at each step.
5. Prefer stable selectors and structural extraction rules over brittle child indices.
6. For javascript-style hrefs, forbid popup assumptions and javascript-eval navigation unless exploration explicitly verified them.
7. Output plain text only. Do not return JSON.
"""
)


CODE_EXPORTER_PROMPT = ChatPromptTemplate.from_template(
    """
You are an expert Python web scraping engineer.

User request:
{user_request}

Entry URL:
{entry_url}

Scraping plan:
{scraping_plan}

Write a complete standalone Python scraper that follows the plan.

Rules:
1. Output raw Python code only. No markdown fences.
2. If the plan clearly describes a static extraction flow, use requests + BeautifulSoup.
3. If the plan describes browser interaction, use Playwright sync API.
4. Launch dynamic browsers with `headless=False` by default.
5. Keep the code directly executable as one file.
6. Follow the plan exactly instead of inventing a different flow.
7. Use `{entry_url}` as the initial page.
8. Implement every page transition, success check, and extraction step described in the plan.
9. Never call page-local JS functions via `page.evaluate()` for navigation or pagination.
10. Never rely on popup behavior unless the plan explicitly requires it.
11. Prefer container-first, label-aware extraction over brittle fixed child indices.
12. For browser interactions that are commonly inspected for automation patterns, add small randomized waits around actions such as navigation, clicking, search submission, scrolling, and closing interrupting overlays.
13. Keep those waits lightweight and human-like; do not add arbitrary long sleeps unless page behavior requires them.
14. If the plan indicates login / captcha / verification risk, include manual handling code that keeps the browser open, pauses with `input()`, and re-checks before resuming. Do not use random waiting as a substitute for user confirmation.
15. If the user wants to extract detailed information, be sure to extract that information based on clear evidence. Do not fabricate or generate it yourself.
16. Do not add redundant try-except logics to keep the code short yet concise and robust. Only use them when necessary.
"""
)
