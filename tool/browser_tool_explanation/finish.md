- `finish`
  Purpose: stop exploration and return control to the main workflow.
  Use when:
  - key page interactions have been verified well enough to synthesize a plan
  - there is enough evidence for pagination, detail access, search, and field structure relevant to the request
  Avoid when:
  - important interaction paths are still unverified
  - the model is only guessing how navigation or extraction works
  Args: `{}`
  Notes:
  - Do not use `finish` just because one possible path exists.
  - Prefer one more evidence-gathering step when the remaining uncertainty could materially change the final code.
