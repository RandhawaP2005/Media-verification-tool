from fastapi import FastAPI,UploadFile, Depends
from fastapi.exceptions import HTTPException
from fastapi.responses import StreamingResponse
from minio import Minio
from minio.error import S3Error
from uuid import uuid4, UUID
from dotenv import load_dotenv
from database import  engine, SessionLocal
from sqlalchemy.orm import Session
from sqlalchemy import text
from database_models import MediaRecord, Base
from hashlib import sha256
from metadata_handler import CLAIM_GENERATOR, sign_img, get_manifest, verify_img
from datetime import datetime
import os, io
from io import BytesIO

load_dotenv()

app = FastAPI()

Base.metadata.create_all(bind=engine)

def reconcile_schema() -> None:
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
        db.close()

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


def get_claim_generator(manifest: dict) -> str | None:
    claim_generator = manifest.get("claim_generator")
    if claim_generator:
        return claim_generator

    claim_generator_info = manifest.get("claim_generator_info") or []
    if claim_generator_info:
        return claim_generator_info[0].get("name")

    return None


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
                c2pa_claim_generator = CLAIM_GENERATOR
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
                c2pa_claim_generator = CLAIM_GENERATOR,
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

@app.post("/upload/verify")
async def verify_upload(file: UploadFile, db:Session = Depends(get_db)):
    img_types = ["image/png", "image/jpeg", "image/heic"]

    if file.content_type not in img_types:
        raise HTTPException(400, detail= f"Unsupported file type: {file.content_type}")

    f_type = file.content_type

    try: 
        raw_bytes = await file.read()
        if not raw_bytes:
            raise HTTPException(status_code=400, detail="Empty Upload")

        manifest = get_manifest(raw_bytes, f_type)
        if not manifest:
            raise HTTPException(status_code=400, detail="Missing C2PA manifest")

        verification_data = verify_img(raw_bytes, f_type)
        if not verification_data:
            raise HTTPException(status_code=400, detail="Unable to verify C2PA manifest")

        computed_sha = get_sha256_hash(io.BytesIO(raw_bytes))
        record = db.query(MediaRecord).filter_by(sha256_bytes=computed_sha).first()
        manifest_store = verification_data["manifest_store"]
        active_manifest_id = manifest_store.get("active_manifest")
        active_manifest = manifest_store.get("manifests", {}).get(active_manifest_id, {})
        claim_generator = get_claim_generator(active_manifest)

        expected_claim_generator = None
        if record and record.manifest_json:
            expected_claim_generator = get_claim_generator(record.manifest_json)
        if record and not expected_claim_generator:
            expected_claim_generator = record.c2pa_claim_generator

        matching_record = bool(record)
        mismatch_reasons = []
        if record and expected_claim_generator != claim_generator:
            matching_record = False
            mismatch_reasons.append("claim_generator")

        validation_state = verification_data.get("validation_state")
        signature_valid = str(validation_state).lower() == "valid"
        if record:
            record.c2pa_signature_valid = signature_valid
            db.commit()

        return {
            "sha256": computed_sha,
            "has_manifest": True,
            "known_to_system": bool(record),
            "matching_record": matching_record,
            "mismatch_reasons": mismatch_reasons,
            "c2pa": {
                "active_manifest": active_manifest_id,
                "claim_generator": claim_generator,
                "validation_state": validation_state,
                "validation_results": verification_data.get("validation_results"),
                "signature_valid": signature_valid
            },
            "record": {
                "image_id": str(record.image_id),
                "object_key": record.object_key,
                "c2pa_status": record.c2pa_status,
                "expected_claim_generator": expected_claim_generator
            } if record else None
        }

    except HTTPException:
        db.rollback()
        raise
    except Exception as e:
        db.rollback()
        raise HTTPException(status_code=500, detail=f"Verification failed: {str(e)}")


def read_img(file) -> BytesIO:
    return BytesIO(file)

@app.get("/image/{image_id}/download", response_class=StreamingResponse)
async def download_signed_img(image_id: UUID, db:Session = Depends(get_db)):
    record = db.query(MediaRecord).filter(MediaRecord.image_id == image_id).first()

    if not record:
        raise HTTPException(status_code=404,detail="Image not found.")

    if record.c2pa_status != "signed":
        raise HTTPException(status_code=400,detail="requested image is not signed.")

    file_bytes = get_img("test", record.object_key)
    file_name = record.object_key.split("/")[-1]

    def iter_file():
        with read_img(file_bytes) as img_file:
            yield from img_file

    return StreamingResponse(
        iter_file(),
        media_type="application/octet-stream",
        headers={"Content-Disposition": f'attachment; filename="{file_name}"'}
    )



