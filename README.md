# Web Crawler Agent

An LLM-driven web crawling agent for complex websites. It first decides whether a page is suitable for static extraction or browser exploration. For dynamic sites, it runs an `exploration` subagent, synthesizes a scraping plan from exploration evidence, and then exports directly runnable Python code.

## What It Does

- Chooses between static and dynamic scraping
- Explores dynamic sites before committing to a final plan
- Uses progressive disclosure during exploration:
  first select a tool, then reveal only that tool's detailed usage
- Exports final runnable code to `exports/final_code.py`
- Uses `click_target` for constrained clicking
- Supports on-site search with `search_site`
- Handles login, captcha, and similar human-gate interruptions inside exploration

## Install Dependencies

Install the required Python packages before running the project:

```bash
pip install -r requirements.txt

playwright install    
#If you use Playwright for dynamic exploration, make sure the browser dependencies are installed in your environment as well.
```

## Configuration

#### `.env`

Create a `.env` file in the project root:

```
API_KEY=your_api_key_here
API_BASE_URL=your_llm_api_base
API_MODEL=your_model_name
USER_AGENT=""  #This would be highly possbily removed or updated in later versions
```

#### `user_information.py`

Before running the project, fill in the task information in ```user_information.py```

Typical fields include:

- target `url`
- `user_request`
- exploration limits such as maximum exploration steps
- detail sampling limits
- human-intervention resume limits

This file is the main place where you describe what site to explore and what information you want the exported code to extract.

#### `session.json`

The project root also contains a local `session.json`. When exploration starts, the browser first checks whether a saved session exists for the target site.

- If a valid session exists, it is reused directly.
- If it does not exist or has expired, the workflow falls back to the existing human-intervention process.
- After you manually complete login or verification, the session is saved locally for later reuse.

This session information is only used inside the local browser tool layer. It is not exposed to the LLM and is not included in exported code.

## Usage

```bash
python main.py
```

**As a special reminder**, the program may occasionally need your intervention, particularly when logging in or submitting a verification code. Please watch for messages in the terminal to continue.

The system will:

- explore the site if dynamic interaction is needed
- synthesize a scraping plan from exploration evidence
- generate final runnable code in ```exports/final_code.py```
- return a human-intervention summary if exploration is blocked

## Debug Information

During execution, you can inspect the process in the
```debug``` folder.

Key files include:

- ```debug/debug_log.json```: main workflow log
- ```debug/exploration_record.json```: detailed exploration history, including tool calls, arguments, and results

These files are useful when checking:

- which node the system ran
- which exploration tools were used
- what parameters were passed
- what results were returned
- where human intervention was triggered

## Workflow

```text
html_loader
-> strategy_router
   |- static  -> static_prepare -> code_exporter -> END
   |- dynamic -> exploration_subagent
                 -> plan_synthesizer
                 -> code_exporter
                 -> END
```

If exploration is blocked by login, captcha, or verification, it returns a human-intervention summary to the main state and stops before code export. You can refer to ```project_logic.md`` (in Chinese) for more detailed information.

## Main Files

- ```main.py```: top-level LangGraph workflow and routing
- ```nodes.py```: top-level nodes only
- ```exploration/nodes.py```: exploration node implementations
- ```exploration/graph.py```: exploration subgraph assembly
- ```tool/browser_tool.py```: browser interaction implementation and shared browser session utilities
- ```tool/pageread_tool.py```: page loading and page-architecture reading utilities
- ```tool/browser_tool_explanation```: tool documentation used for progressive disclosure
- ```prompts.py```: top-level prompts
- ```exploration/prompts.py```: exploration prompts
- ```state.py```: top-level task state
- ```exploration/state.py```: exploration-only state

## Examples

You can refer to ```examples``` folder to see some successful examples of webscraping if interested.

## Update Log

You can refer to ```update_log.md``` see how this project is developed and what is the highlight of the newest version.
