from typing import Any, Literal

from pydantic import BaseModel, EmailStr, Field


# ── Auth Schemas ──────────────────────────────────────────────

class TokenResponse(BaseModel):
    """Returned to frontend after successful OAuth login."""
    access_token: str
    token_type: str = "bearer"
    user_email: str
    user_name: str


class UserProfile(BaseModel):
    """Current logged-in user info — returned by /auth/me."""
    id: int
    zoho_user_id: str
    email: str
    display_name: str | None
    portal_id: str | None


# ── Chat Schemas ──────────────────────────────────────────────

class ChatRequest(BaseModel):
    """
    Sent by frontend on every user message.
    - message: what the user typed (empty string allowed when confirmed is set)
    - session_id: unique ID for this conversation (frontend generates it)
    - confirmed: None on normal messages, True/False when responding to HIL prompt
    """
    message: str = Field(default="", max_length=4000)
    session_id: str = Field(..., min_length=1, max_length=100)
    confirmed: bool | None = Field(default=None)

    def model_post_init(self, __context: Any) -> None:
        if self.confirmed is None and not self.message.strip():
            raise ValueError("message is required when not confirming an action")


class PendingAction(BaseModel):
    """
    Describes a write operation waiting for user confirmation.
    Sent back to frontend when agent wants to perform a write op.
    """
    tool: str                        # e.g. "create_task", "delete_task"
    params: dict[str, Any]           # the exact parameters to be used
    description: str                 # human-readable summary shown to user


class ChatResponse(BaseModel):
    """
    Returned by POST /chat.
    type="message"              → regular reply, display content in thread
    type="confirmation_required" → show PendingAction card with Confirm/Cancel
    type="error"                → something went wrong, display content as error
    """
    type: Literal["message", "confirmation_required", "error"]
    content: str                          # text to display in the chat thread
    pending_action: PendingAction | None = None  # only set when type="confirmation_required"
    session_id: str                       # echoed back so frontend can match responses
