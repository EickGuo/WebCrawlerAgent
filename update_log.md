# Update Log

## v0.1

- Implemented the basic LangGraph crawler workflow
- Added static/dynamic strategy routing
- Added browser exploration, plan synthesis, and basic scraping execution
- Added prompt-driven selector and interaction reasoning

## v0.2

- Replaced black-box `code_executor` with host-side `runtime_executor`
- Added runtime debugging based on `scraping_plan`
- Added final code export after runtime validation
- Added unified tool layer for exploration and runtime
- Upgraded clicking to `click_target`
- Added on-site search via `search_site`
- Added human-gate pause/resume for login, captcha, and verification
- Simplified state memory