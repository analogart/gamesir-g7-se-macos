import subprocess, sys, threading, pathlib, json, locale, rumps
from AppKit import NSImage, NSBezierPath, NSColor, NSMakeRect, NSMakeSize
from gamesir_bridge import GameSirBridge

STRINGS = {
    "pt": {
        "searching": "Status: Procurando controle...",
        "connected": "Conectado: {}",
        "disconnected": "Desconectado (aguardando USB)",
        "profile": "Perfil: {}",
        "config_ui": "Configurar Botões (App Visual)",
        "reload": "Recarregar Configurações",
        "language": "Idioma",
        "quit": "Sair",
        "notify_title": "Configuração",
        "notify_body": "Perfis recarregados do profiles.json!"
    },
    "en": {
        "searching": "Status: Searching for controller...",
        "connected": "Connected: {}",
        "disconnected": "Disconnected (waiting for USB)",
        "profile": "Profile: {}",
        "config_ui": "Configure Buttons (Visual App)",
        "reload": "Reload Configuration",
        "language": "Language",
        "quit": "Quit",
        "notify_title": "Configuration",
        "notify_body": "Profiles reloaded from profiles.json!"
    },
    "es": {
        "searching": "Estado: Buscando control...",
        "connected": "Conectado: {}",
        "disconnected": "Desconectado (esperando USB)",
        "profile": "Perfil: {}",
        "config_ui": "Configurar Botones (App Visual)",
        "reload": "Recargar Configuración",
        "language": "Idioma",
        "quit": "Salir",
        "notify_title": "Configuración",
        "notify_body": "¡Perfiles recargados desde profiles.json!"
    }
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
    NSBezierPath.bezierPathWithRoundedRect_xRadius_yRadius_(NSMakeRect(2.5, 4.5, 17.0, 10.0), 4.8, 4.8).fill()
    NSBezierPath.bezierPathWithRoundedRect_xRadius_yRadius_(NSMakeRect(2.0, 2.0, 5.5, 7.5), 2.6, 2.6).fill()
    NSBezierPath.bezierPathWithRoundedRect_xRadius_yRadius_(NSMakeRect(14.5, 2.0, 5.5, 7.5), 2.6, 2.6).fill()
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

class GameSirMenuBar(rumps.App):
    def __init__(self):
        super().__init__("", quit_button=None)
        self.bridge = GameSirBridge(on_status=self.update_status)
        self.lang = detect_lang(self.bridge.cfg)
        self.last_device = None
        self.status_item = rumps.MenuItem(self.t("searching"))
        self.prof_items = {}
        for name in self.bridge.cfg["profiles"]:
            item = rumps.MenuItem(self.t("profile").format(name), callback=self.select_profile)
            item.profile_name = name
            self.prof_items[name] = item

        self.lang_menu = rumps.MenuItem(self.t("language"))
        self.lang_items = {}
        for code, label in LANG_LABELS.items():
            litem = rumps.MenuItem(label, callback=self.select_lang)
            litem.lang_code = code
            self.lang_items[code] = litem
            self.lang_menu.add(litem)

        self.config_item = rumps.MenuItem(self.t("config_ui"), callback=self.open_config)
        self.reload_item = rumps.MenuItem(self.t("reload"), callback=self.reload_cfg)
        self.quit_item = rumps.MenuItem(self.t("quit"), callback=rumps.quit_application)

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
        threading.Thread(target=self.bridge.run_forever, daemon=True).start()

    def t(self, key):
        return STRINGS.get(self.lang, STRINGS["en"])[key]

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
            item.state = (name == self.bridge.current_profile)
        for code, litem in self.lang_items.items():
            litem.state = (code == self.lang)

    def _set_language(self, code):
        self.lang = code
        self.bridge.cfg["language"] = code
        p = pathlib.Path(__file__).parent / "profiles.json"
        try:
            p.write_text(json.dumps(self.bridge.cfg, indent=2), encoding="utf-8")
        except Exception:
            pass
        self.lang_menu.title = self.t("language")
        self.config_item.title = self.t("config_ui")
        self.reload_item.title = self.t("reload")
        self.quit_item.title = self.t("quit")
        self.status_item.title = self.t("connected").format(self.last_device) if self.last_device else self.t("disconnected")
        self._refresh_checks()

    def select_lang(self, sender):
        self._set_language(sender.lang_code)

    def update_status(self, device_name, profile_name):
        self.last_device = device_name
        self._apply_icon(bool(device_name))
        self.status_item.title = self.t("connected").format(device_name) if device_name else self.t("disconnected")
        self._refresh_checks()

    def select_profile(self, sender):
        self.bridge.set_profile(sender.profile_name, vibrate=True)
        self._refresh_checks()

    def open_config(self, _):
        ui_script = str(pathlib.Path(__file__).parent / "config_ui.py")
        subprocess.Popen([sys.executable, ui_script])

    def reload_cfg(self, _):
        self.bridge.reload_config()
        self.lang = detect_lang(self.bridge.cfg)
        self._set_language(self.lang)
        rumps.notification("GameSir Bridge", self.t("notify_title"), self.t("notify_body"))

if __name__ == "__main__":
    app = GameSirMenuBar()
    @rumps.timer(0.2)
    def _sync_icon(t):
        app._apply_icon(bool(app.last_device))
        t.stop()
    app.run()
