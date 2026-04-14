- `goto`
  Purpose: navigate directly to a URL.
  Use when:
  - the URL is directly usable as an actual page URL
  - the navigation target is already supported by page evidence or prior successful attempts
  Avoid when:
  - the value is a JavaScript pseudo-link such as `javascript:...`
  - repeated direct navigation failures already happened for the same link pattern
  Args: `{"url":"required"}`
  Notes:
  - Use only real URLs, not function calls or inferred placeholders.
  - If direct detail-link access has already failed repeatedly, stop retrying it and switch to click-based access.
  - Prefer `go_back` instead of a fresh `goto` when you only need to return from a detail page to the list page.
  - The tool already adds a small randomized pause around navigation to reduce mechanical timing patterns.
