import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from device_manager import DeviceManager, DeviceStatus, DeviceType


class DeviceManagerTests(unittest.TestCase):
    def test_register_falls_back_to_generic_type_and_marks_online(self):
        manager = DeviceManager()

        device = manager.register(
            name="Field Unit 1",
            device_type="unsupported-type",
            location_name="nonggang",
            latitude=22.45,
            longitude=106.96,
        )

        self.assertEqual(device.device_type, DeviceType.GENERIC)
        self.assertEqual(device.status, DeviceStatus.ONLINE)
        self.assertEqual(manager.device_count, 1)
        self.assertEqual(manager.online_count, 1)

    def test_start_and_end_session_updates_status_and_active_session(self):
        manager = DeviceManager()
        device = manager.register(name="Field Unit 2", device_type="generic")

        session_id = manager.start_session(device.device_id)
        self.assertIsNotNone(session_id)
        self.assertEqual(manager.get_session(device.device_id), session_id)
        self.assertEqual(manager.get(device.device_id).status, DeviceStatus.RECORDING)

        finished_session = manager.end_session(device.device_id)
        self.assertEqual(finished_session, session_id)
        self.assertIsNone(manager.get_session(device.device_id))
        self.assertEqual(manager.get(device.device_id).status, DeviceStatus.ONLINE)

    def test_check_timeouts_marks_stale_devices_offline_and_clears_sessions(self):
        manager = DeviceManager()
        device = manager.register(name="Field Unit 3", device_type="generic")
        session_id = manager.start_session(device.device_id)

        stale_device = manager.get(device.device_id)
        stale_device.last_heartbeat -= manager.HEARTBEAT_TIMEOUT + 5
        manager.check_timeouts()

        self.assertEqual(stale_device.status, DeviceStatus.OFFLINE)
        self.assertIsNone(manager.get_session(device.device_id))
        self.assertNotEqual(session_id, manager.get_session(device.device_id))

    def test_get_map_data_only_returns_devices_with_coordinates(self):
        manager = DeviceManager()
        manager.register(
            name="Mapped Unit", device_type="generic", latitude=22.45, longitude=106.96
        )
        manager.register(name="Unmapped Unit", device_type="generic")

        map_data = manager.get_map_data()

        self.assertEqual(len(map_data), 1)
        self.assertEqual(map_data[0]["name"], "Mapped Unit")


if __name__ == "__main__":
    unittest.main()
