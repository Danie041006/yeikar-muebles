from sqlalchemy import BigInteger, Column, DateTime, ForeignKey, Index, JSON, String, Text
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func

from app.db.base import Base


class AuditEvent(Base):
    """Immutable operational event used to explain who changed business data."""

    __tablename__ = "audit_event"

    id = Column(BigInteger, primary_key=True, index=True)
    actor_user_id = Column(ForeignKey("usuario.id", ondelete="SET NULL"), nullable=True, index=True)
    action = Column(String(50), nullable=False)
    entity_type = Column(String(80), nullable=False, index=True)
    entity_id = Column(String(80), nullable=False, index=True)
    before_data = Column(JSON, nullable=True)
    after_data = Column(JSON, nullable=True)
    changed_fields = Column(JSON, nullable=True)
    ip_address = Column(String(45), nullable=True)
    user_agent = Column(Text, nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False, index=True)

    actor = relationship("Usuario", foreign_keys=[actor_user_id])

    __table_args__ = (
        Index("ix_audit_event_entity_created", "entity_type", "entity_id", "created_at"),
    )
