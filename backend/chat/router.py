"""
POST /chat — main chat endpoint.
Wires together: JWT auth → Zoho token refresh → long-term memory →
multi-agent graph → HIL interrupt handling → long-term memory save.
"""

import json

import structlog
from fastapi import APIRouter, Depends, HTTPException, status
from langchain_core.messages import AIMessage, HumanMessage
from langgraph.types import Command
from sqlalchemy.ext.asyncio import AsyncSession

from backend.agents import build_graph
from backend.auth.middleware import get_current_user
from backend.auth.oauth import zoho_oauth
from backend.database import get_db
from backend.memory.long_term import get_all_memories, set_memory
from backend.models.db import User
from backend.models.schemas import ChatRequest, ChatResponse, PendingAction
from backend.tools import make_zoho_tools
from backend.zoho.client import ZohoClient

logger = structlog.get_logger()
router = APIRouter()


def _thread_id(user_id: int, session_id: str) -> str:
    return f"{user_id}:{session_id}"


def _extract_ai_response(messages: list) -> str:
    """Return the last non-empty AI text message, always as a plain string."""
    for msg in reversed(messages):
        if not isinstance(msg, AIMessage):
            continue
        content = msg.content
        if isinstance(content, str) and content.strip():
            return content.strip()
        if isinstance(content, list):
            text = " ".join(
                b.get("text", "") for b in content
                if isinstance(b, dict) and b.get("type") == "text"
            ).strip()
            if text:
                return text
        # Guard: if content is a dict/object, serialize it rather than return raw
        if content and not isinstance(content, str):
            try:
                return json.dumps(content)
            except Exception:
                pass
    return "Done."


def _format_memory_context(memories: dict[str, str]) -> str | None:
    """Convert DB memory rows into a readable context string for the agent."""
    if not memories:
        return None
    lines = [f"- {k}: {v}" for k, v in memories.items()]
    return "\n".join(lines)


async def _save_session_memory(
    db: AsyncSession,
    user_id: int,
    messages: list,
) -> None:
    """
    After each turn, persist lightweight long-term memory.
    Saves: last_active timestamp and last_project (name) from tool results.
    """
    import json
    from datetime import datetime
    from langchain_core.messages import ToolMessage

    try:
        await set_memory(db, user_id, "last_active", datetime.utcnow().isoformat())

        # Extract last project name from list_projects tool results
        for msg in reversed(messages):
            if not isinstance(msg, ToolMessage):
                continue
            try:
                data = json.loads(msg.content)
                if isinstance(data, list) and data and "name" in data[0]:
                    await set_memory(db, user_id, "last_project", data[0]["name"])
                    break
            except (json.JSONDecodeError, (KeyError, IndexError, TypeError)):
                continue
    except Exception as exc:
        logger.warning("memory_save_failed", error=str(exc))


async def _handle_confirmation(
    *,
    request,
    confirmed: bool,
    client: ZohoClient,
    graph,
    config: dict,
    db,
    user_id: int,
) -> ChatResponse:
    """
    Execute (or cancel) a pending HIL action by reading its params directly
    from the stored interrupt state — bypasses Command(resume) which breaks
    when the graph is rebuilt between requests.
    """
    if not confirmed:
        logger.info("hil_cancelled", user_id=user_id)
        # Resume graph with False so the checkpoint advances cleanly
        try:
            await graph.ainvoke(Command(resume=False), config=config)
        except Exception:
            pass
        return ChatResponse(
            type="message",
            content="Action cancelled.",
            session_id=request.session_id,
        )

    # Read pending interrupt value from the checkpoint
    try:
        state = await graph.aget_state(config)
        iv = None
        for task in (state.tasks or []):
            if task.interrupts:
                iv = task.interrupts[0].value
                break
    except Exception as exc:
        logger.warning("state_read_failed", error=str(exc))
        iv = None

    if not iv:
        return ChatResponse(
            type="error",
            content="No pending action found. Please try your request again.",
            session_id=request.session_id,
        )

    tool = iv.get("tool", "")
    params = iv.get("params", {})
    logger.info("hil_confirmed", user_id=user_id, tool=tool, params=params)

    try:
        if tool == "create_task":
            result = await client.create_task(
                params["project_id"],
                params["name"],
                description=params.get("description"),
                assignee_id=params.get("assignee_id"),
                due_date=params.get("due_date"),
                priority=params.get("priority"),
            )
            content = f"Task **'{result.get('name', params['name'])}'** created successfully."
            if result.get("id"):
                content += f" (ID: {result['id']})"

        elif tool == "update_task":
            result = await client.update_task(
                params["project_id"],
                params["task_id"],
                status=params.get("status"),
                assignee_id=params.get("assignee_id"),
                due_date=params.get("due_date"),
                priority=params.get("priority"),
            )
            content = f"Task **'{result.get('name', params['task_id'])}'** updated successfully."

        elif tool == "delete_task":
            await client.delete_task(params["project_id"], params["task_id"])
            content = f"Task {params['task_id']} deleted successfully."

        else:
            content = f"Unknown action '{tool}'. Nothing was executed."

    except Exception as exc:
        logger.error("hil_action_failed", tool=tool, error=str(exc))
        return ChatResponse(
            type="error",
            content=f"Action failed: {exc}",
            session_id=request.session_id,
        )

    # Advance the graph checkpoint so the session stays consistent
    try:
        await graph.ainvoke(Command(resume=True), config=config)
    except Exception:
        pass

    logger.info("hil_action_success", tool=tool, user_id=user_id)
    return ChatResponse(type="message", content=content, session_id=request.session_id)


@router.post("/chat", response_model=ChatResponse)
async def chat(
    request: ChatRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> ChatResponse:

    if not current_user.portal_id:
        return ChatResponse(
            type="error",
            content="Your Zoho portal ID is missing. Please log out and log in again.",
            session_id=request.session_id,
        )

    # ── Refresh Zoho access token ──────────────────────────────
    try:
        access_token = await zoho_oauth.get_valid_access_token(db, current_user)
    except Exception as exc:
        logger.error("token_refresh_failed", user_id=current_user.id, error=str(exc))
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Your Zoho session has expired. Please log in again.",
        )

    # ── Load long-term memory ──────────────────────────────────
    memories = await get_all_memories(db, current_user.id)
    memory_context = _format_memory_context(memories)

    # ── Build graph with user-specific tools ───────────────────
    client = ZohoClient(access_token=access_token, portal_id=current_user.portal_id)
    query_tools, action_tools = make_zoho_tools(client)
    graph, _ = build_graph(query_tools, action_tools)

    config = {"configurable": {"thread_id": _thread_id(current_user.id, request.session_id)}}

    # ── Confirmed / cancelled: execute directly from stored interrupt ──
    if request.confirmed is not None:
        return await _handle_confirmation(
            request=request,
            confirmed=request.confirmed,
            client=client,
            graph=graph,
            config=config,
            db=db,
            user_id=current_user.id,
        )

    # ── Normal message: invoke graph ───────────────────────────
    try:
        result = await graph.ainvoke(
            {
                "messages": [HumanMessage(content=request.message)],
                "memory_context": memory_context,
            },
            config=config,
        )
    except Exception as exc:
        logger.error("agent_error", user_id=current_user.id, error=str(exc))
        return ChatResponse(
            type="error",
            content="Something went wrong processing your request. Please try again.",
            session_id=request.session_id,
        )

    # ── Check for HIL interrupt (write op awaiting confirmation) ──
    try:
        state = await graph.aget_state(config)
        if state.tasks:
            for task in state.tasks:
                if task.interrupts:
                    iv = task.interrupts[0].value
                    pending = PendingAction(
                        tool=iv.get("tool", ""),
                        params=iv.get("params", {}),
                        description=iv.get("description", ""),
                    )
                    logger.info("hil_interrupt", user_id=current_user.id, tool=pending.tool)
                    return ChatResponse(
                        type="confirmation_required",
                        content=f"I'd like to: **{pending.description}**\n\nDo you confirm?",
                        pending_action=pending,
                        session_id=request.session_id,
                    )
    except Exception as exc:
        logger.warning("state_check_failed", error=str(exc))

    # ── Extract final response ─────────────────────────────────
    messages = result.get("messages", [])
    content = _extract_ai_response(messages)

    # ── Save long-term memory ──────────────────────────────────
    await _save_session_memory(db, current_user.id, messages)

    logger.info("chat_ok", user_id=current_user.id, session_id=request.session_id)
    return ChatResponse(type="message", content=content, session_id=request.session_id)
