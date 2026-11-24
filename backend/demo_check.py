"""Exercise the real CatVTON engine through FastAPI in an interactive GPU session."""

import argparse
from io import BytesIO
import os
from pathlib import Path
from tempfile import TemporaryDirectory
from time import monotonic, sleep

from fastapi.testclient import TestClient
from huggingface_hub import hf_hub_download
from PIL import Image

SOURCE_REVISION = "24a6952918a8c6168b89ae32ad61e7e447e3987b"
EXAMPLES = Path("resource/demo/example")


def sample_bytes(source: Path, folder: Path, index: int = 0) -> bytes:
    paths = sorted(
        path for path in (source / folder).iterdir()
        if path.suffix.lower() in {".jpg", ".jpeg", ".png", ".webp"}
    )
    path = hf_hub_download(
        repo_id="zhengchong/CatVTON",
        repo_type="space",
        revision=SOURCE_REVISION,
        filename=paths[index].relative_to(source).as_posix(),
    )
    with Image.open(path) as image, BytesIO() as buffer:
        image.convert("RGB").save(buffer, format="JPEG", quality=95)
        return buffer.getvalue()


def run_case(client: TestClient, source: Path, poses: str, garment_index: int, output: Path) -> None:
    person = sample_bytes(source, EXAMPLES / "person" / poses)
    garment = sample_bytes(source, EXAMPLES / "condition" / "upper", garment_index)
    created = client.post(
        "/api/jobs",
        data={"consent": "true", "category": "upper"},
        files={
            "person_image": ("person.jpg", person, "image/jpeg"),
            "garment_image": ("garment.jpg", garment, "image/jpeg"),
        },
    )
    created.raise_for_status()
    endpoint = "/api/jobs/" + created.json()["job_id"]

    try:
        deadline = monotonic() + 600
        while monotonic() < deadline:
            response = client.get(endpoint)
            response.raise_for_status()
            job = response.json()
            if job["status"] == "failed":
                raise RuntimeError(job["error_message"])
            if job["status"] == "done":
                result = client.get(endpoint + "/result")
                result.raise_for_status()
                if result.headers["content-type"] != "image/png":
                    raise RuntimeError("Expected a PNG result.")
                with Image.open(BytesIO(result.content)) as image:
                    image.verify()
                output.write_bytes(result.content)
                print(f"{output}: API generation passed ({job['processing_seconds']:.1f}s)")
                break
            sleep(1)
        else:
            raise TimeoutError("CatVTON job exceeded 10 minutes.")
    finally:
        client.delete(endpoint).raise_for_status()

    if client.get(endpoint + "/result").status_code != 404:
        raise RuntimeError("Deleted result is still accessible.")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("source_dir", type=Path, help="Pinned CatVTON Space source checkout")
    parser.add_argument("output_dir", type=Path, help="Directory for permitted demo sample results")
    parser.add_argument("--two-samples", action="store_true")
    args = parser.parse_args()
    source = args.source_dir.resolve()
    args.output_dir.mkdir(parents=True, exist_ok=True)
    os.environ["TRYFIT_CATVTON_SOURCE"] = str(source)
    with TemporaryDirectory(prefix="tryfit-demo-") as storage:
        os.environ["TRYFIT_STORAGE_DIR"] = storage
        from app.main import app

        with TestClient(app) as client:
            run_case(client, source, "men", 0, args.output_dir / "tryfit_api_preview.png")
            if args.two_samples:
                run_case(client, source, "women", 1, args.output_dir / "tryfit_api_preview_2.png")


if __name__ == "__main__":
    main()
