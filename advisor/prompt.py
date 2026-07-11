"""Advisor prompt — asks GPT for a concrete implementation plan.

GPT acts as a senior architect giving a plan with real code.
The local model then executes the plan with tool calls.
"""

from __future__ import annotations


def build_advisor_prompt(query: str, context: str = "") -> str:
    """Build the prompt sent to GPT advisor.

    GPT is asked to provide a concrete plan (analysis + code + verification steps),
    not just a chat answer. The local model will execute this plan with tools.
    """
    ctx_block = f"\n\nBackground context: {context}" if context else ""

    return f"""You are a senior software architect advising a local coding agent.

The local agent has these tools: read_file, search_files, glob_files, edit_file, write_file, \
run_bash, run_test, web_search, github_search. It can execute code and edit files directly.

For the request below, provide a CONCRETE implementation plan:
1. Brief analysis of what needs to be done
2. Specific files to read/modify/create (with paths if you can guess)
3. Code snippets for key changes (full functions, not pseudocode)
4. Verification steps (tests to run, commands to check)

Be direct and concrete. The local agent will execute your plan with real tools.{ctx_block}

Request:
{query}""".strip()
