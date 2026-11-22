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
    NSBezelStyleRegularSquare,
    NSBezelStyleRounded,
    NSBox,
    NSBoxCustom,
    NSButton,
    NSColor,
    NSFloatingWindowLevel,
    NSFont,
    NSImage,
    NSMakeRect,
    NSMenu,
    NSMenuItem,
    NSScreen,
    NSSegmentedControl,
    NSSegmentStyleRounded,
    NSSwitch,
    NSTextAlignmentCenter,
    NSTextAlignmentLeft,
    NSTextAlignmentRight,
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
        "connected": "{}",
        "sub_searching": "Conecte um GameSir via USB",
        "sub_connected": "Driver USB GIP ativo",
        "osd_profile": "Perfil: {}",
        "sec_profiles": "PERFIL ATIVO",
        "sec_options": "PREFERÊNCIAS RÁPIDAS",
        "opt_autoswitch": "Troca automática por app",
        "opt_rumble": "Vibração ao trocar perfil",
        "config_ui": "Configurar Botões (App Visual)",
        "reload": "Recarregar",
        "check_updates": "Atualizações",
        "open_panel": "Abrir Painel de Controle",
        "quit": "Encerrar",
        "ax_fix": "Conceder Permissão de Acessibilidade",
        "upd_title": "Atualizações — GameSir Bridge",
        "upd_latest": "Você já está na versão mais recente ({}).",
        "upd_avail": "Nova versão disponível: {} (atual: {}).\nDeseja abrir a página no GitHub?",
        "upd_err": "Não foi possível verificar atualizações agora.",
        "upd_open": "Abrir GitHub",
        "upd_ok": "OK",
        "hint": "VIEW + ▲ Perfil   •   VIEW + ▼ Painel   •   X mantém em 2º plano",
    },
    "en": {
        "searching": "Searching for controller...",
        "connected": "{}",
        "sub_searching": "Connect a GameSir controller via USB",
        "sub_connected": "USB GIP driver active",
        "osd_profile": "Profile: {}",
        "sec_profiles": "ACTIVE PROFILE",
        "sec_options": "QUICK PREFERENCES",
        "opt_autoswitch": "Auto-switch by active app",
        "opt_rumble": "Rumble feedback on switch",
        "config_ui": "Configure Buttons (Visual App)",
        "reload": "Reload",
        "check_updates": "Updates",
        "open_panel": "Open Control Panel",
        "quit": "Quit",
        "ax_fix": "Grant Accessibility Permission",
        "upd_title": "Updates — GameSir Bridge",
        "upd_latest": "You are running the latest version ({}).",
        "upd_avail": "New version available: {} (current: {}).\nOpen GitHub release page?",
        "upd_err": "Could not check for updates right now.",
        "upd_open": "Open GitHub",
        "upd_ok": "OK",
        "hint": "VIEW + ▲ Profile   •   VIEW + ▼ Panel   •   X keeps running",
    },
    "es": {
        "searching": "Buscando control USB...",
        "connected": "{}",
        "sub_searching": "Conecta un mando GameSir por USB",
        "sub_connected": "Controlador USB GIP activo",
        "osd_profile": "Perfil: {}",
        "sec_profiles": "PERFIL ACTIVO",
        "sec_options": "PREFERENCIAS RÁPIDAS",
        "opt_autoswitch": "Cambio automático por app",
        "opt_rumble": "Vibración al cambiar perfil",
        "config_ui": "Configurar Botones (App Visual)",
        "reload": "Recargar",
        "check_updates": "Actualizaciones",
        "open_panel": "Abrir Panel de Control",
        "quit": "Cerrar",
        "ax_fix": "Conceder Permiso de Accesibilidad",
        "upd_title": "Actualizaciones — GameSir Bridge",
        "upd_latest": "Ya tienes la versión más reciente ({}).",
        "upd_avail": "Nueva versión disponible: {} (actual: {}).\n¿Abrir la página en GitHub?",
        "upd_err": "No se pudieron comprobar actualizaciones ahora.",
        "upd_open": "Abrir GitHub",
        "upd_ok": "OK",
        "hint": "VIEW + ▲ Perfil   •   VIEW + ▼ Panel   •   X sigue en 2º plano",
    },
}

LANG_CODES = ["pt", "en", "es"]
LANG_NAMES = ["PT", "EN", "ES"]


def sf_symbol(name: str, fallback: str = None):
    if hasattr(NSImage, "imageWithSystemSymbolName_accessibilityDescription_"):
        img = NSImage.imageWithSystemSymbolName_accessibilityDescription_(name, None)
        if img is not None:
            return img
        if fallback:
            return NSImage.imageWithSystemSymbolName_accessibilityDescription_(
                fallback, None
            )
    return None


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


def make_card_box(x, y, w, h):
    box = NSBox.alloc().initWithFrame_(NSMakeRect(x, y, w, h))
    box.setBoxType_(NSBoxCustom)
    box.setCornerRadius_(12.0)
    box.setBorderWidth_(1.0)
    box.setBorderColor_(NSColor.colorWithWhite_alpha_(1.0, 0.10))
    box.setFillColor_(NSColor.colorWithWhite_alpha_(1.0, 0.055))
    box.setTitlePosition_(0)  # NSNoTitle
    return box


def make_label(x, y, w, h, text, size=13.0, bold=False, color=None, align=NSTextAlignmentLeft):
    lbl = NSTextField.alloc().initWithFrame_(NSMakeRect(x, y, w, h))
    lbl.setStringValue_(text)
    lbl.setBezeled_(False)
    lbl.setDrawsBackground_(False)
    lbl.setEditable_(False)
    lbl.setSelectable_(False)
    lbl.setAlignment_(align)
    lbl.setFont_(
        NSFont.boldSystemFontOfSize_(size) if bold else NSFont.systemFontOfSize_(size)
    )
    lbl.setTextColor_(color or NSColor.labelColor())
    return lbl


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

        lbl = make_label(
            12,
            11,
            w - 24,
            30,
            label_text,
            size=16.0,
            bold=True,
            align=NSTextAlignmentCenter,
        )
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
            wv.setAutoresizingMask_(18)
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
        self.status_dot = None
        self.status_title = None
        self.status_sub = None
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
        if self.status_title is not None:
            if self.ctrl.last_device:
                self.status_dot.setStringValue_("●")
                self.status_dot.setTextColor_(NSColor.systemGreenColor())
                self.status_title.setStringValue_(
                    self.ctrl.t("connected").format(self.ctrl.last_device)
                )
                self.status_sub.setStringValue_(self.ctrl.t("sub_connected"))
            else:
                self.status_dot.setStringValue_("○")
                self.status_dot.setTextColor_(NSColor.secondaryLabelColor())
                self.status_title.setStringValue_(self.ctrl.t("searching"))
                self.status_sub.setStringValue_(self.ctrl.t("sub_searching"))

        for prof_name, btn in self.profile_buttons.items():
            active = prof_name == self.ctrl.bridge.current_profile
            btn.setState_(1 if active else 0)
            if active:
                btn.setTitle_(f"  {prof_name}")
                ico = sf_symbol("checkmark.circle.fill")
                if ico:
                    btn.setImage_(ico)
                    btn.setImagePosition_(2)  # NSImageLeft
                btn.setContentTintColor_(NSColor.controlAccentColor())
            else:
                btn.setTitle_(f"  {prof_name}")
                ico = sf_symbol("circle")
                if ico:
                    btn.setImage_(ico)
                    btn.setImagePosition_(2)
                btn.setContentTintColor_(NSColor.secondaryLabelColor())

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

        pad = 20
        w = 400
        inner_w = w - (pad * 2)

        header_h = 62
        ax_h = 0 if ax_ok else 44
        prof_card_h = 34 + (len(profiles) * 34) + 8
        prefs_card_h = 88
        actions_h = 84
        footer_h = 56

        h = (
            44  # titlebar clearance
            + header_h
            + (ax_h + 10 if ax_h else 0)
            + 12
            + prof_card_h
            + 12
            + prefs_card_h
            + 14
            + actions_h
            + 12
            + footer_h
            + 16
        )

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
        win.setTitle_("")
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

        # Version pill in top-right
        ver_lbl = make_label(
            w - pad - 70,
            h - 32,
            70,
            18,
            APP_VERSION,
            size=11.0,
            bold=True,
            color=NSColor.secondaryLabelColor(),
            align=NSTextAlignmentRight,
        )
        content.addSubview_(ver_lbl)

        cur_y = h - 44 - header_h

        # 1. Hardware Status Card
        hdr_box = make_card_box(pad, cur_y, inner_w, header_h)
        content.addSubview_(hdr_box)

        self.status_dot = make_label(
            14, 21, 20, 22, "○", size=15.0, bold=True, align=NSTextAlignmentCenter
        )
        self.status_title = make_label(38, 28, inner_w - 52, 20, "", size=14.0, bold=True)
        self.status_sub = make_label(
            38,
            10,
            inner_w - 52,
            16,
            "",
            size=11.5,
            color=NSColor.secondaryLabelColor(),
        )
        hdr_box.addSubview_(self.status_dot)
        hdr_box.addSubview_(self.status_title)
        hdr_box.addSubview_(self.status_sub)

        if not ax_ok:
            cur_y -= ax_h + 10
            ax_btn = NSButton.alloc().initWithFrame_(NSMakeRect(pad, cur_y, inner_w, 34))
            ax_btn.setTitle_(f"  {self.ctrl.t('ax_fix')}")
            ax_btn.setBezelStyle_(NSBezelStyleRounded)
            ax_btn.setContentTintColor_(NSColor.systemOrangeColor())
            ico = sf_symbol("exclamationmark.triangle.fill")
            if ico:
                ax_btn.setImage_(ico)
                ax_btn.setImagePosition_(2)
            ax_btn.setTarget_(self)
            ax_btn.setAction_("openAccessibility:")
            content.addSubview_(ax_btn)

        # 2. Profiles Card
        cur_y -= 12 + prof_card_h
        prof_box = make_card_box(pad, cur_y, inner_w, prof_card_h)
        content.addSubview_(prof_box)

        sec_lbl = make_label(
            14,
            prof_card_h - 24,
            inner_w - 28,
            15,
            self.ctrl.t("sec_profiles"),
            size=10.5,
            bold=True,
            color=NSColor.secondaryLabelColor(),
        )
        prof_box.addSubview_(sec_lbl)

        self.profile_buttons = {}
        py = prof_card_h - 60
        for prof_name in profiles:
            btn = NSButton.alloc().initWithFrame_(
                NSMakeRect(12, py, inner_w - 24, 28)
            )
            btn.setBezelStyle_(NSBezelStyleRegularSquare)
            btn.setBordered_(False)
            btn.setAlignment_(NSTextAlignmentLeft)
            btn.setFont_(NSFont.systemFontOfSize_(13.5))
            btn.setTarget_(self)
            btn.setAction_("selectProf:")
            btn.setIdentifier_(prof_name)
            prof_box.addSubview_(btn)
            self.profile_buttons[prof_name] = btn
            py -= 34

        # 3. Quick Preferences Card
        cur_y -= 12 + prefs_card_h
        pref_box = make_card_box(pad, cur_y, inner_w, prefs_card_h)
        content.addSubview_(pref_box)

        pref_hdr = make_label(
            14,
            prefs_card_h - 22,
            inner_w - 28,
            15,
            self.ctrl.t("sec_options"),
            size=10.5,
            bold=True,
            color=NSColor.secondaryLabelColor(),
        )
        pref_box.addSubview_(pref_hdr)

        # Row 1: Auto-switch
        lbl_as = make_label(14, 41, inner_w - 76, 18, self.ctrl.t("opt_autoswitch"), size=12.5)
        sw_as = NSSwitch.alloc().initWithFrame_(NSMakeRect(inner_w - 56, 37, 40, 24))
        sw_as.setState_(1 if self.ctrl.bridge.cfg.get("auto_switch", True) else 0)
        sw_as.setTarget_(self)
        sw_as.setAction_("toggleAutoSwitch:")
        pref_box.addSubview_(lbl_as)
        pref_box.addSubview_(sw_as)

        # Row 2: Rumble
        lbl_rb = make_label(14, 12, inner_w - 76, 18, self.ctrl.t("opt_rumble"), size=12.5)
        sw_rb = NSSwitch.alloc().initWithFrame_(NSMakeRect(inner_w - 56, 8, 40, 24))
        sw_rb.setState_(1 if self.ctrl.bridge.cfg.get("rumble_feedback", True) else 0)
        sw_rb.setTarget_(self)
        sw_rb.setAction_("toggleRumble:")
        pref_box.addSubview_(lbl_rb)
        pref_box.addSubview_(sw_rb)

        # 4. Primary Action + Secondary 2-Col Row
        cur_y -= 14 + actions_h
        cfg_btn = NSButton.alloc().initWithFrame_(
            NSMakeRect(pad, cur_y + 44, inner_w, 36)
        )
        cfg_btn.setTitle_(f"  {self.ctrl.t('config_ui')}")
        cfg_btn.setBezelStyle_(NSBezelStyleRounded)
        cfg_btn.setKeyEquivalent_("\r")  # Native macOS blue accent button
        ico_cfg = sf_symbol("slider.horizontal.3")
        if ico_cfg:
            cfg_btn.setImage_(ico_cfg)
            cfg_btn.setImagePosition_(7)
        cfg_btn.setTarget_(self)
        cfg_btn.setAction_("openCfg:")
        content.addSubview_(cfg_btn)

        half_w = (inner_w - 10) / 2.0
        rel_btn = NSButton.alloc().initWithFrame_(NSMakeRect(pad, cur_y, half_w, 32))
        rel_btn.setTitle_(f" {self.ctrl.t('reload')}")
        rel_btn.setBezelStyle_(NSBezelStyleRounded)
        ico_rel = sf_symbol("arrow.clockwise")
        if ico_rel:
            rel_btn.setImage_(ico_rel)
            rel_btn.setImagePosition_(7)
        rel_btn.setTarget_(self)
        rel_btn.setAction_("reloadCfg:")
        content.addSubview_(rel_btn)

        upd_btn = NSButton.alloc().initWithFrame_(
            NSMakeRect(pad + half_w + 10, cur_y, half_w, 32)
        )
        upd_btn.setTitle_(f" {self.ctrl.t('check_updates')}")
        upd_btn.setBezelStyle_(NSBezelStyleRounded)
        ico_upd = sf_symbol("arrow.down.circle")
        if ico_upd:
            upd_btn.setImage_(ico_upd)
            upd_btn.setImagePosition_(7)
        upd_btn.setTarget_(self)
        upd_btn.setAction_("checkUpdates:")
        content.addSubview_(upd_btn)

        # 5. Footer: Language Segmented Control + Quit + Shortcut Hint
        cur_y -= 12 + footer_h
        seg = NSSegmentedControl.alloc().initWithFrame_(
            NSMakeRect(pad, cur_y + 26, 156, 26)
        )
        seg.setSegmentCount_(3)
        seg.setSegmentStyle_(NSSegmentStyleRounded)
        for idx, name in enumerate(LANG_NAMES):
            seg.setLabel_forSegment_(name, idx)
            seg.setWidth_forSegment_(50, idx)
        if self.ctrl.lang in LANG_CODES:
            seg.setSelectedSegment_(LANG_CODES.index(self.ctrl.lang))
        seg.setTarget_(self)
        seg.setAction_("selectLangSeg:")
        content.addSubview_(seg)

        quit_btn = NSButton.alloc().initWithFrame_(
            NSMakeRect(w - pad - 110, cur_y + 25, 110, 28)
        )
        quit_btn.setTitle_(f" {self.ctrl.t('quit')}")
        quit_btn.setBezelStyle_(NSBezelStyleRounded)
        quit_btn.setContentTintColor_(NSColor.systemRedColor())
        ico_quit = sf_symbol("power")
        if ico_quit:
            quit_btn.setImage_(ico_quit)
            quit_btn.setImagePosition_(7)
        quit_btn.setTarget_(self)
        quit_btn.setAction_("quitApp:")
        content.addSubview_(quit_btn)

        hint = make_label(
            pad,
            cur_y,
            inner_w,
            16,
            self.ctrl.t("hint"),
            size=10.5,
            color=NSColor.secondaryLabelColor(),
            align=NSTextAlignmentCenter,
        )
        content.addSubview_(hint)

        self.sync_ui()
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

    def toggleAutoSwitch_(self, sender):
        self.ctrl.set_pref("auto_switch", bool(sender.state() == 1))

    def toggleRumble_(self, sender):
        val = bool(sender.state() == 1)
        self.ctrl.set_pref("rumble_feedback", val)
        if val:
            self.ctrl.bridge.rumble(45, 10)

    def selectLangSeg_(self, sender):
        idx = sender.selectedSegment()
        if 0 <= idx < len(LANG_CODES):
            self.ctrl.set_language(LANG_CODES[idx])
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
            self.last_device if self.last_device else self.t("searching")
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
    def _save_cfg(self):
        try:
            get_config_path().write_text(
                json.dumps(self.bridge.cfg, indent=2, ensure_ascii=False),
                encoding="utf-8",
            )
        except Exception:
            pass

    @objc.python_method
    def set_pref(self, key, value):
        self.bridge.cfg[key] = value
        self._save_cfg()

    @objc.python_method
    def set_language(self, code):
        self.lang = code
        self.bridge.cfg["language"] = code
        self._save_cfg()
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
