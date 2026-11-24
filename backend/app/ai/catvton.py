"""GPU-backed CatVTON adapter for the upper-body demo."""

from pathlib import Path
import sys

from PIL import Image

from app.ai.engine import ModelUnavailableError
from app.ai.output_check import OutputValidationError

MODEL_REPO = "zhengchong/CatVTON"
BASE_MODEL = "booksforcharlie/stable-diffusion-inpainting"


class CatVTONEngine:
    """Load the original pipeline on first use and reuse it in the serial worker."""

    model_name = "CatVTON"
    device = "cuda"

    def __init__(self, source: Path, width: int, height: int, steps: int) -> None:
        self._source = source.expanduser().resolve()
        self._runtime = None
        self.run_settings = {
            "width": width,
            "height": height,
            "steps": steps,
            "guidance_scale": 2.5,
            "seed": 42,
        }

    def _load_runtime(self):
        if self._runtime is not None:
            return self._runtime
        if not (self._source / "model" / "pipeline.py").is_file():
            raise ModelUnavailableError("CatVTON source is missing from the configured GPU environment.")
        try:
            import torch
        except ImportError as exc:
            raise ModelUnavailableError("PyTorch is missing from the GPU environment.") from exc
        if not torch.cuda.is_available():
            raise ModelUnavailableError("CatVTON requires a working CUDA GPU in this setup.")

        source_path = str(self._source)
        if source_path not in sys.path:
            sys.path.insert(0, source_path)
        from huggingface_hub import snapshot_download
        from model.cloth_masker import AutoMasker
        from model.pipeline import CatVTONPipeline
        from utils import resize_and_crop, resize_and_padding

        checkpoints = Path(snapshot_download(
            repo_id=MODEL_REPO,
            allow_patterns=["mix-48k-1024/attention/*", "DensePose/*", "SCHP/*"],
        ))
        pipeline = CatVTONPipeline(
            base_ckpt=BASE_MODEL,
            attn_ckpt=str(checkpoints),
            attn_ckpt_version="mix",
            weight_dtype=torch.float16,
            device=self.device,
            use_tf32=False,
        )
        masker = AutoMasker(
            densepose_ckpt=str(checkpoints / "DensePose"),
            schp_ckpt=str(checkpoints / "SCHP"),
            device=self.device,
        )
        self._runtime = (torch, pipeline, masker, resize_and_crop, resize_and_padding)
        return self._runtime

    def generate(
        self, person_image: Path, garment_image: Path, category: str, output_path: Path
    ) -> Path:
        if category != "upper":
            raise ModelUnavailableError("This CatVTON demo supports upper-body garments only.")
        torch, pipeline, masker, resize_and_crop, resize_and_padding = self._load_runtime()
        settings = self.run_settings
        size = (settings["width"], settings["height"])

        with Image.open(person_image) as source:
            person = resize_and_crop(source.convert("RGB"), size)
        with Image.open(garment_image) as source:
            garment = resize_and_padding(source.convert("RGB"), size)

        with torch.inference_mode():
            mask = masker(person, mask_type="upper")["mask"].convert("L")
            mask = mask.resize(size, Image.Resampling.NEAREST)
            if mask.getextrema() != (0, 255):
                raise OutputValidationError(
                    "Could not identify the upper-body clothing area. Try a clear front-facing photo."
                )
            result = pipeline(
                image=person,
                condition_image=garment,
                mask=mask,
                width=size[0],
                height=size[1],
                num_inference_steps=settings["steps"],
                guidance_scale=settings["guidance_scale"],
                generator=torch.Generator(device=self.device).manual_seed(settings["seed"]),
            )[0]

        if result is None:
            raise OutputValidationError("The model could not return a preview for these images.")
        result.save(output_path, format="PNG")
        return output_path
