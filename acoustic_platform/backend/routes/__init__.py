"""Router registry — exports all routers for registration in main.py."""

from routes.health import router as health_router
from routes.config import router as config_router
from routes.maps import router as maps_router
from routes.audio import router as audio_router
from routes.survey import router as survey_router
from routes.detection import router as detection_router
from routes.taxonomy import router as taxonomy_router
from routes.species import router as species_router
from routes.devices import router as devices_router
from routes.export import router as export_router
from routes.realtime import router as realtime_router
from routes.xeno_canto import router as xeno_canto_router
from routes.embeddings import router as embeddings_router
from routes.images import router as images_router
from routes.alerts import router as alerts_router
from routes.soundscape import router as soundscape_router
from routes.phenology import router as phenology_router
from routes.occupancy import router as occupancy_router
from routes.biodiversity_routes import router as biodiversity_router

all_routers = [
    health_router,
    config_router,
    maps_router,
    audio_router,
    survey_router,
    detection_router,
    taxonomy_router,
    species_router,
    devices_router,
    export_router,
    realtime_router,
    xeno_canto_router,
    embeddings_router,
    images_router,
    alerts_router,
    soundscape_router,
    phenology_router,
    occupancy_router,
    biodiversity_router,
]
