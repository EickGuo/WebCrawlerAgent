# Web Crawler Agent

An LLM-driven web crawling agent for complex websites. It first explores the site, verifies real interaction patterns, executes a validated scraping plan with a host-side runtime, and then exports a directly runnable Python scraper.

## What It Does

- Chooses between static and dynamic scraping (highly possibly updated in later versions)
- Explores dynamic sites before committing to a final plan
- Executes scraping through a host-side `runtime_executor`
- Exports final runnable code as `final_code`
- Supports precise clicking with `click_target`
- Supports on-site search with `search_site`
- Supports login, captcha, and other human-gate interruptions with pause/resume

## Workflow

```text
html_loader
-> html_summarizer
-> strategy_router
   |- static  -> static_prepare -> runtime_executor
   |- dynamic -> browser_bootstrap
                 -> exploration_observer
                 -> human_gate_detector
                 -> exploration_decider
                 -> exploration_tool_executor
                 -> exploration_state_updater
                 -> exploration_router
                 -> plan_synthesizer
                 -> runtime_executor
-> result_evaluator
   |- fail -> runtime_debug_agent -> runtime_executor
   |- pass -> runtime_finalizer -> code_exporter
```

## Key Design

### Exploration First

The agent does not assume pagination, detail-page access, search behavior, or field structure in advance. It verifies them from real page evidence first.

### Runtime Before Code Export

The main execution path does not rely on a black-box generated script. The system:

1. builds a structured `scraping_plan`
2. executes it with `runtime_executor`
3. validates the result
4. exports final code only after the plan has been validated

### Human Gate Handling

If the site requires login, captcha, 2FA, or similar manual intervention, the browser stays open and the workflow pauses until the user completes the step.

## Requirements

- Python 3.10+
- Playwright

Install dependencies:

```bash
pip install -r requirements.txt
playwright install
```

## Configuration

### `.env`

Create a `.env` file in the project root:

```env
API_KEY=your_api_key_here
API_BASE_URL=your_llm_api_base
API_MODEL=your_model_name
USER_AGENT=""  #This would be highly possbily removed or updated in later versions
```

### `user_information.py`

Provide the task-specific inputs, such as:

- `url`
- `user_request`
- `max_exploration_steps`
- `max_detail_samples`
- `max_debug_rounds`
- `max_resume_attempts`

## Usage

Run:

```bash
python main.py
```

The system will:

- explore and validate the target site
- execute the validated scraping plan
- generate final runnable code in `final_code`
- pause for manual action if login or captcha is required

## Main Files

- `main.py`: LangGraph workflow and routing
- `nodes.py`: exploration, planning, runtime execution, runtime debugging, code export
- `tools.py`: shared browser capability layer
- `prompts.py`: prompts for each stage
- `validators.py`: JSON validation
- `state.py`: global state definition
- `project_logic.md`: detailed architecture notes
- `problem.md`: problem and evolution log