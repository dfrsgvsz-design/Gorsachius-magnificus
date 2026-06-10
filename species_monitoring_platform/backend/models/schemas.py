"""Pydantic request/response models for the Biodiversity Field Survey Platform."""

from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field


class XCSearchRequest(BaseModel):
    species: str
    country: str = "China"
    max_results: int = 20


class APIKeyRequest(BaseModel):
    key: str


class SiteDetections(BaseModel):
    site_name: str
    species: List[str]


class CompareSitesRequest(BaseModel):
    sites: List[SiteDetections]


class SurveyCreateRequest(BaseModel):
    site_name: str
    region: str = ""
    latitude: Optional[float] = None
    longitude: Optional[float] = None
    habitat_type: str = ""
    protocol: str = "point_count"
    notes: str = ""


class SurveyProjectRequest(BaseModel):
    project_id: Optional[str] = None
    name: str = "未命名项目"
    team_members: List[str] = Field(default_factory=list)
    target_taxa: List[str] = Field(default_factory=list)
    region: str = ""
    survey_window: Dict[str, Any] = Field(default_factory=dict)
    notes: str = ""
    sync_state: str = "synced"
    extra: Dict[str, Any] = Field(default_factory=dict)


class SurveySiteRequest(BaseModel):
    site_id: Optional[str] = None
    project_id: str = ""
    name: str = "未命名样点"
    latitude: Optional[float] = None
    longitude: Optional[float] = None
    geometry: Optional[Dict[str, Any]] = None
    habitat_type: str = ""
    admin_region: str = ""
    region_code: str = ""
    notes: str = ""
    sensitivity: str = "public"
    sync_state: str = "synced"
    extra: Dict[str, Any] = Field(default_factory=dict)


class SurveyRouteRequest(BaseModel):
    route_id: Optional[str] = None
    project_id: str = ""
    site_id: str = ""
    name: str = "未命名路线"
    route_type: str = "transect"
    geometry: Dict[str, Any] = Field(
        default_factory=lambda: {"type": "LineString", "coordinates": []}
    )
    length_m: Optional[float] = None
    source: str = "manual"
    imported_format: str = ""
    original_filename: str = ""
    point_times: List[str] = Field(default_factory=list)
    sync_state: str = "synced"
    extra: Dict[str, Any] = Field(default_factory=dict)


class ObservationRecordRequest(BaseModel):
    observation_id: Optional[str] = None
    project_id: str = ""
    site_id: str = ""
    route_id: str = ""
    event_id: str = ""
    program: str = ""
    submodule: str = ""
    protocol: str = ""
    jurisdiction: str = ""
    taxon_id: str = ""
    scientific_name: str = ""
    chinese_name: str = ""
    english_name: str = ""
    taxon_group: str = ""
    count: int = 1
    evidence_type: str = "visual"
    behavior: str = ""
    breeding_code: str = ""
    habitat_notes: str = ""
    confidence: float = 0.5
    certainty: str = "review_needed"
    sign_type: str = ""
    unknown_taxon: bool = False
    trace_only: bool = False
    latitude: Optional[float] = None
    longitude: Optional[float] = None
    geometry: Optional[Dict[str, Any]] = None
    media: List[Dict[str, Any]] = Field(default_factory=list)
    observer: str = ""
    observed_at: str = ""
    snapped_route_id: str = ""
    snapped_distance_m: float = 0.0
    sensitivity: str = "public"
    record_payload: Dict[str, Any] = Field(default_factory=dict)
    ai_suggestion: Dict[str, Any] = Field(default_factory=dict)
    sync_state: str = "synced"
    extra: Dict[str, Any] = Field(default_factory=dict)


class TrackLogRequest(BaseModel):
    track_id: Optional[str] = None
    project_id: str = ""
    site_id: str = ""
    route_id: str = ""
    event_id: str = ""
    program: str = ""
    submodule: str = ""
    protocol: str = ""
    jurisdiction: str = ""
    name: str = "现场轨迹"
    source: str = "recorded"
    geometry: Dict[str, Any] = Field(
        default_factory=lambda: {"type": "LineString", "coordinates": []}
    )
    point_times: List[str] = Field(default_factory=list)
    distance_m: Optional[float] = None
    duration_s: Optional[float] = None
    started_at: str = ""
    ended_at: str = ""
    observer: str = ""
    weather: Dict[str, Any] = Field(default_factory=dict)
    sync_state: str = "synced"
    extra: Dict[str, Any] = Field(default_factory=dict)


class MapPackageRequest(BaseModel):
    package_id: Optional[str] = None
    project_id: str = ""
    name: str = "离线底图包"
    bbox: Dict[str, Any] = Field(default_factory=dict)
    min_zoom: int = 8
    max_zoom: int = 14
    tile_url: str = ""
    tile_count_estimate: Optional[int] = None
    storage_bytes_estimate: Optional[int] = None
    expires_at: str = ""
    status: str = "planned"
    sync_state: str = "synced"
    extra: Dict[str, Any] = Field(default_factory=dict)


class DesignAssetRequest(BaseModel):
    asset_id: Optional[str] = None
    project_id: str = ""
    site_id: str = ""
    asset_type: str = "route"
    program: str = ""
    submodule: str = ""
    protocol: str = ""
    name: str = "Unnamed Design Asset"
    geometry: Optional[Dict[str, Any]] = None
    parent_asset_id: str = ""
    route_id: str = ""
    status: str = "active"
    sensitivity: str = "public"
    notes: str = ""
    sync_state: str = "synced"
    extra: Dict[str, Any] = Field(default_factory=dict)


class SamplingEventRequest(BaseModel):
    event_id: Optional[str] = None
    project_id: str = ""
    site_id: str = ""
    design_asset_id: str = ""
    route_id: str = ""
    program: str = ""
    submodule: str = ""
    protocol: str = ""
    jurisdiction: str = "mainland_china"
    started_at: str = ""
    ended_at: str = ""
    geometry: Optional[Dict[str, Any]] = None
    weather: Dict[str, Any] = Field(default_factory=dict)
    effort_metrics: Dict[str, Any] = Field(default_factory=dict)
    event_payload: Dict[str, Any] = Field(default_factory=dict)
    observers: List[str] = Field(default_factory=list)
    team: List[str] = Field(default_factory=list)
    notes: str = ""
    sync_state: str = "synced"
    extra: Dict[str, Any] = Field(default_factory=dict)


class ExportJobRequest(BaseModel):
    project_id: str = ""
    site_id: str = ""
    program: str = ""
    protocol: str = ""
    event_id: str = ""
    format: str = "json"
    extra: Dict[str, Any] = Field(default_factory=dict)


class SyncOperationRequest(BaseModel):
    entity_type: str
    operation: str = "upsert"
    entity_id: str = ""
    payload: Dict[str, Any] = Field(default_factory=dict)


class SyncPushRequest(BaseModel):
    device_id: str = ""
    user_id: str = ""
    operations: List[SyncOperationRequest] = Field(default_factory=list)


class DeviceRegisterRequest(BaseModel):
    name: str
    device_type: str = "generic"
    location_name: str = ""
    latitude: float = 0.0
    longitude: float = 0.0
    altitude: float = 0.0
    sample_rate: int = 22050
    channels: int = 1
    bit_depth: int = 16
    metadata: Dict = Field(default_factory=dict)


class BatchScanRequest(BaseModel):
    directory: str
    device_id: Optional[str] = None
    site_name: Optional[str] = None
    camera_serial: Optional[str] = None
    recursive: bool = True


class VerifyRequest(BaseModel):
    detection_id: str
    status: str  # confirmed, rejected, uncertain
    verified_by: str = "anonymous"
    notes: str = ""


class BatchVerifyRequest(BaseModel):
    detection_ids: List[str]
    status: str
    verified_by: str = "anonymous"
    notes: str = ""


class DwCExportRequest(BaseModel):
    species_filter: Optional[list[str]] = None
    date_start: Optional[str] = None
    date_end: Optional[str] = None
    min_confidence: float = 0.0
    verified_only: bool = False
    metadata: dict = {}


class OccupancyRequest(BaseModel):
    species: str
    n_surveys: int = 6
    survey_duration_days: int = 7
    start_date: Optional[str] = None
    end_date: Optional[str] = None


class AlertConfigRequest(BaseModel):
    target_species: list[str] = []
    min_confidence: float = 0.8
    wechat_webhook: Optional[str] = None
    dingtalk_webhook: Optional[str] = None
    email: Optional[str] = None
    platform_url: str = ""
