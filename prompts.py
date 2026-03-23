from langchain_core.prompts import ChatPromptTemplate


HTML_SUMMARIZER_PROMPT = ChatPromptTemplate.from_template(
    """
You are a web page structure analyst.

User request:
{user_request}

Target URL:
{url}

HTML snippet:
{html}

Tasks:
1. Summarize the page structure relevant to the user's request.
2. Infer likely page type: list page / detail page / table page / mixed page.
3. Identify likely selectors or repeated structures.
4. Identify signs of dynamic rendering if any.

Return plain text only.
"""
)


STRATEGY_ROUTER_PROMPT = ChatPromptTemplate.from_template(
    """
You are deciding scraping strategy.

User request:
{user_request}

Target URL:
{url}

HTML summary:
{html_summary}

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

HTML summary:
{html_summary}

Return EXACTLY one JSON object with this schema:
{{
  "mode": "static",
  "entry_url": "{url}",
  "page_pattern": "single_page or list_to_detail",
  "required_actions": [],
  "list_page": {{}},
  "detail_page": {{}},
  "reference_html_snippets": {{"selector_name": "raw html string from the provided snippet, e.g., <div class='W7erk'>..."}},
  "selectors": {{}},
  "validation": {{}},
  "observations": ["important insights from static analysis, like successful selectors, dynamic behaviors, or logical steps"],
  "notes": "short explanation"
}}

Rules:
1. IMPORTANT: Before providing any CSS selectors in the "selectors" field, you MUST extract the exact raw HTML snippet containing the target data from the provided HTML summary and place it in the "reference_html_snippets" field.
2. DO NOT hallucinate class names. Base your selectors strictly on the "reference_html_snippets".
3. Output JSON only. No markdown fences.
"""
)


EXPLORATION_DECIDER_PROMPT = ChatPromptTemplate.from_template(
"""
You are a browser exploration planner.

User request:
{user_request}

Entry URL:
{url}

Current page snapshot:
{current_page_snapshot}

Visited URLs:
{visited_urls}

Detail samples:
{detail_samples}

Exploration history:
{exploration_history}

Available links:
{available_links}

Last listed links:
{last_listed_links}

Choose EXACTLY one next tool call.

Return EXACTLY one JSON object:
{{
  "reasoning": "why this next step is useful",
  "tool": "finish | get_page_snapshot | list_links | list_buttons | click_target | click | goto | go_back | wait_for_selector | scroll_once | extract_preview | count_selector | sample_detail_pages",
  "args": {{}}  # MUST contain the required keys for the chosen tool
}}

Rules:
1. Treat every interaction as a hypothesis that must be verified from page evidence, not prior assumptions.
2. Prefer this evidence order: current DOM facts > listed links/buttons > script snippets > past successful exploration steps.
3. Prefer cheap evidence-gathering actions before risky navigation when behavior is unclear.
4. You MUST NOT choose `finish` until key interactions have been verified:
   - if detail access exists, inspect at least one detail page
   - if pagination exists, verify at least one pagination action
5. Tool list:
   - `finish`: end exploration after key interactions are verified and obtaining enough information for scraping. The following conditions must all be met before calling: at least one detail access method has been verified, or it has been confirmed that no detail page exists; at least one pagination method has been verified, or it has been confirmed that there is only a single page; and sufficient evidence of the field structure has been obtained; args: {{}}
   - `get_page_snapshot`: refresh current structured page snapshot; args: {{}}
   - `list_links`: list links for a selector or scope; args: {{"selector":"optional","limit":20}}
   - `list_buttons`: list visible button texts; args: {{"limit":20}}
   - `click_target`: click a target using as many constraints as possible. However, if the webpage lacks the requested information, only include parameters that are essential, valid, and backed by evidence. Do not artificially populate all fields; args: {{"scope_selector":"optional","selector":"optional","element_selector":"optional","text":"optional","exact":true,"index":0}}
   - `click`: click an element by CSS selector; args: {{"selector":"required"}}
   - `goto`: navigate directly to a URL. If a relative address is provided, make sure to resolve it to an absolute address for access; otherwise, the access may fail; args: {{"url":"required"}}
   - `go_back`: return to previous page; args: {{}}
   - `wait_for_selector`: wait for a selector after interaction/navigation; args: {{"selector":"required"}}
   - `scroll_once`: scroll once to reveal more content; args: {{}}
   - `extract_preview`: preview repeated blocks or rows; args: {{"selector":"optional","limit":"optional"}}
   - `count_selector`: count matching elements; args: {{"selector":"optional"}}
   - `sample_detail_pages`: inspect links chosen by the model. If a relative address is provided, make sure to resolve it to an absolute address for access; otherwise, the access may fail; args: {{"links":[{{"href":"required","source_href":"optional","text":"optional"}}],"limit":2}}
6. For `click_target`, pass arguments in this priority order whenever possible:
   - first `scope_selector` or `selector`
   - then `element_selector`
   - then `text`
   - then `exact`
   - then `index`
   The more constraints you can provide, the better. Avoid sending only {{"text":"2"}} when similar elements may exist elsewhere.
7. For javascript-style hrefs, infer the real target from script snippets and surrounding evidence. Do not assume popup/evaluate behavior from the function name alone.
8. Output JSON only. Missing required args makes the answer invalid.
"""
)


PLAN_SYNTHESIZER_PROMPT = ChatPromptTemplate.from_template(
    """
You are synthesizing a final scraping plan from exploration evidence.

User request:
{user_request}

Entry URL:
{url}

Current page snapshot:
{current_page_snapshot}

Exploration history:
{exploration_history}

Detail samples:
{detail_samples}

Visited URLs:
{visited_urls}

Return EXACTLY one JSON object:
{{
  "mode": "dynamic",
  "entry_url": "{url}",
  "page_pattern": "single_page or list_to_detail or paginated_list or expandable_content",
  "required_actions": [],
  "list_page": {{}},
  "detail_page": {{}},
  "reference_html_snippets": {{"selector_name": "raw html string from the provided snippet, e.g., <div class='W7erk'>..."}},
  "selectors": {{}},
  "validation": {{}},
  "observations": ["important insights from exploration or static analysis, like successful selectors, dynamic behaviors, or logical steps"],
  "notes": "short explanation"
}}

Rules:
1. Include only actions actually needed.
2. Prefer stable selectors.
3. IMPORTANT: Before providing any CSS selectors in the "selectors" field, you MUST extract the exact raw HTML snippet containing the target data from the provided current page snapshot and place it in the "reference_html_snippets" field. DO NOT hallucinate classes.
4. Output JSON only.
5. Encode verified page rules, not one-off fixes. In `observations`, record:
   - how detail navigation really works
   - how pagination was actually verified
   - how important fields are structurally located
   - any fallback path if the primary path is brittle
6. For javascript hrefs, forbid `popup_window` and `javascript_eval`. Use verified URL templates or verified element clicking.
7. For tables/forms/cards, prefer structural relationships and label-based extraction over fixed child indices unless the index was explicitly verified.
"""
)


CODE_GENERATOR_PROMPT = ChatPromptTemplate.from_template(
    """
You are an expert Python web scraping engineer.

User request:
{user_request}

Scraping plan:
{scraping_plan}

Write a complete standalone Python scraper.

Rules:
1. If plan.mode == "static", use requests + BeautifulSoup.
2. If plan.mode == "dynamic", use Playwright sync API.
3. Pay close attention to the `observations` field in the plan. Use these validated logical steps and recorded element selectors instead of guessing.
4. Do not embed prompt HTML directly.
5. Print the final extracted result only.
6. Output raw Python code only.
7. Do not use markdown fences.
8. IMPORTANT - SAMPLE MODE: Define `SAMPLE_LIMIT = 3` near the top of the code.
   - `SAMPLE_LIMIT` MUST only ever be used in slice notation: `some_list[:SAMPLE_LIMIT]`.
   - NEVER use it as a `range()` argument, a loop counter, or any numeric expression.
   - For item lists: `results = items[:SAMPLE_LIMIT]`.
   - For paginated scraping: collect results as a flat list and apply `[:SAMPLE_LIMIT]` to the final list — do NOT limit the page loop itself with SAMPLE_LIMIT.
   - This strict constraint ensures the finalizer can safely remove SAMPLE_LIMIT with a simple regex.
9. When plan.mode == "dynamic", use this general approach:
   - After navigation-sensitive actions, wait for load and for a known selector before extracting.
   - Guard against redirects and timing failures with `try/except playwright.sync_api.TimeoutError`.
   - Launch with `headless=False` by default unless the user explicitly requests headless mode.
10. General interaction rules:
   - Never use `page.evaluate()` to call page-local JS functions for navigation or pagination.
   - Never rely on `page.expect_popup()` unless exploration explicitly verified a real popup event.
   - For javascript-style hrefs, infer the real target from verified evidence, then navigate directly or click the verified element.
   - When clicking an element in a page area that may contain similar text elsewhere, follow the `click_target` principle: prefer scope/container constraints first, then element type, then text, then exact matching, then index as a final disambiguator.
11. General extraction rules:
   - Prefer container-first parsing: locate the row/card/form block, inspect its children, then decide how to extract the value.
   - Do not hardcode fixed child indices unless the plan explicitly verified them.
   - Prefer verified structure, visible labels, repeated patterns, and URL templates over brittle selector chains.
   - If the page structure may vary, write small helper functions and fallback branches instead of duplicating fragile logic.
12. Failure tolerance:
   - Keep partial progress when some records fail.
   - Distinguish navigation failure, missing container, and wrong child/value extraction.
   - Try the next evidence-backed fallback before aborting.
13. Set a reasonable wait time to prevent server overload or being identified as a bot.
"""
)


RESULT_EVALUATOR_PROMPT = ChatPromptTemplate.from_template(
    """
You are evaluating a sample scraper execution for structural correctness.

User request:
{user_request}

Scraping plan:
{scraping_plan}

Execution stdout (sample, up to 3 items):
{result}

Execution stderr:
{error}

Execution meta:
{execution_meta}

Return EXACTLY one JSON object:
{{
  "passed": true or false,
  "reason": "short explanation"
}}

Rules:
1. passed=false if stderr is non-empty.
2. passed=false if stdout is empty.
3. Focus on STRUCTURE, not quantity: if at least 1 valid item is present with the expected fields, passed=true.
4. DO NOT require a minimum item count. The code runs in sample mode intentionally.
5. Output JSON only.
6. If the result suggests the scraper found the right records but missed some fields, treat that as a structural extraction problem rather than total failure.
"""
)


DEBUG_PROMPT = ChatPromptTemplate.from_template(
    """
You are fixing a broken Python scraper.

User request:
{user_request}

Scraping plan:
{scraping_plan}

Broken code:
{code}

Execution stdout:
{result}

Execution stderr:
{error}

Execution meta:
{execution_meta}

Evaluation feedback:
{evaluation_reason}

Fix the code.

Rules:
1. Keep the same scraping plan unless the code clearly failed to implement it.
2. Return full corrected Python code only.
3. Do not use markdown fences.
4. Do not embed prompt HTML directly.
5. Never call page-local JS functions via `page.evaluate()` for navigation/pagination unless exploration explicitly verified that approach.
6. Never assume javascript detail links create a real popup unless exploration explicitly verified a popup event.
7. If a selector hits the right container but returns empty or wrong data, suspect child/value extraction before rewriting the whole scraper.
8. Prefer minimal, evidence-based fixes: repair the specific failed assumption before rewriting unrelated parts.
9. Distinguish these failure classes and fix the right one:
    - wrong target discovery
    - wrong navigation method
    - right container but wrong child/value extraction
    - timing / load-state issue
    - page-structure variation requiring a fallback branch
10. When the code is too brittle, generalize it with container-first parsing, verified text anchors, and fallback branches rather than adding another one-off selector.
"""
)
