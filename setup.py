from setuptools import setup

setup(
    app=["menubar_app.py"],
    name="GameSir Bridge",
    data_files=["profiles.json", "config_ui.py", "gamesir_bridge.py"],
    options={
        "py2app": {
            "argv_emulation": False,
            "plist": {
                "LSUIElement": True,
                "CFBundleIdentifier": "com.analogart.gamesirbridge",
                "CFBundleShortVersionString": "4.0.0",
            },
            "packages": ["usb", "pynput", "rumps", "AppKit"],
        }
    },
    setup_requires=["py2app"],
)
