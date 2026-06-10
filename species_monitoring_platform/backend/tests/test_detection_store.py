import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from detection_store import DetectionStore, VerificationStatus


class DetectionStoreTests(unittest.TestCase):
    def test_compute_occupancy_treats_fully_rejected_session_as_non_detection(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            store = DetectionStore(storage_dir=temp_dir)
            try:
                confirmed_id = store.add_detection(
                    species="Gorsachius magnificus",
                    confidence=0.92,
                    session_id="session-a",
                    time_offset=3.0,
                    site_name="nonggang",
                )
                rejected_id = store.add_detection(
                    species="Gorsachius magnificus",
                    confidence=0.31,
                    session_id="session-b",
                    time_offset=8.0,
                    site_name="nonggang",
                )
                uncertain_id = store.add_detection(
                    species="Gorsachius magnificus",
                    confidence=0.44,
                    session_id="session-c",
                    time_offset=12.0,
                    site_name="nonggang",
                )

                store.verify_detection(
                    confirmed_id, VerificationStatus.CONFIRMED, verified_by="tester"
                )
                store.verify_detection(
                    rejected_id, VerificationStatus.REJECTED, verified_by="tester"
                )
                store.verify_detection(
                    uncertain_id, VerificationStatus.UNCERTAIN, verified_by="tester"
                )

                occupancy = store.compute_occupancy_inputs(
                    "nonggang", "Gorsachius magnificus"
                )

                self.assertEqual(occupancy["n_surveys"], 3)
                self.assertEqual(occupancy["detection_history"], [1, 0, 1])
                self.assertEqual(occupancy["naive_occupancy"], 1)
                self.assertAlmostEqual(
                    occupancy["detection_probability"], 2 / 3, places=4
                )
            finally:
                store.close()

    def test_get_unverified_is_sorted_by_lowest_confidence_first(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            store = DetectionStore(storage_dir=temp_dir)
            try:
                low_id = store.add_detection(
                    species="Species A",
                    confidence=0.11,
                    session_id="session-1",
                    time_offset=1.0,
                    site_name="site-1",
                )
                mid_id = store.add_detection(
                    species="Species B",
                    confidence=0.45,
                    session_id="session-1",
                    time_offset=2.0,
                    site_name="site-1",
                )
                high_id = store.add_detection(
                    species="Species C",
                    confidence=0.87,
                    session_id="session-1",
                    time_offset=3.0,
                    site_name="site-1",
                )

                records = store.get_unverified(limit=10)

                self.assertEqual(
                    [record["detection_id"] for record in records],
                    [low_id, mid_id, high_id],
                )
            finally:
                store.close()

    def test_batch_add_preserves_session_and_site_stats(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            store = DetectionStore(storage_dir=temp_dir)
            try:
                ids = store.batch_add(
                    [
                        {
                            "species": "Species A",
                            "confidence": 0.8,
                            "time_offset": 1.0,
                            "device_id": "dev-1",
                        },
                        {
                            "species": "Species B",
                            "confidence": 0.7,
                            "time_offset": 2.0,
                            "device_id": "dev-1",
                        },
                    ],
                    session_id="session-x",
                    site_name="site-x",
                )
                stats = store.get_stats()
                session_records = store.get_session_detections("session-x")

                self.assertEqual(len(ids), 2)
                self.assertEqual(stats["total_detections"], 2)
                self.assertEqual(stats["sessions"], 1)
                self.assertEqual(stats["sites"], 1)
                self.assertEqual(len(session_records), 2)
            finally:
                store.close()

    def test_batch_verify_persists_reviewer_and_notes(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            store = DetectionStore(storage_dir=temp_dir)
            try:
                first_id = store.add_detection(
                    species="Species A",
                    confidence=0.22,
                    session_id="session-review",
                    time_offset=1.0,
                    site_name="site-review",
                )
                second_id = store.add_detection(
                    species="Species B",
                    confidence=0.28,
                    session_id="session-review",
                    time_offset=2.0,
                    site_name="site-review",
                )

                updated = store.batch_verify(
                    [first_id, second_id],
                    VerificationStatus.REJECTED,
                    verified_by="reviewer-a",
                    notes="shared batch note",
                )
                rows = store.get_session_detections("session-review")

                self.assertEqual(updated, 2)
                self.assertEqual(
                    {row["verification"] for row in rows},
                    {VerificationStatus.REJECTED.value},
                )
                self.assertEqual({row["verified_by"] for row in rows}, {"reviewer-a"})
                self.assertEqual(
                    {row["verification_notes"] for row in rows}, {"shared batch note"}
                )
            finally:
                store.close()


if __name__ == "__main__":
    unittest.main()
