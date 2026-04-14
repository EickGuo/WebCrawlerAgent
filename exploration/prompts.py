from langchain_core.prompts import ChatPromptTemplate


TOOL_SELECTOR_PROMPT = ChatPromptTemplate.from_template(
    """
You are deciding the next exploration tool for a browser agent.

User request:
{user_request}

Entry URL:
{url}

Current page architecture:
{current_page_architecture}

Recent exploration history:
{exploration_history}

Available tool index:
{tool_index}

Return EXACTLY one JSON object:
{{
  "reasoning": "why this tool is the best next step",
  "tool": "one tool name from the index"
}}

Rules:
1. Choose exactly one tool from the provided tool index.
2. Do not return args in this stage.
3. Prefer evidence-gathering before irreversible navigation when behavior is unclear.
4. Do not choose `finish` until key interactions have been verified from evidence. If the user wants to extract detailed information, be sure to use tools to verify how to extract that information before finishing. Do not fabricate or generate it yourself.
5. Use only the current page architecture plus exploration history to decide the next tool.
6. Do not rely solely on whether the URL has changed to determine if the access was successful. Also check whether the desired information appears on the page.
7. Output JSON only.
"""
)


TOOL_ARG_BUILDER_PROMPT = ChatPromptTemplate.from_template(
    """
You are building arguments for one selected exploration tool.

User request:
{user_request}

Entry URL:
{url}

Selected tool:
{selected_tool}

Current page architecture:
{current_page_architecture}

Exploration history:
{exploration_history}

Recent failure summary:
{recent_failure_summary}

Selected tool context:
{selected_tool_context}

Detailed tool documentation:
{tool_doc_content}

Return EXACTLY one JSON object:
{{
  "reasoning": "why these args are appropriate",
  "tool": "{selected_tool}",
  "args": {{}}
}}

Rules:
1. Build args only for the selected tool.
2. Use the current page architecture, exploration history, recent failures, and the detailed tool documentation to build args.
3. Avoid repeating the same failed pattern.
4. If the selected tool is `read_page_architecture`, use `reasoning` to clearly explain how the target information should be extracted from this detail page in runnable code terms.
5. Output JSON only.
"""
)


EXPLORATION_SUMMARIZER_PROMPT = ChatPromptTemplate.from_template(
    """
You are summarizing an exploration session for the main workflow. Later on the scraping code would be generated based on your summary. 

User request:
{user_request}

Exploration history:
{exploration_history}

Stop reason:
{stop_reason}

Return EXACTLY one JSON object:
{{
  "exploration_summary": "concrete and understandable summary of verified interactions and page structure for code generation"
}}

Rules:
1. Keep only the most decision-relevant exploration evidence.
2. Focus on the verified page path that progressively moved toward successful extraction.
3. Summarize which tools worked, which failed, which page transitions happened, and what code-generation implications follow from those findings.
4. If the user wants to extract detailed information, be sure to explain how to extract that information. Do not fabricate or generate it yourself.
5. Do not return exploration history or stop reason; those are filled by code.
6. Output JSON only.
"""
)


HUMAN_INTERVENTION_SUMMARIZER_PROMPT = ChatPromptTemplate.from_template(
    """
You are summarizing an exploration session that requires human intervention.

User request:
{user_request}

Reason:
{reason}

Status:
{status}

Evidence:
{evidence}

Exploration history:
{exploration_history}

Current snapshot:
{current_page_snapshot}

Return EXACTLY one JSON object:
{{
  "required": true,
  "reason": "{reason}",
  "status": "{status}",
  "evidence": [],
  "next_steps": [],
  "summary": "brief summary for the main workflow"
}}

Rules:
1. Explain what blocked exploration and what the user should do next.
2. `next_steps` should be concrete manual actions.
3. Output JSON only.
"""
)
