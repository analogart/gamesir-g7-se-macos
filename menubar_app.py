import fcntl
import json
import locale
import os
import pathlib
import subprocess
import sys
import threading

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
    NSWindow,
    NSWindowStyleMaskClosable,
    NSWindowStyleMaskMiniaturizable,
    NSWindowStyleMaskTitled,
)
from Foundation import NSObject, NSTimer
from gamesir_bridge import GameSirBridge

STRINGS = {
    "pt": {
        "searching": "Status: Procurando controle...",
        "connected": "Conectado: {}",
        "disconnected": "Desconectado (aguardando USB)",
        "osd_profile": "Perfil: {}",
        "config_ui": "Configurar Botões (App Visual)",
        "reload": "Recarregar Configurações",
        "open_panel": "Abrir Painel de Controle",
        "quit": "Encerrar Bridge",
        "hint": "Fechar no X mantém o bridge ativo em segundo plano.\nAtalho no controle: VIEW + ↓ (Painel) | VIEW + ↑ (Perfil)",
    },
    "en": {
        "searching": "Status: Searching for controller...",
        "connected": "Connected: {}",
        "disconnected": "Disconnected (waiting for USB)",
        "osd_profile": "Profile: {}",
        "config_ui": "Configure Buttons (Visual App)",
        "reload": "Reload Configuration",
        "open_panel": "Open Control Panel",
        "quit": "Quit Bridge",
        "hint": "Closing with X keeps the bridge running in background.\nController shortcut: VIEW + ↓ (Panel) | VIEW + ↑ (Profile)",
    },
    "es": {
        "searching": "Estado: Buscando control...",
        "connected": "Conectado: {}",
        "disconnected": "Desconectado (esperando USB)",
        "osd_profile": "Perfil: {}",
        "config_ui": "Configurar Botones (App Visual)",
        "reload": "Recargar Configuración",
        "open_panel": "Abrir Panel de Control",
        "quit": "Cerrar Bridge",
        "hint": "Cerrar con X mantiene el bridge activo en segundo plano.\nAtajo en control: VIEW + ↓ (Panel) | VIEW + ↑ (Perfil)",
    },
}

LANG_LABELS = [("pt", "Português"), ("en", "English"), ("es", "Español")]


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

    def hide_(self, _sender):
        if self.win:
            self.win.orderOut_(None)
            self.win = None
        self.timer = None


class ControlPanel(NSObject):
    def initWithController_(self, ctrl):
        self = objc.super(ControlPanel, self).init()
        if self is None:
            return None
        self.ctrl = ctrl
        self.win = None
        self.status_lbl = None
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
    def update_status_label(self):
        if self.status_lbl is not None:
            st_text = (
                f"●  {self.ctrl.t('connected').format(self.ctrl.last_device)}"
                if self.ctrl.last_device
                else f"○  {self.ctrl.t('searching')}"
            )
            self.status_lbl.setStringValue_(st_text)

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
        w = 380
        h = 285 + (len(profiles) * 38)
        x = (frame.size.width - w) / 2.0
        y = (frame.size.height - h) / 2.0

        win = NSWindow.alloc().initWithContentRect_styleMask_backing_defer_(
            NSMakeRect(x, y, w, h),
            NSWindowStyleMaskTitled
            | NSWindowStyleMaskClosable
            | NSWindowStyleMaskMiniaturizable,
            NSBackingStoreBuffered,
            False,
        )
        win.setTitle_("GameSir Bridge")
        win.setReleasedWhenClosed_(False)
        win.setDelegate_(self)
        content = win.contentView()

        self.status_lbl = NSTextField.alloc().initWithFrame_(
            NSMakeRect(20, h - 46, w - 40, 24)
        )
        self.status_lbl.setBezeled_(False)
        self.status_lbl.setDrawsBackground_(False)
        self.status_lbl.setEditable_(False)
        self.status_lbl.setSelectable_(False)
        self.status_lbl.setFont_(NSFont.boldSystemFontOfSize_(14.0))
        self.status_lbl.setAlignment_(NSTextAlignmentCenter)
        content.addSubview_(self.status_lbl)
        self.update_status_label()

        cur_y = h - 90
        for prof_name in profiles:
            active = prof_name == self.ctrl.bridge.current_profile
            prefix = "✓   " if active else ""
            btn = NSButton.alloc().initWithFrame_(NSMakeRect(30, cur_y, w - 60, 32))
            btn.setTitle_(f"{prefix}{prof_name}")
            btn.setBezelStyle_(NSBezelStyleRounded)
            btn.setTarget_(self)
            btn.setAction_("selectProf:")
            btn.setIdentifier_(prof_name)
            content.addSubview_(btn)
            cur_y -= 38

        cur_y -= 10
        for title, sel in [
            (self.ctrl.t("config_ui"), "openCfg:"),
            (self.ctrl.t("reload"), "reloadCfg:"),
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

    def selectProf_(self, sender):
        self.ctrl.bridge.set_profile(sender.identifier(), vibrate=True, show_osd=True)
        self.show()

    def selectLang_(self, sender):
        self.ctrl.set_language(sender.identifier())
        self.show()

    def openCfg_(self, _sender):
        self.ctrl.open_config_ui()

    def reloadCfg_(self, _sender):
        self.ctrl.reload_all()
        self.show()

    def quitApp_(self, _sender):
        NSApplication.sharedApplication().terminate_(None)


class GameSirAppDelegate(NSObject):
    def init(self):
        self = objc.super(GameSirAppDelegate, self).init()
        if self is None:
            return None

        self.nsapp = NSApplication.sharedApplication()
        self.nsapp.setActivationPolicy_(NSApplicationActivationPolicyRegular)

        icns_path = str(pathlib.Path(__file__).parent / "AppIcon.icns")
        icon = NSImage.alloc().initWithContentsOfFile_(icns_path)
        if icon is not None:
            self.nsapp.setApplicationIconImage_(icon)

        self.osd = ProfileOSD.alloc().init()
        self.panel = ControlPanel.alloc().initWithController_(self)

        self._lock = threading.Lock()
        self._pending_status = None
        self._pending_osd = None
        self._pending_hud = False

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

    def applicationWillTerminate_(self, _notif):
        self.bridge.running = False
        self.bridge.release_all()
        try:
            self._timer.invalidate()
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
            pathlib.Path(__file__).parent.joinpath("profiles.json").write_text(
                json.dumps(self.bridge.cfg, indent=2, ensure_ascii=False),
                encoding="utf-8",
            )
        except Exception:
            pass
        self._setup_top_left_menu()

    @objc.python_method
    def open_config_ui(self):
        subprocess.Popen(
            [sys.executable, str(pathlib.Path(__file__).parent / "config_ui.py")]
        )

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
            self._pending_status = None
            self._pending_osd = None
            self._pending_hud = False

        if st is not None:
            dev, _ = st
            self.last_device = dev
            self.panel.update_status_label()

        if osd is not None:
            self.osd.show(self.t("osd_profile").format(osd.upper()))

        if hud:
            self.panel.toggle()


if __name__ == "__main__":
    delegate = GameSirAppDelegate.alloc().init()
    delegate.nsapp.run()