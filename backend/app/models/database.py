from sqlalchemy import Column, String, DateTime, JSON, Text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.ext.declarative import declarative_base
import uuid
from datetime import datetime

Base = declarative_base()


class Project(Base):
    __tablename__ = "projects"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    clerk_user_id = Column(String, nullable=False, index=True)
    name = Column(String, nullable=False)
    description = Column(Text)

    # Search parameters
    query = Column(String, nullable=False)
    filters = Column(JSON, default={})  # year_range, publication_types, etc.
    status = Column(String, default="pending")  # pending, running, completed, failed

    # Timestamps
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
