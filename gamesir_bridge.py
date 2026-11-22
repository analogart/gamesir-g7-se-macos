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

SUPPORTED_DEVICES = [
    (0x3537, 0x1010, "GameSir G7 SE"),
    (0x3537, 0x1001, "GameSir G7"),
    (0x3537, 0x1002, "GameSir T4 Kaleid"),
    (0x3537, 0x1007, "GameSir G7 HE"),
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
    "vol_up": Key.media_volume_up,
    "vol_down": Key.media_volume_down,
    "mute": Key.media_volume_mute,
    "play_pause": Key.media_play_pause,
}
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
        self._usb_backend = self._init_usb_backend()
        self.reload_config(initial_profile)
        self.on_status = on_status
        self.on_profile_osd = on_profile_osd
        self.on_quick_hud = on_quick_hud
        self.running, self.connected_name, self.ep_out = False, None, None
        self.kb, self.mouse = KbController(), MouseController()
        self.pressed_keys, self.pressed_mouse = set(), set()
        self.active_combos, self.suppressed_buttons = set(), set()
        self.toggled_actions = set()
        self.prev_physical_held = set()
        self.turbo_timers = {}
        self.raw_axes = (0, 0, 0, 0)
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
        if self.ep_out:
            try:
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

    def _connect(self):
        if self._usb_backend is None:
            self._usb_backend = self._init_usb_backend()
        for vid, pid, name in SUPPORTED_DEVICES:
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
                                sent_power = True
                            if len(pkt) >= 18 and pkt[0] == 32:
                                break
                        except Exception:
                            pass
                    self.ep_out, self.connected_name = ep_out, name
                    if self.cfg.get("rumble_feedback", True):
                        self.rumble(60, 15)
                    return dev, ep_in
                except usb.core.USBError:
                    try:
                        usb.util.dispose_resources(dev)
                    except Exception:
                        pass
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
            dev, ep_in = self._connect()
            if dev is None:
                self.connected_name = self.ep_out = None
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
                    try:
                        data = dev.read(
                            ep_in.bEndpointAddress, ep_in.wMaxPacketSize, timeout=16
                        )
                        if len(data) >= 3 and data[0] != 32 and (data[1] & 0x20):
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
                        if len(data) >= 18 and data[0] == 32:
                            self._process_packet(data)
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

    def _process_packet(self, data):
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

        held = {
            name for name, (idx, mask) in BIT_MAP.items() if bool(data[idx] & mask)
        }
        raw_lx, raw_ly = (
            struct.unpack("<h", bytes(data[10:12]))[0],
            struct.unpack("<h", bytes(data[12:14]))[0],
        )
        raw_rx, raw_ry = (
            struct.unpack("<h", bytes(data[14:16]))[0],
            struct.unpack("<h", bytes(data[16:18]))[0],
        )
        self.raw_axes = (raw_lx, raw_ly, raw_rx, raw_ry)

        lx = clamp_axis(raw_lx - int(cal.get("lx_offset", 0)))
        ly = clamp_axis(raw_ly - int(cal.get("ly_offset", 0)))
        rx = clamp_axis(raw_rx - int(cal.get("rx_offset", 0)))
        ry = clamp_axis(raw_ry - int(cal.get("ry_offset", 0)))

        lt, rt = (
            struct.unpack("<H", bytes(data[6:8]))[0],
            struct.unpack("<H", bytes(data[8:10]))[0],
        )

        physical_inputs = set(held)
        if lt > trig_thresh:
            physical_inputs.add("LT")
        if rt > trig_thresh:
            physical_inputs.add("RT")

        shift_active = bool(shift_btn and shift_btn in physical_inputs)
        self._write_live_state(
            sorted(physical_inputs), lx, ly, rx, ry, lt, rt, shift_active
        )

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
        all_btn_names = list(BIT_MAP.keys()) + ["LT", "RT"]
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
