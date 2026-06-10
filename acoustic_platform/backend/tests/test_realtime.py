import asyncio
import sys
import unittest
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from realtime import MonitoringSession, RealtimeProcessor


class MonitoringSessionTests(unittest.TestCase):
    def test_feed_audio_returns_complete_segments_with_overlap_buffer(self):
        session = MonitoringSession(
            session_id="session-1",
            device_id="device-1",
            sample_rate=10,
            segment_duration=2.0,
            overlap=0.5,
        )

        first_chunk = np.arange(10, dtype=np.float32)
        second_chunk = np.arange(10, 20, dtype=np.float32)
        third_chunk = np.arange(20, 30, dtype=np.float32)

        self.assertEqual(session.feed_audio(first_chunk), [])
        self.assertEqual(len(session.feed_audio(second_chunk)), 1)
        self.assertEqual(len(session.feed_audio(third_chunk)), 1)


class RealtimeProcessorTests(unittest.IsolatedAsyncioTestCase):
    async def test_process_audio_generates_detections_and_notifies_listeners(self):
        processor = RealtimeProcessor()
        events = []

        processor.set_inference_pipeline(
            predict_fn=lambda mel_input, top_k=5: [
                {
                    "species_scientific": "Gorsachius magnificus",
                    "confidence": 0.88,
                    "species_chinese": "海南鳽",
                },
                {"species_scientific": "Noise", "confidence": 0.1},
            ],
            mel_fn=lambda segment, sr=22050: segment,
            norm_fn=lambda mel: mel,
        )

        session = processor.create_session(
            device_id="device-1",
            session_id="session-1",
            sample_rate=10,
            confidence_threshold=0.3,
        )
        session.segment_duration = 2.0
        session.__post_init__()

        processor.add_listener("session-1", lambda event: events.append(event))

        pcm = (np.ones(20, dtype=np.int16) * 1000).tobytes()
        detections = await processor.process_audio("session-1", pcm)

        self.assertEqual(len(detections), 1)
        self.assertEqual(detections[0]["species_scientific"], "Gorsachius magnificus")
        self.assertEqual(session.total_segments, 1)
        self.assertEqual(session.unique_species, 1)
        self.assertEqual(len(events), 1)
        self.assertEqual(
            events[0]["detections"][0]["species_scientific"], "Gorsachius magnificus"
        )

    async def test_process_audio_returns_empty_when_pipeline_missing(self):
        processor = RealtimeProcessor()
        processor.create_session(
            device_id="device-1", session_id="session-2", sample_rate=10
        )

        pcm = (np.ones(20, dtype=np.int16) * 1000).tobytes()
        detections = await processor.process_audio("session-2", pcm)

        self.assertEqual(detections, [])


if __name__ == "__main__":
    unittest.main()
