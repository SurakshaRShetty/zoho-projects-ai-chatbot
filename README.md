# Zoho Projects AI Chatbot

An AI-powered chatbot for Zoho Projects using a **multi-agent LangGraph** architecture. Users log in via their own Zoho OAuth credentials and interact through a React chat UI to manage projects and tasks using natural language.

---

## Architecture Overview

```
Browser (React)
    │
    │  POST /chat  (JWT)
    ▼
FastAPI Backend
    │
    ▼
Router Node  ──────────────────────────────────
    │  keyword + LLM classification             │
    ▼                                           ▼
Query Agent                             Action Agent
(read-only tools)                 (write tools + HIL)
    │                                           │
    ▼                                           ▼
list_projects                         create_task ──► interrupt() ──► user confirms
list_tasks                            update_task ──► interrupt() ──► user confirms
get_task_details                      delete_task ──► interrupt() ──► user confirms
list_project_members
get_task_utilisation
```

**Key components:**

| Layer | Technology |
|---|---|
| Frontend | React 18 + Vite + Tailwind CSS |
| Backend | FastAPI (async) |
| Agent orchestration | LangGraph 1.x (StateGraph) |
| LLM | Groq (free) — `llama-3.3-70b-versatile` |
| Auth | Zoho OAuth 2.0 (Authorization Code Grant) |
| Database | SQLite via async SQLAlchemy |
| Short-term memory | LangGraph MemorySaver (in-process) |
| Long-term memory | SQLite `long_term_memory` table |

---

## Setup

### 1. Prerequisites

- Python 3.11+
- Node.js 18+
- A Zoho account with access to Zoho Projects
- A free [Groq API key](https://console.groq.com/)

### 2. Clone and install backend dependencies

```bash
git clone <repo-url>
cd zoho-chatbot
pip install -r requirements.txt
```

### 3. Configure environment variables

```bash
cp .env.example .env
```

Edit `.env` and fill in the required values (see [OAuth Configuration](#oauth-configuration) below):

```env
ZOHO_CLIENT_ID=...
ZOHO_CLIENT_SECRET=...
SECRET_KEY=...          # python -c "import secrets; print(secrets.token_hex(32))"
ENCRYPTION_KEY=...      # python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"
GROQ_API_KEY=...
```

### 4. Install frontend dependencies

```bash
cd frontend
npm install
```

---

## OAuth Configuration

1. Go to [https://api-console.zoho.com/](https://api-console.zoho.com/)
2. Click **Add Client** → choose **Server-based Application**
3. Set the redirect URI to: `http://localhost:8000/auth/callback`
4. Copy the **Client ID** and **Client Secret** into your `.env`

Scopes used (granted automatically during login):
- `ZohoProjects.portals.READ`
- `ZohoProjects.projects.ALL`
- `ZohoProjects.tasks.ALL`
- `ZohoProjects.users.READ`

---

## Running Locally

**Terminal 1 — Backend:**
```bash
cd zoho-chatbot
uvicorn backend.main:app --reload --port 8000
```

**Terminal 2 — Frontend:**
```bash
cd zoho-chatbot/frontend
npm run dev
```

Open **http://localhost:3000** in your browser.

---

## Sample Conversations

| You say | What happens |
|---|---|
| `"What projects do I have?"` | Router → Query Agent → `list_projects` |
| `"Show tasks for the first one"` | Short-term memory recalls project, → `list_tasks` |
| `"Create a task called API Integration"` | Router → Action Agent → `create_task` → HIL confirm |
| `"Delete task #5"` | Action Agent → `delete_task` → HIL confirm |
| `"Who has the most tasks this month?"` | Query Agent → `get_task_utilisation` |

---

## API Endpoints

| Method | Path | Description |
|---|---|---|
| `GET` | `/auth/login` | Redirects to Zoho OAuth consent page |
| `GET` | `/auth/callback` | Handles Zoho redirect, issues JWT |
| `GET` | `/auth/me` | Returns current user profile |
| `GET` | `/auth/logout` | Clears server session |
| `POST` | `/chat` | Main chat endpoint |
| `GET` | `/health` | Liveness check |

**POST /chat request:**
```json
{
  "message": "What are my projects?",
  "session_id": "uuid-string",
  "confirmed": null
}
```

**POST /chat response (confirmation required):**
```json
{
  "type": "confirmation_required",
  "content": "I'd like to: Create task 'Fix bug' in project Alpha. Do you confirm?",
  "pending_action": {
    "tool": "create_task",
    "params": { "project_id": "123", "name": "Fix bug" },
    "description": "Create task 'Fix bug' in project Alpha"
  },
  "session_id": "uuid-string"
}
```

---

## Known Limitations

- **Short-term memory** is in-process (MemorySaver) — lost on server restart. For production, replace with `AsyncSqliteSaver` or `PostgresSaver`.
- **Token storage** uses SQLite — suitable for single-user/demo; use PostgreSQL for multi-user production.
- **Groq rate limits** — free tier has request-per-minute limits; the app will return an error if exceeded.
- **Portal ID** — assumes the user belongs to one Zoho Projects portal (the first one returned by the API).
- HIL confirmation state is tied to the LangGraph thread — refreshing the page mid-confirmation loses the pending action.
