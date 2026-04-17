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

## v0.3

- Rebuilt `exploration` as a LangGraph subgraph
- Simplified exploration state and removed redundant summaries
- Moved tool cautions into `tool/*.md` and Switched progressive disclosure to full snapshot + per-tool docs
- Added post-tool interrupt detection for captcha and blocking overlays, and auto-close flow for dismissible irrelevant popups before human intervention
- Added lightweight randomized waits around sensitive browser actions in `tool/browser_tool.py`, and updated `code_exporter` to instruct generated code to keep similar human-like timing
- Reorganized `tool/` into grouped registries (`browser_tool.py`, `pageread_tool.py`) and moved tool explanations into `tool/browser_tool_explanation/`
- Added local Playwright session reuse via root-level `session.json`, with automatic reuse by site and fallback to human intervention when login state is unavailable or expired
