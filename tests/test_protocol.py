"""Comprehensive offline regression tests for Orchestra of Lights protocol & client."""

from __future__ import annotations

import asyncio
import importlib.util
import json
import struct
import sys
import types
import unittest
from pathlib import Path

PKG_DIR = Path(__file__).resolve().parent.parent / "custom_components" / "orchestra_of_lights"
PKG_NAME = "_ool_test_pkg"
if PKG_NAME not in sys.modules:
    pkg = types.ModuleType(PKG_NAME)
    pkg.__path__ = [str(PKG_DIR)]
    sys.modules[PKG_NAME] = pkg


def _load(name: str):
    full = f"{PKG_NAME}.{name}"
    if full in sys.modules:
        return sys.modules[full]
    spec = importlib.util.spec_from_file_location(full, PKG_DIR / f"{name}.py")
    assert spec and spec.loader
    mod = importlib.util.module_from_spec(spec)
    sys.modules[full] = mod
    spec.loader.exec_module(mod)
    return mod


const = _load("const")
client_mod = _load("client")


class TestOrchestraProtocol(unittest.TestCase):
    """Protocol parser, encoder, and table regression tests."""

    def test_normalize_hub_id(self) -> None:
        self.assertEqual(client_mod.normalize_hub_id("AA:BB:CC:DD:EE:FF"), "aabbccddeeff")
        self.assertEqual(client_mod.normalize_hub_id("aa-bb-cc-dd-ee-ff"), "aabbccddeeff")
        self.assertEqual(client_mod.normalize_hub_id("aabbccddeeff"), "aabbccddeeff")
        for bad in ("", "12345", "zzzzzzzzzzzz", "aa:bb:cc"):
            with self.assertRaises(ValueError):
                client_mod.normalize_hub_id(bad)

    def test_decode_group_name(self) -> None:
        self.assertEqual(client_mod._decode_group_name(b"\xff" * 12), "")
        self.assertEqual(
            client_mod._decode_group_name(b"FrontYard\xff\xff\xff"), "FrontYard"
        )
        self.assertEqual(client_mod._decode_group_name(b"Porch\x00\x00"), "Porch")

    def test_mqtt_varint_and_string(self) -> None:
        self.assertEqual(client_mod._mqtt_encode_len(0), b"\x00")
        self.assertEqual(client_mod._mqtt_encode_len(127), b"\x7f")
        self.assertEqual(client_mod._mqtt_encode_len(128), b"\x80\x01")
        self.assertEqual(client_mod._mqtt_encode_len(16384), b"\x80\x80\x01")
        self.assertEqual(client_mod._mqtt_str("MQTT"), b"\x00\x04MQTT")

    def test_cloud_message_parsing_and_color_mode_persistence(self) -> None:
        updates = []
        c = client_mod.OrchestraOfLightsClient(
            "aabbccddeeff", on_state_update=lambda s: updates.append(s.to_dict())
        )

        cmd_hub = {
            "length": "0000",
            "clientToken": "hub",
            "state": {
                "reported": {
                    "cmd": 1,
                    "change": "2,3,4",
                    "music_mode": 0,
                    "music_order": "0,3,5,1,9,7",
                    "music_order2": "0,3,5,1,9,7,4,6,255,255,255,255",
                    "music_song": 7,
                    "music_cmd": 1,
                    "volume": 45,
                    "lightshow": "34,2",
                    "color_rgb": "10,20,30",
                    "colorbrightness_x": 85,
                    "bt_on": 0,
                    "timer_on": 1,
                    "device_on": 1,
                    "timer_start": "17:0",
                    "timer_stop": "21:0",
                    "timerzone": "-8:0",
                }
            },
        }
        c._parse_cloud_message(
            "$aws/things/aabbccddeeff/cmd/hub", json.dumps(cmd_hub).encode()
        )
        self.assertTrue(c.state.power)
        self.assertEqual(c.state.theme, 34)
        self.assertEqual(c.state.theme_name, "Red & Green")
        self.assertEqual(c.state.effect, 2)
        self.assertEqual(c.state.effect_name, "Sparkle")
        self.assertEqual(c.state.rgb, (10, 20, 30))
        self.assertEqual(c.state.brightness, 85)
        self.assertEqual(c.state.volume, 45)
        self.assertEqual(c.state.song_name, "Feliz Navidad")
        self.assertEqual(c.state.music_playlist, [0, 3, 5, 1, 9, 7, 4, 6])
        self.assertEqual(c.state.timer_start, "17:00")
        self.assertEqual(c.state.timer_stop, "21:00")

        # Regression check: RGB mode must not be overwritten back to "theme" by hub poll cmd=1
        c.state.color_mode = "rgb"
        cmd_hub["state"]["reported"]["color_rgb"] = "0,128,255"
        c._parse_cloud_message(
            "$aws/things/aabbccddeeff/cmd/hub", json.dumps(cmd_hub).encode()
        )
        self.assertEqual(c.state.color_mode, "rgb")
        self.assertEqual(c.state.rgb, (0, 128, 255))

        # Parse /devicelist (new 7-byte format)
        dev_list = {
            "state": {
                "reported": {
                    "device_num": 2,
                    "new_device_list": "2300112233440120005566778802",
                    "group": "eeff",
                    "group_name": "ffffffffffffffffffffffff",
                }
            }
        }
        c._parse_cloud_message(
            "$aws/things/aabbccddeeff/devicelist", json.dumps(dev_list).encode()
        )
        self.assertEqual(len(c.state.devices), 2)
        self.assertEqual(c.state.devices[0].name, "Curtain Light Op. 2")
        self.assertEqual(c.state.devices[1].name, "Virtuoso Speaker Op. 2")
        self.assertTrue(c.state.has_op2_speaker)

        # Parse /pw & /rssi
        pw_msg = {
            "state": {
                "reported": {
                    "pw_on": 0,
                    "hub_ver": "050803",
                    "ssid": "TestWiFi",
                    "24g_ver": 4,
                }
            }
        }
        c._parse_cloud_message(
            "$aws/things/aabbccddeeff/pw", json.dumps(pw_msg).encode()
        )
        self.assertEqual(c.state.hub_ver, "5.8.3")
        self.assertEqual(c.state.rf_ver, 4)
        self.assertEqual(c.state.ssid, "TestWiFi")

        c._parse_cloud_message(
            "$aws/things/aabbccddeeff/rssi",
            json.dumps({"state": {"reported": {"hub_rssi": -61}}}).encode(),
        )
        self.assertEqual(c.state.rssi, -61)
        self.assertGreaterEqual(len(updates), 4)

    def test_local_binary_packet_parsing(self) -> None:
        c = client_mod.OrchestraOfLightsClient("aabbccddeeff")

        # 0xA6 sub=1: 43-byte full state packet
        pkt = bytearray(43)
        pkt[0] = 41
        pkt[2] = 0xA6
        pkt[3] = 1
        pkt[5] = 1  # random mode
        pkt[6] = 1  # playing
        pkt[7] = 2  # Bell Carol
        pkt[8] = 60  # volume
        pkt[9:15] = bytes([0, 1, 2, 3, 255, 255])
        pkt[15] = 1  # Rainbow Wave
        pkt[16] = 4  # Lightshow
        pkt[17:20] = bytes([255, 100, 50])
        pkt[20] = 1  # timer_on
        pkt[21:25] = bytes([17, 30, 22, 0])
        pkt[34] = 80  # brightness
        pkt[35] = 1  # power ON
        pkt[36] = 1  # bt ON
        pkt[37:43] = bytes([6, 7, 255, 255, 255, 255])
        c._parse_local_packet(bytes(pkt))

        self.assertTrue(c.state.power)
        self.assertEqual(c.state.theme, 1)
        self.assertEqual(c.state.effect, 4)
        self.assertEqual(c.state.rgb, (255, 100, 50))
        self.assertEqual(c.state.brightness, 80)
        self.assertEqual(c.state.volume, 60)
        self.assertEqual(c.state.music_song, 2)
        self.assertEqual(c.state.music_playlist, [0, 1, 2, 3, 6, 7])
        self.assertTrue(c.state.bt_on)
        self.assertEqual(c.state.timer_start, "17:30")
        self.assertEqual(c.state.timer_stop, "22:00")

        # 0xA6 sub=2: version
        c._parse_local_packet(bytes([6, 0, 0xA6, 2, 5, 8, 3, 4]))
        self.assertEqual(c.state.hub_ver, "5.8.3")
        self.assertEqual(c.state.rf_ver, 4)

        # 0xA6 sub=10: signed RSSI (-59 = 0xC5)
        c._parse_local_packet(bytes([3, 0, 0xA6, 10, 0xC5]))
        self.assertEqual(c.state.rssi, -59)

    def test_cloud_publish_framing_and_commands(self) -> None:
        c = client_mod.OrchestraOfLightsClient("aabbccddeeff")
        c.state.connected = True
        c.state.transport = const.TRANSPORT_CLOUD
        c._cred_expiry = 9999999999.0

        sent_frames: list[bytes] = []

        async def fake_ws_send(payload: bytes, opcode: int = 0x82) -> None:
            sent_frames.append(payload)

        c._ws_send = fake_ws_send  # type: ignore[method-assign]

        async def run_cmds() -> None:
            await c.set_power(True)
            await c.set_theme(34, 2)
            await c.set_rgb(12, 34, 56, 70)
            await c.play_song(7)
            await c.set_volume(45)
            await c.set_bluetooth(True)
            await c.set_timer(False, 17, 0, 21, 0)

        asyncio.run(run_cmds())
        self.assertEqual(len(sent_frames), 7)

        # Verify every MQTT PUBLISH frame has exact little-endian hex byte length
        for frame in sent_frames:
            self.assertEqual(frame[0] & 0xF0, 0x30)
            idx = 1
            while frame[idx] & 0x80:
                idx += 1
            idx += 1
            tlen = struct.unpack("!H", frame[idx : idx + 2])[0]
            topic = frame[idx + 2 : idx + 2 + tlen].decode()
            body = frame[idx + 2 + tlen :].decode()
            self.assertTrue(topic.startswith("$aws/things/aabbccddeeff/"))
            doc = json.loads(body)
            expected_hex = f"{len(body):04X}"
            expected_le = expected_hex[2:4] + expected_hex[0:2]
            self.assertEqual(doc["length"], expected_le)

    def test_local_binary_command_encoding(self) -> None:
        c = client_mod.OrchestraOfLightsClient("aabbccddeeff")
        c.state.connected = True
        c.state.transport = const.TRANSPORT_LOCAL

        sent_pkts: list[bytes] = []

        async def fake_local_send(data: bytes) -> None:
            sent_pkts.append(data)

        c._local_send = fake_local_send  # type: ignore[method-assign]

        async def run_cmds() -> None:
            await c.set_power(True)
            await c.set_theme(0, 4)
            await c.set_rgb(255, 0, 128, 80)
            await c.play_song(2)
            await c.pause_music()
            await c.resume_music()
            await c.set_volume(45)

        asyncio.run(run_cmds())
        self.assertEqual(sent_pkts[0], bytes([3, 0, 0xA6, 9, 1]))
        self.assertEqual(sent_pkts[1], bytes([11, 0, 0xAA, 0, 0, 2, 0, 4, 0, 0, 0, 0, 0]))
        self.assertEqual(sent_pkts[2], bytes([11, 0, 0xAA, 0, 0, 3, 255, 0, 128, 0, 0, 0, 80]))
        self.assertEqual(sent_pkts[3], bytes([11, 0, 0xAA, 0, 0, 1, 1, 2, 0, 0, 0, 0, 0]))
        self.assertEqual(sent_pkts[4], bytes([11, 0, 0xAA, 0, 0, 1, 2, 0, 0, 0, 0, 0, 0]))
        self.assertEqual(sent_pkts[5], bytes([11, 0, 0xAA, 0, 0, 1, 3, 0, 0, 0, 0, 0, 0]))
        self.assertEqual(sent_pkts[6], bytes([11, 0, 0xAA, 0, 0, 1, 4, 45, 45, 0, 0, 0, 0]))

    def test_theme_effect_song_tables(self) -> None:
        self.assertEqual(len(const.THEMES), 44)
        self.assertEqual(len(const.EFFECTS), 5)
        self.assertEqual(len(const.SONGS), 12)
        self.assertEqual(len(const.THEME_NAME_TO_ID), len(const.THEMES))
        self.assertEqual(len(const.SONG_NAME_TO_ID), len(const.SONGS))
        self.assertIn(32, const.OP2_SPEAKER_IDS)


if __name__ == "__main__":
    unittest.main()
