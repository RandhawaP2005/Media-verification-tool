from fastapi import FastAPI,UploadFile
from fastapi.exceptions import HTTPException
from minio import Minio

app = FastAPI()

client = Minio(
    endpoint= "minio:9000",
    access_key= "admin",
    secret_key= "password",
    secure=False
)

@app.get("/health")
def health():
    return {"ok": True, "service": "backend", "version": "0.1"}


@app.post("/upload/image")
async def upload_image(file: UploadFile):
    img_types = ["image/png", "image/jpeg", "image/jpg", "image/heic"]

    if file.content_type not in img_types:
        return HTTPException(400, detail= f"Unsupported file type: {file.content_type}")
    else:
        file_type = ""
        for img_type in img_types:
            if img_type == file.content_type:
                file_type = img_type.removeprefix("image/")
                break

        client.put_object(
            bucket_name= "test",
            object_name= f"test_image2.{file_type}",
            data= file.file,
            length= file.size
        )
        return "Upload successful."