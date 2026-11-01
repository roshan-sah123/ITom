from datetime import datetime

from sqlalchemy import Boolean, DateTime, Integer, LargeBinary, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, TimestampMixin


class KnowledgeContent(Base, TimestampMixin):
    __tablename__ = "knowledge_content"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    request_id: Mapped[str] = mapped_column(String(32), unique=True)
    payload_hash: Mapped[str] = mapped_column(String(64))
    name: Mapped[str] = mapped_column(String(160))
    description: Mapped[str] = mapped_column(Text)
    category: Mapped[str] = mapped_column(String(100))
    file_name: Mapped[str] = mapped_column(String(150))
    file_type: Mapped[str] = mapped_column(String(120))
    file_size: Mapped[int] = mapped_column(Integer)
    file_data: Mapped[bytes] = mapped_column(LargeBinary, deferred=True)
    revision: Mapped[int] = mapped_column(Integer, default=1)
    validated_by: Mapped[str | None] = mapped_column(String(128))
    validated_on: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    is_deleted: Mapped[bool] = mapped_column(Boolean, default=False)
