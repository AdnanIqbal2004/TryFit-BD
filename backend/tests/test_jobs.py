"""Tests for serial job execution, controlled model errors, and output checks."""

from __future__ import annotations

import asyncio
from pathlib import Path

import pytest
from PIL import Image

from app.ai.engine import UnconfiguredTryOnEngine
from app.ai.output_check import OutputValidationError, validate_output_image
from app.services.job_manager import JobManager, JobNotFoundError
from tests.conftest import make_image_bytes


async def _wait_for_terminal(manager: JobManager, job_id: str, timeout: float = 3.0):
    deadline = asyncio.get_running_loop().time() + timeout
    while asyncio.get_running_loop().time() < deadline:
        snapshot = manager.get_status(job_id)
        if snapshot.status in {"done", "failed"}:
            return snapshot
        await asyncio.sleep(0.01)
    raise AssertionError("Job did not reach a terminal state before timeout")


def test_unconfigured_model_fails_job_without_fabricating_output(settings):
    async def scenario():
        manager = JobManager(settings, UnconfiguredTryOnEngine())
        await manager.start()
        submitted = await manager.submit(
            make_image_bytes(), ".jpg", make_image_bytes(), ".jpg", "upper"
        )
        assert submitted.status == "waiting"
        failed = await _wait_for_terminal(manager, submitted.job_id)
        assert failed.status == "failed"
        assert "no model has been approved" in failed.error_message
        with pytest.raises(JobNotFoundError):
            manager.get_result_path(submitted.job_id)
        await manager.shutdown()

    asyncio.run(scenario())


def test_gpu_out_of_memory_is_controlled_and_worker_continues(settings):
    class OOMThenSuccessEngine:
        model_name = "test-engine"
        device = "test-device"
        run_settings = {"steps": 1}

        def __init__(self):
            self.calls = 0

        def generate(self, person_image: Path, garment_image: Path, category: str, output_path: Path) -> Path:
            self.calls += 1
            if self.calls == 1:
                raise RuntimeError("CUDA out of memory")
            output_path.parent.mkdir(parents=True, exist_ok=True)
            image = Image.new("RGB", (64, 64))
            pixels = image.load()
            for y in range(64):
                for x in range(64):
                    pixels[x, y] = (x * 4, y * 4, (x + y) * 2)
            image.save(output_path, format="PNG")
            return output_path

    async def scenario():
        manager = JobManager(settings, OOMThenSuccessEngine())
        await manager.start()
        first = await manager.submit(make_image_bytes(), ".jpg", make_image_bytes(), ".jpg", "upper")
        second = await manager.submit(make_image_bytes(), ".jpg", make_image_bytes(), ".jpg", "upper")
        first_result = await _wait_for_terminal(manager, first.job_id)
        second_result = await _wait_for_terminal(manager, second.job_id)
        assert first_result.status == "failed"
        assert "GPU ran out of memory" in first_result.error_message
        assert second_result.status == "done"
        assert manager.get_result_path(second.job_id).is_file()
        await manager.delete(second.job_id)
        with pytest.raises(JobNotFoundError):
            manager.get_result_path(second.job_id)
        await manager.shutdown()

    asyncio.run(scenario())


def test_output_check_rejects_blank_image(tmp_path):
    blank_path = tmp_path / "blank.png"
    Image.new("RGB", (32, 32), "white").save(blank_path)
    with pytest.raises(OutputValidationError, match="appears blank"):
        validate_output_image(blank_path)


def test_output_check_rejects_corrupt_file(tmp_path):
    corrupt_path = tmp_path / "corrupt.png"
    corrupt_path.write_bytes(b"not an image")
    with pytest.raises(OutputValidationError, match="could not be read"):
        validate_output_image(corrupt_path)
