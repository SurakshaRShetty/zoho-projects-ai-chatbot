from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Integer, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from backend.database import Base


class User(Base):
    """
    One row per Zoho user who has logged in.
    Tokens are stored encrypted — see auth/oauth.py for encrypt/decrypt logic.
    """

    __tablename__ = "users"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    zoho_user_id: Mapped[str] = mapped_column(String(100), unique=True, nullable=False, index=True)
    email: Mapped[str] = mapped_column(String(255), unique=True, nullable=False)
    display_name: Mapped[str] = mapped_column(String(255), nullable=True)

    # Encrypted Zoho OAuth tokens
    access_token_encrypted: Mapped[str] = mapped_column(Text, nullable=False)
    refresh_token_encrypted: Mapped[str] = mapped_column(Text, nullable=False)

    # When the access_token expires — used to decide if refresh is needed
    token_expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)

    # Zoho portal ID — fetched once after first login, reused for all API calls
    portal_id: Mapped[str] = mapped_column(String(100), nullable=True)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    # Relationship — one user has many memory entries
    memories: Mapped[list["LongTermMemory"]] = relationship(
        "LongTermMemory", back_populates="user", cascade="all, delete-orphan"
    )


class LongTermMemory(Base):
    """
    Key-value store for per-user long-term memory.
    Examples:
      key="last_project_id",  value="123456"
      key="preferred_sort",   value="due_date"
      key="frequent_projects", value='["123","456"]'
    """

    __tablename__ = "long_term_memory"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), nullable=False, index=True)
    key: Mapped[str] = mapped_column(String(100), nullable=False)
    value: Mapped[str] = mapped_column(Text, nullable=False)  # JSON string
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    user: Mapped["User"] = relationship("User", back_populates="memories")
