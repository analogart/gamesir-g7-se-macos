# GameSir G7 SE Universal Bridge for macOS (v5.2.0)

Userspace USB GIP-to-keyboard & mouse bridge for macOS — no kernel extensions required. Features a native macOS Control Panel window, Dock integration, live web button configurator, automatic profile switching by active window, and rumble feedback.

## Supported Controllers
- **GameSir G7 SE** (`0x3537:0x1010`)
- **GameSir G7** (`0x3537:0x1001`)
- **GameSir G7 HE** (`0x3537:0x1007`)
- **GameSir T4 Kaleid** (`0x3537:0x1002`)

## Features
- **Native Control Panel & OSD:** Switch profiles with a click or via controller shortcuts with floating on-screen notifications and vibration feedback.
- **Visual Web Configurator (`localhost:58492`):** Remap buttons, sticks, deadzones, trigger thresholds, mouse speed/curve, auto-switch app rules, and global macros with a real-time controller tester.
- **Auto-Switch by Active App:** Automatically switches between `emulators`, `mac_games`, and `desktop_media` based on the focused window (PCSX2, Dolphin, OpenEmu, RetroArch, Steam, browsers, etc.).
- **Analog Mouse & Scroll:** Use the right stick as a radial-curved mouse cursor and hold `LB + Right Stick` for smooth scrolling.

## Quick Install
```bash
git clone [https://github.com/analogart/gamesir-g7-se-macos.git](https://github.com/analogart/gamesir-g7-se-macos.git)
cd gamesir-g7-se-macos
bash install.sh
```

> **macOS Permissions:** On first launch, grant **Accessibility** and **Input Monitoring** permissions to **GameSir Bridge** (and **Python**) in **System Settings > Privacy & Security** (or run `open "x-apple.systempreferences:com.apple.preference.security?Privacy_Accessibility"` in Terminal).

## Controller Shortcuts
| Shortcut | Action |
| :--- | :--- |
| `VIEW + D-Pad Up` | Cycle profiles with OSD & rumble feedback |
| `VIEW + D-Pad Down` | Show / hide the native Control Panel window |
| `VIEW + MENU` | Quit active app (`Cmd + Q`) |
| `LB + RB` | Take screenshot (`Cmd + Shift + 3`) |
| `LB + Right Stick` | Scroll (when right stick is in `mouse` mode) |

## CLI Mode & Uninstall
- **Run headless in Terminal:** `python3 gamesir_bridge.py emulators`
- **Uninstall completely (app, LaunchAgent, and temp files):** `bash uninstall.sh`
