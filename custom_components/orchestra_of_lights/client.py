"""Zero-dependency async client for Gemmy Orchestra of Lights Hub.

Supports both:
  1. Local LAN binary TCP protocol (port 8087) + UDP discovery (port 8087)
  2. AWS IoT Core MQTT over WebSocket (unauthenticated Cognito Identity Pool)
"""

from __future__ import annotations

import asyncio
import base64
import datetime
import hashlib
import hmac
import json
import logging
import os
import socket
import ssl
import struct
import time
import urllib.parse
import uuid
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any

from .const import (
    AWS_COGNITO_POOL_ID,
    AWS_COGNITO_REGION,
    AWS_IOT_ENDPOINT,
    AWS_IOT_REGION,
    DEFAULT_PORT,
    DEVICE_TYPES,
    EFFECTS,
    OP2_SPEAKER_IDS,
    PRESET_LIGHTSHOWS,
    SOLID_COLOR_THEMES,
    SONGS,
    THEMES,
    TRANSPORT_AUTO,
    TRANSPORT_CLOUD,
    TRANSPORT_LOCAL,
)

_LOGGER = logging.getLogger(__name__)


def normalize_hub_id(hub_id: str) -> str:
    """Normalize a MAC / Hub ID string to 12 lowercase hex characters."""
    cleaned = "".join(c for c in hub_id.strip().lower() if c in "0123456789abcdef")
    if len(cleaned) != 12:
        raise ValueError(
            f"Invalid Hub ID / MAC address '{hub_id}': expected 12 hex characters"
        )
    return cleaned


def _decode_group_name(raw: bytes) -> str:
    """Decode 0xFF-padded 12-byte group name."""
    end = 0
    for i in range(min(12, len(raw))):
        if raw[i] == 0xFF or raw[i] == 0x00:
            break
        end += 1
    if end == 0:
        return ""
    return raw[:end].decode("utf-8", errors="replace").strip()


@dataclass
class PairedDevice:
    """A 2.4 GHz Orchestra of Lights product paired to the hub."""

    device_id: int
    name: str
    mac: str
    bound: bool
    slot: int


@dataclass
class OrchestraState:
    """Current state of an Orchestra of Lights Hub."""

    hub_id: str = ""
    connected: bool = False
    transport: str = ""
    power: bool = False
    theme: int = 0
    effect: int = 4
    rgb: tuple[int, int, int] = (255, 255, 255)
    brightness: int = 100
    color_mode: str = "theme"  # "theme" or "rgb"
    music_mode: int = 0  # 0=loop, 1=random
    music_status: int = 0  # 0=stopped, 1=playing, 2=paused
    music_song: int = 0
    music_playlist: list[int] = field(default_factory=lambda: [0, 1, 2, 3, 4, 5])
    volume: int = 50
    bt_on: bool = False
    timer_on: bool = False
    timer_start: str = "17:00"
    timer_stop: str = "21:00"
    timer_zone: str = "-8:0"
    hub_ver: str = ""
    rf_ver: int = 0
    ssid: str = ""
    group_id: str = ""
    group_name: str = ""
    has_password: bool = False
    rssi: int | None = None
    devices: list[PairedDevice] = field(default_factory=list)
    last_updated: float = 0.0

    @property
    def has_op2_speaker(self) -> bool:
        return any(d.device_id in OP2_SPEAKER_IDS for d in self.devices)

    @property
    def theme_name(self) -> str:
        return THEMES.get(self.theme, f"Theme {self.theme}")

    @property
    def effect_name(self) -> str:
        return EFFECTS.get(self.effect, f"Effect {self.effect}")

    @property
    def song_name(self) -> str:
        return SONGS.get(self.music_song, f"Song {self.music_song + 1}")

    def to_dict(self) -> dict[str, Any]:
        return {
            "hub_id": self.hub_id,
            "connected": self.connected,
            "transport": self.transport,
            "power": self.power,
            "color_mode": self.color_mode,
            "theme": self.theme,
            "theme_name": self.theme_name,
            "effect": self.effect,
            "effect_name": self.effect_name,
            "rgb": list(self.rgb),
            "brightness": self.brightness,
            "music_status": self.music_status,
            "music_mode": "random" if self.music_mode == 1 else "loop",
            "music_song": self.music_song,
            "song_name": self.song_name,
            "music_playlist": self.music_playlist,
            "volume": self.volume,
            "bt_on": self.bt_on,
            "timer_on": self.timer_on,
            "timer_start": self.timer_start,
            "timer_stop": self.timer_stop,
            "timer_zone": self.timer_zone,
            "hub_ver": self.hub_ver,
            "rf_ver": self.rf_ver,
            "ssid": self.ssid,
            "group_id": self.group_id,
            "group_name": self.group_name,
            "rssi": self.rssi,
            "devices": [
                {
                    "id": d.device_id,
                    "name": d.name,
                    "mac": d.mac,
                    "bound": d.bound,
                    "slot": d.slot,
                }
                for d in self.devices
            ],
        }


# ---------------------------------------------------------------------------
# Minimal async HTTP / WebSocket / MQTT 3.1.1 helpers (stdlib only)
# ---------------------------------------------------------------------------


def _mqtt_encode_len(length: int) -> bytes:
    out = bytearray()
    while True:
        byte = length % 128
        length //= 128
        if length > 0:
            byte |= 0x80
        out.append(byte)
        if length == 0:
            break
    return bytes(out)


def _mqtt_str(text: str) -> bytes:
    raw = text.encode("utf-8")
    return struct.pack("!H", len(raw)) + raw


def _sigv4_sign(key: bytes, msg: str) -> bytes:
    return hmac.new(key, msg.encode("utf-8"), hashlib.sha256).digest()


def _create_ssl_context() -> ssl.SSLContext:
    return ssl.create_default_context()


async def _async_https_post_json(
    host: str, path: str, headers: dict[str, str], payload: dict[str, Any], timeout: float = 10.0
) -> dict[str, Any]:
    """Perform a minimal async HTTPS POST with JSON body using stdlib asyncio."""
    body = json.dumps(payload, separators=(",", ":")).encode("utf-8")
    ssl_ctx = await asyncio.to_thread(_create_ssl_context)
    reader, writer = await asyncio.wait_for(
        asyncio.open_connection(host, 443, ssl=ssl_ctx, server_hostname=host),
        timeout=timeout,
    )
    try:
        req_lines = [
            f"POST {path} HTTP/1.1",
            f"Host: {host}",
            f"Content-Length: {len(body)}",
            "Connection: close",
        ]
        for k, v in headers.items():
            req_lines.append(f"{k}: {v}")
        req_bytes = ("\r\n".join(req_lines) + "\r\n\r\n").encode("ascii") + body
        writer.write(req_bytes)
        await writer.drain()

        raw = await asyncio.wait_for(reader.read(), timeout=timeout)
    finally:
        writer.close()
        try:
            await writer.wait_closed()
        except Exception:
            pass

    header_end = raw.find(b"\r\n\r\n")
    if header_end == -1:
        raise ConnectionError("Malformed HTTP response from AWS Cognito")
    header_part = raw[:header_end].decode("ascii", errors="replace")
    body_part = raw[header_end + 4 :]

    status_line = header_part.split("\r\n", 1)[0]
    parts = status_line.split(" ", 2)
    status_code = int(parts[1]) if len(parts) >= 2 and parts[1].isdigit() else 0

    if "transfer-encoding: chunked" in header_part.lower():
        decoded = bytearray()
        idx = 0
        while idx < len(body_part):
            nl = body_part.find(b"\r\n", idx)
            if nl == -1:
                break
            chunk_len = int(body_part[idx:nl].split(b";", 1)[0], 16)
            if chunk_len == 0:
                break
            idx = nl + 2
            decoded.extend(body_part[idx : idx + chunk_len])
            idx += chunk_len + 2
        body_part = bytes(decoded)

    if status_code >= 400:
        raise ConnectionError(
            f"AWS Cognito HTTP {status_code}: {body_part.decode('utf-8', errors='replace')}"
        )
    return json.loads(body_part.decode("utf-8"))


async def discover_hubs_udp(
    broadcast_addrs: list[str] | None = None, timeout: float = 2.0
) -> list[dict[str, Any]]:
    """Send UDP discovery packet (03 00 B0 00 01) on port 8087 to find local hubs."""

    def _probe() -> list[dict[str, Any]]:
        found: dict[str, dict[str, Any]] = {}
        addrs = broadcast_addrs or ["255.255.255.255"]
        sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)
        sock.settimeout(timeout)
        probe = bytes([3, 0, 0xB0, 0, 1])
        try:
            for addr in addrs:
                try:
                    sock.sendto(probe, (addr, DEFAULT_PORT))
                except OSError:
                    pass
            deadline = time.monotonic() + timeout
            while time.monotonic() < deadline:
                sock.settimeout(max(0.1, deadline - time.monotonic()))
                try:
                    data, (ip, _) = sock.recvfrom(256)
                except TimeoutError:
                    break
                if len(data) >= 11 and data[2] == 0xB1:
                    mac_bytes = data[5:11]
                    if all(b == 0xFF for b in mac_bytes):
                        continue
                    hub_id = mac_bytes.hex()
                    group_name = ""
                    old_version = True
                    if data[0] == 33 and len(data) >= 35:
                        group_name = _decode_group_name(data[19:31])
                        old_version = data[34] == 0
                    found[hub_id] = {
                        "hub_id": hub_id,
                        "host": ip,
                        "group_name": group_name,
                        "old_version": old_version,
                    }
        finally:
            sock.close()
        return list(found.values())

    return await asyncio.to_thread(_probe)


# ---------------------------------------------------------------------------
# Main Client
# ---------------------------------------------------------------------------


class OrchestraOfLightsClient:
    """Async client for Gemmy Orchestra of Lights Hub (Local TCP 8087 + AWS IoT MQTT)."""

    def __init__(
        self,
        hub_id: str,
        host: str | None = None,
        port: int = DEFAULT_PORT,
        password: str = "",
        transport: str = TRANSPORT_AUTO,
        on_state_update: Callable[[OrchestraState], None] | None = None,
    ) -> None:
        self.hub_id = normalize_hub_id(hub_id)
        self.host = host.strip() if host else None
        self.port = port
        self.password = password or ""
        self.transport_pref = transport
        self._on_state_update = on_state_update

        self.state = OrchestraState(hub_id=self.hub_id)
        self._client_id = str(uuid.uuid4())
        self._reader: asyncio.StreamReader | None = None
        self._writer: asyncio.StreamWriter | None = None
        self._rx_task: asyncio.Task[None] | None = None
        self._keepalive_task: asyncio.Task[None] | None = None
        self._write_lock = asyncio.Lock()
        self._pkt_id = 1
        self._state_event = asyncio.Event()
        self._pw_event = asyncio.Event()
        self._rssi_event = asyncio.Event()
        self._devlist_event = asyncio.Event()
        self._cred_expiry: float = 0.0
        self._closing = False

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    async def connect(self) -> str:
        """Connect to the hub using the configured transport preference.

        Returns the active transport ("local" or "cloud").
        """
        self._closing = False
        await self._close_transport()

        if self.transport_pref in (TRANSPORT_LOCAL, TRANSPORT_AUTO) and self.host:
            try:
                await self._connect_local()
                return TRANSPORT_LOCAL
            except Exception as err:
                if self.transport_pref == TRANSPORT_LOCAL:
                    raise
                _LOGGER.debug(
                    "Local TCP connection to %s:%s failed (%s); falling back to AWS IoT MQTT",
                    self.host,
                    self.port,
                    err,
                )

        if self.transport_pref in (TRANSPORT_CLOUD, TRANSPORT_AUTO):
            await self._connect_cloud()
            return TRANSPORT_CLOUD

        raise ConnectionError("No valid transport available (provide a local IP or enable cloud)")

    async def disconnect(self) -> None:
        """Close connection and background tasks."""
        self._closing = True
        await self._close_transport()

    async def _close_transport(self) -> None:
        for task in (self._keepalive_task, self._rx_task):
            if task and not task.done():
                task.cancel()
                try:
                    await task
                except asyncio.CancelledError:
                    pass
        self._keepalive_task = None
        self._rx_task = None

        if self._writer:
            try:
                self._writer.close()
                await self._writer.wait_closed()
            except Exception:
                pass
        self._writer = None
        self._reader = None
        self.state.connected = False

    def _notify(self) -> None:
        self.state.last_updated = time.time()
        if self._on_state_update:
            try:
                self._on_state_update(self.state)
            except Exception:
                _LOGGER.exception("Error in state update callback")

    # ------------------------------------------------------------------
    # Local TCP 8087 Transport
    # ------------------------------------------------------------------

    async def _connect_local(self) -> None:
        assert self.host is not None
        reader, writer = await asyncio.wait_for(
            asyncio.open_connection(self.host, self.port), timeout=2.5
        )
        sock = writer.get_extra_info("socket")
        if sock is not None:
            try:
                sock.setsockopt(socket.IPPROTO_TCP, socket.TCP_NODELAY, 1)
            except OSError:
                pass

        self._reader = reader
        self._writer = writer
        self.state.transport = TRANSPORT_LOCAL
        self.state.connected = True

        self._rx_task = asyncio.create_task(self._local_rx_loop())
        self._keepalive_task = asyncio.create_task(self._local_keepalive_loop())

        # Local handshake (matches MyApp.k): time sync -> auth check -> version
        now = datetime.datetime.now().astimezone()
        tz_hours = int((now.utcoffset() or datetime.timedelta()).total_seconds() // 3600)
        tz_sign = 0 if tz_hours >= 0 else 1
        tz_abs = abs(tz_hours)
        time_pkt = bytes(
            [
                0x0B,
                0x00,
                0xAA,
                0x00,
                0x00,
                0xE1,
                now.hour,
                now.minute,
                now.second,
                tz_sign,
                tz_abs,
                0x00,
                0x00,
            ]
        )
        await self._local_send(time_pkt)
        await asyncio.sleep(0.1)
        await self._local_send(bytes([0x03, 0x00, 0xA0, 0x00, 0x01]))
        if self.password:
            await asyncio.sleep(0.1)
            pw_bytes = self.password.encode("utf-8")
            await self._local_send(bytes([len(pw_bytes) + 2, 0x00, 0xA0, 0x01]) + pw_bytes)
        await asyncio.sleep(0.1)
        await self._local_send(bytes([0x02, 0x00, 0xA6, 0x02]))

    async def _local_send(self, data: bytes) -> None:
        if not self._writer:
            raise ConnectionError("Local TCP socket not connected")
        async with self._write_lock:
            self._writer.write(data)
            await self._writer.drain()

    async def _local_keepalive_loop(self) -> None:
        heartbeat = bytes([0x04, 0x00, 0xAF, 0x00, 0x00, 0x00])
        try:
            while not self._closing and self.state.connected:
                await asyncio.sleep(20)
                await self._local_send(heartbeat)
        except asyncio.CancelledError:
            pass
        except Exception as err:
            _LOGGER.debug("Local keepalive ended: %s", err)
            self.state.connected = False

    async def _local_rx_loop(self) -> None:
        assert self._reader is not None
        try:
            while not self._closing:
                data = await self._reader.read(1024)
                if not data:
                    break
                self._parse_local_packet(data)
        except asyncio.CancelledError:
            pass
        except Exception as err:
            _LOGGER.debug("Local RX loop error: %s", err)
        finally:
            self.state.connected = False

    def _parse_local_packet(self, data: bytes) -> None:
        if len(data) < 4:
            return
        cmd = data[2]
        sub = data[3]

        if cmd == 0xA6:
            if sub == 1 and len(data) >= 36:
                self.state.music_mode = data[5]
                self.state.music_status = data[6]
                self.state.music_song = data[7]
                self.state.volume = data[8]
                songs = [b for b in data[9:15] if b != 0xFF]
                if len(data) >= 43:
                    songs.extend(b for b in data[37:43] if b != 0xFF)
                self.state.music_playlist = songs
                self.state.theme = data[15]
                self.state.effect = data[16]
                self.state.rgb = (data[17], data[18], data[19])
                self.state.timer_on = data[20] == 1
                self.state.timer_start = f"{data[21]:02d}:{data[22]:02d}"
                self.state.timer_stop = f"{data[23]:02d}:{data[24]:02d}"
                self.state.brightness = data[34]
                self.state.power = data[35] == 1
                if len(data) >= 37:
                    self.state.bt_on = data[36] == 1
                self._state_event.set()
                self._notify()
            elif sub == 2 and len(data) >= 7:
                self.state.hub_ver = f"{data[4]}.{data[5]}.{data[6]}"
                if len(data) >= 8:
                    self.state.rf_ver = data[7]
                self._pw_event.set()
                self._notify()
            elif sub == 10 and len(data) >= 5:
                rssi = data[4] if data[4] < 128 else data[4] - 256
                self.state.rssi = rssi
                self._rssi_event.set()
                self._notify()
        elif cmd == 0xA5:
            if sub == 0 and len(data) >= 10:
                count = data[4] + data[5]
                grp = (data[6] << 8) | data[7]
                self.state.group_id = f"{grp:04x}"
                devices: list[PairedDevice] = []
                for idx in range(count):
                    off = 10 + idx * 8
                    if off + 8 <= len(data):
                        dev_id = data[off] | (data[off + 1] << 8)
                        mac = data[off : off + 6].hex()
                        slot = data[off + 6]
                        devices.append(
                            PairedDevice(
                                device_id=dev_id,
                                name=DEVICE_TYPES.get(dev_id, f"Device {dev_id} ({mac})"),
                                mac=mac,
                                bound=slot != 0xFF,
                                slot=slot,
                            )
                        )
                self.state.devices = devices
                self._devlist_event.set()
                self._notify()
            elif sub == 3 and len(data) >= 17 and data[4] == 1:
                self.state.group_name = _decode_group_name(data[5:17])
                self._notify()

    # ------------------------------------------------------------------
    # AWS IoT Core MQTT-over-WebSocket Transport
    # ------------------------------------------------------------------

    async def _get_cognito_credentials(self) -> dict[str, Any]:
        cognito_host = f"cognito-identity.{AWS_COGNITO_REGION}.amazonaws.com"
        ident = await _async_https_post_json(
            cognito_host,
            "/",
            {
                "Content-Type": "application/x-amz-json-1.1",
                "X-Amz-Target": "AWSCognitoIdentityService.GetId",
            },
            {"IdentityPoolId": AWS_COGNITO_POOL_ID},
        )
        identity_id = ident["IdentityId"]
        creds_resp = await _async_https_post_json(
            cognito_host,
            "/",
            {
                "Content-Type": "application/x-amz-json-1.1",
                "X-Amz-Target": "AWSCognitoIdentityService.GetCredentialsForIdentity",
            },
            {"IdentityId": identity_id},
        )
        creds = creds_resp["Credentials"]
        self._cred_expiry = float(creds.get("Expiration", time.time() + 3000))
        return creds

    def _build_presigned_ws_path(self, creds: dict[str, Any]) -> str:
        now = datetime.datetime.now(datetime.UTC)
        amz_date = now.strftime("%Y%m%dT%H%M%SZ")
        date_stamp = now.strftime("%Y%m%d")
        service = "iotdevicegateway"
        cred_scope = f"{date_stamp}/{AWS_IOT_REGION}/{service}/aws4_request"

        params = {
            "X-Amz-Algorithm": "AWS4-HMAC-SHA256",
            "X-Amz-Credential": f"{creds['AccessKeyId']}/{cred_scope}",
            "X-Amz-Date": amz_date,
            "X-Amz-SignedHeaders": "host",
        }
        canonical_qs = "&".join(
            f"{urllib.parse.quote(k, safe='')}={urllib.parse.quote(v, safe='')}"
            for k, v in sorted(params.items())
        )
        canonical_request = (
            f"GET\n/mqtt\n{canonical_qs}\nhost:{AWS_IOT_ENDPOINT}\n\nhost\n"
            f"{hashlib.sha256(b'').hexdigest()}"
        )
        string_to_sign = (
            f"AWS4-HMAC-SHA256\n{amz_date}\n{cred_scope}\n"
            f"{hashlib.sha256(canonical_request.encode('utf-8')).hexdigest()}"
        )
        k_date = _sigv4_sign(("AWS4" + creds["SecretKey"]).encode("utf-8"), date_stamp)
        k_region = _sigv4_sign(k_date, AWS_IOT_REGION)
        k_service = _sigv4_sign(k_region, service)
        k_signing = _sigv4_sign(k_service, "aws4_request")
        signature = hmac.new(
            k_signing, string_to_sign.encode("utf-8"), hashlib.sha256
        ).hexdigest()
        token = urllib.parse.quote(creds["SessionToken"], safe="")
        return f"/mqtt?{canonical_qs}&X-Amz-Signature={signature}&X-Amz-Security-Token={token}"

    async def _connect_cloud(self) -> None:
        creds = await self._get_cognito_credentials()
        ws_path = self._build_presigned_ws_path(creds)

        ssl_ctx = await asyncio.to_thread(_create_ssl_context)
        reader, writer = await asyncio.wait_for(
            asyncio.open_connection(
                AWS_IOT_ENDPOINT, 443, ssl=ssl_ctx, server_hostname=AWS_IOT_ENDPOINT
            ),
            timeout=10.0,
        )
        self._reader = reader
        self._writer = writer

        ws_key = base64.b64encode(os.urandom(16)).decode("ascii")
        handshake = (
            f"GET {ws_path} HTTP/1.1\r\n"
            f"Host: {AWS_IOT_ENDPOINT}\r\n"
            f"Upgrade: websocket\r\n"
            f"Connection: Upgrade\r\n"
            f"Sec-WebSocket-Key: {ws_key}\r\n"
            f"Sec-WebSocket-Version: 13\r\n"
            f"Sec-WebSocket-Protocol: mqtt\r\n\r\n"
        )
        writer.write(handshake.encode("ascii"))
        await writer.drain()

        resp_hdr = await asyncio.wait_for(reader.readuntil(b"\r\n\r\n"), timeout=10.0)
        first_line = resp_hdr.split(b"\r\n", 1)[0].decode("ascii", errors="replace")
        if "101" not in first_line:
            await self._close_transport()
            raise ConnectionError(f"AWS IoT WebSocket upgrade failed: {first_line}")

        # MQTT 3.1.1 CONNECT
        var_hdr = _mqtt_str("MQTT") + bytes([4, 2]) + struct.pack("!H", 60)
        payload = _mqtt_str(self._client_id)
        await self._ws_send(
            bytes([0x10]) + _mqtt_encode_len(len(var_hdr) + len(payload)) + var_hdr + payload
        )
        _, connack = await asyncio.wait_for(self._ws_recv(), timeout=10.0)
        if len(connack) < 4 or connack[0] != 0x20 or connack[3] != 0:
            await self._close_transport()
            raise ConnectionError(f"MQTT CONNACK rejected: {connack.hex(' ')}")

        # Subscribe to all hub topics
        topics = [
            f"$aws/things/{self.hub_id}/pw",
            f"$aws/things/{self.hub_id}/rssi",
            f"$aws/things/{self.hub_id}/name",
            f"$aws/things/{self.hub_id}/state",
            f"$aws/things/{self.hub_id}/heartbeat",
            f"$aws/things/{self.hub_id}/cmd/hub",
            f"$aws/things/{self.hub_id}/devicelist",
        ]
        sub_payload = bytearray(struct.pack("!H", self._next_pkt_id()))
        for topic in topics:
            sub_payload.extend(_mqtt_str(topic))
            sub_payload.append(0)  # QoS 0
        await self._ws_send(
            bytes([0x82]) + _mqtt_encode_len(len(sub_payload)) + bytes(sub_payload)
        )
        # Wait for SUBACK
        _, suback = await asyncio.wait_for(self._ws_recv(), timeout=10.0)
        if not suback or (suback[0] & 0xF0) != 0x90:
            _LOGGER.debug("Unexpected packet while awaiting SUBACK: %s", suback.hex(" "))

        self.state.transport = TRANSPORT_CLOUD
        self.state.connected = True
        self._rx_task = asyncio.create_task(self._cloud_rx_loop())
        self._keepalive_task = asyncio.create_task(self._cloud_keepalive_loop())

    def _next_pkt_id(self) -> int:
        pid = self._pkt_id
        self._pkt_id = (self._pkt_id % 65535) + 1
        return pid

    async def _ws_send(self, payload: bytes, opcode: int = 0x82) -> None:
        if not self._writer:
            raise ConnectionError("WebSocket not connected")
        mask = os.urandom(4)
        n = len(payload)
        hdr = bytearray([opcode])
        if n < 126:
            hdr.append(0x80 | n)
        elif n < 65536:
            hdr.append(0x80 | 126)
            hdr.extend(struct.pack("!H", n))
        else:
            hdr.append(0x80 | 127)
            hdr.extend(struct.pack("!Q", n))
        hdr.extend(mask)
        masked = bytes(payload[i] ^ mask[i % 4] for i in range(n))
        async with self._write_lock:
            self._writer.write(bytes(hdr) + masked)
            await self._writer.drain()

    async def _ws_recv(self) -> tuple[int, bytes]:
        assert self._reader is not None
        header = await self._reader.readexactly(2)
        b0, b1 = header[0], header[1]
        masked = bool(b1 & 0x80)
        length = b1 & 0x7F
        if length == 126:
            length = struct.unpack("!H", await self._reader.readexactly(2))[0]
        elif length == 127:
            length = struct.unpack("!Q", await self._reader.readexactly(8))[0]
        mask_key = await self._reader.readexactly(4) if masked else b""
        data = await self._reader.readexactly(length)
        if masked:
            data = bytes(data[i] ^ mask_key[i % 4] for i in range(length))
        return b0 & 0x0F, data

    async def _cloud_keepalive_loop(self) -> None:
        try:
            while not self._closing and self.state.connected:
                await asyncio.sleep(45)
                if not self.state.connected:
                    break
                # MQTT PINGREQ
                await self._ws_send(bytes([0xC0, 0x00]))
        except asyncio.CancelledError:
            pass
        except Exception as err:
            _LOGGER.debug("Cloud keepalive ended: %s", err)
            self.state.connected = False

    async def _cloud_rx_loop(self) -> None:
        try:
            while not self._closing:
                opcode, data = await self._ws_recv()
                if opcode == 0x8:  # WS close
                    break
                if opcode == 0x9:  # WS ping -> pong
                    await self._ws_send(data, opcode=0x8A)
                    continue
                if opcode not in (0x1, 0x2) or not data:
                    continue
                self._handle_mqtt_frame(data)
        except asyncio.CancelledError:
            pass
        except Exception as err:
            _LOGGER.debug("Cloud RX loop ended: %s", err)
        finally:
            self.state.connected = False

    def _handle_mqtt_frame(self, buf: bytes) -> None:
        pos = 0
        while pos < len(buf):
            pkt_type = buf[pos] & 0xF0
            pos += 1
            mult = 1
            rem_len = 0
            while pos < len(buf):
                b = buf[pos]
                pos += 1
                rem_len += (b & 0x7F) * mult
                if not (b & 0x80):
                    break
                mult *= 128
            pkt_body = buf[pos : pos + rem_len]
            pos += rem_len

            if pkt_type == 0x30 and len(pkt_body) >= 2:  # PUBLISH
                tlen = struct.unpack("!H", pkt_body[:2])[0]
                topic = pkt_body[2 : 2 + tlen].decode("utf-8", errors="replace")
                msg_raw = pkt_body[2 + tlen :]
                self._parse_cloud_message(topic, msg_raw)

    def _parse_cloud_message(self, topic: str, payload: bytes) -> None:
        if not payload:
            return
        try:
            doc = json.loads(payload.decode("utf-8"))
            reported = doc.get("state", {}).get("reported", {})
        except Exception as err:
            _LOGGER.debug("Failed parsing MQTT payload on %s: %s", topic, err)
            return

        if topic.endswith("/cmd/hub"):
            self.state.music_mode = int(reported.get("music_mode", self.state.music_mode))
            self.state.music_status = int(reported.get("music_cmd", self.state.music_status))
            self.state.music_song = int(reported.get("music_song", self.state.music_song))
            self.state.volume = int(reported.get("volume", self.state.volume))

            order_str = reported.get("music_order2") or reported.get("music_order")
            if order_str:
                try:
                    self.state.music_playlist = [
                        int(x) for x in order_str.split(",") if x.strip() and int(x) != 255
                    ]
                except ValueError:
                    pass

            ls = reported.get("lightshow", "")
            new_theme = self.state.theme
            new_effect = self.state.effect
            if "," in ls:
                parts = ls.split(",")
                if len(parts) == 2:
                    new_theme = int(parts[0])
                    new_effect = int(parts[1])

            rgb_str = reported.get("color_rgb", "")
            new_rgb = self.state.rgb
            if "," in rgb_str:
                parts = rgb_str.split(",")
                if len(parts) == 3:
                    new_rgb = (int(parts[0]), int(parts[1]), int(parts[2]))

            if (new_theme, new_effect) != (self.state.theme, self.state.effect):
                self.state.color_mode = "theme"
            elif new_rgb != self.state.rgb:
                self.state.color_mode = "rgb"

            self.state.theme = new_theme
            self.state.effect = new_effect
            self.state.rgb = new_rgb
            self.state.brightness = int(
                reported.get("colorbrightness_x", self.state.brightness)
            )
            self.state.power = int(reported.get("device_on", 0)) == 1
            self.state.bt_on = int(reported.get("bt_on", 0)) == 1
            self.state.timer_on = int(reported.get("timer_on", 0)) == 1
            if "timer_start" in reported:
                sh, sm = (int(x) for x in str(reported["timer_start"]).split(":"))
                self.state.timer_start = f"{sh:02d}:{sm:02d}"
            if "timer_stop" in reported:
                eh, em = (int(x) for x in str(reported["timer_stop"]).split(":"))
                self.state.timer_stop = f"{eh:02d}:{em:02d}"
            if "timerzone" in reported:
                self.state.timer_zone = str(reported["timerzone"])

            self._state_event.set()
            self._notify()

        elif topic.endswith("/pw"):
            self.state.has_password = int(reported.get("pw_on", 0)) == 1
            ver_hex = str(reported.get("hub_ver", ""))
            if len(ver_hex) == 6:
                try:
                    vb = bytes.fromhex(ver_hex)
                    self.state.hub_ver = f"{vb[0]}.{vb[1]}.{vb[2]}"
                except ValueError:
                    self.state.hub_ver = ver_hex
            self.state.rf_ver = int(reported.get("24g_ver", self.state.rf_ver))
            if "ssid" in reported:
                self.state.ssid = str(reported["ssid"])
            if "group" in reported:
                self.state.group_id = str(reported["group"])
            if "group_name" in reported:
                try:
                    self.state.group_name = _decode_group_name(
                        bytes.fromhex(str(reported["group_name"]))
                    )
                except ValueError:
                    pass
            self._pw_event.set()
            self._notify()

        elif topic.endswith("/rssi"):
            if "hub_rssi" in reported:
                raw_rssi = int(reported["hub_rssi"])
                self.state.rssi = raw_rssi if raw_rssi < 128 else raw_rssi - 256
                self._rssi_event.set()
                self._notify()

        elif topic.endswith("/name"):
            if reported.get("request_type") == 1 and "group_name" in reported:
                try:
                    self.state.group_name = _decode_group_name(
                        bytes.fromhex(str(reported["group_name"]))
                    )
                    self._notify()
                except ValueError:
                    pass

        elif topic.endswith("/devicelist"):
            count = int(reported.get("device_num", 0))
            new_list = reported.get("new_device_list")
            old_list = reported.get("device_list")
            if "group" in reported:
                self.state.group_id = str(reported["group"])
            if "group_name" in reported:
                try:
                    self.state.group_name = _decode_group_name(
                        bytes.fromhex(str(reported["group_name"]))
                    )
                except ValueError:
                    pass

            devices: list[PairedDevice] = []
            if new_list:
                raw = bytes.fromhex(str(new_list))
                for idx in range(count):
                    off = idx * 7
                    if off + 7 <= len(raw):
                        dev_id = raw[off] | (raw[off + 1] << 8)
                        mac = raw[off : off + 6].hex()
                        slot = raw[off + 6]
                        devices.append(
                            PairedDevice(
                                device_id=dev_id,
                                name=DEVICE_TYPES.get(dev_id, f"Device {dev_id} ({mac})"),
                                mac=mac,
                                bound=slot != 0xFF,
                                slot=slot,
                            )
                        )
            elif old_list:
                raw = bytes.fromhex(str(old_list))
                for idx in range(count):
                    off = idx * 6
                    if off + 6 <= len(raw):
                        dev_id = raw[off] | (raw[off + 1] << 8)
                        mac = raw[off : off + 6].hex()
                        devices.append(
                            PairedDevice(
                                device_id=dev_id,
                                name=DEVICE_TYPES.get(dev_id, f"Device {dev_id} ({mac})"),
                                mac=mac,
                                bound=False,
                                slot=255,
                            )
                        )
            self.state.devices = devices
            self._devlist_event.set()
            self._notify()

    async def _cloud_publish(self, subtopic: str, reported: dict[str, Any]) -> None:
        if not self.state.connected or self.state.transport != TRANSPORT_CLOUD:
            raise ConnectionError("Cloud MQTT not connected")
        doc: dict[str, Any] = {
            "clientToken": f"android{self._client_id}",
            "length": "AB00",
            "state": {"reported": reported},
        }
        raw_len = len(json.dumps(doc, separators=(",", ":")))
        hex_len = f"{raw_len:04X}"
        doc["length"] = hex_len[2:4] + hex_len[0:2]
        body = json.dumps(doc, separators=(",", ":")).encode("utf-8")

        topic = f"$aws/things/{self.hub_id}/{subtopic}"
        pub = _mqtt_str(topic) + body
        await self._ws_send(bytes([0x30]) + _mqtt_encode_len(len(pub)) + pub)

    async def _ensure_connected(self) -> None:
        if not self.state.connected:
            await self.connect()
        elif (
            self.state.transport == TRANSPORT_CLOUD
            and self._cred_expiry
            and time.time() > self._cred_expiry - 300
        ):
            _LOGGER.debug("Refreshing AWS Cognito credentials before expiry")
            await self.connect()

    # ------------------------------------------------------------------
    # Query Methods
    # ------------------------------------------------------------------

    async def refresh_state(self, timeout: float = 5.0) -> OrchestraState:
        """Request current lighting/music/timer state from the hub."""
        await self._ensure_connected()
        self._state_event.clear()
        if self.state.transport == TRANSPORT_LOCAL:
            await self._local_send(bytes([0x02, 0x00, 0xA6, 0x01]))
        else:
            await self._cloud_publish(
                "request",
                {
                    "hub_cmd": 1,
                    "hub_name": 0,
                    "hub_pw": 0,
                    "hub_rssi": 0,
                    "hub_scandevicelist": 0,
                    "hub_superreset": 0,
                },
            )
        await asyncio.wait_for(self._state_event.wait(), timeout=timeout)
        return self.state

    async def refresh_info(self, timeout: float = 5.0) -> OrchestraState:
        """Request firmware version, RSSI, and paired device list."""
        await self._ensure_connected()
        self._pw_event.clear()
        self._rssi_event.clear()
        self._devlist_event.clear()

        if self.state.transport == TRANSPORT_LOCAL:
            await self._local_send(bytes([0x02, 0x00, 0xA6, 0x02]))
            await asyncio.sleep(0.1)
            await self._local_send(bytes([0x02, 0x00, 0xA6, 0x0A]))
            await asyncio.sleep(0.1)
            await self._local_send(bytes([0x03, 0x00, 0xA5, 0x00, 0x01]))
        else:
            await self._cloud_publish(
                "request",
                {
                    "hub_cmd": 0,
                    "hub_name": 0,
                    "hub_pw": 1,
                    "hub_rssi": 0,
                    "hub_scandevicelist": 0,
                    "hub_superreset": 0,
                },
            )
            await self._cloud_publish(
                "request",
                {
                    "hub_cmd": 0,
                    "hub_name": 0,
                    "hub_pw": 0,
                    "hub_rssi": 1,
                    "hub_scandevicelist": 0,
                    "hub_superreset": 0,
                },
            )
            await self._cloud_publish(
                "request",
                {
                    "hub_cmd": 0,
                    "hub_name": 0,
                    "hub_pw": 0,
                    "hub_rssi": 0,
                    "hub_scandevicelist": 2,
                    "hub_superreset": 0,
                },
            )

        await asyncio.gather(
            asyncio.wait_for(self._pw_event.wait(), timeout=timeout),
            asyncio.wait_for(self._rssi_event.wait(), timeout=timeout),
            asyncio.wait_for(self._devlist_event.wait(), timeout=timeout),
            return_exceptions=True,
        )
        return self.state

    async def refresh_all(self, timeout: float = 5.0) -> OrchestraState:
        """Refresh both live state and hub metadata/devices."""
        await self.refresh_state(timeout=timeout)
        await self.refresh_info(timeout=timeout)
        return self.state

    # ------------------------------------------------------------------
    # Control Commands
    # ------------------------------------------------------------------

    async def set_power(self, on: bool) -> None:
        """Turn lights ON or OFF."""
        await self._ensure_connected()
        if self.state.transport == TRANSPORT_LOCAL:
            await self._local_send(bytes([0x03, 0x00, 0xA6, 0x09, 1 if on else 0]))
        else:
            await self._cloud_publish(
                "cmd/app",
                {"cmd": 0, "change": "11", "device_on": 1 if on else 0},
            )
        self.state.power = on
        if not on:
            self.state.music_status = 0
        self._notify()

    async def set_rgb(
        self, r: int, g: int, b: int, brightness: int | None = None
    ) -> None:
        """Set custom RGB color (0-255 each) and brightness (0-100)."""
        await self._ensure_connected()
        r = max(0, min(255, int(r)))
        g = max(0, min(255, int(g)))
        b = max(0, min(255, int(b)))
        bri = (
            self.state.brightness
            if brightness is None
            else max(0, min(100, int(brightness)))
        )

        if self.state.transport == TRANSPORT_LOCAL:
            await self._local_send(
                bytes([0x0B, 0x00, 0xAA, 0x00, 0x00, 0x03, r, g, b, 0, 0, 0, bri])
            )
        else:
            await self._cloud_publish(
                "cmd/app",
                {
                    "cmd": 3,
                    "change": "7",
                    "colorbrightness_x": bri,
                    "color_rgb": f"{r},{g},{b}",
                    "colorwheel_xy": "0,0",
                    "colorwhite_x": 100,
                },
            )
        self.state.rgb = (r, g, b)
        self.state.brightness = bri
        self.state.color_mode = "rgb"
        self.state.power = True
        self.state.music_status = 0
        self._notify()

    async def set_theme(self, theme: int, effect: int | None = None) -> None:
        """Set a preset lightshow, holiday theme, or color theme + effect."""
        await self._ensure_connected()
        theme = int(theme)
        if theme in PRESET_LIGHTSHOWS:
            eff = 4
        else:
            eff = self.state.effect if effect is None else int(effect)
            if theme in SOLID_COLOR_THEMES and eff == 4:
                eff = 0
            eff = max(0, min(4, eff))

        if self.state.transport == TRANSPORT_LOCAL:
            await self._local_send(
                bytes([0x0B, 0x00, 0xAA, 0x00, 0x00, 0x02, theme, eff, 0, 0, 0, 0, 0])
            )
        else:
            await self._cloud_publish(
                "cmd/app",
                {"cmd": 2, "change": "6", "lightshow": f"{theme},{eff}"},
            )
        self.state.theme = theme
        self.state.effect = eff
        self.state.color_mode = "theme"
        self.state.power = True
        self.state.music_status = 0
        self._notify()

    async def play_song(self, song_index: int) -> None:
        """Start playing a built-in song (0..11)."""
        await self._ensure_connected()
        idx = max(0, min(11, int(song_index)))
        if self.state.transport == TRANSPORT_LOCAL:
            await self._local_send(
                bytes([0x0B, 0x00, 0xAA, 0x00, 0x00, 0x01, 0x01, idx, 0, 0, 0, 0, 0])
            )
        else:
            await self._cloud_publish(
                "cmd/app",
                {"cmd": 1, "change": "3,4", "music_cmd": 1, "music_song": idx},
            )
        self.state.music_song = idx
        self.state.music_status = 1
        self.state.power = True
        self._notify()

    async def pause_music(self) -> None:
        """Pause current musical lightshow."""
        await self._ensure_connected()
        if self.state.transport == TRANSPORT_LOCAL:
            await self._local_send(
                bytes([0x0B, 0x00, 0xAA, 0x00, 0x00, 0x01, 0x02, 0, 0, 0, 0, 0, 0])
            )
        else:
            await self._cloud_publish(
                "cmd/app",
                {"cmd": 1, "change": "4", "music_cmd": 2},
            )
        self.state.music_status = 2
        self._notify()

    async def resume_music(self) -> None:
        """Resume paused musical lightshow."""
        await self._ensure_connected()
        if self.state.transport == TRANSPORT_LOCAL:
            await self._local_send(
                bytes([0x0B, 0x00, 0xAA, 0x00, 0x00, 0x01, 0x03, 0, 0, 0, 0, 0, 0])
            )
        else:
            await self._cloud_publish(
                "cmd/app",
                {"cmd": 1, "change": "4", "music_cmd": 3},
            )
        self.state.music_status = 1
        self.state.power = True
        self._notify()

    async def set_volume(self, volume: int) -> None:
        """Set speaker volume (0..100)."""
        await self._ensure_connected()
        vol = max(0, min(100, int(volume)))
        if self.state.transport == TRANSPORT_LOCAL:
            await self._local_send(
                bytes([0x0B, 0x00, 0xAA, 0x00, 0x00, 0x01, 0x04, vol, vol, 0, 0, 0, 0])
            )
        else:
            await self._cloud_publish(
                "cmd/app",
                {"cmd": 1, "change": "5", "volume": vol, "volume_x": vol},
            )
        self.state.volume = vol
        self._notify()

    async def set_music_mode(self, random_mode: bool) -> None:
        """Set music playback mode (False=loop, True=random/shuffle)."""
        await self._ensure_connected()
        mode = 1 if random_mode else 0
        if self.state.transport == TRANSPORT_LOCAL:
            await self._local_send(
                bytes([0x0B, 0x00, 0xAA, 0x00, 0x00, 0x01, 0x00, mode, 0, 0, 0, 0, 0])
            )
        else:
            await self._cloud_publish(
                "cmd/app",
                {"cmd": 1, "change": "1", "music_mode": mode},
            )
        self.state.music_mode = mode
        self._notify()

    async def set_playlist(self, song_indices: list[int]) -> None:
        """Set active playlist order (up to 12 song indices 0..11)."""
        await self._ensure_connected()
        padded = [max(0, min(11, int(i))) for i in song_indices[:12]]
        while len(padded) < 12:
            padded.append(255)
        if self.state.transport == TRANSPORT_LOCAL:
            await self._local_send(
                bytes([17, 0x00, 0xAA, 0x00, 0x00, 0x06, 0x00, *padded])
            )
        else:
            await self._cloud_publish(
                "cmd/app",
                {
                    "cmd": 1,
                    "change": "2",
                    "music_order2": ",".join(str(x) for x in padded),
                },
            )
        self.state.music_playlist = [x for x in padded if x != 255]
        self._notify()

    async def set_bluetooth(self, enabled: bool) -> None:
        """Enable or disable Bluetooth audio streaming mode on the speaker."""
        await self._ensure_connected()
        if self.state.transport == TRANSPORT_LOCAL:
            await self._local_send(
                bytes([0x03, 0x00, 0xA6, 0x0D, 1 if enabled else 0])
            )
        else:
            await self._cloud_publish(
                "cmd/app",
                {"cmd": 4, "change": "8", "bt_on": 1 if enabled else 0},
            )
        self.state.bt_on = enabled
        self._notify()

    async def set_timer(
        self,
        enabled: bool,
        start_hour: int | None = None,
        start_min: int | None = None,
        stop_hour: int | None = None,
        stop_min: int | None = None,
    ) -> None:
        """Enable or disable the hub's built-in daily timer."""
        await self._ensure_connected()
        if start_hour is None or start_min is None:
            sh, sm = (int(x) for x in self.state.timer_start.split(":"))
        else:
            sh, sm = int(start_hour), int(start_min)
        if stop_hour is None or stop_min is None:
            eh, em = (int(x) for x in self.state.timer_stop.split(":"))
        else:
            eh, em = int(stop_hour), int(stop_min)

        if self.state.transport == TRANSPORT_LOCAL:
            await self._local_send(
                bytes(
                    [
                        0x0B,
                        0x00,
                        0xAA,
                        0x00,
                        0x00,
                        0xE0,
                        1 if enabled else 0,
                        sh,
                        sm,
                        eh,
                        em,
                        0,
                        0,
                    ]
                )
            )
        else:
            now = datetime.datetime.now().astimezone()
            tz_hours = int(
                (now.utcoffset() or datetime.timedelta()).total_seconds() // 3600
            )
            tz_str = f"+{tz_hours}:0" if tz_hours > 0 else f"{tz_hours}:0"
            await self._cloud_publish(
                "cmd/app",
                {
                    "cmd": 5,
                    "change": "9",
                    "timer_on": 1 if enabled else 0,
                    "timer_currenttime": now.strftime("%H:%M:%S"),
                    "timer_start": f"{sh:02d}:{sm:02d}",
                    "timer_stop": f"{eh:02d}:{em:02d}",
                    "timerzone": tz_str,
                },
            )
        self.state.timer_on = enabled
        self.state.timer_start = f"{sh:02d}:{sm:02d}"
        self.state.timer_stop = f"{eh:02d}:{em:02d}"
        self._notify()
