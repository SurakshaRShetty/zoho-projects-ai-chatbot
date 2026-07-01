"""
ZohoClient — async HTTP client for the Zoho Projects REST API.
"""

from typing import Any

import httpx
import structlog

from backend.config import settings

logger = structlog.get_logger()

BASE = settings.zoho_api_base_url


class ZohoAPIError(Exception):
    def __init__(self, status_code: int, message: str) -> None:
        self.status_code = status_code
        self.message = message
        super().__init__(f"Zoho API error {status_code}: {message}")


class ZohoClient:
    def __init__(self, access_token: str, portal_id: str) -> None:
        self.access_token = access_token
        self.portal_id = portal_id
        self._base = f"{BASE}/restapi/portal/{portal_id}"

    @property
    def _headers(self) -> dict[str, str]:
        return {"Authorization": f"Zoho-oauthtoken {self.access_token}"}

    # ── Internal helpers ──────────────────────────────────────

    async def _get(self, path: str, params: dict | None = None) -> dict:
        url = f"{self._base}{path}"
        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.get(url, headers=self._headers, params=params or {})
        return self._parse(response)

    async def _post(self, path: str, data: dict) -> dict:
        url = f"{self._base}{path}"
        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.post(url, headers=self._headers, data=data)
        return self._parse(response)

    async def _delete(self, path: str) -> dict:
        url = f"{self._base}{path}"
        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.delete(url, headers=self._headers)
        return self._parse(response)

    def _parse(self, response: httpx.Response) -> dict:
        try:
            data = response.json()
        except Exception:
            data = {}
        if not response.is_success:
            message = (
                data.get("error", {}).get("message", "")
                if isinstance(data, dict)
                else response.text or "Unknown error"
            )
            logger.error("zoho_api_error", status=response.status_code, message=message)
            raise ZohoAPIError(response.status_code, message or response.text)
        if isinstance(data, dict) and "error" in data:
            message = data["error"].get("message", str(data["error"]))
            raise ZohoAPIError(200, message)
        return data

    # ── Projects ──────────────────────────────────────────────

    async def list_projects(self) -> list[dict]:
        data = await self._get("/projects/")
        projects = data.get("projects", [])
        logger.info("zoho_list_projects", count=len(projects))
        return [
            {
                "id": str(p.get("id", "")),
                "name": p.get("name", ""),
                "status": p.get("status", ""),
                "description": p.get("description", ""),
                "owner": p.get("owner_name", ""),
            }
            for p in projects
        ]

    # ── Tasks ─────────────────────────────────────────────────

    async def list_tasks(
        self,
        project_id: str,
        status: str | None = None,
        assignee: str | None = None,
        due_date: str | None = None,
    ) -> list[dict]:
        # Zoho does not support status/assignee/due_date as query params —
        # fetch all tasks then filter client-side.
        data = await self._get(f"/projects/{project_id}/tasks/")
        tasks = data.get("tasks", [])

        if status:
            status_lower = status.lower()
            open_terms = {"open", "in progress", "to do", "not closed", "notclosed"}
            closed_terms = {"closed", "completed", "done"}
            if status_lower in open_terms:
                tasks = [t for t in tasks if t.get("status", {}).get("type", "").lower() == "open"]
            elif status_lower in closed_terms:
                tasks = [t for t in tasks if t.get("status", {}).get("type", "").lower() == "closed"]

        if assignee:
            assignee_lower = assignee.lower()
            tasks = [
                t for t in tasks
                if assignee_lower in (
                    t.get("details", {}).get("owners", [{}])[0].get("name", "").lower()
                )
            ]

        if due_date:
            tasks = [t for t in tasks if t.get("end_date", "") <= due_date]

        logger.info("zoho_list_tasks", project_id=project_id, count=len(tasks))
        return [self._format_task(t) for t in tasks]

    async def get_task_details(self, project_id: str, task_id: str) -> dict:
        data = await self._get(f"/projects/{project_id}/tasks/{task_id}/")
        tasks = data.get("tasks", [])
        if not tasks:
            raise ZohoAPIError(404, f"Task {task_id} not found in project {project_id}")
        logger.info("zoho_get_task", project_id=project_id, task_id=task_id)
        return self._format_task(tasks[0])

    async def create_task(
        self,
        project_id: str,
        name: str,
        description: str | None = None,
        assignee_id: str | None = None,
        due_date: str | None = None,
        priority: str | None = None,
    ) -> dict:
        payload: dict[str, Any] = {"name": name}
        if description:
            payload["description"] = description
        if due_date:
            payload["due_date"] = due_date
        if priority:
            payload["priority"] = priority.capitalize()
        if assignee_id:
            payload["person_responsible"] = assignee_id

        data = await self._post(f"/projects/{project_id}/tasks/", payload)
        tasks = data.get("tasks", [{}])
        logger.info("zoho_create_task", project_id=project_id, task_name=name)
        return self._format_task(tasks[0]) if tasks else {"name": name}

    async def update_task(
        self,
        project_id: str,
        task_id: str,
        status: str | None = None,
        assignee_id: str | None = None,
        due_date: str | None = None,
        priority: str | None = None,
    ) -> dict:
        payload: dict[str, Any] = {}
        if status:
            payload["status"] = status
        if due_date:
            payload["due_date"] = due_date
        if priority:
            payload["priority"] = priority.capitalize()
        if assignee_id:
            payload["person_responsible"] = assignee_id

        if not payload:
            raise ValueError("At least one field must be provided to update")

        data = await self._post(f"/projects/{project_id}/tasks/{task_id}/", payload)
        tasks = data.get("tasks", [{}])
        logger.info("zoho_update_task", project_id=project_id, task_id=task_id)
        return self._format_task(tasks[0]) if tasks else {}

    async def delete_task(self, project_id: str, task_id: str) -> bool:
        await self._delete(f"/projects/{project_id}/tasks/{task_id}/")
        logger.info("zoho_delete_task", project_id=project_id, task_id=task_id)
        return True

    # ── Members ───────────────────────────────────────────────

    async def list_project_members(self, project_id: str) -> list[dict]:
        data = await self._get(f"/projects/{project_id}/users/")
        users = data.get("users", [])
        logger.info("zoho_list_members", project_id=project_id, count=len(users))
        return [
            {
                "id": str(u.get("id", "")),
                "name": u.get("name", ""),
                "email": u.get("email", ""),
                "role": u.get("role", ""),
            }
            for u in users
        ]

    # ── Task utilisation ──────────────────────────────────────

    async def get_task_utilisation(self, project_id: str) -> list[dict]:
        import asyncio
        members, tasks = await asyncio.gather(
            self.list_project_members(project_id),
            self.list_tasks(project_id),
        )
        stats: dict[str, dict] = {
            m["name"]: {
                "member_id": m["id"],
                "name": m["name"],
                "email": m["email"],
                "role": m["role"],
                "total_tasks": 0,
                "open_tasks": 0,
                "closed_tasks": 0,
            }
            for m in members
        }
        def _match_member(assignee: str) -> str:
            """Match a task assignee name to a members-dict key.
            Zoho task owners sometimes return first-name only; members use full name."""
            if assignee in stats:
                return assignee
            al = assignee.lower()
            for key in stats:
                kl = key.lower()
                if kl.startswith(al) or al.startswith(kl):
                    return key
            return assignee  # unmatched — will create an "Unassigned" bucket

        for task in tasks:
            assignee = task.get("assignee", "Unassigned")
            key = _match_member(assignee)
            if key not in stats:
                stats[key] = {
                    "member_id": "",
                    "name": key,
                    "email": "",
                    "role": "",
                    "total_tasks": 0,
                    "open_tasks": 0,
                    "closed_tasks": 0,
                }
            stats[key]["total_tasks"] += 1
            if task.get("status", "").lower() in ("open", "in progress", "to do"):
                stats[key]["open_tasks"] += 1
            else:
                stats[key]["closed_tasks"] += 1
        return sorted(stats.values(), key=lambda x: x["total_tasks"], reverse=True)

    # ── Formatter ─────────────────────────────────────────────

    def _format_task(self, t: dict) -> dict:
        owners = t.get("details", {}).get("owners", [{}])
        assignee = owners[0].get("name", "Unassigned") if owners else "Unassigned"
        status = t.get("status", "")
        if isinstance(status, dict):
            status = status.get("name", "")
        return {
            "id": str(t.get("id", "")),
            "name": t.get("name", ""),
            "status": status,
            "priority": t.get("priority", ""),
            "assignee": assignee,
            "due_date": t.get("end_date", ""),
            "created_date": t.get("created_date", ""),
            "description": t.get("description", ""),
            "project_id": str(t.get("project_id", "")),
        }

