import fcntl, os, sys
_lock_fp = open("/tmp/gamesir_bridge.lock", "w")
try:
    fcntl.flock(_lock_fp, fcntl.LOCK_EX | fcntl.LOCK_NB)
except OSError:
    sys.exit(0)
import json
import locale
import pathlib
import subprocess
import sys
import threading
import rumps
from AppKit import (
    NSBackingStoreBuffered,
    NSBezierPath,
    NSColor,
    NSFloatingWindowLevel,
    NSFont,
    NSImage,
    NSMakeRect,
    NSMakeSize,
    NSScreen,
    NSTextAlignmentCenter,
    NSTextField,
    NSWindow,
)
from Foundation import NSTimer
from gamesir_bridge import GameSirBridge

STRINGS = {
    "pt": {
        "searching": "Status: Procurando controle...",
        "connected": "Conectado: {}",
        "disconnected": "Desconectado (aguardando USB)",
        "profile": "Perfil: {}",
        "osd_profile": "Perfil: {}",
        "config_ui": "Configurar Botões (App Visual)",
        "reload": "Recarregar Configurações",
        "language": "Idioma",
        "quit": "Sair",
        "notify_title": "Configuração",
        "notify_body": "Perfis recarregados do profiles.json!",
    },
    "en": {
        "searching": "Status: Searching for controller...",
        "connected": "Connected: {}",
        "disconnected": "Disconnected (waiting for USB)",
        "profile": "Profile: {}",
        "osd_profile": "Profile: {}",
        "config_ui": "Configure Buttons (Visual App)",
        "reload": "Reload Configuration",
        "language": "Language",
        "quit": "Quit",
        "notify_title": "Configuration",
        "notify_body": "Profiles reloaded from profiles.json!",
    },
    "es": {
        "searching": "Estado: Buscando control...",
        "connected": "Conectado: {}",
        "disconnected": "Desconectado (esperando USB)",
        "profile": "Perfil: {}",
        "osd_profile": "Perfil: {}",
        "config_ui": "Configurar Botones (App Visual)",
        "reload": "Recargar Configuración",
        "language": "Idioma",
        "quit": "Salir",
        "notify_title": "Configuración",
        "notify_body": "¡Perfiles recargados desde profiles.json!",
    },
}

LANG_LABELS = {"pt": "Português", "en": "English", "es": "Español"}


def detect_lang(cfg):
    lang = cfg.get("language")
    if lang in STRINGS:
        return lang
    loc = (locale.getdefaultlocale()[0] or "en").lower()
    if loc.startswith("pt"):
        return "pt"
    if loc.startswith("es"):
        return "es"
    return "en"


def build_menubar_icon(connected=True):
    img = NSImage.alloc().initWithSize_(NSMakeSize(22, 18))
    img.lockFocus()
    NSColor.blackColor().set()
    NSBezierPath.bezierPathWithRoundedRect_xRadius_yRadius_(
        NSMakeRect(2.5, 4.5, 17.0, 10.0), 4.8, 4.8
    ).fill()
    NSBezierPath.bezierPathWithRoundedRect_xRadius_yRadius_(
        NSMakeRect(2.0, 2.0, 5.5, 7.5), 2.6, 2.6
    ).fill()
    NSBezierPath.bezierPathWithRoundedRect_xRadius_yRadius_(
        NSMakeRect(14.5, 2.0, 5.5, 7.5), 2.6, 2.6
    ).fill()
    NSColor.clearColor().set()
    NSBezierPath.bezierPathWithOvalInRect_(NSMakeRect(13.5, 9.5, 2.2, 2.2)).fill()
    NSBezierPath.bezierPathWithOvalInRect_(NSMakeRect(15.8, 7.5, 2.2, 2.2)).fill()
    NSBezierPath.bezierPathWithRect_(NSMakeRect(5.5, 8.8, 4.2, 1.5)).fill()
    NSBezierPath.bezierPathWithRect_(NSMakeRect(6.85, 7.45, 1.5, 4.2)).fill()
    if not connected:
        NSColor.blackColor().set()
        NSBezierPath.bezierPathWithOvalInRect_(NSMakeRect(17.2, 13.0, 4.0, 4.0)).fill()
    img.unlockFocus()
    img.setTemplate_(True)
    return img


class ProfileOSD:
    def __init__(self):
        self.win = None
        self.timer = None

    def show(self, label_text):
        if self.timer:
            self.timer.invalidate()
            self.timer = None
        if self.win:
            self.win.orderOut_(None)
            self.win = None

        screen = NSScreen.mainScreen()
        if not screen:
            return
        frame = screen.frame()
        w, h = 320, 52
        x = (frame.size.width - w) / 2.0
        y = 110.0

        win = NSWindow.alloc().initWithContentRect_styleMask_backing_defer_(
            NSMakeRect(x, y, w, h), 0, NSBackingStoreBuffered, False
        )
        win.setLevel_(NSFloatingWindowLevel)
        win.setOpaque_(False)
        win.setBackgroundColor_(NSColor.colorWithCalibratedWhite_alpha_(0.08, 0.88))
        win.setIgnoresMouseEvents_(True)
        win.setHasShadow_(True)
        win.contentView().setWantsLayer_(True)
        win.contentView().layer().setCornerRadius_(15.0)

        lbl = NSTextField.alloc().initWithFrame_(NSMakeRect(12, 11, w - 24, 30))
        lbl.setStringValue_(label_text)
        lbl.setBezeled_(False)
        lbl.setDrawsBackground_(False)
        lbl.setEditable_(False)
        lbl.setSelectable_(False)
        lbl.setTextColor_(NSColor.whiteColor())
        lbl.setFont_(NSFont.boldSystemFontOfSize_(16.0))
        lbl.setAlignment_(NSTextAlignmentCenter)

        win.contentView().addSubview_(lbl)
        win.orderFrontRegardless()
        self.win = win
        self.timer = NSTimer.scheduledTimerWithTimeInterval_target_selector_userInfo_repeats_(
            1.5, self, "hide:", None, False
        )

    def hide_(self, _):
        if self.win:
            self.win.orderOut_(None)
            self.win = None
        self.timer = None


class GameSirMenuBar(rumps.App):
    def __init__(self):
        super().__init__("GS", quit_button=None)
        self.osd = ProfileOSD()
        self._lock = threading.Lock()
        self._pending_status = None
        self._pending_osd = None

        self.bridge = GameSirBridge(
            on_status=self._queue_status,
            on_profile_osd=self._queue_osd,
        )
        self.lang = detect_lang(self.bridge.cfg)
        self.last_device = None

        self.status_item = rumps.MenuItem(self.t("searching"))
        self.prof_items = {}
        for name in self.bridge.cfg["profiles"]:
            item = rumps.MenuItem(
                self.t("profile").format(name), callback=self.select_profile
            )
            item.profile_name = name
            self.prof_items[name] = item

        self.lang_menu = rumps.MenuItem(self.t("language"))
        self.lang_items = {}
        for code, label in LANG_LABELS.items():
            litem = rumps.MenuItem(label, callback=self.select_lang)
            litem.lang_code = code
            self.lang_items[code] = litem
            self.lang_menu.add(litem)

        self.config_item = rumps.MenuItem(
            self.t("config_ui"), callback=self.open_config
        )
        self.reload_item = rumps.MenuItem(self.t("reload"), callback=self.reload_cfg)
        self.quit_item = rumps.MenuItem(self.t("quit"), callback=self.quit_app)

        self.menu = [
            self.status_item,
            None,
            *self.prof_items.values(),
            None,
            self.config_item,
            self.reload_item,
            self.lang_menu,
            None,
            self.quit_item,
        ]
        self._icon_on = build_menubar_icon(True)
        self._icon_off = build_menubar_icon(False)
        self._refresh_checks()

        self._ui_timer = rumps.Timer(self._flush_ui, 0.15)
        self._ui_timer.start()
        threading.Thread(target=self.bridge.run_forever, daemon=True).start()

    def t(self, key):
        return STRINGS.get(self.lang, STRINGS["en"])[key]

    def _queue_status(self, device_name, profile_name):
        with self._lock:
            self._pending_status = (device_name, profile_name)

    def _queue_osd(self, profile_name):
        with self._lock:
            self._pending_osd = profile_name

    def _flush_ui(self, _):
        with self._lock:
            st = self._pending_status
            osd_prof = self._pending_osd
            self._pending_status = None
            self._pending_osd = None

        if st is not None:
            dev, _ = st
            self.last_device = dev
            self._apply_icon(bool(dev))
            self.status_item.title = (
                self.t("connected").format(dev) if dev else self.t("disconnected")
            )
            self._refresh_checks()

        if osd_prof is not None:
            self.osd.show(self.t("osd_profile").format(osd_prof.upper()))

    def _apply_icon(self, connected):
        try:
            btn = self._nsapp.nsstatusitem.button()
            btn.setImage_(self._icon_on if connected else self._icon_off)
            btn.setTitle_("")
        except Exception:
            pass

    def _refresh_checks(self):
        for name, item in self.prof_items.items():
            item.title = self.t("profile").format(name)
            item.state = name == self.bridge.current_profile
        for code, litem in self.lang_items.items():
            litem.state = code == self.lang

    def _set_language(self, code):
        self.lang = code
        self.bridge.cfg["language"] = code
        p = pathlib.Path(__file__).parent / "profiles.json"
        try:
            p.write_text(
                json.dumps(self.bridge.cfg, indent=2, ensure_ascii=False),
                encoding="utf-8",
            )
        except Exception:
            pass
        self.lang_menu.title = self.t("language")
        self.config_item.title = self.t("config_ui")
        self.reload_item.title = self.t("reload")
        self.quit_item.title = self.t("quit")
        self.status_item.title = (
            self.t("connected").format(self.last_device)
            if self.last_device
            else self.t("disconnected")
        )
        self._refresh_checks()

    def select_lang(self, sender):
        self._set_language(sender.lang_code)

    def select_profile(self, sender):
        self.bridge.set_profile(sender.profile_name, vibrate=True, show_osd=True)
        self._refresh_checks()

    def open_config(self, _):
        ui_script = str(pathlib.Path(__file__).parent / "config_ui.py")
        subprocess.Popen([sys.executable, ui_script])

    def reload_cfg(self, _):
        self.bridge.release_all()
        self.bridge.reload_config()
        self.lang = detect_lang(self.bridge.cfg)
        self._set_language(self.lang)
        rumps.notification(
            "GameSir Bridge", self.t("notify_title"), self.t("notify_body")
        )

    def quit_app(self, _):
        self.bridge.running = False
        self.bridge.release_all()
        rumps.quit_application()


if __name__ == "__main__":
    app = GameSirMenuBar()

    @rumps.timer(0.2)
    def _sync_icon(t):
        app._apply_icon(bool(app.last_device))
        t.stop()

    app.run()