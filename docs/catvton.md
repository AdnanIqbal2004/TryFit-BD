# CatVTON GPU setup

The backend includes a CatVTON adapter. It supports the normal NVIDIA CUDA PyTorch runtime and detects AMD ROCm PyTorch builds. ROCm's PyTorch uses the `torch.cuda` API and `cuda` device string internally; the adapter detects `torch.version.hip`, selects FP16 for AMD, and reports the AMD runtime and GPU through `/api/health`.

This change is code-level AMD support, not a successful CatVTON run on AMD hardware. No AMD GPU is attached to this development environment, so the complete CatVTON, DensePose, and SCHP dependency stack still needs validation on the target PC.

## AMD compatibility

First identify the exact Radeon GPU and operating system. “AMD GPU” alone is not enough to select a working ROCm wheel. AMD's current ROCm 7.2.1 Linux matrix lists supported Radeon RX 7000/9000 models and PyTorch 2.9.1; its Windows matrix lists a smaller set, Windows 11, Python 3.12, and PyTorch 2.9.1. AMD also documents that Windows currently supports PyTorch but not the complete ROCm stack. Detectron2's own install guide says Windows is not officially supported. Therefore, native Ubuntu with an officially supported GPU is the preferred CatVTON test environment; a Windows install may run PyTorch on GPU but the CatVTON DensePose path is not yet confirmed.

Use AMD's versioned compatibility and install instructions rather than installing the CatVTON requirements wholesale:

- [AMD Radeon Linux compatibility](https://rocm.docs.amd.com/projects/radeon-ryzen/en/docs-7.2.1/docs/compatibility/compatibilityrad/native_linux/native_linux_compatibility.html)
- [AMD Radeon Windows compatibility](https://rocm.docs.amd.com/projects/radeon-ryzen/en/latest/docs/compatibility/compatibilityrad/windows/windows_compatibility.html)
- [AMD Linux PyTorch installation](https://rocm.docs.amd.com/projects/radeon-ryzen/en/docs-7.2/docs/install/installrad/native_linux/install-pytorch.html)
- [AMD Windows PyTorch installation](https://rocm.docs.amd.com/projects/radeon-ryzen/en/docs-7.2.1/docs/install/installrad/windows/install-pytorch.html)
- [Detectron2 installation notes](https://github.com/facebookresearch/detectron2/blob/main/INSTALL.md)

## Configure the TryFit backend

1. Install an AMD-supported ROCm/PyTorch combination for the exact GPU and OS. Use Python 3.12 if following AMD's ROCm 7.2.1 Radeon wheels.
2. Before installing other project packages, run `python scripts/check_amd_runtime.py` from the repository root. Confirm that `torch.cuda.is_available()` returns `True`, `torch.version.hip` is populated, and `torch.cuda.get_device_name(0)` reports the Radeon GPU. AMD intentionally exposes the GPU through these PyTorch names.
3. Install the CatVTON source at the recorded academic test revision `999bdbe81e6008a3f5749af7c1e0b0fa3d21b48e`, the compatible Diffusers/Transformers packages, and Detectron2 plus DensePose/SCHP dependencies in that same environment. Keep the ROCm PyTorch build; do not let requirements replace it with CUDA or CPU Torch. Do not install `xformers` unless the selected AMD runtime specifically documents a compatible build.
4. Install the backend into that environment, copy `.env.example` to `.env`, and set:

   ```dotenv
   TRYFIT_MODEL_NAME=catvton
   TRYFIT_DEVICE=rocm
   TRYFIT_CATVTON_SOURCE=./third_party/CatVTON
   ```

   `TRYFIT_DEVICE=auto` also detects ROCm; `rocm` makes the expected runtime explicit. This backend enables CatVTON when `TRYFIT_CATVTON_SOURCE` is set. It passes `cuda` to CatVTON because that is how ROCm PyTorch represents its accelerator.

5. Start the API on the AMD PC and open `/api/health`. It should show `model_available: true` and a device label containing `ROCm` and the GPU name. If it says unavailable, inspect the backend startup log for the specific dependency/import error. Verify a consent-gated test job before using the setup elsewhere.

The known model run was on a Tesla T4 using 768×1024 input, 50 steps, and guidance 2.5. It took about 110 seconds and the result was judged unsatisfactory. AMD performance and quality are unknown. Jobs remain serialized. Keep `TRYFIT_MODEL_NAME=unselected` on computers without the validated GPU stack.

## Licensing and use limits

The upstream CatVTON repository labels its materials CC BY-NC-SA 4.0. This is not cleared for a paid SaaS. Base-model, DensePose, SCHP, dependency, checkpoint, and dataset terms are separate and must be reviewed before any wider use. This adapter is for the project's academic evaluation only; it does not change the prior NO-GO quality recommendation or provide commercial rights.

The app requires a verified merchant session or workspace API key for inference. Image requests are sent to the configured backend host after consent and are stored privately for the configured retention period.
