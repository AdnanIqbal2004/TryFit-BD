# TryFit BD

A two-person capstone prototype for AI-generated upper-body virtual try-on. The React interface sends a person photo and a garment photo to FastAPI. The backend checks consent, validates images, queues inference, and temporarily stores the inputs and the preview. A user can delete the result from the form.

## Faculty demo

**Previously demonstrated in Colab:** CatVTON generated a 576 × 768 upper-body preview on a Tesla T4 using an automatic mask. The denoising progress bar showed about 16 seconds for one sample. Use the notebook to show the input photos, automatic mask, and final preview. The output is an AI-generated approximation.

**Web demo:** The CatVTON adapter is enabled when `TRYFIT_CATVTON_SOURCE` points to the authors' source checkout in an environment with working PyTorch CUDA and Detectron2. The model loads on the first request. Do one rehearsal to download weights and warm the model before presenting.

### Run the real API check in Colab

1. In a fresh T4 runtime, run the GPU check, CatVTON source checkout, Python package installation, and Detectron2 installation cells from `tryfit_catvton_Test.ipynb`. Skip the notebook's model-loading and inference cells for this check because the API will load its own model.
2. Upload the provided TryFit BD source ZIP in the Colab Files sidebar. In a new code cell, unpack it and install the backend:

   ```python
   !unzip -oq /content/TryFit-BD-demo.zip -d /content/tryfit-demo
   %pip install av
   %pip install -e "/content/tryfit-demo/backend[dev]"
   ```

3. Run the real API through a test client inside Colab. This exercises upload, automatic masking, GPU inference, polling, PNG retrieval, and deletion:

   ```python
   !python /content/tryfit-demo/backend/demo_check.py /content/catvton-source /content/tryfit-results --two-samples
   ```

4. If the command reports `API generation passed`, display the result and check the face, garment details, hands, and areas outside the mask. First-job time can include model loading.

   ```python
   from IPython.display import Image, display

   display(Image(filename="/content/tryfit-results/tryfit_api_preview.png"))
   display(Image(filename="/content/tryfit-results/tryfit_api_preview_2.png"))
   ```

For the presentation, keep a permitted sample and its verified output saved locally as backup. If a GPU is unavailable, show the web workflow on Windows and demonstrate the actual AI result separately in Colab or using that saved output.

### Run the app on an NVIDIA GPU host

Use the same Python environment in which the notebook's CatVTON and Detectron2 imports pass. The source checkout uses [CatVTON Space revision 24a6952](https://huggingface.co/spaces/zhengchong/CatVTON/tree/24a6952918a8c6168b89ae32ad61e7e447e3987b).

Run from the repository root:

```bash
npm --prefix frontend ci
npm --prefix frontend run build
cd backend
python -m pip install -e .
export TRYFIT_CATVTON_SOURCE=/absolute/path/to/catvton-source
python -m uvicorn app.main:app --host 127.0.0.1 --port 8000
```

Open http://127.0.0.1:8000 on that machine. Select a clear front-facing person photo and a separate upper-body garment image, give consent, and click **Create preview**. Check the result, then use **Delete temporary images and start over**. A device that lacks a compatible GPU can run the interface and API in development mode with the model disabled.

### Windows development

From `backend`, run `py -3.11 -m venv .venv` if needed, then `.venv\Scripts\python.exe -m pip install -e ".[dev]"` and `.venv\Scripts\python.exe -m uvicorn app.main:app --reload --port 8000`. In a separate terminal from `frontend`, run `npm ci` and `npm run dev`. Vite forwards `/api` requests to port 8000.

## Verification

- Backend: `python -m pytest` from `backend` with the development dependencies installed.
- Frontend: `npm --prefix frontend run build` and `npm --prefix frontend run lint`.
- GPU: run the Colab API check above, inspect both results and record failures.

The current demo accepts uploaded garments. The proposal also calls for a sample catalogue. The model weights are published under [CC BY-NC-SA 4.0](https://huggingface.co/zhengchong/CatVTON). Keep private uploads, generated outputs, model weights and credentials out of Git.
