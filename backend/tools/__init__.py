"""
LangChain tools wrapping ZohoClient methods.

Split into two groups matching the multi-agent architecture:
  QUERY tools  — read-only, used by the Query Agent
  ACTION tools — write operations with HIL, used by the Action Agent
  (list_projects / list_project_members are shared so Action Agent can resolve names to IDs)
"""

import json

import structlog
from langchain_core.tools import StructuredTool
from langgraph.types import interrupt

from backend.zoho.client import ZohoClient

logger = structlog.get_logger()


def make_zoho_tools(client: ZohoClient) -> tuple[list, list]:
    """
    Returns (query_tools, action_tools) bound to the given ZohoClient.
    query_tools  — read operations only
    action_tools — write operations + lookup helpers (list_projects, list_members)
    """

    # ── Shared read helpers ────────────────────────────────────
    # These are created once and added to both tool lists so each agent
    # can resolve names → IDs independently without crossing responsibilities.

    async def list_projects() -> str:
        """List all Zoho Projects the user has access to."""
        projects = await client.list_projects()
        logger.info("tool_list_projects", count=len(projects))
        return json.dumps(projects)

    async def _resolve_project_id_early(project_id: str) -> str:
        """Resolve project name → numeric ID for read tools. Raises ValueError on failure (caught by handle_tool_errors)."""
        if project_id.isdigit():
            return project_id
        projects = await client.list_projects()
        match = next((p for p in projects if p["name"].lower() == project_id.lower()), None)
        if match:
            return match["id"]
        available = ", ".join(p["name"] for p in projects)
        raise ValueError(f"Project '{project_id}' not found. Available: {available}")

    async def list_project_members(project_id: str) -> str:
        """List all members of a project. Pass project name or numeric ID as project_id."""
        project_id = await _resolve_project_id_early(project_id)
        members = await client.list_project_members(project_id)
        return json.dumps(members)

    # ── Query-only tools ───────────────────────────────────────

    async def list_tasks(
        project_id: str,
        status: str | None = None,
        assignee: str | None = None,
        due_date: str | None = None,
    ) -> str:
        """List tasks in a project. Optional filters: status (open/closed), assignee (member name), due_date (YYYY-MM-DD)."""
        project_id = await _resolve_project_id_early(project_id)
        tasks = await client.list_tasks(project_id, status=status, assignee=assignee, due_date=due_date)
        logger.info("tool_list_tasks", project_id=project_id, count=len(tasks))
        return json.dumps(tasks)

    async def get_task_details(project_id: str, task_id: str) -> str:
        """Get full details of a specific task."""
        project_id = await _resolve_project_id_early(project_id)
        task = await client.get_task_details(project_id, task_id)
        return json.dumps(task)

    async def get_task_utilisation(project_id: str) -> str:
        """Get task workload statistics per team member: open, closed, and total counts."""
        project_id = await _resolve_project_id_early(project_id)
        stats = await client.get_task_utilisation(project_id)
        return json.dumps(stats)

    # ── Action tools (write + HIL) ─────────────────────────────

    async def _resolve_project_id(project_id: str) -> tuple[str | None, str]:
        """Return (numeric_id, display_name) or (None, error_message)."""
        projects = await client.list_projects()
        if project_id.isdigit():
            match = next((p for p in projects if p["id"] == project_id), None)
            if match:
                return match["id"], match["name"]
            return project_id, project_id  # unknown ID, use as-is
        match = next(
            (p for p in projects if p["name"].lower() == project_id.lower()),
            None,
        )
        if match:
            return match["id"], match["name"]
        available = ", ".join(p["name"] for p in projects)
        return None, f"Project '{project_id}' not found. Available: {available}"

    async def _resolve_task_id(project_id: str, task_id: str) -> tuple[str | None, str]:
        """Return (numeric_id, display_name) or (None, error_message). Always verifies live."""
        tasks = await client.list_tasks(project_id)
        if task_id.isdigit():
            match = next((t for t in tasks if t["id"] == task_id), None)
            if match:
                return match["id"], match["name"]
        match = next(
            (t for t in tasks if t["name"].lower() == task_id.lower()),
            None,
        )
        if match:
            return match["id"], match["name"]
        available = ", ".join(t["name"] for t in tasks)
        return None, f"Task '{task_id}' not found. Available tasks: {available}"

    async def _resolve_member_id(project_id: str, assignee: str) -> tuple[str | None, str]:
        """Resolve member name or ID → (numeric_id, display_name)."""
        members = await client.list_project_members(project_id)
        if assignee.isdigit():
            match = next((m for m in members if m["id"] == assignee), None)
            if match:
                return match["id"], match["name"]
            return assignee, assignee  # unknown ID, use as-is
        match = next(
            (m for m in members if m["name"].lower() == assignee.lower()),
            None,
        )
        if match:
            return match["id"], match["name"]
        available = ", ".join(m["name"] for m in members)
        return None, f"Member '{assignee}' not found in project. Available members: {available}"

    async def create_task(
        project_id: str,
        name: str,
        description: str | None = None,
        assignee_id: str | None = None,
        due_date: str | None = None,
        priority: str | None = None,
    ) -> str:
        """Create a new task in a project. Requires user confirmation before executing. due_date: MM-DD-YYYY. priority: high/medium/low/none."""
        project_id, project_name = await _resolve_project_id(project_id)
        if project_id is None:
            return project_name  # error message

        resolved_assignee_id = None
        assignee_display = None
        if assignee_id:
            resolved_assignee_id, assignee_display = await _resolve_member_id(project_id, assignee_id)
            if resolved_assignee_id is None:
                return assignee_display  # error message

        params: dict = {"project_id": project_id, "name": name}
        if description:
            params["description"] = description
        if resolved_assignee_id:
            params["assignee_id"] = resolved_assignee_id  # numeric ID for Zoho API
        if due_date:
            params["due_date"] = due_date
        if priority:
            params["priority"] = priority

        assignee_label = f" assigned to {assignee_display}" if assignee_display else ""
        confirmed = interrupt({
            "tool": "create_task",
            "params": params,
            "description": f"Create task '{name}' in project '{project_name}'{assignee_label}",
        })
        if not confirmed:
            return "Task creation cancelled by user."
        result = await client.create_task(
            project_id, name,
            description=description,
            assignee_id=resolved_assignee_id,
            due_date=due_date,
            priority=priority,
        )
        return f"Task created: '{result.get('name')}' (ID: {result.get('id')})"

    async def update_task(
        project_id: str,
        task_id: str,
        status: str | None = None,
        assignee_id: str | None = None,
        due_date: str | None = None,
        priority: str | None = None,
    ) -> str:
        """Update fields of an existing task. Requires user confirmation. Only provide fields you want to change."""
        project_id, project_name = await _resolve_project_id(project_id)
        if project_id is None:
            return project_name  # error message
        task_id, task_name = await _resolve_task_id(project_id, task_id)
        if task_id is None:
            return task_name  # error message

        resolved_assignee_id = None
        assignee_display = None
        if assignee_id:
            resolved_assignee_id, assignee_display = await _resolve_member_id(project_id, assignee_id)
            if resolved_assignee_id is None:
                return assignee_display  # error message

        params: dict = {"project_id": project_id, "task_id": task_id}
        summary: list[str] = []
        if status:
            params["status"] = status
            summary.append(f"status → {status}")
        if resolved_assignee_id:
            params["assignee_id"] = resolved_assignee_id  # numeric ID for Zoho API
            summary.append(f"assignee → {assignee_display}")
        if due_date:
            params["due_date"] = due_date
            summary.append(f"due_date → {due_date}")
        if priority:
            params["priority"] = priority
            summary.append(f"priority → {priority}")

        confirmed = interrupt({
            "tool": "update_task",
            "params": params,
            "description": f"Update task '{task_name}': {', '.join(summary) or 'no changes'}",
        })
        if not confirmed:
            return "Task update cancelled by user."
        result = await client.update_task(
            project_id, task_id,
            status=status,
            assignee_id=resolved_assignee_id,
            due_date=due_date,
            priority=priority,
        )
        return f"Task updated: '{result.get('name')}' (ID: {result.get('id')})"

    async def delete_task(project_id: str, task_id: str) -> str:
        """Permanently delete a task. This cannot be undone. Requires user confirmation."""
        project_id, project_name = await _resolve_project_id(project_id)
        if project_id is None:
            return project_name  # error message
        task_id, task_name = await _resolve_task_id(project_id, task_id)
        if task_id is None:
            return task_name  # error message
        confirmed = interrupt({
            "tool": "delete_task",
            "params": {"project_id": project_id, "task_id": task_id},
            "description": f"Permanently delete task '{task_name}' from project '{project_name}'",
        })
        if not confirmed:
            return "Task deletion cancelled by user."
        await client.delete_task(project_id, task_id)
        return f"Task {task_id} deleted successfully."

    # ── Build tool lists ───────────────────────────────────────

    _list_projects = StructuredTool.from_function(
        coroutine=list_projects, name="list_projects",
        description="List all Zoho Projects the user has access to.",
    )
    _list_members = StructuredTool.from_function(
        coroutine=list_project_members, name="list_project_members",
        description="List all members of a project. Pass the project name or numeric ID as `project_id`.",
    )

    query_tools = [
        _list_projects,
        StructuredTool.from_function(
            coroutine=list_tasks, name="list_tasks",
            description="List tasks in a project. Filters: status (open/closed), assignee (name), due_date (YYYY-MM-DD).",
        ),
        StructuredTool.from_function(
            coroutine=get_task_details, name="get_task_details",
            description="Get full details of a specific task by project_id and task_id.",
        ),
        _list_members,
        StructuredTool.from_function(
            coroutine=get_task_utilisation, name="get_task_utilisation",
            description="Get task workload statistics per team member: open, closed, and total task counts.",
        ),
    ]

    _list_tasks_action = StructuredTool.from_function(
        coroutine=list_tasks, name="list_tasks",
        description="Look up tasks in a project by name or ID. Use before update_task or delete_task if you need to verify a task exists.",
    )

    action_tools = [
        _list_projects,
        _list_members,
        _list_tasks_action,
        StructuredTool.from_function(
            coroutine=create_task, name="create_task",
            description="Create a new task in a project. Requires user confirmation. due_date: MM-DD-YYYY. priority: high/medium/low/none.",
        ),
        StructuredTool.from_function(
            coroutine=update_task, name="update_task",
            description="Update fields of an existing task. Requires user confirmation. Only provide fields you want to change.",
        ),
        StructuredTool.from_function(
            coroutine=delete_task, name="delete_task",
            description="Permanently delete a task. This cannot be undone. Requires user confirmation.",
        ),
    ]

    return query_tools, action_tools
