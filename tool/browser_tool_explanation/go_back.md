- `go_back`
  Purpose: return to the previous page.
  Use when:
  - you just visited a detail page and need to return to the list page
  - a navigation path was exploratory and you want to go back instead of reopening from scratch
  Avoid when:
  - browser history is unreliable or the previous page may not be the intended target
  - you need to jump to a known different URL; use `goto`
  Args: `{}`
  Notes:
  - Prefer this for simple return navigation after detail inspection.
  - After returning, the current page architecture is refreshed automatically by the exploration flow.
