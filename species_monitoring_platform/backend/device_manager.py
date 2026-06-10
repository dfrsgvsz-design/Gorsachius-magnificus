"""
Field Device Manager — 野外采集设备注册、心跳、状态管理。

支持设备类型:
- AudioMoth (自动录音器)
- Raspberry Pi + USB麦克风
- 专业声音记录仪 (Song Meter, Wildlife Acoustics)
- 手机/平板 (通过WebSocket)

设备通信协议:
- 注册: POST /api/devices/register
- 心跳: WebSocket ping/pong
- 音频流: WebSocket binary frames (PCM 16-bit, 22050Hz)
"""

import time
import uuid
from dataclasses import dataclass, field, asdict
from typing import Dict, List, Optional
from enum import Enum
from datetime import datetime, UTC


class DeviceStatus(str, Enum):
    ONLINE = "online"
    OFFLINE = "offline"
    RECORDING = "recording"
    ERROR = "error"


class DeviceType(str, Enum):
    AUDIOMOTH = "audiomoth"
    RASPBERRY_PI = "raspberry_pi"
    SONG_METER = "song_meter"
    MOBILE = "mobile"
    GENERIC = "generic"


@dataclass
class DeviceInfo:
    device_id: str
    name: str
    device_type: DeviceType
    location_name: str = ""
    latitude: float = 0.0
    longitude: float = 0.0
    altitude: float = 0.0
    sample_rate: int = 22050
    channels: int = 1
    bit_depth: int = 16
    status: DeviceStatus = DeviceStatus.OFFLINE
    registered_at: str = ""
    last_heartbeat: float = 0.0
    total_recordings: int = 0
    total_detections: int = 0
    metadata: Dict = field(default_factory=dict)

    def to_dict(self) -> Dict:
        d = asdict(self)
        d["status"] = self.status.value
        d["device_type"] = self.device_type.value
        d["last_heartbeat_ago"] = self._heartbeat_ago()
        return d

    def _heartbeat_ago(self) -> str:
        if self.last_heartbeat == 0:
            return "never"
        elapsed = time.time() - self.last_heartbeat
        if elapsed < 60:
            return f"{int(elapsed)}s ago"
        elif elapsed < 3600:
            return f"{int(elapsed / 60)}m ago"
        else:
            return f"{int(elapsed / 3600)}h ago"


class DeviceManager:
    """Manages field recording devices and their states."""

    HEARTBEAT_TIMEOUT = 120  # seconds before marking device offline

    def __init__(self):
        self._devices: Dict[str, DeviceInfo] = {}
        self._active_sessions: Dict[str, str] = {}  # device_id -> session_id

    @property
    def device_count(self) -> int:
        return len(self._devices)

    @property
    def online_count(self) -> int:
        return sum(
            1
            for d in self._devices.values()
            if d.status in (DeviceStatus.ONLINE, DeviceStatus.RECORDING)
        )

    def register(
        self,
        name: str,
        device_type: str = "generic",
        location_name: str = "",
        latitude: float = 0.0,
        longitude: float = 0.0,
        altitude: float = 0.0,
        sample_rate: int = 22050,
        channels: int = 1,
        bit_depth: int = 16,
        metadata: Dict = None,
    ) -> DeviceInfo:
        """Register a new device or update existing one."""
        device_id = str(uuid.uuid4())[:12]
        try:
            dt = DeviceType(device_type)
        except ValueError:
            dt = DeviceType.GENERIC

        device = DeviceInfo(
            device_id=device_id,
            name=name,
            device_type=dt,
            location_name=location_name,
            latitude=latitude,
            longitude=longitude,
            altitude=altitude,
            sample_rate=sample_rate,
            channels=channels,
            bit_depth=bit_depth,
            status=DeviceStatus.ONLINE,
            registered_at=datetime.now(UTC).isoformat().replace("+00:00", "Z"),
            last_heartbeat=time.time(),
            metadata=metadata or {},
        )
        self._devices[device_id] = device
        return device

    def unregister(self, device_id: str) -> bool:
        if device_id in self._devices:
            del self._devices[device_id]
            self._active_sessions.pop(device_id, None)
            return True
        return False

    def get(self, device_id: str) -> Optional[DeviceInfo]:
        return self._devices.get(device_id)

    def heartbeat(self, device_id: str) -> bool:
        device = self._devices.get(device_id)
        if not device:
            return False
        device.last_heartbeat = time.time()
        if device.status == DeviceStatus.OFFLINE:
            device.status = DeviceStatus.ONLINE
        return True

    def set_status(self, device_id: str, status: DeviceStatus):
        device = self._devices.get(device_id)
        if device:
            device.status = status
            device.last_heartbeat = time.time()

    def start_session(self, device_id: str) -> Optional[str]:
        """Start a recording session for a device."""
        device = self._devices.get(device_id)
        if not device:
            return None
        session_id = f"{device_id}_{int(time.time())}"
        self._active_sessions[device_id] = session_id
        device.status = DeviceStatus.RECORDING
        device.last_heartbeat = time.time()
        return session_id

    def end_session(self, device_id: str) -> Optional[str]:
        """End a recording session."""
        device = self._devices.get(device_id)
        if not device:
            return None
        session_id = self._active_sessions.pop(device_id, None)
        device.status = DeviceStatus.ONLINE
        device.last_heartbeat = time.time()
        return session_id

    def get_session(self, device_id: str) -> Optional[str]:
        return self._active_sessions.get(device_id)

    def increment_stats(self, device_id: str, recordings: int = 0, detections: int = 0):
        device = self._devices.get(device_id)
        if device:
            device.total_recordings += recordings
            device.total_detections += detections

    def check_timeouts(self):
        """Mark devices as offline if heartbeat timed out."""
        now = time.time()
        for device in self._devices.values():
            if device.status in (DeviceStatus.ONLINE, DeviceStatus.RECORDING):
                if now - device.last_heartbeat > self.HEARTBEAT_TIMEOUT:
                    device.status = DeviceStatus.OFFLINE
                    self._active_sessions.pop(device.device_id, None)

    def list_all(self) -> List[Dict]:
        self.check_timeouts()
        return [d.to_dict() for d in self._devices.values()]

    def list_online(self) -> List[Dict]:
        self.check_timeouts()
        return [
            d.to_dict()
            for d in self._devices.values()
            if d.status in (DeviceStatus.ONLINE, DeviceStatus.RECORDING)
        ]

    def list_by_location(self) -> Dict[str, List[Dict]]:
        """Group devices by location."""
        self.check_timeouts()
        groups: Dict[str, List[Dict]] = {}
        for d in self._devices.values():
            loc = d.location_name or "Unknown"
            groups.setdefault(loc, []).append(d.to_dict())
        return groups

    def get_map_data(self) -> List[Dict]:
        """Get device data for map visualization."""
        self.check_timeouts()
        return [
            {
                "device_id": d.device_id,
                "name": d.name,
                "lat": d.latitude,
                "lng": d.longitude,
                "status": d.status.value,
                "location": d.location_name,
                "detections": d.total_detections,
            }
            for d in self._devices.values()
            if d.latitude != 0 or d.longitude != 0
        ]


import threading

_manager: Optional[DeviceManager] = None
_manager_lock = threading.Lock()


def get_device_manager() -> DeviceManager:
    global _manager
    if _manager is None:
        with _manager_lock:
            if _manager is None:
                _manager = DeviceManager()
    return _manager
