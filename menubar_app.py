import ctypes
import fcntl
import json
import locale
import os
import pathlib
import signal
import subprocess
import sys
import threading
import urllib.request
import webbrowser

from app_paths import (
    APP_VERSION,
    GITHUB_REPO,
    get_config_path,
    get_pid_path,
    get_resource_dir,
)

LOCK_PATH = "/tmp/gamesir_bridge.lock"
WAKE_PATH = "/tmp/gamesir_bridge.wake"

_lock_fp = open(LOCK_PATH, "w")
try:
    fcntl.flock(_lock_fp, fcntl.LOCK_EX | fcntl.LOCK_NB)
except OSError:
    try:
        pathlib.Path(WAKE_PATH).write_text("1", encoding="utf-8")
    except Exception:
        pass
    sys.exit(0)

import objc
from AppKit import (
    NSAlert,
    NSAlertFirstButtonReturn,
    NSApplication,
    NSApplicationActivationPolicyRegular,
    NSBackingStoreBuffered,
    NSBezelStyleRounded,
    NSButton,
    NSColor,
    NSFloatingWindowLevel,
    NSFont,
    NSImage,
    NSMakeRect,
    NSMenu,
    NSMenuItem,
    NSScreen,
    NSTextAlignmentCenter,
    NSTextField,
    NSVisualEffectBlendingModeBehindWindow,
    NSVisualEffectMaterialHUDWindow,
    NSVisualEffectStateActive,
    NSVisualEffectView,
    NSWindow,
    NSWindowStyleMaskClosable,
    NSWindowStyleMaskFullSizeContentView,
    NSWindowStyleMaskMiniaturizable,
    NSWindowStyleMaskResizable,
    NSWindowStyleMaskTitled,
)
from Foundation import NSObject, NSTimer, NSURL, NSURLRequest

try:
    from WebKit import WKWebView, WKWebViewConfiguration

    HAS_WEBKIT = True
except ImportError:
    HAS_WEBKIT = False

from config_ui import PORT as CONFIG_UI_PORT, start_background_server
from gamesir_bridge import GameSirBridge

STRINGS = {
    "pt": {
        "searching": "Procurando controle USB...",
        "connected": "Conectado: {}",
        "osd_profile": "Perfil: {}",
        "config_ui": "Configurar Botões (App Visual)",
        "reload": "Recarregar Configurações",
        "check_updates": "Verificar Atualizações",
        "open_panel": "Abrir Painel de Controle",
        "quit": "Encerrar Bridge",
        "ax_warn": "Permissão de Acessibilidade pendente",
        "ax_fix": "Conceder Permissão de Acessibilidade",
        "upd_title": "Atualizações — GameSir Bridge",
        "upd_latest": "Você já está na versão mais recente ({}).",
        "upd_avail": "Nova versão disponível: {} (atual: {}).\nDeseja abrir a página no GitHub?",
        "upd_err": "Não foi possível verificar atualizações agora.",
        "upd_open": "Abrir GitHub",
        "upd_ok": "OK",
        "hint": "Fechar no X mantém o bridge ativo em segundo plano.\nAtalhos: VIEW + ▲ (Painel) | VIEW + ▼ (Perfil)",
    },
    "en": {
        "searching": "Searching for USB controller...",
        "connected": "Connected: {}",
        "osd_profile": "Profile: {}",
        "config_ui": "Configure Buttons (Visual App)",
        "reload": "Reload Configuration",
        "check_updates": "Check for Updates",
        "open_panel": "Open Control Panel",
        "quit": "Quit Bridge",
        "ax_warn": "Accessibility permission required",
        "ax_fix": "Grant Accessibility Permission",
        "upd_title": "Updates — GameSir Bridge",
        "upd_latest": "You are running the latest version ({}).",
        "upd_avail": "New version available: {} (current: {}).\nOpen GitHub release page?",
        "upd_err": "Could not check for updates right now.",
        "upd_open": "Open GitHub",
        "upd_ok": "OK",
        "hint": "Closing with X keeps the bridge running in background.\nShortcuts: VIEW + ▲ (Panel) | VIEW + ▼ (Profile)",
    },
    "es": {
        "searching": "Buscando control USB...",
        "connected": "Conectado: {}",
        "osd_profile": "Perfil: {}",
        "config_ui": "Configurar Botones (App Visual)",
        "reload": "Recargar Configuración",
        "check_updates": "Buscar Actualizaciones",
        "open_panel": "Abrir Panel de Control",
        "quit": "Cerrar Bridge",
        "ax_warn": "Permiso de Accesibilidad pendiente",
        "ax_fix": "Conceder Permiso de Accesibilidad",
        "upd_title": "Actualizaciones — GameSir Bridge",
        "upd_latest": "Ya tienes la versión más reciente ({}).",
        "upd_avail": "Nueva versión disponible: {} (actual: {}).\n¿Abrir la página en GitHub?",
        "upd_err": "No se pudieron comprobar actualizaciones ahora.",
        "upd_open": "Abrir GitHub",
        "upd_ok": "OK",
        "hint": "Cerrar con X mantiene el bridge activo en segundo plano.\nAtajos: VIEW + ▲ (Panel) | VIEW + ▼ (Perfil)",
    },
}

LANG_LABELS = [("pt", "Português"), ("en", "English"), ("es", "Español")]


def is_accessibility_trusted():
    try:
        app_services = ctypes.cdll.LoadLibrary(
            "/System/Library/Frameworks/ApplicationServices.framework/ApplicationServices"
        )
        app_services.AXIsProcessTrusted.restype = ctypes.c_bool
        return bool(app_services.AXIsProcessTrusted())
    except Exception:
        return True


def detect_lang(cfg):
    lang = cfg.get("language")
    if lang in STRINGS:
        return lang
    loc = (locale.getlocale()[0] or "en").lower()
    if loc.startswith("pt"):
        return "pt"
    if loc.startswith("es"):
        return "es"
    return "en"


class ProfileOSD(NSObject):
    def init(self):
        self = objc.super(ProfileOSD, self).init()
        if self is None:
            return None
        self.win = None
        self.timer = None
        return self

    @objc.python_method
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
        win.setBackgroundColor_(NSColor.clearColor())
        win.setIgnoresMouseEvents_(True)
        win.setHasShadow_(True)

        fx = NSVisualEffectView.alloc().initWithFrame_(NSMakeRect(0, 0, w, h))
        fx.setMaterial_(NSVisualEffectMaterialHUDWindow)
        fx.setBlendingMode_(NSVisualEffectBlendingModeBehindWindow)
        fx.setState_(NSVisualEffectStateActive)
        win.setContentView_(fx)

        lbl = NSTextField.alloc().initWithFrame_(NSMakeRect(12, 11, w - 24, 30))
        lbl.setStringValue_(label_text)
        lbl.setBezeled_(False)
        lbl.setDrawsBackground_(False)
        lbl.setEditable_(False)
        lbl.setSelectable_(False)
        lbl.setTextColor_(NSColor.labelColor())
        lbl.setFont_(NSFont.boldSystemFontOfSize_(16.0))
        lbl.setAlignment_(NSTextAlignmentCenter)

        fx.addSubview_(lbl)
        win.orderFrontRegardless()
        self.win = win
        self.timer = NSTimer.scheduledTimerWithTimeInterval_target_selector_userInfo_repeats_(
            1.5, self, "hide:", None, False
        )

    def hide_(self, _sender):
        if self.win:
            self.win.orderOut_(None)
            self.win = None
        self.timer = None


class ConfigWebWindow(NSObject):
    def init(self):
        self = objc.super(ConfigWebWindow, self).init()
        if self is None:
            return None
        self.win = None
        self.webview = None
        return self

    def windowShouldClose_(self, sender):
        sender.orderOut_(None)
        return False

    @objc.python_method
    def show(self, url_str=f"http://127.0.0.1:{CONFIG_UI_PORT}"):
        if not HAS_WEBKIT:
            webbrowser.open(url_str)
            return

        if self.win is None:
            screen = NSScreen.mainScreen()
            frame = screen.frame() if screen else NSMakeRect(0, 0, 1280, 800)
            w = min(1160, int(frame.size.width * 0.88))
            h = min(780, int(frame.size.height * 0.86))
            x = (frame.size.width - w) / 2.0
            y = (frame.size.height - h) / 2.0

            win = NSWindow.alloc().initWithContentRect_styleMask_backing_defer_(
                NSMakeRect(x, y, w, h),
                NSWindowStyleMaskTitled
                | NSWindowStyleMaskClosable
                | NSWindowStyleMaskMiniaturizable
                | NSWindowStyleMaskResizable,
                NSBackingStoreBuffered,
                False,
            )
            win.setTitle_(f"GameSir Bridge {APP_VERSION} — Visual Configurator")
            win.setReleasedWhenClosed_(False)
            win.setDelegate_(self)

            cfg = WKWebViewConfiguration.alloc().init()
            wv = WKWebView.alloc().initWithFrame_configuration_(
                NSMakeRect(0, 0, w, h), cfg
            )
            wv.setAutoresizingMask_(18)  # Width + Height sizable
            win.setContentView_(wv)
            self.win = win
            self.webview = wv

        req = NSURLRequest.requestWithURL_(NSURL.URLWithString_(url_str))
        self.webview.loadRequest_(req)
        NSApplication.sharedApplication().activateIgnoringOtherApps_(True)
        self.win.makeKeyAndOrderFront_(None)


class ControlPanel(NSObject):
    def initWithController_(self, ctrl):
        self = objc.super(ControlPanel, self).init()
        if self is None:
            return None
        self.ctrl = ctrl
        self.win = None
        self.status_lbl = None
        self.profile_buttons = {}
        return self

    def windowShouldClose_(self, sender):
        sender.orderOut_(None)
        return False

    @objc.python_method
    def is_visible(self):
        return self.win is not None and self.win.isVisible()

    @objc.python_method
    def toggle(self):
        if self.is_visible():
            self.win.orderOut_(None)
        else:
            self.show()

    @objc.python_method
    def sync_ui(self):
        if self.status_lbl is not None:
            if self.ctrl.last_device:
                self.status_lbl.setStringValue_(
                    f"● {self.ctrl.t('connected').format(self.ctrl.last_device)}"
                )
                self.status_lbl.setTextColor_(NSColor.systemGreenColor())
            else:
                self.status_lbl.setStringValue_(f"○ {self.ctrl.t('searching')}")
                self.status_lbl.setTextColor_(NSColor.labelColor())
        for prof_name, btn in self.profile_buttons.items():
            active = prof_name == self.ctrl.bridge.current_profile
            btn.setTitle_(f"✓ {prof_name}" if active else prof_name)

    @objc.python_method
    def show(self):
        if self.win is not None:
            self.win.orderOut_(None)
            self.win = None

        screen = NSScreen.mainScreen()
        if not screen:
            return
        frame = screen.frame()
        profiles = list(self.ctrl.bridge.cfg.get("profiles", {}).keys())
        ax_ok = is_accessibility_trusted()
        extra_ax_h = 0 if ax_ok else 44
        w = 390
        h = 338 + (len(profiles) * 38) + extra_ax_h
        x = (frame.size.width - w) / 2.0
        y = (frame.size.height - h) / 2.0

        win = NSWindow.alloc().initWithContentRect_styleMask_backing_defer_(
            NSMakeRect(x, y, w, h),
            NSWindowStyleMaskTitled
            | NSWindowStyleMaskClosable
            | NSWindowStyleMaskMiniaturizable
            | NSWindowStyleMaskFullSizeContentView,
            NSBackingStoreBuffered,
            False,
        )
        win.setTitle_(f"GameSir Bridge {APP_VERSION}")
        win.setTitlebarAppearsTransparent_(True)
        win.setOpaque_(False)
        win.setBackgroundColor_(NSColor.clearColor())
        win.setHasShadow_(True)
        win.setReleasedWhenClosed_(False)
        win.setDelegate_(self)

        content = NSVisualEffectView.alloc().initWithFrame_(NSMakeRect(0, 0, w, h))
        content.setMaterial_(NSVisualEffectMaterialHUDWindow)
        content.setBlendingMode_(NSVisualEffectBlendingModeBehindWindow)
        content.setState_(NSVisualEffectStateActive)
        win.setContentView_(content)

        self.status_lbl = NSTextField.alloc().initWithFrame_(
            NSMakeRect(20, h - 62, w - 40, 24)
        )
        self.status_lbl.setBezeled_(False)
        self.status_lbl.setDrawsBackground_(False)
        self.status_lbl.setEditable_(False)
        self.status_lbl.setSelectable_(False)
        self.status_lbl.setFont_(NSFont.boldSystemFontOfSize_(14.0))
        self.status_lbl.setAlignment_(NSTextAlignmentCenter)
        content.addSubview_(self.status_lbl)

        cur_y = h - 104
        if not ax_ok:
            ax_btn = NSButton.alloc().initWithFrame_(NSMakeRect(30, cur_y, w - 60, 32))
            ax_btn.setTitle_(f"⚠ {self.ctrl.t('ax_fix')}")
            ax_btn.setBezelStyle_(NSBezelStyleRounded)
            ax_btn.setTarget_(self)
            ax_btn.setAction_("openAccessibility:")
            content.addSubview_(ax_btn)
            cur_y -= 42

        self.profile_buttons = {}
        for prof_name in profiles:
            btn = NSButton.alloc().initWithFrame_(NSMakeRect(30, cur_y, w - 60, 32))
            btn.setBezelStyle_(NSBezelStyleRounded)
            btn.setTarget_(self)
            btn.setAction_("selectProf:")
            btn.setIdentifier_(prof_name)
            content.addSubview_(btn)
            self.profile_buttons[prof_name] = btn
            cur_y -= 38

        self.sync_ui()

        cur_y -= 10
        for title, sel in [
            (self.ctrl.t("config_ui"), "openCfg:"),
            (self.ctrl.t("reload"), "reloadCfg:"),
            (self.ctrl.t("check_updates"), "checkUpdates:"),
            (self.ctrl.t("quit"), "quitApp:"),
        ]:
            btn = NSButton.alloc().initWithFrame_(NSMakeRect(30, cur_y, w - 60, 32))
            btn.setTitle_(title)
            btn.setBezelStyle_(NSBezelStyleRounded)
            btn.setTarget_(self)
            btn.setAction_(sel)
            content.addSubview_(btn)
            cur_y -= 38

        cur_y -= 6
        btn_w = (w - 72) / 3.0
        for idx, (code, label) in enumerate(LANG_LABELS):
            prefix = "• " if code == self.ctrl.lang else ""
            lbtn = NSButton.alloc().initWithFrame_(
                NSMakeRect(30 + idx * (btn_w + 6), cur_y, btn_w, 26)
            )
            lbtn.setTitle_(f"{prefix}{label}")
            lbtn.setBezelStyle_(NSBezelStyleRounded)
            lbtn.setTarget_(self)
            lbtn.setAction_("selectLang:")
            lbtn.setIdentifier_(code)
            content.addSubview_(lbtn)

        cur_y -= 42
        hint = NSTextField.alloc().initWithFrame_(NSMakeRect(16, cur_y, w - 32, 34))
        hint.setStringValue_(self.ctrl.t("hint"))
        hint.setBezeled_(False)
        hint.setDrawsBackground_(False)
        hint.setEditable_(False)
        hint.setSelectable_(False)
        hint.setTextColor_(NSColor.secondaryLabelColor())
        hint.setFont_(NSFont.systemFontOfSize_(11.0))
        hint.setAlignment_(NSTextAlignmentCenter)
        content.addSubview_(hint)

        NSApplication.sharedApplication().activateIgnoringOtherApps_(True)
        win.makeKeyAndOrderFront_(None)
        self.win = win

    def openAccessibility_(self, _sender):
        subprocess.Popen(
            [
                "open",
                "x-apple.systempreferences:com.apple.preference.security?Privacy_Accessibility",
            ]
        )

    def selectProf_(self, sender):
        self.ctrl.bridge.set_profile(sender.identifier(), vibrate=True, show_osd=True)
        self.sync_ui()

    def selectLang_(self, sender):
        self.ctrl.set_language(sender.identifier())
        self.show()

    def openCfg_(self, _sender):
        self.ctrl.open_config_ui()

    def reloadCfg_(self, _sender):
        self.ctrl.reload_all()
        self.show()

    def checkUpdates_(self, _sender):
        self.ctrl.check_github_updates()

    def quitApp_(self, _sender):
        NSApplication.sharedApplication().terminate_(None)


class GameSirAppDelegate(NSObject):
    def init(self):
        self = objc.super(GameSirAppDelegate, self).init()
        if self is None:
            return None

        self.nsapp = NSApplication.sharedApplication()
        self.nsapp.setActivationPolicy_(NSApplicationActivationPolicyRegular)

        icns_path = str(get_resource_dir() / "AppIcon.icns")
        icon = NSImage.alloc().initWithContentsOfFile_(icns_path)
        if icon is not None:
            self.nsapp.setApplicationIconImage_(icon)

        self.osd = ProfileOSD.alloc().init()
        self.panel = ControlPanel.alloc().initWithController_(self)
        self.config_win = ConfigWebWindow.alloc().init()

        self._lock = threading.Lock()
        self._pending_status = None
        self._pending_osd = None
        self._pending_hud = False
        self._pending_update_result = None

        self.bridge = GameSirBridge(
            on_status=self._queue_status,
            on_profile_osd=self._queue_osd,
            on_quick_hud=self._queue_hud,
        )
        self.lang = detect_lang(self.bridge.cfg)
        self.last_device = None

        self._setup_top_left_menu()
        self.nsapp.setDelegate_(self)
        return self

    def applicationDidFinishLaunching_(self, _notif):
        self._timer = NSTimer.scheduledTimerWithTimeInterval_target_selector_userInfo_repeats_(
            0.15, self, "flushUiTimer:", None, True
        )
        threading.Thread(target=self.bridge.run_forever, daemon=True).start()
        self.panel.show()

    def applicationShouldHandleReopen_hasVisibleWindows_(self, _sender, _flag):
        self.panel.show()
        return True

    def applicationDockMenu_(self, _sender):
        menu = NSMenu.alloc().init()
        status_title = (
            self.t("connected").format(self.last_device)
            if self.last_device
            else self.t("searching")
        )
        st_item = NSMenuItem.alloc().initWithTitle_action_keyEquivalent_(
            status_title, None, ""
        )
        st_item.setEnabled_(False)
        menu.addItem_(st_item)
        menu.addItem_(NSMenuItem.separatorItem())

        for prof_name in self.bridge.cfg.get("profiles", {}).keys():
            item = NSMenuItem.alloc().initWithTitle_action_keyEquivalent_(
                prof_name, "dockSelectProfile:", ""
            )
            item.setTarget_(self)
            item.setRepresentedObject_(prof_name)
            if prof_name == self.bridge.current_profile:
                item.setState_(1)
            menu.addItem_(item)

        menu.addItem_(NSMenuItem.separatorItem())
        cfg_item = NSMenuItem.alloc().initWithTitle_action_keyEquivalent_(
            self.t("config_ui"), "openCfgAction:", ""
        )
        cfg_item.setTarget_(self)
        menu.addItem_(cfg_item)
        return menu

    def dockSelectProfile_(self, sender):
        self.bridge.set_profile(sender.representedObject(), vibrate=True, show_osd=True)
        if self.panel.is_visible():
            self.panel.sync_ui()

    def applicationWillTerminate_(self, _notif):
        self.bridge.running = False
        self.bridge.release_all()
        try:
            self._timer.invalidate()
        except Exception:
            pass
        pid_file = get_pid_path()
        if pid_file.exists():
            try:
                old_pid = int(pid_file.read_text().strip())
                if old_pid != os.getpid():
                    os.kill(old_pid, signal.SIGTERM)
                pid_file.unlink(missing_ok=True)
            except Exception:
                pass

    @objc.python_method
    def t(self, key):
        return STRINGS.get(self.lang, STRINGS["en"])[key]

    @objc.python_method
    def _setup_top_left_menu(self):
        menubar = NSMenu.alloc().init()
        app_menu_item = NSMenuItem.alloc().init()
        menubar.addItem_(app_menu_item)
        app_menu = NSMenu.alloc().init()

        open_item = NSMenuItem.alloc().initWithTitle_action_keyEquivalent_(
            self.t("open_panel"), "openPanelAction:", "g"
        )
        open_item.setTarget_(self)
        app_menu.addItem_(open_item)

        cfg_item = NSMenuItem.alloc().initWithTitle_action_keyEquivalent_(
            self.t("config_ui"), "openCfgAction:", ","
        )
        cfg_item.setTarget_(self)
        app_menu.addItem_(cfg_item)

        app_menu.addItem_(NSMenuItem.separatorItem())

        quit_item = NSMenuItem.alloc().initWithTitle_action_keyEquivalent_(
            self.t("quit"), "terminate:", "q"
        )
        app_menu.addItem_(quit_item)

        app_menu_item.setSubmenu_(app_menu)
        self.nsapp.setMainMenu_(menubar)

    def openPanelAction_(self, _sender):
        self.panel.show()

    def openCfgAction_(self, _sender):
        self.open_config_ui()

    @objc.python_method
    def set_language(self, code):
        self.lang = code
        self.bridge.cfg["language"] = code
        try:
            get_config_path().write_text(
                json.dumps(self.bridge.cfg, indent=2, ensure_ascii=False),
                encoding="utf-8",
            )
        except Exception:
            pass
        self._setup_top_left_menu()

    @objc.python_method
    def open_config_ui(self):
        start_background_server()
        if HAS_WEBKIT:
            NSTimer.scheduledTimerWithTimeInterval_target_selector_userInfo_repeats_(
                0.15, self, "openNativeWebTimer:", None, False
            )
        else:
            webbrowser.open(f"http://127.0.0.1:{CONFIG_UI_PORT}")

    def openNativeWebTimer_(self, _t):
        self.config_win.show(f"http://127.0.0.1:{CONFIG_UI_PORT}")

    @objc.python_method
    def check_github_updates(self):
        def _worker():
            try:
                req = urllib.request.Request(
                    f"https://api.github.com/repos/{GITHUB_REPO}/releases/latest",
                    headers={"User-Agent": "GameSir-Bridge-macOS"},
                )
                with urllib.request.urlopen(req, timeout=5) as resp:
                    data = json.loads(resp.read().decode("utf-8"))
                    tag = data.get("tag_name") or APP_VERSION
                    url = data.get("html_url") or f"https://github.com/{GITHUB_REPO}"
                    with self._lock:
                        self._pending_update_result = ("ok", tag, url)
            except Exception:
                try:
                    req = urllib.request.Request(
                        f"https://api.github.com/repos/{GITHUB_REPO}/tags",
                        headers={"User-Agent": "GameSir-Bridge-macOS"},
                    )
                    with urllib.request.urlopen(req, timeout=5) as resp:
                        tags = json.loads(resp.read().decode("utf-8"))
                        tag = tags[0]["name"] if tags else APP_VERSION
                        url = f"https://github.com/{GITHUB_REPO}/releases"
                        with self._lock:
                            self._pending_update_result = ("ok", tag, url)
                except Exception:
                    with self._lock:
                        self._pending_update_result = ("err", None, None)

        threading.Thread(target=_worker, daemon=True).start()

    @objc.python_method
    def _show_update_alert(self, state, tag, url):
        alert = NSAlert.alloc().init()
        alert.setMessageText_(self.t("upd_title"))
        if state == "err":
            alert.setInformativeText_(self.t("upd_err"))
            alert.addButtonWithTitle_(self.t("upd_ok"))
            alert.runModal()
        elif tag == APP_VERSION:
            alert.setInformativeText_(self.t("upd_latest").format(APP_VERSION))
            alert.addButtonWithTitle_(self.t("upd_ok"))
            alert.runModal()
        else:
            alert.setInformativeText_(self.t("upd_avail").format(tag, APP_VERSION))
            alert.addButtonWithTitle_(self.t("upd_open"))
            alert.addButtonWithTitle_(self.t("upd_ok"))
            if alert.runModal() == NSAlertFirstButtonReturn:
                webbrowser.open(url)

    @objc.python_method
    def reload_all(self):
        self.bridge.release_all()
        self.bridge.reload_config()
        self.lang = detect_lang(self.bridge.cfg)
        self._setup_top_left_menu()

    @objc.python_method
    def _queue_status(self, dev, pr):
        with self._lock:
            self._pending_status = (dev, pr)

    @objc.python_method
    def _queue_osd(self, pr):
        with self._lock:
            self._pending_osd = pr

    @objc.python_method
    def _queue_hud(self):
        with self._lock:
            self._pending_hud = True

    def flushUiTimer_(self, _t):
        if os.path.exists(WAKE_PATH):
            try:
                os.remove(WAKE_PATH)
            except OSError:
                pass
            self.panel.show()

        with self._lock:
            st = self._pending_status
            osd = self._pending_osd
            hud = self._pending_hud
            upd = self._pending_update_result
            self._pending_status = None
            self._pending_osd = None
            self._pending_hud = False
            self._pending_update_result = None

        if st is not None:
            dev, _ = st
            self.last_device = dev
            if len(self.panel.profile_buttons) != len(
                self.bridge.cfg.get("profiles", {})
            ):
                if self.panel.is_visible():
                    self.panel.show()
            else:
                self.panel.sync_ui()

        if osd is not None:
            self.osd.show(self.t("osd_profile").format(osd.upper()))

        if hud:
            self.panel.toggle()

        if upd is not None:
            self._show_update_alert(*upd)


if __name__ == "__main__":
    delegate = GameSirAppDelegate.alloc().init()
    delegate.nsapp.run()
