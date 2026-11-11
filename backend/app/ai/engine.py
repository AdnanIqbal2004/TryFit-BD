"""Swappable interface for locally hosted virtual try-on models."""

from __future__ import annotations

from pathlib import Path
from typing import Protocol


class ModelUnavailableError(RuntimeError):
    """Raised when no approved local model is configured."""


class TryOnEngine(Protocol):
    """Inference contract implemented by a selected local pretrained model."""

    model_name: str
    device: str
    run_settings: dict[str, str | int | float | bool]

    def generate(
        self,
        person_image: Path,
        garment_image: Path,
        category: str,
        output_path: Path,
    ) -> Path:
        """Generate one preview and return its private output path."""
        ...


class UnconfiguredTryOnEngine:
    """Safe placeholder that never fabricates an inference result."""

    model_name = "unselected"
    device = "unconfigured"
    run_settings: dict[str, str | int | float | bool] = {}

    def generate(
        self,
        person_image: Path,
        garment_image: Path,
        category: str,
        output_path: Path,
    ) -> Path:
        raise ModelUnavailableError(
            "Try-on generation is unavailable because no model has been approved and configured."
        )
