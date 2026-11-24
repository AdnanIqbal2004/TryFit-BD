"""Print GPU/runtime facts needed before attempting CatVTON on AMD hardware."""

from __future__ import annotations

import platform
import sys


def main() -> int:
    print(f"OS: {platform.platform()}")
    print(f"Python: {sys.version.split()[0]} ({sys.executable})")
    try:
        import torch
    except Exception as exc:
        print(f"PyTorch import: FAILED ({type(exc).__name__}: {exc})")
        return 1

    hip = getattr(torch.version, "hip", None)
    cuda = getattr(torch.version, "cuda", None)
    print(f"PyTorch: {torch.__version__}")
    print(f"ROCm/HIP build: {hip or 'no'}")
    print(f"CUDA build metadata: {cuda or 'no'}")
    print(f"torch.cuda.is_available(): {torch.cuda.is_available()}")
    try:
        print(f"GPU count: {torch.cuda.device_count()}")
        for index in range(torch.cuda.device_count()):
            print(f"GPU {index}: {torch.cuda.get_device_name(index)}")
    except Exception as exc:
        print(f"GPU query failed: {type(exc).__name__}: {exc}")
    if hip and torch.cuda.is_available():
        print("Result: PyTorch detects an AMD ROCm GPU; TryFit can select TRYFIT_DEVICE=rocm.")
        return 0
    if not hip:
        print("Result: This is not a ROCm PyTorch build. Install the AMD-supported ROCm wheel for this OS/GPU.")
    else:
        print("Result: ROCm PyTorch is installed, but no usable AMD GPU was detected.")
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
