- `click_target`
  Purpose: click a page element using multiple evidence-backed constraints.
  Use when:
  - the target may be ambiguous if matched by text only
  - you can describe the target by scope, selector, element type, text, or index
  - the page contains repeated labels such as page numbers, “详情”, “查看”, or similar repeated actions
  Avoid when:
  - you do not have enough evidence to narrow the target yet; inspect the current page architecture first
  Args: `{"scope_selector":"optional","selector":"optional","element_selector":"optional","text":"optional","exact":false,"index":0}`
  Notes:
  - Pass stronger constraints whenever possible: `selector` or `scope_selector` first, then `element_selector`, then `text`, then `exact`, then `index`.
  - Do not rely on `text` alone when similar elements probably exist.
  - Use `exact=true` for short texts or page numbers when partial matching may hit the wrong target.
  - Use `index` only after other constraints are still not unique.
  - The tool already injects a small randomized pause before and after the click; do not add artificial waiting just to mimic human pacing.
