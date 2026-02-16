from fastapi import FastAPI,UploadFile, Depends
from fastapi.exceptions import HTTPException
from minio import Minio
from minio.error import S3Error
from uuid import uuid4
from dotenv import load_dotenv
from database import  engine, SessionLocal
from sqlalchemy.orm import Session
from database_models import MediaRecord, Base
from hashlib import sha256
import os

load_dotenv()

app = FastAPI()

Base.metadata.create_all(bind=engine)

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
    try:
        response = client.get_object(bucket_name=bucket_name, object_name=object_name)
        return get_sha256_hash(response)
    except S3Error as e:
        raise RuntimeError(f"Minio get object failed: {e.code} {e.message}") from e
    finally:
        if response:
            response.close()
            response.release_conn()



@app.post("/upload/image")
async def upload_image(file: UploadFile, db:Session = Depends(get_db)):
    img_types = ["image/png", "image/jpeg", "image/jpg", "image/heic"]

    if file.content_type not in img_types:
        return HTTPException(400, detail= f"Unsupported file type: {file.content_type}")
    else:
        ext = ""
        for img_type in img_types:
            if img_type == file.content_type:
                ext = img_type.removeprefix("image/")
                break
        
        #Create unique image_id
        image_id = uuid4()
        object_key = f"test/2026/02/{image_id}.{ext}" # test and date is placeholder until user is defined

        client.put_object(
            bucket_name= "test",
            object_name= object_key,
            data= file.file,
            length= file.size,
            content_type= file.content_type
        )

        minio_file_hash = get_img(bucket_name="test", object_name=object_key)

        db.add(MediaRecord(
            image_id=image_id,
            bucket="test",
            object_key=object_key,
            sha256_bytes=minio_file_hash,
        ))

        db.commit()

        return "Upload successful."