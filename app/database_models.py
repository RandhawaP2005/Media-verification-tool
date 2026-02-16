from sqlalchemy.orm import declarative_base
from sqlalchemy import String, Column, DateTime, func
from sqlalchemy.dialects.postgresql import UUID

Base = declarative_base()

class MediaRecord(Base):

    __tablename__ = "media_authenticity"

    image_id = Column(UUID(as_uuid=True), primary_key= True, nullable=False)
    #user_id = Column(UUID(as_uuid=True), nullable=False, index=True)
    bucket = Column(String, nullable=False, unique=True)
    object_key = Column(String, nullable=False, unique=True)
    sha256_bytes = Column(String(64), nullable=False)
    status= Column(String, nullable=False, default="queued")
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    #TODO: updated_at needs to be added
