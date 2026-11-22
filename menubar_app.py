import subprocess, sys, threading, pathlib, rumps
from gamesir_bridge import GameSirBridge

class GameSirMenuBar(rumps.App):
    def __init__(self):
        super().__init__("🎮", quit_button="Sair")
        self.bridge = GameSirBridge(on_status=self.update_status)
        self.status_item = rumps.MenuItem("Status: Procurando controle...")
        self.prof_items = {}
        for name in self.bridge.cfg["profiles"]:
            item = rumps.MenuItem(f"Perfil: {name}", callback=self.select_profile)
            item.profile_name = name
            self.prof_items[name] = item

        self.menu = [
            self.status_item,
            None,
            *self.prof_items.values(),
            None,
            rumps.MenuItem("Configurar Botoes (App Visual)", callback=self.open_config),
            rumps.MenuItem("Recarregar Configuracoes", callback=self.reload_cfg),
        ]
        self._refresh_checks()
        threading.Thread(target=self.bridge.run_forever, daemon=True).start()

    def _refresh_checks(self):
        for name, item in self.prof_items.items():
            item.state = (name == self.bridge.current_profile)

    def update_status(self, device_name, profile_name):
        self.title = "🎮" if device_name else "🎮⚠️"
        self.status_item.title = f"Conectado: {device_name}" if device_name else "Desconectado (aguardando USB)"
        self._refresh_checks()

    def select_profile(self, sender):
        self.bridge.set_profile(sender.profile_name, vibrate=True)
        self._refresh_checks()

    def open_config(self, _):
        ui_script = str(pathlib.Path(__file__).parent / "config_ui.py")
        subprocess.Popen([sys.executable, ui_script])

    def reload_cfg(self, _):
        self.bridge.reload_config()
        self._refresh_checks()
        rumps.notification("GameSir Bridge", "Configuracao", "Perfis recarregados do profiles.json!")

if __name__ == "__main__":
    GameSirMenuBar().run()
