from sqlalchemy.orm import declarative_base
from sqlalchemy import ForeignKey, String, Column, DateTime, func, Boolean
from sqlalchemy.dialects.postgresql import UUID, JSONB

Base = declarative_base()

class MediaRecord(Base):

    __tablename__ = "media_authenticity"

    image_id = Column(UUID(as_uuid=True), primary_key= True, nullable=False)
    #user_id = Column(UUID(as_uuid=True), nullable=False, index=True)
    bucket = Column(String, nullable=False)
    object_key = Column(String, nullable=False, unique=True)
    sha256_bytes = Column(String(64))
    #status= Column(String, nullable=False, default="queued")
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    c2pa_status = Column(String, nullable = False, default="unsigned"),
    c2pa_claim_generator = Column(String)
    c2pa_signature_valid = Column(Boolean, nullable = True)
    manifest_json = Column(JSONB, nullable=True)
    parent_image_id = Column(UUID, ForeignKey("media_authenticity.image_id"), nullable=True, index= True)
    #TODO: updated_at needs to be added
