#!/usr/bin/env python3
"""Standalone macOS/Linux CLI for testing Gemmy Orchestra of Lights Hub control."""

from __future__ import annotations

import argparse
import asyncio
import importlib.util
import json
import os
import sys
import types
from pathlib import Path

# Load const.py and client.py directly so the CLI works on macOS without Home Assistant installed
_PKG_DIR = Path(__file__).resolve().parent / "custom_components" / "orchestra_of_lights"
_PKG_NAME = "_ool_pkg"
_pkg = types.ModuleType(_PKG_NAME)
_pkg.__path__ = [str(_PKG_DIR)]
sys.modules[_PKG_NAME] = _pkg

def _load_mod(name: str):
    spec = importlib.util.spec_from_file_location(f"{_PKG_NAME}.{name}", _PKG_DIR / f"{name}.py")
    assert spec and spec.loader
    mod = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = mod
    spec.loader.exec_module(mod)
    return mod

_const = _load_mod("const")
_client = _load_mod("client")

OrchestraOfLightsClient = _client.OrchestraOfLightsClient
discover_hubs_udp = _client.discover_hubs_udp
EFFECT_NAME_TO_ID = _const.EFFECT_NAME_TO_ID
EFFECTS = _const.EFFECTS
SONGS = _const.SONGS
THEME_NAME_TO_ID = _const.THEME_NAME_TO_ID
THEMES = _const.THEMES
TRANSPORT_AUTO = _const.TRANSPORT_AUTO
TRANSPORT_CLOUD = _const.TRANSPORT_CLOUD
TRANSPORT_LOCAL = _const.TRANSPORT_LOCAL


def _resolve_theme(value: str) -> int:
    if value.isdigit():
        return int(value)
    low = value.strip().lower()
    for name, tid in THEME_NAME_TO_ID.items():
        if name.lower() == low:
            return tid
    for name, tid in THEME_NAME_TO_ID.items():
        if low in name.lower():
            return tid
    raise SystemExit(f"Unknown theme '{value}'. Run `list` to see valid themes.")


def _resolve_effect(value: str | None) -> int | None:
    if value is None:
        return None
    if value.isdigit():
        return int(value)
    low = value.strip().lower()
    for name, eid in EFFECT_NAME_TO_ID.items():
        if name.lower() == low or low in name.lower():
            return eid
    raise SystemExit(f"Unknown effect '{value}'. Valid: {', '.join(EFFECTS.values())}")


async def _run(args: argparse.Namespace) -> None:
    if args.command == "list":
        print("=== EFFECTS ===")
        for eid, name in sorted(EFFECTS.items()):
            print(f"  {eid:2d}: {name}")
        print("\n=== THEMES ===")
        for tid, name in sorted(THEMES.items()):
            print(f"  {tid:2d}: {name}")
        print("\n=== SONGS ===")
        for sid, name in sorted(SONGS.items()):
            print(f"  {sid:2d}: {name}")
        return

    if args.command == "discover":
        hubs = await discover_hubs_udp(timeout=3.0)
        print(json.dumps(hubs, indent=2))
        return

    if not args.hub_id:
        raise SystemExit(
            "Missing --hub-id (12-char Hub MAC address). Pass --hub-id <mac> or set OOL_HUB_ID."
        )

    client = OrchestraOfLightsClient(
        hub_id=args.hub_id,
        host=args.host,
        password=args.password,
        transport=args.transport,
    )
    try:
        active = await client.connect()
        print(f"Connected via {active.upper()} transport to hub {client.hub_id}")

        if args.command == "status":
            await client.refresh_all()
            print(json.dumps(client.state.to_dict(), indent=2))
            return

        if args.command == "power":
            on = args.state.lower() in ("on", "1", "true")
            await client.set_power(on)
            await asyncio.sleep(0.5)
            await client.refresh_state()
            print(f"Power -> {'ON' if client.state.power else 'OFF'}")

        elif args.command == "rgb":
            await client.set_rgb(args.r, args.g, args.b, args.brightness)
            await asyncio.sleep(0.5)
            await client.refresh_state()
            print(
                f"RGB -> {client.state.rgb} brightness={client.state.brightness}%"
            )

        elif args.command == "theme":
            tid = _resolve_theme(args.theme)
            eid = _resolve_effect(args.effect)
            await client.set_theme(tid, eid)
            await asyncio.sleep(0.5)
            await client.refresh_state()
            print(
                f"Theme -> {client.state.theme_name} ({client.state.theme}), "
                f"Effect -> {client.state.effect_name} ({client.state.effect})"
            )

        elif args.command == "play":
            await client.play_song(args.song)
            await asyncio.sleep(0.5)
            await client.refresh_state()
            print(f"Playing -> [{client.state.music_song}] {client.state.song_name}")

        elif args.command == "pause":
            await client.pause_music()
            print("Music paused")

        elif args.command == "resume":
            await client.resume_music()
            print("Music resumed")

        elif args.command == "volume":
            await client.set_volume(args.level)
            await asyncio.sleep(0.5)
            await client.refresh_state()
            print(f"Volume -> {client.state.volume}%")

        elif args.command == "bt":
            on = args.state.lower() in ("on", "1", "true")
            await client.set_bluetooth(on)
            print(f"Bluetooth speaker mode -> {'ON' if on else 'OFF'}")

        elif args.command == "timer":
            await client.refresh_state()
            on = args.state.lower() in ("on", "1", "true")
            sh = sm = eh = em = None
            if args.start:
                sh, sm = (int(x) for x in args.start.split(":"))
            if args.stop:
                eh, em = (int(x) for x in args.stop.split(":"))
            await client.set_timer(on, sh, sm, eh, em)
            await asyncio.sleep(0.5)
            await client.refresh_state()
            print(
                f"Timer -> {'ON' if client.state.timer_on else 'OFF'} "
                f"({client.state.timer_start} - {client.state.timer_stop})"
            )
    finally:
        await client.disconnect()


def main() -> None:
    parser = argparse.ArgumentParser(description="Gemmy Orchestra of Lights CLI")
    parser.add_argument(
        "--hub-id",
        default=os.environ.get("OOL_HUB_ID", ""),
        help="Hub MAC / ID (12 hex chars, or set OOL_HUB_ID env var)",
    )
    parser.add_argument(
        "--host",
        default=os.environ.get("OOL_HOST", ""),
        help="Optional local Hub IP for TCP 8087 (or set OOL_HOST env var)",
    )
    parser.add_argument(
        "--password",
        default=os.environ.get("OOL_PASSWORD", ""),
        help="Optional Hub password (or set OOL_PASSWORD env var)",
    )
    parser.add_argument(
        "--transport",
        choices=[TRANSPORT_AUTO, TRANSPORT_LOCAL, TRANSPORT_CLOUD],
        default=TRANSPORT_AUTO,
        help="Transport mode (auto tries local TCP 8087, falls back to AWS IoT MQTT)",
    )

    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("list", help="List all themes, effects, and songs")
    sub.add_parser("discover", help="Discover hubs on local LAN via UDP 8087")
    sub.add_parser("status", help="Fetch full hub status, RSSI, and paired devices")

    p_pow = sub.add_parser("power", help="Turn lights on/off")
    p_pow.add_argument("state", choices=["on", "off"])

    p_rgb = sub.add_parser("rgb", help="Set custom RGB color")
    p_rgb.add_argument("r", type=int)
    p_rgb.add_argument("g", type=int)
    p_rgb.add_argument("b", type=int)
    p_rgb.add_argument("--brightness", "-b", type=int, default=100)

    p_theme = sub.add_parser("theme", help="Set preset lightshow/theme and effect")
    p_theme.add_argument("theme", help="Theme ID or name (e.g. 'Christmas LightShow', 'Halloween', 'Red & Green')")
    p_theme.add_argument("--effect", "-e", default=None, help="Effect ID or name (Steady, Glimmer, Sparkle, Starry Night, Lightshow)")

    p_play = sub.add_parser("play", help="Play a song (0..11)")
    p_play.add_argument("song", type=int)

    sub.add_parser("pause", help="Pause music")
    sub.add_parser("resume", help="Resume music")

    p_vol = sub.add_parser("volume", help="Set volume (0..100)")
    p_vol.add_argument("level", type=int)

    p_bt = sub.add_parser("bt", help="Toggle Bluetooth speaker mode")
    p_bt.add_argument("state", choices=["on", "off"])

    p_timer = sub.add_parser("timer", help="Enable/disable built-in hub timer")
    p_timer.add_argument("state", choices=["on", "off"])
    p_timer.add_argument("--start", help="Start time HH:MM")
    p_timer.add_argument("--stop", help="Stop time HH:MM")

    args = parser.parse_args()
    asyncio.run(_run(args))


if __name__ == "__main__":
    main()
