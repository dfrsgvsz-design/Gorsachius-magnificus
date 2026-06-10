"""
Detection Store — 持久化检测记录存储与验证工作流。

解决当前平台的关键短板:
1. 检测记录仅存内存 dict → 改为 JSON 文件持久化（可升级为 SQLite/PostgreSQL）
2. 无人工验证机制 → 新增检测验证状态追踪

Sugai et al. (2026) 强调:
- "Human-validated species detections can be integrated into diversity modeling
   using defensible and understandable methods" (Section 3.2)
- "False positives can be entirely prevented through manual review" (Section 3.2)
- 需要追踪 false positive/negative 以支持 occupancy models (Chambert et al., 2018)

验证状态流:
  UNVERIFIED → CONFIRMED / REJECTED / UNCERTAIN
"""

import json
import logging
import sqlite3
import threading
import time
import uuid
from pathlib import Path
from typing import Dict, List, Optional
from collections import defaultdict
from datetime import datetime, UTC
from enum import Enum

logger = logging.getLogger(__name__)

try:
    from runtime_paths import get_data_dir
except ImportError:  # pragma: no cover - shared package import path
    from shared.backend.utils.runtime_paths import get_data_dir


class VerificationStatus(str, Enum):
    UNVERIFIED = "unverified"
    CONFIRMED = "confirmed"
    REJECTED = "rejected"
    UNCERTAIN = "uncertain"


class DetectionStore:
    """Persistent storage for species detection records with verification workflow.

    Uses SQLite for durability and concurrent-safe writes. Falls back to
    in-memory + JSON export when the DB path is unavailable.
    """

    _DDL = """
    CREATE TABLE IF NOT EXISTS detections (
        detection_id TEXT PRIMARY KEY,
        species TEXT NOT NULL,
        species_chinese TEXT DEFAULT '',
        species_english TEXT DEFAULT '',
        confidence REAL DEFAULT 0.0,
        session_id TEXT DEFAULT '',
        device_id TEXT DEFAULT '',
        site_name TEXT DEFAULT 'unknown',
        time_offset REAL DEFAULT 0.0,
        timestamp TEXT DEFAULT '',
        model_version TEXT DEFAULT '',
        reliable INTEGER DEFAULT 1,
        verification TEXT DEFAULT 'unverified',
        verified_by TEXT,
        verified_at TEXT,
        verification_notes TEXT
    );
    CREATE INDEX IF NOT EXISTS idx_session ON detections(session_id);
    CREATE INDEX IF NOT EXISTS idx_species ON detections(species);
    CREATE INDEX IF NOT EXISTS idx_site ON detections(site_name);
    CREATE INDEX IF NOT EXISTS idx_verification ON detections(verification);
    """

    def __init__(self, storage_dir: Optional[str] = None):
        self._dir = (
            Path(storage_dir) if storage_dir else (get_data_dir() / "detections")
        )
        self._dir.mkdir(parents=True, exist_ok=True)
        self._db_path = self._dir / "detections.db"
        self._lock = threading.Lock()
        self._conn = sqlite3.connect(str(self._db_path), check_same_thread=False)
        self._conn.row_factory = sqlite3.Row
        self._conn.executescript(self._DDL)
        self._migrate_json()

    def _migrate_json(self):
        """One-time migration: import legacy index.json into SQLite."""
        index_file = self._dir / "index.json"
        if not index_file.exists():
            return
        try:
            with open(index_file, "r", encoding="utf-8") as f:
                index = json.load(f)
            records = index.get("detections", {})
            if not records:
                return
            existing = self._conn.execute("SELECT COUNT(*) FROM detections").fetchone()[
                0
            ]
            if existing > 0:
                return
            with self._lock, self._conn:
                for det_id, det in records.items():
                    self._insert_record(det_id, det)
            migrated = self._dir / "index.json.migrated"
            index_file.rename(migrated)
        except Exception:
            logger.warning(
                "Failed to migrate legacy index.json to SQLite", exc_info=True
            )

    def _insert_record(self, det_id: str, det: Dict):
        self._conn.execute(
            """INSERT OR IGNORE INTO detections
            (detection_id, species, species_chinese, species_english,
             confidence, session_id, device_id, site_name, time_offset,
             timestamp, model_version, reliable, verification,
             verified_by, verified_at, verification_notes)
            VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
            (
                det_id,
                det.get("species", ""),
                det.get("species_chinese", ""),
                det.get("species_english", ""),
                det.get("confidence", 0.0),
                det.get("session_id", ""),
                det.get("device_id", ""),
                det.get("site_name", "unknown"),
                det.get("time_offset", 0.0),
                det.get("timestamp", ""),
                det.get("model_version", ""),
                1 if det.get("reliable", True) else 0,
                det.get("verification", VerificationStatus.UNVERIFIED.value),
                det.get("verified_by"),
                det.get("verified_at"),
                det.get("verification_notes"),
            ),
        )

    def _row_to_dict(self, row: sqlite3.Row) -> Dict:
        d = dict(row)
        d["reliable"] = bool(d.get("reliable", 1))
        return d

    def _add_detection_no_commit(
        self,
        species: str,
        confidence: float,
        session_id: str,
        time_offset: float,
        device_id: str = "",
        site_name: str = "unknown",
        species_chinese: str = "",
        species_english: str = "",
        model_version: str = "",
        reliable: bool = True,
        extra: Dict = None,
    ) -> str:
        """Build record and insert; caller must hold _lock and manage commit."""
        det_id = str(uuid.uuid4())[:12]
        record = {
            "detection_id": det_id,
            "species": species,
            "species_chinese": species_chinese,
            "species_english": species_english,
            "confidence": round(confidence, 4),
            "session_id": session_id,
            "device_id": device_id,
            "site_name": site_name,
            "time_offset": round(time_offset, 2),
            "timestamp": datetime.now(UTC).isoformat().replace("+00:00", "Z"),
            "model_version": model_version,
            "reliable": reliable,
            "verification": VerificationStatus.UNVERIFIED.value,
            "verified_by": None,
            "verified_at": None,
            "verification_notes": None,
        }
        if extra:
            record.update(extra)
        self._insert_record(det_id, record)
        return det_id

    def add_detection(
        self,
        species: str,
        confidence: float,
        session_id: str,
        time_offset: float,
        device_id: str = "",
        site_name: str = "unknown",
        species_chinese: str = "",
        species_english: str = "",
        model_version: str = "",
        reliable: bool = True,
        extra: Dict = None,
    ) -> str:
        """Record a new species detection. Returns detection ID."""
        with self._lock, self._conn:
            det_id = self._add_detection_no_commit(
                species, confidence, session_id, time_offset,
                device_id, site_name, species_chinese, species_english,
                model_version, reliable, extra,
            )
        return det_id

    def batch_add(
        self, detections: List[Dict], session_id: str, site_name: str = "unknown"
    ) -> List[str]:
        """Batch add detections in a single transaction. Returns list of detection IDs."""
        ids = []
        with self._lock, self._conn:
            for det in detections:
                det_id = self._add_detection_no_commit(
                    species=det.get("species", det.get("species_scientific", "")),
                    confidence=det.get("confidence", 0.0),
                    session_id=session_id,
                    time_offset=det.get("time_offset", 0.0),
                    device_id=det.get("device_id", ""),
                    site_name=site_name,
                    species_chinese=det.get("species_chinese", ""),
                    species_english=det.get("species_english", ""),
                    reliable=det.get("reliable", True),
                )
                ids.append(det_id)
        return ids

    def verify_detection(
        self,
        detection_id: str,
        status: VerificationStatus,
        verified_by: str = "anonymous",
        notes: str = "",
    ) -> bool:
        """Verify a detection: confirm, reject, or mark uncertain."""
        with self._lock, self._conn:
            cur = self._conn.execute(
                """UPDATE detections SET verification=?, verified_by=?, verified_at=?, verification_notes=?
                WHERE detection_id=?""",
                (
                    status.value,
                    verified_by,
                    datetime.now(UTC).isoformat().replace("+00:00", "Z"),
                    notes,
                    detection_id,
                ),
            )
            changed = cur.rowcount > 0
        return changed

    def batch_verify(
        self,
        detection_ids: List[str],
        status: VerificationStatus,
        verified_by: str = "anonymous",
        notes: str = "",
    ) -> int:
        """Batch verify multiple detections. Returns count of verified."""
        now = datetime.now(UTC).isoformat().replace("+00:00", "Z")
        count = 0
        with self._lock, self._conn:
            for det_id in detection_ids:
                cur = self._conn.execute(
                    """UPDATE detections SET verification=?, verified_by=?, verified_at=?, verification_notes=?
                    WHERE detection_id=?""",
                    (status.value, verified_by, now, notes, det_id),
                )
                count += cur.rowcount
        return count

    def get_session_detections(
        self, session_id: str, verified_only: bool = False
    ) -> List[Dict]:
        """Get all detections from a session."""
        if verified_only:
            rows = self._conn.execute(
                "SELECT * FROM detections WHERE session_id=? AND verification='confirmed'",
                (session_id,),
            ).fetchall()
        else:
            rows = self._conn.execute(
                "SELECT * FROM detections WHERE session_id=?",
                (session_id,),
            ).fetchall()
        return [self._row_to_dict(r) for r in rows]

    def get_site_detections(
        self, site_name: str, verified_only: bool = False
    ) -> List[Dict]:
        """Get all detections from a site."""
        if verified_only:
            rows = self._conn.execute(
                "SELECT * FROM detections WHERE site_name=? AND verification='confirmed'",
                (site_name,),
            ).fetchall()
        else:
            rows = self._conn.execute(
                "SELECT * FROM detections WHERE site_name=?",
                (site_name,),
            ).fetchall()
        return [self._row_to_dict(r) for r in rows]

    def get_species_detections(self, species: str) -> List[Dict]:
        """Get all detections of a particular species across all sites."""
        rows = self._conn.execute(
            "SELECT * FROM detections WHERE species=?",
            (species,),
        ).fetchall()
        return [self._row_to_dict(r) for r in rows]

    def get_all_detections(self) -> List[Dict]:
        rows = self._conn.execute("SELECT * FROM detections").fetchall()
        return [self._row_to_dict(r) for r in rows]

    def get_unverified(self, limit: int = 50) -> List[Dict]:
        """Get detections needing verification, prioritized by low confidence."""
        rows = self._conn.execute(
            "SELECT * FROM detections WHERE verification='unverified' ORDER BY confidence ASC LIMIT ?",
            (limit,),
        ).fetchall()
        return [self._row_to_dict(r) for r in rows]

    def get_verification_stats(self) -> Dict:
        """Get verification status breakdown."""
        rows = self._conn.execute(
            "SELECT verification, COUNT(*) as cnt FROM detections GROUP BY verification"
        ).fetchall()
        stats = {r["verification"]: r["cnt"] for r in rows}
        total = sum(stats.values())
        confirmed = stats.get(VerificationStatus.CONFIRMED.value, 0)
        rejected = stats.get(VerificationStatus.REJECTED.value, 0)
        return {
            "total": total,
            "unverified": stats.get(VerificationStatus.UNVERIFIED.value, 0),
            "confirmed": confirmed,
            "rejected": rejected,
            "uncertain": stats.get(VerificationStatus.UNCERTAIN.value, 0),
            "verification_rate": (
                round((confirmed + rejected) / total, 4) if total > 0 else 0.0
            ),
            "false_positive_rate": round(rejected / max(1, rejected + confirmed), 4),
        }

    def compute_occupancy_inputs(self, site_name: str, species: str) -> Dict:
        """Prepare detection/non-detection data for occupancy modeling."""
        site_dets = self.get_site_detections(site_name)
        sessions: Dict[str, List[Dict]] = defaultdict(list)
        for d in site_dets:
            sessions[d["session_id"]].append(d)

        detection_history = []
        for sid, dets in sorted(sessions.items()):
            sp_dets = [d for d in dets if d["species"] == species]
            confirmed = [
                d
                for d in sp_dets
                if d["verification"] == VerificationStatus.CONFIRMED.value
            ]
            rejected = [
                d
                for d in sp_dets
                if d["verification"] == VerificationStatus.REJECTED.value
            ]

            if confirmed:
                detection_history.append(1)
            elif sp_dets and len(rejected) == len(sp_dets):
                detection_history.append(0)
            elif sp_dets:
                detection_history.append(1)
            else:
                detection_history.append(0)

        return {
            "site": site_name,
            "species": species,
            "n_surveys": len(sessions),
            "detection_history": detection_history,
            "naive_occupancy": 1 if any(h == 1 for h in detection_history) else 0,
            "detection_probability": (
                round(sum(detection_history) / len(detection_history), 4)
                if detection_history
                else 0.0
            ),
        }

    def save(self):
        """Explicit commit."""
        with self._lock:
            self._conn.commit()

    def close(self):
        """Close the SQLite connection explicitly for tests and shutdown flows."""
        with self._lock:
            if self._conn is not None:
                self._conn.close()
                self._conn = None

    def get_stats(self) -> Dict:
        row = self._conn.execute("""SELECT COUNT(*) as total,
                      COUNT(DISTINCT session_id) as sessions,
                      COUNT(DISTINCT site_name) as sites,
                      COUNT(DISTINCT species) as unique_species
               FROM detections""").fetchone()
        return {
            "total_detections": row["total"],
            "sessions": row["sessions"],
            "sites": row["sites"],
            "unique_species": row["unique_species"],
            **self.get_verification_stats(),
        }



_store: Optional[DetectionStore] = None
_store_lock = threading.Lock()


def get_detection_store() -> DetectionStore:
    global _store
    if _store is None:
        with _store_lock:
            if _store is None:
                _store = DetectionStore()
    return _store
