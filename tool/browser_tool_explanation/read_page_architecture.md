- `read_page_architecture`
  Purpose: read the relevant page architecture and explain how the requested information should be extracted from it.
  Use when:
  - a detail page or other target page has just been reached or sampled
  - you need to turn raw page structure into an extraction explanation for later code generation
  Avoid when:
  - there is no reliable page architecture available yet
  - you still need to verify navigation before discussing extraction
  Args: `{}`
  Notes:
  - This tool is often used immediately after `sample_detail_pages`.
  - Put the extraction explanation in the LLM reasoning for this step, not in speculative selectors that were never observed.
  - Explain which part of the page likely contains the target data, how code should read it, and how success should be confirmed.
