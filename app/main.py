from fastapi import FastAPI,UploadFile, Depends
from fastapi.exceptions import HTTPException
from minio import Minio
from minio.error import S3Error
from uuid import uuid4
from dotenv import load_dotenv
from database import  engine, SessionLocal
from sqlalchemy.orm import Session
from sqlalchemy import text
from database_models import MediaRecord, Base
from hashlib import sha256
from metadata_handler import sign_img, get_manifest
from datetime import datetime
import os, io

load_dotenv()

app = FastAPI()

Base.metadata.create_all(bind=engine)


def reconcile_schema() -> None:
    # `create_all()` will not remove an existing unique constraint, so fix the
    # legacy schema explicitly on startup.
    with engine.begin() as conn:
        conn.execute(
            text(
                """
                ALTER TABLE media_authenticity
                DROP CONSTRAINT IF EXISTS media_authenticity_bucket_key
                """
            )
        )


reconcile_schema()

client = Minio(
    endpoint= os.getenv('MINIO_CLIENT_END_POINT'),
    access_key= os.getenv('MINIO_CLIENT_ACCESS_KEY'),
    secret_key= os.getenv('MINIO_CLIENT_SECRET_KEY'),
    secure=False
)

@app.get("/health")
def health():
    return {"ok": True, "service": "backend", "version": "0.1"}

def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close

def get_sha256_hash(download) -> str:
    h = sha256()
    chunk_size = 1024 * 1024

    while True:
        chunk = download.read(chunk_size)
        if not chunk:
            break
        h.update(chunk)
    
    return h.hexdigest()

def get_img(bucket_name:str, object_name:str) -> bytes:
    response = None
    try:
        response = client.get_object(bucket_name=bucket_name, object_name=object_name)
        return response.read()
    finally:
        if response:
            response.close()
            response.release_conn()


@app.post("/upload/image")
async def upload_image(file: UploadFile, db:Session = Depends(get_db)):
    img_types = ["image/png", "image/jpeg", "image/heic"]

    if file.content_type not in img_types:
        raise HTTPException(400, detail= f"Unsupported file type: {file.content_type}")
    else:
        f_type = file.content_type
        ext = ""
        for img_type in img_types:
            if img_type == f_type:
                ext = img_type.removeprefix("image/")
                break
        
        try: 
            raw_bytes = await file.read()
            if not raw_bytes:
                raise HTTPException(status_code=400, detail="Empty Upload")

            #Create unique image_id
            raw_image_id = uuid4()
            bucket_name = "test"
            object_key = f"{raw_image_id}.{ext}" # test and date is placeholder until user is defined

            client.put_object(
                bucket_name= "test",
                object_name= object_key,
                data= io.BytesIO(raw_bytes),
                length= len(raw_bytes),
                content_type= f_type
            )

            db.add(MediaRecord(
                image_id = raw_image_id,
                bucket = bucket_name,
                object_key = object_key,
                sha256_bytes = get_sha256_hash(io.BytesIO(raw_bytes)),
                c2pa_status = "unsigned",
                c2pa_claim_generator = "Media-Verification-Tool"
            ))

            minio_file = get_img(bucket_name="test", object_name=object_key)
            signed_bytes = sign_img(format=f_type, input=io.BytesIO(minio_file), f_name= object_key, existing=True)
            signed_image_id = uuid4()
            signed_object_name = f"{signed_image_id}_signed.{ext}"

            client.put_object(
                bucket_name = bucket_name,
                object_name= signed_object_name,
                data = io.BytesIO(signed_bytes),
                length = len(signed_bytes),
                content_type = f_type
            )

            manifest = get_manifest(io.BytesIO(signed_bytes), f_type)
            print({"manifest": manifest})
            db.add(MediaRecord(
                image_id=signed_image_id,
                bucket="test",
                object_key=signed_object_name,
                sha256_bytes=get_sha256_hash(io.BytesIO(signed_bytes)),
                c2pa_status = "signed",
                c2pa_claim_generator = "Media-Verification-Tool",
                manifest_json = manifest,
                parent_image_id = raw_image_id
            ))

            db.commit()

            return {
               "raw_image_id": str(raw_image_id),
               "signed_image_id": str(signed_image_id)
            }

        except HTTPException:
            db.rollback()
            raise
        except Exception as e:
            db.rollback()
            raise HTTPException(status_code=500, detail=f"Upload/sign failed: {str(e)}")

#@app.post("")
