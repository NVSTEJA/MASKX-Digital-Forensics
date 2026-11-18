# MASKX — Digital Forensics Dashboard

Responsive React + Tailwind dashboard with a Python Flask backend for live reverse-image searching through **SerpApi's Google Lens API**.

## 1. Requirements

- Node.js 18+ and npm
- Python 3.10+
- A SerpApi account and API key: https://serpapi.com/
- Internet access from the Python backend

## 2. Configure the image-search API

1. Create/sign in to your SerpApi account and copy your private API key.
2. Open the `backend` folder.
3. Copy `.env.example` and name the copy `.env`.
4. Open `backend/.env` and replace the example value:

```env
SERPAPI_API_KEY=put_your_real_key_here
```

Do not put this key in `src`, React code, or any variable beginning with `VITE_`. Do not commit `.env` to GitHub.

## 3. Start the Python backend (Terminal 1)

In VS Code, open the MASKX project folder, then run:

```powershell
cd backend
py -m pip install -r requirements.txt
py app.py
```

The backend runs at `http://127.0.0.1:8000`. Keep this terminal open. Check `http://127.0.0.1:8000/api/health` in your browser; it should show `"status": "ok"` and `"provider_configured": true` after the API key is configured.

## 4. Start the React frontend (Terminal 2)

Open a second VS Code terminal in the project root (the folder containing `package.json`):

```powershell
npm.cmd install
npm.cmd run dev
```

Open the Vite URL, normally `http://localhost:5173`.

## 5. Run a live image trace

1. Open **AI Detection** and upload an image.
2. Open **Global Image Trace**.
3. Click **Start global trace**.
4. MASKX sends the image to the local Python backend. The backend converts it to JPEG under the provider's 500 KB upload limit, uploads it to SerpApi's Image API, then queries Google Lens with the temporary image ID.
5. MASKX displays the visual matches returned by the provider, including available thumbnails, source names and links.

## API endpoints

- `GET /api/health` — backend and API-key configuration status
- `POST /api/trace` — multipart form upload; image field name is `image`

## Important limits and privacy notes

- SerpApi's image upload endpoint currently accepts JPG/JPEG, PNG and WebP up to 500 KB. MASKX prepares supported uploaded raster images as JPEG to fit that provider limit. See [SerpApi Image API](https://serpapi.com/image-api).
- The temporary `image_id` used by Google Lens expires after 10 minutes. SerpApi's documentation says uploaded images may be stored for 30 days for debugging. Do not submit sensitive/private evidence unless your use complies with provider terms and your institution's policies.
- Google Lens/SerpApi results are indexed web matches, not a complete scan of the internet. No match does not prove that an image has never been published. A visual match does not establish authenticity, ownership, date, identity or manipulation.
- AI classification is a separate pretrained-model prediction with the limitations documented below. Morph detection and pixel-level localization are not implemented.
- Evidence management stores files and audit records locally, but is not certified immutable storage or a complete legally validated chain-of-custody platform. Do not use it as a production forensic system or as sole evidence in a legal or disciplinary decision.

## Troubleshooting

- **`SerpApi API key is missing`**: make sure `backend/.env` exists, the key is correct, and restart `py app.py`.
- **`Failed to fetch`**: make sure the backend terminal is still running at port 8000.
- **Provider upload error**: confirm the key/account is active and use a valid image file.
- **No visual matches**: the provider returned no visual matches for this query; it does not mean the image is absent from the web.
- **PowerShell blocks `npm.ps1`**: use `npm.cmd install` and `npm.cmd run dev` as shown above.

## Included pages

Dashboard, AI Detection, Morph Detection, Global Image Trace, Forensic Analysis, Case Management, Investigation History, Reports and Settings.

## 6. AI image classification (optional model installation)

The AI Detection page no longer generates random scores. It calls `POST /api/analyze` and runs the configured pretrained Hugging Face image-classification model in the Python backend. The default model is `umm-maybe/AI-image-detector`.

Install the optional model runtime from the `backend` directory (Python 3.11 is recommended):

```powershell
py -3.11 -m pip install -r requirements-ai.txt
```

The first analysis downloads model weights (several hundred MB) and can take time. The model runs on CPU by default. You can select another compatible Transformers image-classification model by setting `AI_MODEL_ID` in `backend/.env` and restarting the backend.

**Model limitation:** the default model card describes this as an October 2022 proof-of-concept intended for artistic images, not a deepfake-photo detector. It predates newer image generators and can misclassify photos, screenshots and other general imagery. Treat its output as a model prediction for triage, never as proof. It does not create pixel-level heatmaps and does not detect morphing/manipulation. Model reference: https://huggingface.co/umm-maybe/AI-image-detector

## 7. Digital evidence management

On **AI Detection**, select an image. Open **Forensic Analysis**, enter the source and acquisition method, then choose **Preserve original & create working copy**. The backend stores separate files under `backend/evidence_store/originals` and `backend/evidence_store/working`, records metadata in a local manifest, and calculates SHA-256 over the received original bytes. Use **Verify SHA-256** to compare the stored original against the intake hash.

The backend appends acquisition and verification events to a local hash-linked JSONL audit file. An examiner action can also be added through `POST /api/evidence/<evidence_id>/actions`. This is a basic local audit trail, not cryptographically signed, externally anchored or immutable storage. The evidence folder is excluded from Git. Back it up securely and do not treat this prototype as a certified chain-of-custody solution.

Additional endpoints:

- `POST /api/analyze` — multipart image field `image`; returns pretrained model classification scores
- `POST /api/evidence` — multipart `image`, `source`, `method`, optional `examiner`; preserves evidence and returns SHA-256
- `GET /api/evidence` — list local evidence records
- `POST /api/evidence/<evidence_id>/verify` — recompute and compare SHA-256
- `POST /api/evidence/<evidence_id>/actions` — append an examiner action to the audit log
