- `sample_detail_pages`
  Purpose: inspect candidate detail links directly before finalizing detail-page logic.
  Use when:
  - you already have candidate detail links or URLs to test
  - you need evidence about detail-page structure before writing the final plan
  Avoid when:
  - links are empty or speculative
  - repeated direct-link attempts already failed for the same pattern; then try page clicking instead
  Args: `{"links":[{"href":"required","source_href":"optional","text":"optional"}],"limit":2}`
  Notes:
  - Prefer links that come from actual page evidence, not guessed URLs.
  - Keep `limit` small and representative.
  - If the direct detail URL pattern has already failed multiple times, do not keep retrying the same approach.
  - Preserve `source_href` when available so later reasoning can compare the original page link with the tested URL.
  - After this tool succeeds, exploration should immediately read the sampled detail-page architecture and explain how the final scraper should extract the requested information from it.
