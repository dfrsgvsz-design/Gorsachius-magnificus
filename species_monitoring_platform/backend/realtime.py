"""
Real-time Audio Stream Processing — WebSocket端点接入野外采集设备。

工作流:
1. 设备通过 WebSocket 连接并发送PCM音频帧
2. 服务端缓冲音频数据至3秒窗口(可配置)
3. 每个窗口生成mel频谱图 → CNN推理 → 物种检测
4. 检测结果实时推送到前端仪表盘
5. 累积统计物种丰富度和多样性指标

音频格式:
- PCM 16-bit signed, little-endian
- 单声道 (mono)
- 采样率: 22050Hz (默认)
- 每帧大小: 可变 (推荐4096 samples = ~186ms)
"""

import asyncio
import json
import time
import numpy as np
from collections import defaultdict
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Callable, Any
from datetime import datetime, UTC


@dataclass
class MonitoringSession:
    """A real-time monitoring session from a device."""

    session_id: str
    device_id: str
    start_time: float = field(default_factory=time.time)
    sample_rate: int = 22050
    segment_duration: float = 3.0
    overlap: float = 0.5
    confidence_threshold: float = 0.3
    # Accumulated state
    total_segments: int = 0
    all_detections: List[Dict] = field(default_factory=list)
    species_counts: Dict[str, int] = field(default_factory=lambda: defaultdict(int))
    species_first_seen: Dict[str, float] = field(default_factory=dict)
    # Audio buffer
    _buffer: np.ndarray = field(default=None, repr=False)
    _buffer_pos: int = 0
    is_active: bool = True

    def __post_init__(self):
        buf_size = int(self.sample_rate * self.segment_duration)
        self._buffer = np.zeros(buf_size, dtype=np.float32)
        self._buffer_pos = 0

    @property
    def duration_seconds(self) -> float:
        return time.time() - self.start_time

    @property
    def unique_species(self) -> int:
        return len(self.species_counts)

    @property
    def total_detections_count(self) -> int:
        return len(self.all_detections)

    def feed_audio(self, pcm_data: np.ndarray) -> List[np.ndarray]:
        """
        Feed PCM audio samples into the buffer.
        Returns list of complete segments ready for analysis.
        """
        segments = []
        segment_size = len(self._buffer)
        hop_size = int(segment_size * (1 - self.overlap))

        pos = 0
        while pos < len(pcm_data):
            space = segment_size - self._buffer_pos
            chunk = pcm_data[pos : pos + space]
            self._buffer[self._buffer_pos : self._buffer_pos + len(chunk)] = chunk
            self._buffer_pos += len(chunk)
            pos += len(chunk)

            if self._buffer_pos >= segment_size:
                segments.append(self._buffer.copy())
                # Shift buffer for overlap
                overlap_samples = segment_size - hop_size
                self._buffer[:overlap_samples] = self._buffer[hop_size:]
                self._buffer_pos = overlap_samples

        return segments

    def add_detection(
        self, species: str, confidence: float, segment_time: float, extra: Dict = None
    ):
        """Record a species detection."""
        detection = {
            "species": species,
            "confidence": round(confidence, 4),
            "time_offset": round(segment_time, 2),
            "timestamp": datetime.now(UTC).isoformat().replace("+00:00", "Z"),
        }
        if extra:
            detection.update(extra)
        self.all_detections.append(detection)
        self.species_counts[species] += 1
        if species not in self.species_first_seen:
            self.species_first_seen[species] = segment_time

    def get_summary(self) -> Dict:
        """Get current session summary."""
        return {
            "session_id": self.session_id,
            "device_id": self.device_id,
            "duration_seconds": round(self.duration_seconds, 1),
            "total_segments": self.total_segments,
            "total_detections": self.total_detections_count,
            "unique_species": self.unique_species,
            "species_counts": dict(self.species_counts),
            "species_timeline": [
                {"species": sp, "first_seen": round(t, 2)}
                for sp, t in sorted(self.species_first_seen.items(), key=lambda x: x[1])
            ],
            "is_active": self.is_active,
        }

    def get_accumulation_data(self) -> Dict:
        """Get species accumulation curve data."""
        if not self.all_detections:
            return {"time_points": [], "cumulative_species": []}

        sorted_dets = sorted(self.all_detections, key=lambda d: d["time_offset"])
        seen = set()
        time_points = []
        cumulative = []

        for det in sorted_dets:
            seen.add(det["species"])
            time_points.append(det["time_offset"])
            cumulative.append(len(seen))

        return {
            "time_points": time_points,
            "cumulative_species": cumulative,
        }


class RealtimeProcessor:
    """
    Manages multiple concurrent monitoring sessions.
    Processes audio segments and dispatches detection results.
    """

    def __init__(self):
        self._sessions: Dict[str, MonitoringSession] = {}
        self._listeners: Dict[str, List[Callable]] = defaultdict(list)
        # Inference function will be set by main.py
        self._predict_fn: Optional[Callable] = None
        self._mel_fn: Optional[Callable] = None
        self._norm_fn: Optional[Callable] = None
        self._use_dual_channel: bool = False
        self._dual_mel_fn: Optional[Callable] = None

    def set_inference_pipeline(
        self, predict_fn, mel_fn, norm_fn, use_dual_channel=False, dual_mel_fn=None
    ):
        """Set the inference functions from the main app."""
        self._predict_fn = predict_fn
        self._mel_fn = mel_fn
        self._norm_fn = norm_fn
        self._use_dual_channel = use_dual_channel
        self._dual_mel_fn = dual_mel_fn

    def create_session(
        self,
        device_id: str,
        session_id: str,
        sample_rate: int = 22050,
        confidence_threshold: float = 0.3,
    ) -> MonitoringSession:
        """Create a new monitoring session."""
        session = MonitoringSession(
            session_id=session_id,
            device_id=device_id,
            sample_rate=sample_rate,
            confidence_threshold=confidence_threshold,
        )
        self._sessions[session_id] = session
        return session

    def get_session(self, session_id: str) -> Optional[MonitoringSession]:
        return self._sessions.get(session_id)

    def end_session(self, session_id: str) -> Optional[Dict]:
        """End session and return final summary."""
        session = self._sessions.get(session_id)
        if not session:
            return None
        session.is_active = False
        summary = session.get_summary()
        return summary

    def remove_session(self, session_id: str):
        self._sessions.pop(session_id, None)
        self._listeners.pop(session_id, None)

    def list_sessions(self) -> List[Dict]:
        return [s.get_summary() for s in self._sessions.values()]

    def add_listener(self, session_id: str, callback: Callable):
        """Add a listener for detection events on a session."""
        self._listeners[session_id].append(callback)

    def remove_listener(self, session_id: str, callback: Callable):
        if session_id in self._listeners:
            self._listeners[session_id] = [
                cb for cb in self._listeners[session_id] if cb != callback
            ]

    async def process_audio(self, session_id: str, pcm_bytes: bytes) -> List[Dict]:
        """
        Process incoming audio bytes from a device.
        Returns list of new detections (if any).
        """
        session = self._sessions.get(session_id)
        if not session or not session.is_active:
            return []

        if not all([self._predict_fn, self._mel_fn, self._norm_fn]):
            return []

        # Convert PCM bytes to float32 samples
        pcm_array = (
            np.frombuffer(pcm_bytes, dtype=np.int16).astype(np.float32) / 32768.0
        )

        # Feed into buffer and get complete segments
        segments = session.feed_audio(pcm_array)
        new_detections = []

        for seg in segments:
            session.total_segments += 1
            segment_time = session.duration_seconds

            if self._use_dual_channel and self._dual_mel_fn:
                mel_input = self._dual_mel_fn(seg, sr=session.sample_rate)
            else:
                mel = self._mel_fn(seg, sr=session.sample_rate)
                mel_input = self._norm_fn(mel)

            predictions = self._predict_fn(mel_input, top_k=5)

            # Filter by confidence threshold
            for pred in predictions:
                if pred["confidence"] >= session.confidence_threshold:
                    session.add_detection(
                        species=pred["species_scientific"],
                        confidence=pred["confidence"],
                        segment_time=segment_time,
                        extra={
                            "species_chinese": pred.get("species_chinese", ""),
                            "species_english": pred.get("species_english", ""),
                        },
                    )
                    new_detections.append(
                        {
                            **pred,
                            "time_offset": round(segment_time, 2),
                            "session_id": session_id,
                        }
                    )

        # Notify listeners
        if new_detections:
            await self._notify_listeners(session_id, new_detections, session)

        return new_detections

    async def _notify_listeners(
        self, session_id: str, detections: List[Dict], session: MonitoringSession
    ):
        """Notify all listeners of new detections."""
        event = {
            "type": "detection",
            "session_id": session_id,
            "detections": detections,
            "summary": session.get_summary(),
            "accumulation": session.get_accumulation_data(),
        }
        for callback in self._listeners.get(session_id, []):
            try:
                if asyncio.iscoroutinefunction(callback):
                    await callback(event)
                else:
                    callback(event)
            except Exception as e:
                import logging

                logging.getLogger("bird_platform").error("Listener error: %s", e)


import threading

_processor: Optional[RealtimeProcessor] = None
_processor_lock = threading.Lock()


def get_realtime_processor() -> RealtimeProcessor:
    global _processor
    if _processor is None:
        with _processor_lock:
            if _processor is None:
                _processor = RealtimeProcessor()
    return _processor
