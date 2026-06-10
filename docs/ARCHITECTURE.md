# Architecture Overview

## System Architecture

The workspace consists of three projects sharing a common technology stack:

### Technology Stack
- **Backend**: Python 3.10+, FastAPI, SQLite, PyTorch/ONNX
- **Frontend**: React 18, Vite 6, Tailwind CSS, Capacitor 8
- **Mobile**: Android via Capacitor, iOS planned
- **ML/AI**: Custom CNN models (v1-v7), BirdNET integration, ONNX inference

### acoustic_platform
Focused on acoustic biodiversity surveys. Core features:
- Real-time audio analysis and species detection
- Xeno-Canto integration for reference recordings
- Embedding-based few-shot detection
- Device management for field recorders

### species_monitoring_platform
Extended platform for comprehensive field surveys. Additional features:
- Multi-modal surveys (audio + camera trap + visual)
- Field operations management (transects, protocols, checklists)
- Offline-first with sync engine
- GPS route tracking
- Alert/notification system via webhooks

### project_sdm_stoten
Research project for Species Distribution Modeling. Outputs:
- SDM analysis with MaxEnt/ensemble methods
- Climate projection under multiple GCM scenarios
- Conservation gap analysis
- STOTEN journal manuscript and supplementary materials

## Shared Components

Both platforms share core modules in `shared/backend/`:
- Audio processing and spectrogram generation
- CNN model architectures (5 versions)
- External API clients (GBIF, eBird, iNaturalist, Xeno-Canto)
- Biodiversity index calculations
- Darwin Core export
- BirdNET and ONNX inference engines

## Data Flow

1. **Audio Input** → Audio Processor → Spectrogram → CNN/BirdNET → Detection
2. **Survey Data** → Survey Store (SQLite) → Sync Engine → Export (DwC/CSV)
3. **Camera Trap** → Image Processor → EXIF extraction → Sequence grouping
4. **SDM Pipeline** → Occurrence data + Environmental layers → MaxEnt → Projections
