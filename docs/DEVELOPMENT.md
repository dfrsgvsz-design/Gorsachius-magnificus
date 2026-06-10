# Development Guide

## Prerequisites
- Python 3.10+
- Node.js 18+
- npm 9+
- Android Studio (for mobile builds)

## Backend Setup
```bash
cd <platform>/backend
python -m venv .venv
.venv\Scripts\activate  # Windows
pip install -r requirements.txt
python main.py
```
API runs on http://localhost:8000

## Frontend Setup
```bash
cd <platform>/frontend
npm install
npm run dev
```
Dev server runs on http://localhost:5173

## Environment Variables
| Variable | Description | Required |
|----------|-------------|----------|
| CORS_ORIGINS | Comma-separated allowed origins | Production |
| EBIRD_API_KEY | eBird API key for species data | Optional |
| RATE_MAX_CLIENTS | Max rate limiter entries | Optional |

## Mobile Build
```bash
cd <platform>/frontend
npm run build
npx cap sync android
npx cap open android
```

## Testing
```bash
cd <platform>/backend
pytest tests/
```

## Project SDM
```bash
cd project_sdm_stoten
pip install -r requirements.txt  # if exists
python analysis_scripts/unified_pipeline.py
```
