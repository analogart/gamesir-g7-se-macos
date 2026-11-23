import ctypes
import ctypes.util
import json
import math
import os
import pathlib
import shutil
import struct
import subprocess
import sys
import time
import usb.backend.libusb1
import usb.core
import usb.util
from pynput.keyboard import Controller as KbController, Key
from pynput.mouse import Controller as MouseController, Button

from app_paths import find_libusb_path, get_config_path

try:
    from AppKit import NSWorkspace
except ImportError:
    NSWorkspace = None

LIVE_STATE_PATH = "/tmp/gamesir_live.json"

# (VID, PID, Model Name, Protocol: "gip" | "vendor_usb" | "vendor_hid")
SUPPORTED_DEVICES = [
    # Xbox GIP family (G7 SE, G7, G7 HE, T4 Kaleid)
    (0x3537, 0x1010, "GameSir G7 SE", "gip"),
    (0x3537, 0x1001, "GameSir G7", "gip"),
    (0x3537, 0x1002, "GameSir T4 Kaleid", "gip"),
    (0x3537, 0x1004, "GameSir T4 Kaleid (XUSB)", "gip"),
    (0x3537, 0x1007, "GameSir G7 HE", "gip"),
    (0x3537, 0x100F, "GameSir G7 SE (Alt)", "gip"),
    (0x3537, 0x1022, "GameSir G7 Pro (GIP)", "gip"),
    (0x3537, 0x1069, "GameSir G7 SE (Rev B)", "gip"),
    (0x3537, 0x106D, "GameSir G7 SE (Rev C)", "gip"),
    (0x3537, 0x1071, "GameSir G7 SE (Rev D)", "gip"),
    (0x3537, 0x1073, "GameSir G7 SE (Rev E)", "gip"),
    (0x3537, 0x1075, "GameSir G7 SE (Rev F)", "gip"),
    (0x3537, 0x1077, "GameSir G7 SE (Rev G)", "gip"),
    (0x3537, 0x108F, "GameSir G7 SE (Rev H)", "gip"),
    (0x3537, 0x10A0, "GameSir G7 SE (XInput)", "gip"),
    # Vendor GameSir USB family (G7 Pro)
    (0x3537, 0x1003, "GameSir G7 Pro", "vendor_usb"),
    (0x3537, 0x105D, "GameSir G7 Pro (USB)", "vendor_usb"),
    (0x3537, 0x105E, "GameSir G7 Pro (USB B)", "vendor_usb"),
    (0x3537, 0x109B, "GameSir G7 Pro (USB C)", "vendor_usb"),
    (0x3537, 0x109C, "GameSir G7 Pro (USB D)", "vendor_usb"),
    (0x3537, 0x10BA, "GameSir G7 Pro (USB E)", "vendor_usb"),
    # Vendor GameSir Enhanced HID family (Cyclone 2, G7 Pro 8K PC)
    (0x3537, 0x0575, "GameSir Cyclone 2", "vendor_hid"),
    (0x3537, 0x100B, "GameSir Cyclone 2 (Dongle)", "vendor_hid"),
    (0x3537, 0x1053, "GameSir Cyclone 2 (Wired)", "vendor_hid"),
    (0x3537, 0x10C5, "GameSir G7 Pro 8K PC", "vendor_hid"),
    (0x3537, 0x10C6, "GameSir G7 Pro 8K PC (B)", "vendor_hid"),
    (0x3537, 0x10C7, "GameSir G7 Pro 8K PC (C)", "vendor_hid"),
    (0x3537, 0x10C8, "GameSir G7 Pro 8K PC (D)", "vendor_hid"),
]

SPECIAL_KEYS = {
    "enter": Key.enter,
    "esc": Key.esc,
    "space": Key.space,
    "tab": Key.tab,
    "backspace": Key.backspace,
    "shift": Key.shift,
    "ctrl": Key.ctrl,
    "cmd": Key.cmd,
    "up": Key.up,
    "down": Key.down,
    "left": Key.left,
    "right": Key.right,
    "page_up": Key.page_up,
    "page_down": Key.page_down,
    "f1": Key.f1,
    "f2": Key.f2,
    "f3": Key.f3,
    "f4": Key.f4,
    "f5": Key.f5,
    "f6": Key.f6,
    "f7": Key.f7,
    "f8": Key.f8,
    "f9": Key.f9,
    "f10": Key.f10,
    "f11": Key.f11,
    "f12": Key.f12,
    "f13": Key.f13,
    "f14": Key.f14,
    "f15": Key.f15,
    "vol_up": Key.media_volume_up,
    "vol_down": Key.media_volume_down,
    "mute": Key.media_volume_mute,
    "play_pause": Key.media_play_pause,
}

# Standard Xbox GIP input packet (cmd 0x20) bit offsets
BIT_MAP = {
    "A": (4, 16),
    "B": (4, 32),
    "X": (4, 64),
    "Y": (4, 128),
    "MENU": (4, 4),
    "VIEW": (4, 8),
    "SHARE": (4, 2),
    "UP": (5, 1),
    "DOWN": (5, 2),
    "LEFT": (5, 4),
    "RIGHT": (5, 8),
    "LB": (5, 16),
    "RB": (5, 32),
    "L3": (5, 64),
    "R3": (5, 128),
}

# Vendor 64-byte extra buttons at byte 60 (from OpenJoystickDriver GameSirDriver)
EXTRA_BYTE60_MAP = {
    "SHARE": 0x02,
    "L4": 0x08,
    "R4": 0x10,
    "M": 0x20,
    "L5": 0x40,
    "R5": 0x80,
}

ALL_DIGITAL_BUTTONS = list(BIT_MAP.keys()) + ["L4", "R4", "L5", "R5", "M"]


def clamp_axis(val):
    return max(-32768, min(32767, int(val)))


def calc_radial_vector(rx, ry, deadzone, max_speed, curve=1.8):
    mag = math.hypot(rx, ry)
    if mag <= deadzone:
        return 0.0, 0.0
    norm = (min(mag, 32768.0) - deadzone) / (32768.0 - deadzone)
    scaled = (norm**curve) * max_speed
    return (rx / mag) * scaled, (ry / mag) * scaled


def _run_macos_shortcut(sc_name: str):
    if not sc_name:
        return
    shortcuts_bin = shutil.which("shortcuts") or (
        "/usr/bin/shortcuts" if os.path.exists("/usr/bin/shortcuts") else None
    )
    if shortcuts_bin:
        try:
            subprocess.Popen([shortcuts_bin, "run", sc_name])
        except Exception:
            pass


class VirtualGamepadPublisher:
    """Publishes a native macOS HID gamepad via IOHIDUserDevice when entitled/available."""

    # Standard Xbox-style HID Report Descriptor (14 bytes report: buttons, hat, X, Y, Z, Rz, LT, RT)
    HID_DESCRIPTOR = bytes([
        0x05, 0x01,        # Usage Page (Generic Desktop)
        0x09, 0x05,        # Usage (Game Pad)
        0xA1, 0x01,        # Collection (Application)
        0x85, 0x01,        #   Report ID (1)
        0x05, 0x09,        #   Usage Page (Button)
        0x19, 0x01,        #   Usage Minimum (Button 1)
        0x29, 0x10,        #   Usage Maximum (Button 16)
        0x15, 0x00,        #   Logical Minimum (0)
        0x25, 0x01,        #   Logical Maximum (1)
        0x75, 0x01,        #   Report Size (1)
        0x95, 0x10,        #   Report Count (16)
        0x81, 0x02,        #   Input (Data,Var,Abs)
        0x05, 0x01,        #   Usage Page (Generic Desktop)
        0x09, 0x39,        #   Usage (Hat switch)
        0x15, 0x01,        #   Logical Minimum (1)
        0x25, 0x08,        #   Logical Maximum (8)
        0x35, 0x00,        #   Physical Minimum (0)
        0x46, 0x3B, 0x01,  #   Physical Maximum (315)
        0x65, 0x14,        #   Unit (Eng Rot: Angular Pos)
        0x75, 0x04,        #   Report Size (4)
        0x95, 0x01,        #   Report Count (1)
        0x81, 0x42,        #   Input (Data,Var,Abs,Null)
        0x75, 0x04,        #   Report Size (4)
        0x95, 0x01,        #   Report Count (1)
        0x81, 0x03,        #   Input (Const,Var,Abs)
        0x05, 0x01,        #   Usage Page (Generic Desktop)
        0x09, 0x30,        #   Usage (X)
        0x09, 0x31,        #   Usage (Y)
        0x09, 0x32,        #   Usage (Z)
        0x09, 0x35,        #   Usage (Rz)
        0x16, 0x00, 0x80,  #   Logical Minimum (-32768)
        0x26, 0xFF, 0x7F,  #   Logical Maximum (32767)
        0x75, 0x10,        #   Report Size (16)
        0x95, 0x04,        #   Report Count (4)
        0x81, 0x02,        #   Input (Data,Var,Abs)
        0x05, 0x02,        #   Usage Page (Simulation Controls)
        0x09, 0xC5,        #   Usage (Brake / LT)
        0x09, 0xC4,        #   Usage (Accelerator / RT)
        0x15, 0x00,        #   Logical Minimum (0)
        0x26, 0xFF, 0x03,  #   Logical Maximum (1023)
        0x75, 0x10,        #   Report Size (16)
        0x95, 0x02,        #   Report Count (2)
        0x81, 0x02,        #   Input (Data,Var,Abs)
        0xC0,              # End Collection
    ])

    def __init__(self):
        self.active = False
        self._device = None
        self._iokit = None
        self._cf = None
        self._try_init()

    def _try_init(self):
        try:
            iokit_path = ctypes.util.find_library("IOKit")
            cf_path = ctypes.util.find_library("CoreFoundation")
            if not iokit_path or not cf_path:
                return
            self._iokit = ctypes.CDLL(iokit_path)
            self._cf = ctypes.CDLL(cf_path)

            self._cf.CFStringCreateWithCString.argtypes = [ctypes.c_void_p, ctypes.c_char_p, ctypes.c_uint32]
            self._cf.CFStringCreateWithCString.restype = ctypes.c_void_p
            self._cf.CFDataCreate.argtypes = [ctypes.c_void_p, ctypes.c_char_p, ctypes.c_long]
            self._cf.CFDataCreate.restype = ctypes.c_void_p
            self._cf.CFNumberCreate.argtypes = [ctypes.c_void_p, ctypes.c_long, ctypes.c_void_p]
            self._cf.CFNumberCreate.restype = ctypes.c_void_p
            self._cf.CFDictionaryCreateMutable.argtypes = [ctypes.c_void_p, ctypes.c_long, ctypes.c_void_p, ctypes.c_void_p]
            self._cf.CFDictionaryCreateMutable.restype = ctypes.c_void_p
            self._cf.CFDictionarySetValue.argtypes = [ctypes.c_void_p, ctypes.c_void_p, ctypes.c_void_p]
            self._cf.CFRelease.argtypes = [ctypes.c_void_p]

            self._iokit.IOHIDUserDeviceCreate.argtypes = [ctypes.c_void_p, ctypes.c_void_p]
            self._iokit.IOHIDUserDeviceCreate.restype = ctypes.c_void_p
            self._iokit.IOHIDUserDeviceHandleReport.argtypes = [ctypes.c_void_p, ctypes.c_char_p, ctypes.c_long]
            self._iokit.IOHIDUserDeviceHandleReport.restype = ctypes.c_int

            def cf_str(s):
                return self._cf.CFStringCreateWithCString(None, s.encode("utf-8"), 0x08000100)

            def cf_int(val):
                c_val = ctypes.c_int32(val)
                return self._cf.CFNumberCreate(None, 3, ctypes.byref(c_val))

            props = self._cf.CFDictionaryCreateMutable(None, 0, None, None)
            desc_data = self._cf.CFDataCreate(None, self.HID_DESCRIPTOR, len(self.HID_DESCRIPTOR))
            self._cf.CFDictionarySetValue(props, cf_str("ReportDescriptor"), desc_data)
            self._cf.CFDictionarySetValue(props, cf_str("VendorID"), cf_int(0x045E))
            self._cf.CFDictionarySetValue(props, cf_str("ProductID"), cf_int(0x02FD))
            self._cf.CFDictionarySetValue(props, cf_str("Product"), cf_str("GameSir Virtual Xbox Controller"))
            self._cf.CFDictionarySetValue(props, cf_str("Manufacturer"), cf_str("GameSir Bridge"))
            self._cf.CFDictionarySetValue(props, cf_str("Transport"), cf_str("USB"))

            dev = self._iokit.IOHIDUserDeviceCreate(None, props)
            if dev:
                self._device = dev
                self.active = True
        except Exception:
            self.active = False

    def send_state(self, held, lx, ly, rx, ry, lt, rt):
        if not self.active or not self._device:
            return False
        btn_bits = 0
        btn_order = ["A", "B", "X", "Y", "LB", "RB", "VIEW", "MENU", "L3", "R3", "SHARE", "L4", "R4", "L5", "R5", "M"]
        for idx, name in enumerate(btn_order):
            if name in held:
                btn_bits |= (1 << idx)

        up, down, left, right = "UP" in held, "DOWN" in held, "LEFT" in held, "RIGHT" in held
        hat = 0
        if up and right:
            hat = 2
        elif down and right:
            hat = 4
        elif down and left:
            hat = 6
        elif up and left:
            hat = 8
        elif up:
            hat = 1
        elif right:
            hat = 3
        elif down:
            hat = 5
        elif left:
            hat = 7

        # Invert Y for standard HID GamePad convention (-32768 = up)
        hid_ly = clamp_axis(-ly)
        hid_ry = clamp_axis(-ry)
        report = struct.pack(
            "<BHhhhhHH",
            0x01,
            btn_bits,
            hat & 0x0F,
            clamp_axis(lx),
            hid_ly,
            clamp_axis(rx),
            hid_ry,
            max(0, min(1023, int(lt))),
            max(0, min(1023, int(rt))),
        )
        try:
            res = self._iokit.IOHIDUserDeviceHandleReport(self._device, report, len(report))
            return res == 0
        except Exception:
            return False

    def close(self):
        if self._device and self._cf:
            try:
                self._cf.CFRelease(self._device)
            except Exception:
                pass
        self._device = None
        self.active = False


class GameSirBridge:
    def __init__(
        self,
        initial_profile=None,
        on_status=None,
        on_profile_osd=None,
        on_quick_hud=None,
    ):
        self.config_path = get_config_path()
        self._last_mtime = 0.0
        self._last_live_write = 0.0
        self._last_keepalive = 0.0
        self._usb_backend = self._init_usb_backend()
        self.reload_config(initial_profile)
        self.on_status = on_status
        self.on_profile_osd = on_profile_osd
        self.on_quick_hud = on_quick_hud
        self.running = False
        self.connected_name = None
        self.connected_protocol = None
        self.battery_pct = None
        self.ep_out = None
        self.kb, self.mouse = KbController(), MouseController()
        self.virtual_pad = VirtualGamepadPublisher()
        self.pressed_keys, self.pressed_mouse = set(), set()
        self.active_combos, self.suppressed_buttons = set(), set()
        self.toggled_actions = set()
        self.prev_physical_held = set()
        self.turbo_timers = {}
        self.raw_axes = (0, 0, 0, 0)
        self._vendor_seq = 0
        self._extra_held = set()
        self._rem_x = self._rem_y = self._scroll_rem_x = self._scroll_rem_y = 0.0

    @staticmethod
    def _init_usb_backend():
        lib_path = find_libusb_path()
        if lib_path:
            backend = usb.backend.libusb1.get_backend(find_library=lambda _: lib_path)
            if backend is not None:
                return backend
        return usb.backend.libusb1.get_backend()

    def reload_config(self, override_profile=None):
        try:
            self._last_mtime = self.config_path.stat().st_mtime
        except OSError:
            pass
        self.cfg = json.loads(self.config_path.read_text(encoding="utf-8"))
        if override_profile and override_profile in self.cfg["profiles"]:
            self.current_profile = override_profile
        elif getattr(self, "current_profile", None) not in self.cfg["profiles"]:
            self.current_profile = self.cfg.get("active_profile") or next(
                iter(self.cfg["profiles"])
            )

    def _check_hot_reload(self):
        try:
            mtime = self.config_path.stat().st_mtime
            if mtime > self._last_mtime:
                self.release_all()
                self.reload_config()
                if self.on_status:
                    self.on_status(self.connected_name, self.current_profile)
        except Exception:
            pass

    def set_profile(self, name, vibrate=True, show_osd=True):
        if name in self.cfg["profiles"] and name != self.current_profile:
            self.release_all()
            self.current_profile = name
            if vibrate and self.cfg.get("rumble_feedback", True):
                self.rumble(45, 12)
            if self.on_status:
                self.on_status(self.connected_name, self.current_profile)
            if show_osd and self.on_profile_osd:
                self.on_profile_osd(self.current_profile)

    def rumble(self, strength=50, duration_10ms=15):
        if not self.ep_out:
            return
        try:
            if self.connected_protocol == "gip":
                self.ep_out.write(
                    [
                        0x09,
                        0x00,
                        0x00,
                        0x09,
                        0x00,
                        0x0F,
                        0x00,
                        0x00,
                        strength,
                        strength,
                        duration_10ms,
                        0x00,
                        0x00,
                    ]
                )
            else:
                # Enhanced HID / Vendor 64-byte rumble report (Report ID 0x0F)
                pkt = [0x0F, 0x01, strength, strength, duration_10ms] + [0x00] * 59
                self.ep_out.write(pkt)
        except Exception:
            pass

    def release_all(self):
        for k in list(self.pressed_keys):
            try:
                self.kb.release(k)
            except Exception:
                pass
        for b in list(self.pressed_mouse):
            try:
                self.mouse.release(b)
            except Exception:
                pass
        if self.virtual_pad.active:
            self.virtual_pad.send_state(set(), 0, 0, 0, 0, 0, 0)
        self.pressed_keys.clear()
        self.pressed_mouse.clear()
        self.toggled_actions.clear()
        self.prev_physical_held.clear()
        self.turbo_timers.clear()
        self._rem_x = self._rem_y = self._scroll_rem_x = self._scroll_rem_y = 0.0

    def trigger_macro(self, combo_str):
        val = combo_str.strip()
        if val.lower().startswith("shortcut:"):
            sc_name = val.split(":", 1)[1].strip()
            _run_macos_shortcut(sc_name)
            return
        keys = [
            SPECIAL_KEYS.get(k.strip().lower(), k.strip().lower())
            for k in val.split("+")
            if k.strip()
        ]
        for k in keys:
            self.kb.press(k)
        time.sleep(0.04)
        for k in reversed(keys):
            self.kb.release(k)

    def _write_live_state(self, held_list, lx, ly, rx, ry, lt, rt, shift_active=False):
        now = time.time()
        if now - self._last_live_write < 0.08:
            return
        self._last_live_write = now
        try:
            payload = {
                "connected": self.connected_name,
                "protocol": self.connected_protocol,
                "battery": self.battery_pct,
                "virtual_gamepad_ready": self.virtual_pad.active,
                "profile": self.current_profile,
                "shift_active": shift_active,
                "held": held_list,
                "lx": lx,
                "ly": ly,
                "rx": rx,
                "ry": ry,
                "raw_lx": self.raw_axes[0],
                "raw_ly": self.raw_axes[1],
                "raw_rx": self.raw_axes[2],
                "raw_ry": self.raw_axes[3],
                "lt": lt,
                "rt": rt,
                "ts": now,
            }
            tmp_path = f"{LIVE_STATE_PATH}.tmp"
            with open(tmp_path, "w", encoding="utf-8") as f:
                json.dump(payload, f)
            os.replace(tmp_path, LIVE_STATE_PATH)
        except Exception:
            pass

    def _send_vendor_keepalive(self):
        if not self.ep_out or self.connected_protocol not in ("vendor_usb", "vendor_hid"):
            return
        now = time.time()
        if now - self._last_keepalive < 0.45:
            return
        self._last_keepalive = now
        self._vendor_seq = (self._vendor_seq + 1) & 0xFF
        try:
            if self.connected_protocol == "vendor_hid":
                pkt = [0x0F, 0xF2] + [0x00] * 62
            else:
                pkt = [0x0F, 0x00, self._vendor_seq, 0x02, 0xF2] + [0x00] * 59
            self.ep_out.write(pkt)
        except Exception:
            pass

    def _connect(self):
        if self._usb_backend is None:
            self._usb_backend = self._init_usb_backend()
        for vid, pid, name, proto in SUPPORTED_DEVICES:
            try:
                dev = usb.core.find(
                    idVendor=vid, idProduct=pid, backend=self._usb_backend
                )
            except usb.core.USBError:
                continue
            if dev is not None:
                try:
                    dev.set_configuration()
                    usb.util.claim_interface(dev, 0)
                    intf = dev.get_active_configuration()[(0, 0)]
                    ep_out = usb.util.find_descriptor(
                        intf,
                        custom_match=lambda e: usb.util.endpoint_direction(
                            e.bEndpointAddress
                        )
                        == usb.util.ENDPOINT_OUT,
                    )
                    ep_in = usb.util.find_descriptor(
                        intf,
                        custom_match=lambda e: usb.util.endpoint_direction(
                            e.bEndpointAddress
                        )
                        == usb.util.ENDPOINT_IN,
                    )
                    self.ep_out = ep_out
                    self.connected_name = name
                    self.connected_protocol = proto
                    self.battery_pct = None
                    self._extra_held.clear()
                    self._vendor_seq = 0

                    if proto == "gip":
                        seq, sent_power, t0 = 1, False, time.time()
                        while time.time() - t0 < 1.0:
                            try:
                                pkt = list(ep_in.read(64, timeout=100))
                                if len(pkt) >= 3 and (pkt[1] & 0x20):
                                    ep_out.write(
                                        [
                                            0x01,
                                            0x20,
                                            pkt[2],
                                            0x09,
                                            0x00,
                                            pkt[0],
                                            0x20,
                                            0x02,
                                            0x00,
                                            0x00,
                                            0x00,
                                            0x00,
                                            0x00,
                                        ]
                                    )
                                if not sent_power and pkt[0] in (0x02, 0x04, 0x07):
                                    ep_out.write([0x05, 0x20, seq, 0x01, 0x00])
                                    seq += 1
                                    time.sleep(0.05)
                                    ep_out.write(
                                        [0x0A, 0x20, seq, 0x03, 0x00, 0x01, 0x14]
                                    )
                                    seq += 1
                                    # Enable GameSir extra input reporting (L4/R4/M)
                                    time.sleep(0.03)
                                    ep_out.write([0x4D, 0x10, seq, 0x02, 0x07, 0x00])
                                    seq += 1
                                    sent_power = True
                                if len(pkt) >= 18 and pkt[0] == 32:
                                    break
                            except Exception:
                                pass
                    else:
                        self._last_keepalive = 0.0
                        self._send_vendor_keepalive()

                    if self.cfg.get("rumble_feedback", True):
                        self.rumble(60, 15)
                    return dev, ep_in
                except usb.core.USBError:
                    try:
                        usb.util.dispose_resources(dev)
                    except Exception:
                        pass
                    self.connected_name = None
                    self.connected_protocol = None
                    return None, None
        return None, None

    def _check_frontmost_app(self):
        if not NSWorkspace or not self.cfg.get("auto_switch", True):
            return
        app = NSWorkspace.sharedWorkspace().frontmostApplication()
        if app:
            app_name = (app.localizedName() or "").lower()
            if getattr(self, "_last_app_name", None) == app_name:
                return
            self._last_app_name = app_name
            for keyword, target_prof in self.cfg.get("app_rules", {}).items():
                if keyword.lower() in app_name:
                    self.set_profile(target_prof, vibrate=True, show_osd=True)
                    break

    def _set_input(self, action, pressed):
        if not action:
            return
        if action.lower().startswith("shortcut:"):
            if pressed:
                sc_name = action.split(":", 1)[1].strip()
                _run_macos_shortcut(sc_name)
            return
        if action in ("mouse_left", "mouse_right"):
            btn = Button.left if action == "mouse_left" else Button.right
            if pressed and btn not in self.pressed_mouse:
                self.mouse.press(btn)
                self.pressed_mouse.add(btn)
            elif not pressed and btn in self.pressed_mouse:
                self.mouse.release(btn)
                self.pressed_mouse.remove(btn)
        else:
            k = SPECIAL_KEYS.get(action.lower(), action)
            if pressed and k not in self.pressed_keys:
                self.kb.press(k)
                self.pressed_keys.add(k)
            elif not pressed and k in self.pressed_keys:
                self.kb.release(k)
                self.pressed_keys.remove(k)

    def run_forever(self):
        self.running, last_check = True, 0.0
        while self.running:
            rumble_req = pathlib.Path("/tmp/gamesir_rumble_test.json")
            if rumble_req.exists():
                try:
                    rumble_req.unlink(missing_ok=True)
                    self.rumble(75, 45)
                except Exception:
                    pass

            dev, ep_in = self._connect()
            if dev is None:
                self.connected_name = self.connected_protocol = self.ep_out = None
                self.battery_pct = None
                self.raw_axes = (0, 0, 0, 0)
                self._write_live_state([], 0, 0, 0, 0, 0, 0, False)
                if self.on_status:
                    self.on_status(None, self.current_profile)
                time.sleep(1.5)
                continue
            if self.on_status:
                self.on_status(self.connected_name, self.current_profile)
            try:
                while self.running:
                    now = time.time()
                    if now - last_check > 0.6:
                        self._check_hot_reload()
                        self._check_frontmost_app()
                        last_check = now
                    if self.connected_protocol in ("vendor_usb", "vendor_hid"):
                        self._send_vendor_keepalive()
                    try:
                        data = dev.read(
                            ep_in.bEndpointAddress, ep_in.wMaxPacketSize, timeout=16
                        )
                        if self.connected_protocol == "gip":
                            if len(data) >= 3 and data[0] not in (0x20, 0x0F) and (data[1] & 0x20):
                                self.ep_out.write(
                                    [
                                        0x01,
                                        0x20,
                                        data[2],
                                        0x09,
                                        0x00,
                                        data[0],
                                        0x20,
                                        0x02,
                                        0x00,
                                        0x00,
                                        0x00,
                                        0x00,
                                        0x00,
                                    ]
                                )
                            if len(data) >= 64 and data[0] == 0x0F and data[4] == 0xE0:
                                # GIP Vendor telemetry packet carrying back paddles (L4/R4/L5/R5/M)
                                self._extra_held = {
                                    bname for bname, mask in EXTRA_BYTE60_MAP.items() if bool(data[60] & mask)
                                }
                            elif len(data) >= 18 and data[0] == 0x20:
                                self._process_gip_packet(data)
                        else:
                            self._process_vendor_packet(data)
                    except usb.core.USBTimeoutError:
                        pass
            except usb.core.USBError:
                self.release_all()
                time.sleep(1.0)
            finally:
                try:
                    usb.util.release_interface(dev, 0)
                except Exception:
                    pass
                try:
                    usb.util.dispose_resources(dev)
                except Exception:
                    pass
                self.ep_out = None
        self.release_all()

    def _process_gip_packet(self, data):
        held = {
            name for name, (idx, mask) in BIT_MAP.items() if bool(data[idx] & mask)
        }
        held.update(self._extra_held)
        raw_lx, raw_ly = (
            struct.unpack("<h", bytes(data[10:12]))[0],
            struct.unpack("<h", bytes(data[12:14]))[0],
        )
        raw_rx, raw_ry = (
            struct.unpack("<h", bytes(data[14:16]))[0],
            struct.unpack("<h", bytes(data[16:18]))[0],
        )
        lt, rt = (
            struct.unpack("<H", bytes(data[6:8]))[0],
            struct.unpack("<H", bytes(data[8:10]))[0],
        )
        self._dispatch_parsed_state(held, raw_lx, raw_ly, raw_rx, raw_ry, lt, rt)

    def _process_vendor_packet(self, data):
        if len(data) == 20 and data[0] == 0x00 and data[1] == 0x14:
            # Standard 20-byte XUSB report on G7 Pro USB
            b2, b3 = data[2], data[3]
            held = set(self._extra_held)
            xusb_map = [
                (b2, 0x01, "UP"), (b2, 0x02, "DOWN"), (b2, 0x04, "LEFT"), (b2, 0x08, "RIGHT"),
                (b2, 0x10, "MENU"), (b2, 0x20, "VIEW"), (b2, 0x40, "L3"), (b2, 0x80, "R3"),
                (b3, 0x01, "LB"), (b3, 0x02, "RB"),
                (b3, 0x10, "A"), (b3, 0x20, "B"), (b3, 0x40, "X"), (b3, 0x80, "Y"),
            ]
            for byte_val, mask, name in xusb_map:
                if byte_val & mask:
                    held.add(name)
            lt = int(data[4]) * 4
            rt = int(data[5]) * 4
            raw_lx, raw_ly = struct.unpack("<h", bytes(data[6:8]))[0], struct.unpack("<h", bytes(data[8:10]))[0]
            raw_rx, raw_ry = struct.unpack("<h", bytes(data[10:12]))[0], struct.unpack("<h", bytes(data[12:14]))[0]
            self._dispatch_parsed_state(held, raw_lx, raw_ly, raw_rx, raw_ry, lt, rt)
            return

        if len(data) < 64:
            return

        if data[0] == 0x10 and data[3] == 0x3C and data[4] == 0xE0:
            # G7 Pro USB 64-byte telemetry packet (battery + L4/R4/L5/R5/M)
            self.battery_pct = min(100, int(data[33]))
            self._extra_held = {
                bname for bname, mask in EXTRA_BYTE60_MAP.items() if bool(data[60] & mask)
            }
            return

        if data[0] == 0x12:
            # Enhanced HID 64-byte report (Cyclone 2, G7 Pro 8K PC)
            self.battery_pct = min(100, int(data[36]))
            face = data[5]
            meta = data[6]
            held = set()
            hat = face & 0x0F
            hat_dirs = {
                0: ("UP",), 1: ("UP", "RIGHT"), 2: ("RIGHT",), 3: ("DOWN", "RIGHT"),
                4: ("DOWN",), 5: ("DOWN", "LEFT"), 6: ("LEFT",), 7: ("UP", "LEFT"),
            }
            for d in hat_dirs.get(hat, ()):
                held.add(d)
            for byte_val, mask, name in [
                (face, 0x10, "X"), (face, 0x20, "A"), (face, 0x40, "B"), (face, 0x80, "Y"),
                (meta, 0x01, "LB"), (meta, 0x02, "RB"), (meta, 0x10, "VIEW"),
                (meta, 0x20, "MENU"), (meta, 0x40, "L3"), (meta, 0x80, "R3"),
            ]:
                if byte_val & mask:
                    held.add(name)
            for bname, mask in EXTRA_BYTE60_MAP.items():
                if data[60] & mask:
                    held.add(bname)

            def u8_to_s16(v):
                return clamp_axis((int(v) - 128) * 256)

            raw_lx = u8_to_s16(data[1])
            raw_ly = u8_to_s16(255 - data[2])
            raw_rx = u8_to_s16(data[3])
            raw_ry = u8_to_s16(255 - data[4])
            lt = int(data[8]) * 4
            rt = int(data[9]) * 4
            self._dispatch_parsed_state(held, raw_lx, raw_ly, raw_rx, raw_ry, lt, rt)

    def _dispatch_parsed_state(self, held, raw_lx, raw_ly, raw_rx, raw_ry, lt, rt):
        prof = self.cfg["profiles"][self.current_profile]
        btns = prof["buttons"]
        shift_btn = prof.get("shift_button", "")
        shift_btns = prof.get("shift_buttons", {})
        turbo_set = set(prof.get("turbo_buttons", []))
        toggle_set = set(prof.get("toggle_buttons", []))
        turbo_hz = max(2, min(40, int(prof.get("turbo_rate", 12))))
        turbo_half_period = 0.5 / turbo_hz

        deadzone = prof.get("deadzone", self.cfg.get("deadzone", 10000))
        trig_thresh = prof.get(
            "trigger_threshold", self.cfg.get("trigger_threshold", 200)
        )
        cal = self.cfg.get("calibration", {})

        self.raw_axes = (raw_lx, raw_ly, raw_rx, raw_ry)

        lx = clamp_axis(raw_lx - int(cal.get("lx_offset", 0)))
        ly = clamp_axis(raw_ly - int(cal.get("ly_offset", 0)))
        rx = clamp_axis(raw_rx - int(cal.get("rx_offset", 0)))
        ry = clamp_axis(raw_ry - int(cal.get("ry_offset", 0)))

        physical_inputs = set(held)
        if lt > trig_thresh:
            physical_inputs.add("LT")
        if rt > trig_thresh:
            physical_inputs.add("RT")

        shift_active = bool(shift_btn and shift_btn in physical_inputs)
        self._write_live_state(
            sorted(physical_inputs), lx, ly, rx, ry, lt, rt, shift_active
        )

        # Native Virtual Gamepad output (when profile output_mode == "virtual_gamepad" and entitled)
        if prof.get("output_mode") == "virtual_gamepad" and self.virtual_pad.active:
            self.virtual_pad.send_state(physical_inputs, lx, ly, rx, ry, lt, rt)
            self.prev_physical_held = physical_inputs
            return

        self.suppressed_buttons.intersection_update(physical_inputs)

        if "VIEW" in held and "UP" in held:
            if "CYCLE" not in self.active_combos:
                self.active_combos.add("CYCLE")
                self.suppressed_buttons.update({"VIEW", "UP"})
                pl = list(self.cfg["profiles"].keys())
                self.set_profile(
                    pl[(pl.index(self.current_profile) + 1) % len(pl)],
                    vibrate=True,
                    show_osd=True,
                )
            self.prev_physical_held = physical_inputs
            return
        self.active_combos.discard("CYCLE")

        if "VIEW" in held and "DOWN" in held:
            if "HUD" not in self.active_combos:
                self.active_combos.add("HUD")
                self.suppressed_buttons.update({"VIEW", "DOWN"})
                if self.on_quick_hud:
                    self.on_quick_hud()
            self.prev_physical_held = physical_inputs
            return
        self.active_combos.discard("HUD")

        triggered = False
        for c_key, m_val in self.cfg.get("combos", {}).items():
            req = {b.strip() for b in c_key.split("+") if b.strip()}
            if req and req.issubset(physical_inputs):
                triggered = True
                if c_key not in self.active_combos:
                    self.active_combos.add(c_key)
                    self.suppressed_buttons.update(req)
                    self.release_all()
                    self.trigger_macro(m_val)
            else:
                self.active_combos.discard(c_key)
        if triggered:
            self.prev_physical_held = physical_inputs
            return

        is_mouse = prof.get("right_stick_mode") == "mouse"
        if is_mouse and ("LB" in held) and (math.hypot(rx, ry) > deadzone):
            self.suppressed_buttons.add("LB")

        now = time.time()
        all_btn_names = ALL_DIGITAL_BUTTONS + ["LT", "RT"]
        desired_actions = {}

        for name in all_btn_names:
            if shift_btn and name == shift_btn:
                continue

            phys_down = (name in physical_inputs) and (
                name not in self.suppressed_buttons
            )
            just_pressed = phys_down and (name not in self.prev_physical_held)

            base_act = btns.get(name, "")
            shift_act = shift_btns.get(name, "") if shift_active else ""
            action = shift_act if (shift_active and shift_act) else base_act

            if not action:
                continue

            if name in toggle_set:
                if just_pressed:
                    if action in self.toggled_actions:
                        self.toggled_actions.remove(action)
                    else:
                        self.toggled_actions.add(action)
                if action in self.toggled_actions:
                    desired_actions[action] = True
                else:
                    desired_actions.setdefault(action, False)
            elif name in turbo_set and phys_down:
                t0 = self.turbo_timers.setdefault(name, now)
                phase = int((now - t0) / turbo_half_period) % 2 == 0
                if phase:
                    desired_actions[action] = True
                else:
                    desired_actions.setdefault(action, False)
            else:
                self.turbo_timers.pop(name, None)
                if phys_down:
                    desired_actions[action] = True
                else:
                    desired_actions.setdefault(action, False)

        for action, state in desired_actions.items():
            self._set_input(action, state)

        self.prev_physical_held = physical_inputs
        self._process_sticks(prof, deadzone, lx, ly, rx, ry, is_mouse, held)

    def _process_sticks(self, prof, deadzone, lx, ly, rx, ry, is_mouse, held):
        ls = prof["left_stick"]
        if math.hypot(lx, ly) > deadzone:
            self._set_input(ls.get("left"), lx < -deadzone * 0.6)
            self._set_input(ls.get("right"), lx > deadzone * 0.6)
            self._set_input(ls.get("up"), ly > deadzone * 0.6)
            self._set_input(ls.get("down"), ly < -deadzone * 0.6)
        else:
            for d in ("left", "right", "up", "down"):
                self._set_input(ls.get(d), False)

        rs = prof["right_stick"]
        if is_mouse:
            curve = prof.get("mouse_curve", self.cfg.get("mouse_curve", 1.8))
            if "LB" in held:
                sx, sy = calc_radial_vector(
                    rx, ry, deadzone, prof.get("scroll_speed", 2.8), 1.5
                )
                self._scroll_rem_x += sx
                self._scroll_rem_y += sy
                ix, iy = int(self._scroll_rem_x), int(self._scroll_rem_y)
                if ix or iy:
                    self.mouse.scroll(ix, iy)
                    self._scroll_rem_x -= ix
                    self._scroll_rem_y -= iy
                self._rem_x = self._rem_y = 0.0
            else:
                mx, my = calc_radial_vector(
                    rx,
                    ry,
                    deadzone,
                    prof.get("mouse_speed", self.cfg.get("mouse_speed", 18)),
                    curve,
                )
                self._rem_x += mx
                self._rem_y -= my
                ix, iy = int(self._rem_x), int(self._rem_y)
                if ix or iy:
                    self.mouse.move(ix, iy)
                    self._rem_x -= ix
                    self._rem_y -= iy
                self._scroll_rem_x = self._scroll_rem_y = 0.0
        elif math.hypot(rx, ry) > deadzone:
            for d, c in (
                ("left", rx < -deadzone * 0.6),
                ("right", rx > deadzone * 0.6),
                ("up", ry > deadzone * 0.6),
                ("down", ry < -deadzone * 0.6),
            ):
                self._set_input(rs.get(d), c)
        else:
            for d in ("left", "right", "up", "down"):
                self._set_input(rs.get(d), False)


if __name__ == "__main__":
    p = sys.argv[1] if len(sys.argv) > 1 else None
    b = GameSirBridge(p, on_status=lambda d, pr: print(d or "Desconectado", pr))
    try:
        b.run_forever()
    except KeyboardInterrupt:
        b.running = False
        b.release_all()
