- `wait_for_selector`
  Purpose: wait for a target element to appear after an interaction.
  Use when:
  - you expect a specific container, result area, or detail section to load
  - you need confirmation that a prior interaction succeeded
  Avoid when:
  - you do not have a credible selector yet
  - you actually need a different navigation or interaction step rather than a success check
  Args: `{"selector":"required"}`
  Notes:
  - Use selectors that correspond to meaningful success conditions, not incidental wrappers.
  - This is best as a verification step after click, search, or navigation.
