- `scroll_once`
  Purpose: reveal more content on pages that lazy-load or extend the list after scrolling.
  Use when:
  - the page likely loads more results on scroll
  - visible content appears truncated and no explicit pagination is obvious
  Avoid when:
  - the page clearly uses standard pagination controls already visible
  Args: `{}`
  Notes:
  - Use this as a test step, then verify change with a fresh snapshot or count.
  - Do not keep scrolling repeatedly without confirming that new content is actually appearing.
  - The tool already adds a small randomized pause before and after the scroll action.
