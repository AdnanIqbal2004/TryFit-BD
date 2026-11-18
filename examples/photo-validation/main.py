from io import BytesIO

from fastapi import FastAPI, File, Form, HTTPException, UploadFile
from PIL import Image

app = FastAPI(title="TryFit BD API")
MAX_PHOTO_BYTES = 5 * 1024 * 1024
MAX_IMAGE_SIDE = 4096


@app.get("/health")
def health():
    return {"status": "ok"}


@app.post("/photos/validate")
def validate_photo(
    consent: bool = Form(...),
    photo: UploadFile = File(...),
):
    if not consent:
        raise HTTPException(status_code=400, detail="Consent is required.")

    data = photo.file.read(MAX_PHOTO_BYTES + 1)
    if len(data) > MAX_PHOTO_BYTES:
        raise HTTPException(status_code=413, detail="Choose a photo under 5 MB.")

    try:
        with Image.open(BytesIO(data), formats=["JPEG", "PNG"]) as image:
            width, height = image.size
            if max(width, height) > MAX_IMAGE_SIDE:
                raise HTTPException(
                    status_code=400,
                    detail="Photo width and height must each be at most 4096 pixels.",
                )
            image.load()
            image_format = image.format
    except (OSError, ValueError, Image.DecompressionBombError) as error:
        raise HTTPException(
            status_code=400, detail="Choose a valid JPEG or PNG photo."
        ) from error

    return {
        "status": "valid",
        "format": image_format,
        "width": width,
        "height": height,
    }