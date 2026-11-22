import json, pathlib, struct, sys, time, usb.core, usb.util
from pynput.keyboard import Controller as KbController, Key
from pynput.mouse import Controller as MouseController, Button

try:
    from AppKit import NSWorkspace
except ImportError:
    NSWorkspace = None

SUPPORTED_DEVICES = [
    (0x3537, 0x1010, "GameSir G7 SE"),
    (0x3537, 0x1001, "GameSir G7"),
    (0x3537, 0x1002, "GameSir T4 Kaleid"),
    (0x3537, 0x1007, "GameSir G7 HE"),
]

SPECIAL_KEYS = {
    "enter": Key.enter, "esc": Key.esc, "space": Key.space, "tab": Key.tab,
    "backspace": Key.backspace, "shift": Key.shift, "ctrl": Key.ctrl, "cmd": Key.cmd,
    "up": Key.up, "down": Key.down, "left": Key.left, "right": Key.right,
    "page_up": Key.page_up, "page_down": Key.page_down, "f1": Key.f1,
    "f11": Key.f11, "f12": Key.f12,
    "vol_up": Key.media_volume_up, "vol_down": Key.media_volume_down,
    "mute": Key.media_volume_mute, "play_pause": Key.media_play_pause
}

BIT_MAP = {
    "A": (4, 16), "B": (4, 32), "X": (4, 64), "Y": (4, 128),
    "MENU": (4, 4), "VIEW": (4, 8), "SHARE": (4, 2),
    "UP": (5, 1), "DOWN": (5, 2), "LEFT": (5, 4), "RIGHT": (5, 8),
    "LB": (5, 16), "RB": (5, 32), "L3": (5, 64), "R3": (5, 128)
}

def calc_mouse_delta(raw_val, deadzone, max_speed, curve=1.8):
    if abs(raw_val) <= deadzone:
        return 0
    sign = 1 if raw_val > 0 else -1
    norm = (abs(raw_val) - deadzone) / (32768.0 - deadzone)
    return int(round(sign * (norm ** curve) * max_speed))

class GameSirBridge:
    def __init__(self, initial_profile=None, on_status=None):
        self.config_path = pathlib.Path(__file__).parent / "profiles.json"
        self.reload_config(initial_profile)
        self.on_status = on_status
        self.running = False
        self.connected_name = None
        self.ep_out = None
        self.kb, self.mouse = KbController(), MouseController()
        self.pressed_keys, self.pressed_mouse = set(), set()
        self.active_combos = set()

    def reload_config(self, override_profile=None):
        self.cfg = json.loads(self.config_path.read_text(encoding="utf-8"))
        if override_profile and override_profile in self.cfg["profiles"]:
            self.current_profile = override_profile
        else:
            self.current_profile = self.cfg.get("active_profile", "emulators")

    def set_profile(self, name, vibrate=True):
        if name in self.cfg["profiles"] and name != self.current_profile:
            self.release_all()
            self.current_profile = name
            if vibrate and self.cfg.get("rumble_feedback", True):
                self.rumble(45, 12)
            if self.on_status:
                self.on_status(self.connected_name, self.current_profile)

    def rumble(self, strength=50, duration_10ms=15):
        if self.ep_out:
            try:
                self.ep_out.write([0x09, 0x00, 0x00, 0x09, 0x00, 0x0F, 0x00, 0x00, strength, strength, duration_10ms, 0x00, 0x00])
            except Exception:
                pass

    def release_all(self):
        for k in list(self.pressed_keys): self.kb.release(k)
        for b in list(self.pressed_mouse): self.mouse.release(b)
        self.pressed_keys.clear()
        self.pressed_mouse.clear()

    def trigger_macro(self, combo_str):
        keys = [SPECIAL_KEYS.get(k.strip().lower(), k.strip().lower()) for k in combo_str.split("+")]
        for k in keys: self.kb.press(k)
        time.sleep(0.05)
        for k in reversed(keys): self.kb.release(k)

    def _connect(self):
        for vid, pid, name in SUPPORTED_DEVICES:
            dev = usb.core.find(idVendor=vid, idProduct=pid)
            if dev is not None:
                dev.set_configuration()
                usb.util.claim_interface(dev, 0)
                intf = dev.get_active_configuration()[(0, 0)]
                ep_out = usb.util.find_descriptor(intf, custom_match=lambda e: usb.util.endpoint_direction(e.bEndpointAddress) == usb.util.ENDPOINT_OUT)
                ep_in = usb.util.find_descriptor(intf, custom_match=lambda e: usb.util.endpoint_direction(e.bEndpointAddress) == usb.util.ENDPOINT_IN)
                seq = 1
                sent_power = False
                t0 = time.time()
                while time.time() - t0 < 1.0:
                    try:
                        pkt = list(ep_in.read(64, timeout=100))
                        if len(pkt) >= 3 and (pkt[1] & 0x20):
                            self.ep_out.write([0x01, 0x20, pkt[2], 0x09, 0x00, pkt[0], 0x20, 0x02, 0x00, 0x00, 0x00, 0x00, 0x00])
                        if not sent_power and pkt[0] in (0x02, 0x04, 0x07):
                            ep_out.write([0x05, 0x20, seq, 0x01, 0x00]); seq += 1
                            time.sleep(0.05)
                            ep_out.write([0x0A, 0x20, seq, 0x03, 0x00, 0x01, 0x14]); seq += 1
                            sent_power = True
                        if len(pkt) >= 18 and pkt[0] == 32:
                            break
                    except Exception:
                        pass
                self.ep_out = ep_out
                self.connected_name = name
                if self.cfg.get("rumble_feedback", True):
                    self.rumble(60, 15)
                return dev, ep_in
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
                    self.set_profile(target_prof, vibrate=True)
                    break

    def _set_input(self, action, pressed):
        if not action: return
        if action in ("mouse_left", "mouse_right"):
            btn = Button.left if action == "mouse_left" else Button.right
            if pressed and btn not in self.pressed_mouse: self.mouse.press(btn); self.pressed_mouse.add(btn)
            elif not pressed and btn in self.pressed_mouse: self.mouse.release(btn); self.pressed_mouse.remove(btn)
        else:
            k = SPECIAL_KEYS.get(action.lower(), action)
            if pressed and k not in self.pressed_keys: self.kb.press(k); self.pressed_keys.add(k)
            elif not pressed and k in self.pressed_keys: self.kb.release(k); self.pressed_keys.remove(k)

    def run_forever(self):
        self.running = True
        last_focus_check = 0
        profile_list = list(self.cfg["profiles"].keys())

        while self.running:
            dev, ep_in = self._connect()
            if dev is None:
                self.connected_name = None
                self.ep_out = None
                if self.on_status: self.on_status(None, self.current_profile)
                time.sleep(1.5)
                continue

            if self.on_status: self.on_status(self.connected_name, self.current_profile)
            try:
                while self.running:
                    now = time.time()
                    if now - last_focus_check > 0.6:
                        self._check_frontmost_app()
                        last_focus_check = now

                    try:
                        data = dev.read(ep_in.bEndpointAddress, ep_in.wMaxPacketSize, timeout=20)
                        if len(data) >= 3 and data[0] != 32 and (data[1] & 0x20):
                         self.ep_out.write([0x01, 0x20, data[2], 0x09, 0x00, data[0], 0x20, 0x02, 0x00, 0x00, 0x00, 0x00, 0x00])
                        if len(data) >= 18 and data[0] == 32:
                            prof = self.cfg["profiles"][self.current_profile]
                            btns, ls, rs = prof["buttons"], prof["left_stick"], prof["right_stick"]
                            deadzone = prof.get("deadzone", self.cfg.get("deadzone", 10000))
                            mouse_speed = prof.get("mouse_speed", self.cfg.get("mouse_speed", 22))
                            curve = prof.get("mouse_curve", self.cfg.get("mouse_curve", 1.8))

                            held = {name for name, (idx, mask) in BIT_MAP.items() if bool(data[idx] & mask)}

                            if "VIEW" in held and "UP" in held:
                                if "CYCLE" not in self.active_combos:
                                    self.active_combos.add("CYCLE")
                                    nxt = profile_list[(profile_list.index(self.current_profile) + 1) % len(profile_list)]
                                    self.set_profile(nxt, vibrate=True)
                                continue
                            else:
                                self.active_combos.discard("CYCLE")

                            combo_triggered = False
                            for combo_key, macro_val in self.cfg.get("combos", {}).items():
                                req = {b.strip() for b in combo_key.split("+")}
                                if req.issubset(held):
                                    combo_triggered = True
                                    if combo_key not in self.active_combos:
                                        self.active_combos.add(combo_key)
                                        self.release_all()
                                        self.trigger_macro(macro_val)
                                else:
                                    self.active_combos.discard(combo_key)

                            if combo_triggered:
                                continue

                            for name in BIT_MAP:
                                self._set_input(btns.get(name), name in held)

                            lt, rt = struct.unpack("<H", bytes(data[6:8]))[0], struct.unpack("<H", bytes(data[8:10]))[0]
                            self._set_input(btns.get("LT"), lt > 200)
                            self._set_input(btns.get("RT"), rt > 200)

                            lx, ly = struct.unpack("<h", bytes(data[10:12]))[0], struct.unpack("<h", bytes(data[12:14]))[0]
                            self._set_input(ls.get("left"), lx < -deadzone)
                            self._set_input(ls.get("right"), lx > deadzone)
                            self._set_input(ls.get("up"), ly > deadzone)
                            self._set_input(ls.get("down"), ly < -deadzone)

                            rx, ry = struct.unpack("<h", bytes(data[14:16]))[0], struct.unpack("<h", bytes(data[16:18]))[0]
                            if prof.get("right_stick_mode") == "mouse":
                                dx = calc_mouse_delta(rx, deadzone, mouse_speed, curve)
                                dy = calc_mouse_delta(-ry, deadzone, mouse_speed, curve)
                                if dx or dy: self.mouse.move(dx, dy)
                            else:
                                self._set_input(rs.get("left"), rx < -deadzone)
                                self._set_input(rs.get("right"), rx > deadzone)
                                self._set_input(rs.get("up"), ry > deadzone)
                                self._set_input(rs.get("down"), ry < -deadzone)
                    except usb.core.USBTimeoutError:
                        pass
            except usb.core.USBError:
                self.release_all()
                time.sleep(1)
        self.release_all()

if __name__ == "__main__":
    p = sys.argv[1] if len(sys.argv) > 1 else None
    bridge = GameSirBridge(p, on_status=lambda dev, prof: print(f"Status: {dev or 'Desconectado'} | Perfil: [{prof}]"))
    try:
        bridge.run_forever()
    except KeyboardInterrupt:
        bridge.running = False
        bridge.release_all()
