- `search_site`
  Purpose: perform an on-page search before extraction.
  Use when:
  - the user request depends on a keyword, title, company name, person name, or topic search
  - the page exposes a visible search input or search area
  Avoid when:
  - the page has no credible search controls
  - the request is about extracting what is already visible without searching
  Args: `{"query":"required","input_selector":"required","submit_selector":"optional","submit_text":"optional","scope_selector":"optional","press_enter":true,"result_selector":"optional"}`
  Notes:
  - `query` should come from the user request or a clearly derived search term.
  - Use `scope_selector` when there may be multiple forms or inputs on the page.
  - Prefer `submit_selector` when the submit control is identifiable; otherwise `press_enter` is acceptable.
  - Use `result_selector` when you already know what should appear after search and want stronger evidence of success.
  - The tool already adds small randomized pauses while focusing the input, typing/filling, and submitting.
