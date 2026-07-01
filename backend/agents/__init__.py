"""
Multi-agent LangGraph system for Zoho Projects chatbot.

Architecture:
  START → router → query_agent  ↔ query_tools  → END
                 → action_agent ↔ action_tools → END

Router   : keyword check + LLM fallback — decides query vs action
Query Agent  : read-only tools (list, get, report)
Action Agent : write tools with interrupt()-based HIL (create, update, delete)
"""

from functools import lru_cache
from typing import Annotated, Literal, Optional

import structlog
from langchain_core.messages import AIMessage, BaseMessage, HumanMessage, SystemMessage, ToolMessage
from langgraph.checkpoint.memory import MemorySaver
from langgraph.graph import END, START, StateGraph
from langgraph.graph.message import add_messages
from langgraph.prebuilt import ToolNode
from langgraph.types import Command
from typing_extensions import TypedDict

from backend.config import settings

logger = structlog.get_logger()


# ── Graph state ───────────────────────────────────────────────

class AgentState(TypedDict):
    messages: Annotated[list[BaseMessage], add_messages]
    mode: Optional[str]          # "query" or "action" — set by router
    memory_context: Optional[str]  # long-term memory injected per session


# ── System prompts ────────────────────────────────────────────

QUERY_SYSTEM = """\
You are the Query Agent for a Zoho Projects assistant. You ONLY read and report data — never write.

Tools:
- list_projects          → list all projects with their status and description
- list_tasks             → list tasks in a project with optional filters (status, assignee, due_date)
- get_task_details       → full details of a single task
- list_project_members   → all members of a project with roles
- get_task_utilisation   → task load summary per member

Rules:
• If the user asks about PROJECTS (list projects, show projects, what are my projects), call list_projects ONLY — do NOT call list_tasks.
• If the user asks about TASKS, call list_projects first (to resolve the project ID), then call list_tasks.
• If the user asks about workload, utilisation, task load, or per-member stats, call get_task_utilisation ONLY — do NOT call list_tasks.
• Call each tool EXACTLY ONCE per request. Never call the same tool twice.
• If the user does not specify a status, call list_tasks with NO status filter to get all tasks.
• If list_tasks returns 0 tasks, report "No tasks found" — do NOT retry or call list_tasks again.
• Present results with bullet points or short tables.
• Never attempt to create, update, or delete anything.
"""

ACTION_SYSTEM = """\
You are the Action Agent for a Zoho Projects assistant. You handle write operations only.

Tools:
- list_projects          → look up project IDs by name (pass project name, ID resolved automatically)
- list_project_members   → look up member IDs before assigning (pass project name or ID)
- create_task            → create a NEW task that does not exist yet (confirmation required)
- update_task            → change fields on an EXISTING task, e.g. priority, status, due_date (confirmation required)
- delete_task            → permanently remove an EXISTING task (confirmation required)

Rules:
• Use create_task ONLY when the user asks to create or add a new task.
• Use update_task when the user asks to change, update, edit, or modify an existing task.
• Use delete_task when the user asks to delete or remove an existing task.
• Call each tool AT MOST ONCE per request. Never repeat the same tool call.
• Pass task names directly — they are resolved to IDs automatically. Do NOT invent or guess task IDs.
• If a tool returns an error (member not found, task not found, etc.), STOP immediately and report the exact error to the user. Do NOT call any more tools.
• If an assignee name is not found in list_project_members results, tell the user which members ARE available. Do NOT call create_task or update_task.
• due_date format: MM-DD-YYYY | priority: high / medium / low / none
"""

ROUTER_PROMPT = """\
Classify the user message as exactly one of: query OR action.

query  → reading, listing, showing, fetching, summarising, reporting
action → creating, adding, updating, editing, deleting, removing, assigning, changing

Reply with a single word only: query or action\
"""

WRITE_KEYWORDS = {
    "create", "add", "make", "new task", "update", "change", "edit",
    "modify", "delete", "remove", "assign", "set priority", "mark",
    "close", "reopen", "move",
}


# ── Singletons ────────────────────────────────────────────────

@lru_cache(maxsize=1)
def get_checkpointer() -> MemorySaver:
    return MemorySaver()


@lru_cache(maxsize=1)
def _get_llm():
    if settings.llm_provider == "groq":
        from langchain_groq import ChatGroq
        return ChatGroq(
            model=settings.llm_model,
            api_key=settings.groq_api_key,
            temperature=0,
        )
    if settings.llm_provider == "anthropic":
        from langchain_anthropic import ChatAnthropic
        return ChatAnthropic(
            model=settings.llm_model,
            api_key=settings.anthropic_api_key,
            max_tokens=4096,
        )
    from langchain_openai import ChatOpenAI
    return ChatOpenAI(
        model=settings.llm_model,
        api_key=settings.openai_api_key,
    )


# ── Graph factory ─────────────────────────────────────────────

def build_graph(query_tools: list, action_tools: list):
    """
    Builds the compiled multi-agent graph.
    Returns (graph, checkpointer).
    Called once per request with user-specific tools.
    The shared MemorySaver preserves conversation history across requests.
    """
    llm = _get_llm()
    checkpointer = get_checkpointer()

    query_llm  = llm.bind_tools(query_tools)
    action_llm = llm.bind_tools(action_tools)

    # ── Router ────────────────────────────────────────────────

    async def router(state: AgentState) -> Command[Literal["query_agent", "action_agent"]]:
        content = ""
        for m in reversed(state["messages"]):
            if hasattr(m, "content") and isinstance(m.content, str):
                content = m.content.lower()
                break

        # Fast keyword scan
        if any(kw in content for kw in WRITE_KEYWORDS):
            mode = "action"
        else:
            # LLM fallback for ambiguous phrasing
            try:
                resp = await llm.ainvoke([
                    SystemMessage(content=ROUTER_PROMPT),
                    HumanMessage(content=content),
                ])
                mode = "action" if "action" in resp.content.strip().lower() else "query"
            except Exception:
                mode = "query"

        logger.info("router_decision", mode=mode, msg=content[:80])
        return Command(goto=f"{mode}_agent", update={"mode": mode})

    # ── Agent nodes ───────────────────────────────────────────

    async def query_agent(state: AgentState) -> dict:
        system = QUERY_SYSTEM
        if state.get("memory_context"):
            system += f"\n\nContext from user's previous sessions:\n{state['memory_context']}"
        messages = [SystemMessage(content=system)] + state["messages"]
        response = await query_llm.ainvoke(messages)
        return {"messages": [response]}

    async def action_agent(state: AgentState) -> dict:
        system = ACTION_SYSTEM
        if state.get("memory_context"):
            system += f"\n\nContext from user's previous sessions:\n{state['memory_context']}"
        messages = [SystemMessage(content=system)] + state["messages"]
        response = await action_llm.ainvoke(messages)
        return {"messages": [response]}

    # ── Routing conditions ────────────────────────────────────

    def query_next(state: AgentState) -> str:
        last = state["messages"][-1]
        if isinstance(last, AIMessage) and getattr(last, "tool_calls", None):
            return "query_tools"
        return END

    def action_next(state: AgentState) -> str:
        last = state["messages"][-1]
        if isinstance(last, AIMessage) and getattr(last, "tool_calls", None):
            return "action_tools"
        return END

    _WRITE_TOOL_NAMES = {"create_task", "update_task", "delete_task"}

    def action_tools_next(state: AgentState) -> str:
        """After action_tools: END immediately if a write op just completed.
        This prevents a second LLM call that tends to loop or produce errors."""
        for msg in reversed(state["messages"]):
            if isinstance(msg, ToolMessage):
                if getattr(msg, "name", None) in _WRITE_TOOL_NAMES:
                    return END
                break
        return "action_agent"

    # ── Assemble graph ────────────────────────────────────────

    builder = StateGraph(AgentState)

    builder.add_node("router",       router)
    builder.add_node("query_agent",  query_agent)
    builder.add_node("query_tools",  ToolNode(query_tools,  handle_tool_errors=True))
    builder.add_node("action_agent", action_agent)
    builder.add_node("action_tools", ToolNode(action_tools, handle_tool_errors=True))

    builder.add_edge(START, "router")

    builder.add_conditional_edges(
        "query_agent",
        query_next,
        {"query_tools": "query_tools", END: END},
    )
    builder.add_edge("query_tools", "query_agent")

    builder.add_conditional_edges(
        "action_agent",
        action_next,
        {"action_tools": "action_tools", END: END},
    )
    builder.add_conditional_edges(
        "action_tools",
        action_tools_next,
        {"action_agent": "action_agent", END: END},
    )

    graph = builder.compile(checkpointer=checkpointer)
    return graph, checkpointer
