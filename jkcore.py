#!/usr/bin/env python3
"""
jkcore - protocol, parser and BLE worker for JK BMS (JK02_32S, hardware 11.x).

Offsets follow syssi/esphome-jk-bms (components/jk_bms_ble/jk_bms_ble.cpp).
Read-only: only the "device info" and "cell info" requests are ever sent.
"""
import asyncio
import logging
import math
import struct
import threading
import time
import types


log = logging.getLogger("jkmon")

# --------------------------------------------------------------------------
# Protocol
# --------------------------------------------------------------------------
SERVICE_UUID = "0000ffe0-0000-1000-8000-00805f9b34fb"
CHAR_UUID = "0000ffe1-0000-1000-8000-00805f9b34fb"

HEADER = b"\x55\xAA\xEB\x90"  # start of every response frame
FRAME_LEN = 300  # CRC is the last (300th) byte, even if the BMS pads to 320
MAX_BUF = 384 + 16

CMD_CELL_INFO = 0x96
CMD_DEVICE_INFO = 0x97

FRAME_SETTINGS = 0x01
FRAME_CELL_INFO = 0x02
FRAME_DEVICE_INFO = 0x03

# JK02_32S: cell block is 16 bytes longer, resistance block another 16
OFF1 = 16
OFF2 = 32

# Names of error/alarm bits of the 32-bit bitmask. Only bits confirmed against the JK phone app are listed;
# other bits are shown as "bit N". English text here is translated in the GUI (see i18n.py).
ERROR_NAMES: dict = {
    4: "Cell overvoltage protection (OVP)",  # confirmed in the JK app ("Cell OVP"): charging may be stopped
    19: "Recommendation: change the BMS settings password",  # confirmed in the JK app
}
# Bits that are notices, not faults (shown in blue, not as a warning).
INFO_BITS = {19}


def checksum(data) -> int:
    return sum(data) & 0xFF


def build_command(cmd: int, value: int = 0, length: int = 0) -> bytes:
    """20-byte request frame: AA 55 90 EB <cmd> <len> <value LE32> ... <crc>"""
    f = bytearray(20)
    f[0:4] = b"\xAA\x55\x90\xEB"
    f[4] = cmd
    f[5] = length
    f[6:10] = (value & 0xFFFFFFFF).to_bytes(4, "little")
    f[19] = checksum(f[:19])
    return bytes(f)


class FrameAssembler:
    """Collects 20-byte BLE notifications into 300-byte frames."""

    def __init__(self):
        self.buf = bytearray()

    def feed(self, data: bytes):
        frames = []
        if len(self.buf) > MAX_BUF:
            log.warning("frame buffer overflow, dropping")
            self.buf.clear()
        if len(data) >= 4 and bytes(data[:4]) == HEADER:
            self.buf.clear()
        self.buf += data
        if len(self.buf) >= FRAME_LEN:
            frame = bytes(self.buf[:FRAME_LEN])
            self.buf.clear()
            if checksum(frame[:-1]) == frame[-1]:
                frames.append(frame)
            else:
                log.warning("CRC mismatch (got 0x%02X, expected 0x%02X)", frame[-1], checksum(frame[:-1]))
        return frames


def parse_cell_info(f: bytes) -> dict:
    u8 = lambda i: f[i]
    u16 = lambda i: struct.unpack_from("<H", f, i)[0]
    i16 = lambda i: struct.unpack_from("<h", f, i)[0]
    u32 = lambda i: struct.unpack_from("<I", f, i)[0]
    i32 = lambda i: struct.unpack_from("<i", f, i)[0]

    mask = u32(54 + OFF1)
    cells = []
    for i in range(32):
        v = u16(6 + 2 * i) / 1000
        r = u16(64 + OFF1 + 2 * i) / 1000
        enabled = bool(mask >> i & 1) if mask else v > 0
        if enabled:
            cells.append({"n": i + 1, "v": round(v, 3), "r": round(r, 3)})

    live = [c for c in cells if c["v"] > 0]
    if live:
        vmin = min(live, key=lambda c: c["v"])
        vmax = max(live, key=lambda c: c["v"])
        avg = sum(c["v"] for c in live) / len(live)
        stats = {
            "min": vmin["v"], "min_cell": vmin["n"],
            "max": vmax["v"], "max_cell": vmax["n"],
            "avg": round(avg, 3), "delta": round(vmax["v"] - vmin["v"], 3),
        }
        sum_cells = sum(c["v"] for c in live)
    else:
        stats = {"min": 0, "min_cell": 0, "max": 0, "max_cell": 0, "avg": 0, "delta": 0}
        sum_cells = 0.0

    pack_v = u32(118 + OFF2) / 1000
    current = i32(126 + OFF2) / 1000  # + charging, - discharging
    errors_raw = u32(134 + OFF2)
    errors = []
    error_bits = []
    for bit in range(32):
        if errors_raw >> bit & 1:
            error_bits.append(bit)
            errors.append(ERROR_NAMES.get(bit, f"bit {bit}"))

    absent = u16(182 + OFF2)  # bit0 MOS, bit1 T1 ... bit5 T5 (set = sensor absent)
    temps = {"mos": round(i16(112 + OFF2) / 10, 1)}
    temps["t1"] = round(i16(130 + OFF2) / 10, 1)
    temps["t2"] = round(i16(132 + OFF2) / 10, 1)
    for name, off, bit in (("t3", 226, 3), ("t4", 224, 4), ("t5", 222, 5)):
        if not (absent >> bit & 1):
            temps[name] = round(i16(off + OFF2) / 10, 1)

    # cross-check: pack voltage must roughly equal the sum of cell voltages
    sane = bool(live) and abs(pack_v - sum_cells) <= max(0.6, 0.02 * pack_v)

    return {
        "counter": u8(5),
        "pack_v": round(pack_v, 3),
        "current": round(current, 3),
        "power": round(pack_v * current, 1),
        "soc": u8(141 + OFF2),
        "soh": u8(158 + OFF2),
        "cap_remaining": round(u32(142 + OFF2) / 1000, 2),
        "cap_nominal": round(u32(146 + OFF2) / 1000, 2),
        "cycles": u32(150 + OFF2),
        "cycle_capacity": round(u32(154 + OFF2) / 1000, 1),
        "runtime_s": u32(162 + OFF2),
        "cells": cells,
        "cell_stats": stats,
        "cell_count": len(cells),
        "temps": temps,
        "balance_current": round(i16(138 + OFF2) / 1000, 3),
        "balance_mode": u8(140 + OFF2),  # 0 off, 1 charging balancer, 2 discharging balancer
        "chg_mos": bool(u8(166 + OFF2)),
        "dsg_mos": bool(u8(167 + OFF2)),
        "precharge": bool(u8(168 + OFF2)),
        "heating": bool(u8(183 + OFF2)),
        "heating_current": round(i16(204 + OFF2) / 1000, 3),
        "errors_raw": f"0x{errors_raw:08X}",
        "errors": errors,
        "error_bits": error_bits,
        "sane": sane,
    }


def _cstr(b: bytes) -> str:
    s = bytes(b).split(b"\0")[0].decode("ascii", "ignore").strip()
    return s if s.isprintable() else ""


def parse_device_info(f: bytes) -> dict:
    """Best effort; layout from esphome-jk-bms decode_device_info_."""
    return {
        "vendor": _cstr(f[6:22]),
        "hw": _cstr(f[22:30]),
        "sw": _cstr(f[30:38]),
        "uptime_s": struct.unpack_from("<I", f, 38)[0],
        "power_on": struct.unpack_from("<I", f, 42)[0],
    }


# --------------------------------------------------------------------------
# Synthetic frames (for --demo and self tests)
# --------------------------------------------------------------------------
def build_demo_frame(t: float, counter: int = 0, cells: int = 8) -> bytes:
    f = bytearray(FRAME_LEN)
    f[0:4] = HEADER
    f[4] = FRAME_CELL_INFO
    f[5] = counter & 0xFF
    total = 0
    for i in range(cells):
        mv = int(3320 + 25 * math.sin(t / 7 + i) + (18 if i == 3 else 0))
        total += mv
        struct.pack_into("<H", f, 6 + 2 * i, mv)
        struct.pack_into("<H", f, 64 + OFF1 + 2 * i, 1 + i % 3)
    struct.pack_into("<I", f, 54 + OFF1, (1 << cells) - 1)
    current_ma = int(12000 * math.sin(t / 15))
    struct.pack_into("<h", f, 112 + OFF2, 312)
    struct.pack_into("<I", f, 118 + OFF2, total)
    struct.pack_into("<i", f, 126 + OFF2, current_ma)
    struct.pack_into("<h", f, 130 + OFF2, 241)
    struct.pack_into("<h", f, 132 + OFF2, 236)
    struct.pack_into("<h", f, 138 + OFF2, 480 if int(t) % 20 < 10 else 0)
    f[140 + OFF2] = 1 if int(t) % 20 < 10 else 0
    f[141 + OFF2] = 67
    struct.pack_into("<I", f, 142 + OFF2, 134000)
    struct.pack_into("<I", f, 146 + OFF2, 200000)
    struct.pack_into("<I", f, 150 + OFF2, 42)
    struct.pack_into("<I", f, 154 + OFF2, 8400000)
    f[158 + OFF2] = 98
    struct.pack_into("<I", f, 162 + OFF2, 5_400_000)
    f[166 + OFF2] = 1
    f[167 + OFF2] = 1
    struct.pack_into("<H", f, 182 + OFF2, 0b111000)  # T3..T5 absent
    f[-1] = checksum(f[:-1])
    return bytes(f)


def build_demo_device_info() -> bytes:
    f = bytearray(FRAME_LEN)
    f[0:4] = HEADER
    f[4] = FRAME_DEVICE_INFO
    f[6:6 + 11] = b"JK_B2A8S20P"
    f[22:22 + 4] = b"V11A"
    f[30:30 + 6] = b"V11.54"
    struct.pack_into("<I", f, 38, 5_400_000)
    struct.pack_into("<I", f, 42, 180)
    f[-1] = checksum(f[:-1])
    return bytes(f)


# --------------------------------------------------------------------------
# State holder + web server
# --------------------------------------------------------------------------
class Monitor:
    def __init__(self, raw_log: str | None = None):
        self.status = "starting"
        self.address = None
        self.device = {}
        self.data = None
        self.last_frame = 0.0  # monotonic
        self.last_raw = b""
        self.raw_log = raw_log

    def snapshot(self) -> dict:
        age = round(time.monotonic() - self.last_frame, 1) if self.last_frame else None
        return {
            "status": self.status,
            "address": self.address,
            "device": self.device,
            "data": self.data,
            "age": age,
        }

    def set_status(self, status: str, address: str | None = None):
        self.status = status
        if address:
            self.address = address
        self.notify()

    def on_frame(self, frame: bytes):
        ftype = frame[4]
        if self.raw_log:
            with open(self.raw_log, "a") as fh:
                fh.write(f"{time.time():.3f} {ftype:02X} {frame.hex()}\n")
        if ftype == FRAME_CELL_INFO:
            try:
                self.data = parse_cell_info(frame)
            except Exception:
                log.exception("failed to parse cell info frame")
                return
            self.last_frame = time.monotonic()
            self.last_raw = frame
            self.status = "connected"
        elif ftype == FRAME_DEVICE_INFO:
            self.device = parse_device_info(frame)
            log.info("device info: %s", self.device)
        elif ftype == FRAME_SETTINGS:
            log.debug("settings frame ignored")
        else:
            log.debug("unknown frame type 0x%02X", ftype)
        self.notify()

    def notify(self):
        pass  # the GUI polls snapshot()


# --------------------------------------------------------------------------
# Data sources
# --------------------------------------------------------------------------
async def demo_loop(mon: Monitor):
    mon.set_status("connected", "DEMO")
    mon.on_frame(build_demo_device_info())
    n = 0
    while True:
        mon.on_frame(build_demo_frame(time.time(), n))
        n += 1
        await asyncio.sleep(1)


def _pick_chars(client):
    notify_ch = write_ch = None
    for svc in client.services:
        if svc.uuid.lower() != SERVICE_UUID:
            continue
        for ch in svc.characteristics:
            if ch.uuid.lower() != CHAR_UUID:
                continue
            props = set(ch.properties)
            if notify_ch is None and ({"notify", "indicate"} & props):
                notify_ch = ch
            if write_ch is None and ({"write", "write-without-response"} & props):
                write_ch = ch
    return notify_ch, write_ch


async def ble_loop(mon: Monitor, args):
    from bleak import BleakClient, BleakScanner

    prefix = args.name_prefix.upper()
    delay = 3
    while True:
        try:
            mon.set_status("scanning")
            if args.address:
                dev = await BleakScanner.find_device_by_address(args.address, timeout=15)
            else:
                dev = await BleakScanner.find_device_by_filter(
                    lambda d, adv: ((d.name or adv.local_name or "").upper().startswith(prefix)),
                    timeout=15,
                )
            if dev is None:
                log.info("no BMS found, retrying")
                mon.set_status("offline")
                await asyncio.sleep(delay)
                continue

            log.info("found %s (%s)", dev.name, dev.address)

            pin = getattr(args, "pin", None)
            if pin:
                mon.set_status("pairing", dev.address)
                try:
                    from blepair import PairError, ensure_paired
                    await ensure_paired(dev.address, pin)
                except PairError as e:
                    # Most JK BMS do not use Bluetooth pairing at all, so just try to connect anyway.
                    log.warning("Pairing failed (%s), trying to connect without it", e)
                except Exception as e:  # noqa: BLE001 - e.g. no D-Bus; try to connect anyway
                    log.warning("pairing step skipped: %r", e)

            mon.set_status("connecting", dev.address)
            gone = asyncio.Event()
            asm = FrameAssembler()

            async with BleakClient(dev, disconnected_callback=lambda c: gone.set(), timeout=20) as client:
                notify_ch, write_ch = _pick_chars(client)
                if notify_ch is None or write_ch is None:
                    raise RuntimeError("FFE0/FFE1 characteristics not found - not a JK BMS?")
                use_response = "write-without-response" not in write_ch.properties

                async def send(cmd):
                    await client.write_gatt_char(write_ch, build_command(cmd), response=use_response)

                def on_notify(_, data: bytearray):
                    for frame in asm.feed(bytes(data)):
                        mon.on_frame(frame)

                await client.start_notify(notify_ch, on_notify)
                await send(CMD_DEVICE_INFO)
                await asyncio.sleep(0.6)
                await send(CMD_CELL_INFO)
                mon.last_frame = 0.0
                mon.set_status("connected", dev.address)
                delay = 3
                started = time.monotonic()

                while not gone.is_set():
                    await asyncio.sleep(1)
                    idle = time.monotonic() - (mon.last_frame or started)
                    if idle > 30:
                        log.warning("no data for 30 s, reconnecting")
                        break
                    if idle > 5:
                        await send(CMD_CELL_INFO)  # BMS stops streaming sometimes; ask again
        except asyncio.CancelledError:
            raise
        except Exception as e:  # noqa: BLE001
            log.warning("BLE error: %r", e)
        mon.set_status("offline")
        await asyncio.sleep(delay)
        delay = min(delay * 2, 30)


# --------------------------------------------------------------------------
# Worker thread + scanner used by the GUI
# --------------------------------------------------------------------------
class BmsWorker(threading.Thread):
    """Runs the BLE loop (or the demo) in its own asyncio loop. Read worker.mon.snapshot()."""

    def __init__(self, address=None, pin=None, demo=False, name_prefix="JK"):
        super().__init__(daemon=True)
        self.args = types.SimpleNamespace(address=address, pin=pin, name_prefix=name_prefix)
        self.demo = demo
        self.mon = Monitor()
        self.loop = None
        self._task = None
        self._ready = threading.Event()

    def run(self):
        self.loop = asyncio.new_event_loop()
        asyncio.set_event_loop(self.loop)
        coro = demo_loop(self.mon) if self.demo else ble_loop(self.mon, self.args)
        self._task = self.loop.create_task(coro)
        self._ready.set()
        try:
            self.loop.run_until_complete(self._task)
        except asyncio.CancelledError:
            pass
        except Exception:  # noqa: BLE001
            log.exception("worker crashed")
        finally:
            self.loop.close()

    def stop(self):
        self._ready.wait(3)
        if self.loop is not None and self._task is not None and not self.loop.is_closed():
            self.loop.call_soon_threadsafe(self._task.cancel)
        self.join(timeout=8)


def scan_devices(timeout: float = 8.0) -> dict:
    """Blocking BLE scan. Returns {address: {"name", "rssi", "ffe0"}}."""
    async def go():
        from bleak import BleakScanner
        return await BleakScanner.discover(timeout=timeout, return_adv=True)

    found = {}
    for addr, (dev, adv) in asyncio.run(go()).items():
        found[addr] = {
            "name": dev.name or adv.local_name or "",
            "rssi": adv.rssi,
            "ffe0": any(u.lower().startswith("0000ffe0") for u in adv.service_uuids),
        }
    return found
