# GameSir G7 SE Universal Bridge for macOS (v3.0)

Userspace USB GIP-to-keyboard & mouse bridge for macOS with Menu Bar app, visual button configurator, auto-profile switching by active window, rumble feedback, and multi-controller support.

## Supported Controllers (Experimental Multi-PID)
- GameSir G7 SE (`0x3537:0x1010`)
- GameSir G7 (`0x3537:0x1001`)
- GameSir G7 HE (`0x3537:0x1007`)
- GameSir T4 Kaleid (`0x3537:0x1002`)

## Quick Install
```bash
bash install.sh
```
*(Make sure **Terminal** is enabled in **System Settings > Privacy & Security > Accessibility**)*

## Usage
- **Menu Bar App + Visual Configurator (Recommended):**
  ```bash
  source .venv/bin/activate && python3 menubar_app.py
  ```
- **CLI Mode:**
  ```bash
  python3 gamesir_bridge.py emulators
  ```

## Built-in Shortcuts
- `VIEW + D-Pad Up`: Cycle profiles manually with rumble feedback
- `VIEW + MENU`: Quit active app (`Cmd + Q`)
- `LB + RB`: Take screenshot (`Cmd + Shift + 3`)
