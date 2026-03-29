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

Current page links:
{current_page_links}

Last listed links:
{last_listed_links}

Choose EXACTLY one next tool call.

Return EXACTLY one JSON object:
{{
  "reasoning": "why this next step is useful",
  "tool": "finish | get_page_snapshot | list_links | list_buttons | search_site | click_target | click | goto | go_back | wait_for_selector | scroll_once | extract_preview | count_selector | sample_detail_pages",
  "args": {{}}
}}

Rules:
1. Treat every interaction as a hypothesis that must be verified from page evidence, not prior assumptions.
2. Prefer this evidence order: current DOM facts > listed links/buttons > script snippets > past successful exploration steps.
3. Prefer cheap evidence-gathering actions before risky navigation when behavior is unclear.
4. You MUST NOT choose `finish` until key interactions have been verified:
   - if detail access exists, inspect at least one detail page
   - if pagination exists, verify at least one pagination action
   - if the user request clearly requires searching for a keyword/name/case number and the page provides search capability, verify at least one search action
5. Tool list:
   - `finish`: end exploration only after enough navigation and extraction evidence has been verified; args: {{}}
   - `get_page_snapshot`: refresh current structured page snapshot; args: {{}}
   - `list_links`: list links for a selector or scope; args: {{"selector":"optional","limit":20}}
   - `list_buttons`: list visible button texts; args: {{"limit":20}}
   - `search_site`: perform an on-page search before extraction; args: {{"query":"required","input_selector":"required","submit_selector":"optional","submit_text":"optional","scope_selector":"optional","press_enter":true,"result_selector":"optional"}}
   - `click_target`: click a target using as many evidence-backed constraints as possible; args: {{"scope_selector":"optional","selector":"optional","element_selector":"optional","text":"optional","exact":true,"index":0}}
   - `click`: click an element by CSS selector; args: {{"selector":"required"}}
   - `goto`: navigate directly to a URL; resolve relative URLs before calling; args: {{"url":"required"}}
   - `go_back`: return to previous page; args: {{}}
   - `wait_for_selector`: wait for a selector after interaction/navigation; args: {{"selector":"required"}}
   - `scroll_once`: scroll once to reveal more content; args: {{}}
   - `extract_preview`: preview repeated blocks or rows; args: {{"selector":"optional","limit":"optional"}}
   - `count_selector`: count matching elements; args: {{"selector":"optional"}}
   - `sample_detail_pages`: inspect links chosen by the model; resolve relative URLs before calling; args: {{"links":[{{"href":"required","source_href":"optional","text":"optional"}}],"limit":2}}
6. For `click_target`, pass arguments in this priority order whenever possible:
   - first `scope_selector` or `selector`
   - then `element_selector`
   - then `text`
   - then `exact`
   - then `index`
   The more constraints you can provide, the better. Avoid sending only {{"text":"2"}} when similar elements may exist elsewhere.
7. For javascript-style hrefs, infer the real target from script snippets and surrounding evidence. Do not assume popup/evaluate behavior from the function name alone.
8. If the user request asks for results for a specific keyword, person, company, case number, or title, and the page contains search inputs or search controls, prefer verifying the search flow with `search_site`.
9. Output JSON only. Missing required args makes the answer invalid.
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
   - whether a keyword search step is required and how it was verified
   - how detail navigation really works
   - how pagination was actually verified
   - how important fields are structurally located
   - any fallback path if the primary path is brittle
6. For javascript hrefs, forbid `popup_window` and `javascript_eval`. Use verified URL templates or verified element clicking.
7. For tables/forms/cards, prefer structural relationships and label-based extraction over fixed child indices unless the index was explicitly verified.
8. If search is required, encode it in `required_actions`, for example:
   - {{"type":"search","query":"keyword","input_selector":"...","submit_selector":"optional","submit_text":"optional","scope_selector":"optional","press_enter":true,"result_selector":"optional"}}
"""
)


RESULT_EVALUATOR_PROMPT = ChatPromptTemplate.from_template(
    """
You are evaluating a runtime scraper execution for structural correctness.

User request:
{user_request}

Scraping plan:
{scraping_plan}

Runtime result sample:
{result}

Runtime error:
{error}

Execution meta:
{execution_meta}

Return EXACTLY one JSON object:
{{
  "passed": true or false,
  "reason": "short explanation"
}}

Rules:
1. passed=false if error is non-empty.
2. passed=false if result is empty.
3. Focus on STRUCTURE, not quantity: if at least 1 valid item is present with the expected fields, passed=true.
4. Output JSON only.
5. If the result suggests the scraper found the right records but missed some fields, treat that as a structural extraction problem rather than total failure.
"""
)


RUNTIME_DEBUG_PROMPT = ChatPromptTemplate.from_template(
    """
You are fixing a broken runtime scraping plan.

User request:
{user_request}

Scraping plan:
{scraping_plan}

Runtime result sample:
{result}

Runtime error:
{error}

Execution meta:
{execution_meta}

Evaluation feedback:
{evaluation_reason}

Return a corrected scraping plan JSON object with the same schema as the current plan.

Rules:
1. Keep the same high-level intent unless the current plan clearly failed.
2. Return JSON only. No markdown fences. No explanations.
3. Prefer minimal, evidence-based edits to the plan.
4. Never switch to javascript_eval or popup assumptions unless exploration explicitly verified them.
5. If extraction hit the right container but returned empty or wrong data, fix field structure rules before changing unrelated selectors.
6. Prefer container-first, label-aware, fallback-friendly rules over brittle nth-child assumptions.
7. When click targets may be ambiguous, strengthen click_target constraints with scope, selector, element type, text, exact, and index in that order.
8. If the failure is navigation-related, repair required_actions, list_page, detail_page, selectors, validation, or observations so the runtime can interpret the plan correctly.
"""
)


CODE_EXPORTER_PROMPT = ChatPromptTemplate.from_template(
    """
You are an expert Python web scraping engineer.

User request:
{user_request}

Validated scraping plan:
{scraping_plan}

Validated runtime result sample:
{result}

Write a complete standalone Python scraper that follows the validated plan.

Rules:
1. Output raw Python code only. No markdown fences.
2. If plan.mode == "static", use requests + BeautifulSoup.
3. If plan.mode == "dynamic", use Playwright sync API.
4. Launch dynamic browsers with `headless=False` by default.
5. Keep the code directly executable as one file.
6. Follow the validated `observations`, `list_page`, `detail_page`, `selectors`, and `validation` fields instead of guessing.
7. If `required_actions` contains a search step, implement that search before list or detail extraction.
8. Never call page-local JS functions via `page.evaluate()` for navigation or pagination.
9. Never rely on popup behavior unless the validated plan explicitly requires it.
10. When click targets may be ambiguous, follow the `click_target` principle in code: scope or selector first, then element type, then text, then exact matching, then index.
11. Prefer container-first, label-aware extraction over brittle fixed child indices.
12. Include runtime human gate handling:
    - detect login / captcha / verification pages by URL, text, and common selectors
    - keep the browser open
    - pause with `input()` for manual completion
    - re-check before resuming
13. Print the final extracted result as JSON.
14. Keep partial progress if some records fail.
15. The code should reflect the validated runtime plan, not a fresh guess.
"""
)
