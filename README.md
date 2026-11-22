# GameSir Bridge for macOS (`v6.0.0`)

Userspace USB GIP (Gaming Input Protocol) driver, key/mouse mapper, and native macOS HUD app for **GameSir G7 SE**, **GameSir G7**, **GameSir G7 HE**, and **GameSir T4 Kaleid** on Apple Silicon & Intel Macs.

## What's New in v6.0.0
* **Native Translucent macOS HUD & Embedded Configurator:** True `NSVisualEffectView` HUD window, Dock quick-switch menu, and an integrated `WKWebView` visual configurator window.
* **Live SVG Controller Telemetry:** Real-time interactive controller visualizer showing pressed buttons, analog stick vectors, deadzone rings, and trigger pressure bars.
* **Zero-Drift Analog Calibration:** One-click resting center calibration (`lx`, `ly`, `rx`, `ry` offsets) saved directly to `profiles.json`.
* **Shift Layer (Secondary Mappings):** Assign any button as a modifier to unlock a full second layer of actions per profile.
* **Per-Button Turbo (Rapid-Fire) & Toggle (Hold Lock):** Configure adjustable rapid-fire (`2–40 Hz`) or toggle locks on any button.
* **Press-to-Bind Recorder, Presets & JSON Import/Export:** Bind keys with a single keypress (`⌨️`), load ready-made templates (`PCSX2`, `Dolphin`, `Hollow Knight`), or share profiles.
* **macOS Shortcuts Integration:** Trigger native macOS Shortcuts from any button or combo using `shortcut:Shortcut Name`.
* **Full Multi-Language UI:** English, Português, and Español across both the native macOS HUD and the Visual Configurator.

## Quick Shortcuts
* `VIEW + UP`: Cycle active profile (with floating HUD notification and controller rumble)
* `VIEW + DOWN`: Toggle Control Panel HUD
* `LB + Right Stick` (in Mouse mode): 2D Trackpad-style Scroll

## Requirements
* macOS 12+
* Python 3 + `pyusb`, `pynput`, `pyobjc` (`libusb` via Homebrew: `brew install libusb`)
* Accessibility permission granted to **GameSir Bridge.app** in *System Settings → Privacy & Security → Accessibility*.