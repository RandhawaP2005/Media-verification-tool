from email.policy import default
from sqlalchemy.orm import declarative_base
from sqlalchemy import String, Column, DateTime, func, Boolean
from sqlalchemy.dialects.postgresql import UUID, JSONB

Base = declarative_base()

class MediaRecord(Base):

    __tablename__ = "media_authenticity"

    image_id = Column(UUID(as_uuid=True), primary_key= True, nullable=False)
    #user_id = Column(UUID(as_uuid=True), nullable=False, index=True)
    bucket = Column(String, nullable=False, unique=True)
    object_key = Column(String, nullable=False, unique=True)
    raw_sha256_bytes = Column(String(64))
    signed_sha256_bytes = Column(String(64))
    status= Column(String, nullable=False, default="queued")
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    signed_object_key = Column(String, nullable = True)
    c2pa_status = Column(String, nullable = False, default="unsigned"),
    c2pa_claim_generater = Column(String)
    c2pa_signature_valid = Column(Boolean, nullable = True)
    manifest_json = Column(JSONB)
    #TODO: updated_at needs to be added
