"""Router registry — collects all APIRouter instances for registration in main."""

from .alerts import router as alerts_router
from .audio import router as audio_router
from .biodiversity_routes import router as biodiversity_router
from .config import router as config_router
from .detection import router as detection_router
from .devices import router as devices_router
from .embeddings import router as embeddings_router
from .export import router as export_router
from .field_ops import router as field_ops_router
from .health import router as health_router
from .images import router as images_router
from .maps import router as maps_router
from .multimodal import router as multimodal_router
from .occupancy import router as occupancy_router
from .phenology import router as phenology_router
from .realtime import router as realtime_router
from .soundscape import router as soundscape_router
from .species import router as species_router
from .survey import router as survey_router
from .taxonomy import router as taxonomy_router
from .xeno_canto import router as xeno_canto_router

all_routers = [
    health_router,
    config_router,
    maps_router,
    audio_router,
    survey_router,
    taxonomy_router,
    species_router,
    detection_router,
    devices_router,
    realtime_router,
    xeno_canto_router,
    embeddings_router,
    images_router,
    biodiversity_router,
    export_router,
    alerts_router,
    soundscape_router,
    phenology_router,
    occupancy_router,
    field_ops_router,
    multimodal_router,
]
