import http.server
import json
import os
import pathlib
import signal
import socketserver
import threading
import time
import urllib.parse
import webbrowser

PORT = 58492
BASE_DIR = pathlib.Path(__file__).parent
CONFIG_PATH = BASE_DIR / "profiles.json"
PID_PATH = BASE_DIR / ".config_ui.pid"
LIVE_STATE_PATH = pathlib.Path("/tmp/gamesir_live.json")

HTML_TEMPLATE = """<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>GameSir Bridge v5.2 — Configurator</title>
<style>
  :root { --bg: #0f1115; --card: #181b22; --border: #2a2f3d; --accent: #3b82f6; --ok: #10b981; --danger: #ef4444; --text: #f3f4f6; --muted: #9ca3af; }
  body { font-family: -apple-system, BlinkMacSystemFont, "SF Pro Text", sans-serif; background: var(--bg); color: var(--text); margin: 0; padding: 24px; }
  .container { max-width: 1020px; margin: 0 auto; }
  header { display: flex; justify-content: space-between; align-items: center; margin-bottom: 18px; border-bottom: 1px solid var(--border); padding-bottom: 16px; gap: 12px; flex-wrap: wrap; }
  h1 { font-size: 22px; margin: 0; }
  .toolbar { display: flex; gap: 10px; align-items: center; flex-wrap: wrap; }
  select, input, textarea, button { background: var(--card); color: var(--text); border: 1px solid var(--border); border-radius: 8px; padding: 8px 12px; font-size: 13px; font-family: inherit; }
  button { cursor: pointer; font-weight: 600; transition: 0.15s; }
  button.primary { background: var(--accent); border-color: var(--accent); color: #fff; }
  button.primary:hover { filter: brightness(1.1); }
  button.danger { background: rgba(239,68,68,0.15); border-color: var(--danger); color: var(--danger); }
  .live-bar { background: var(--card); border: 1px solid var(--border); border-radius: 12px; padding: 12px 16px; margin-bottom: 18px; display: flex; justify-content: space-between; align-items: center; flex-wrap: wrap; gap: 12px; font-size: 13px; }
  .pill { display: inline-block; background: var(--accent); color: #fff; padding: 2px 8px; border-radius: 6px; font-weight: 700; margin-right: 4px; font-size: 12px; }
  .grid { display: grid; grid-template-columns: repeat(auto-fit, minmax(290px, 1fr)); gap: 16px; margin-bottom: 20px; }
  .card { background: var(--card); border: 1px solid var(--border); border-radius: 12px; padding: 16px; }
  .card h2 { font-size: 14px; margin: 0 0 14px 0; color: var(--accent); text-transform: uppercase; letter-spacing: 0.5px; }
  .row { display: flex; justify-content: space-between; align-items: center; margin-bottom: 10px; gap: 10px; }
  .row label { font-size: 13px; color: var(--muted); }
  .row input, .row select { width: 145px; text-align: center; }
  textarea { width: 100%; box-sizing: border-box; min-height: 92px; font-family: ui-monospace, SFMono-Regular, monospace; font-size: 12px; line-height: 1.5; }
  .hint { font-size: 11px; color: var(--muted); margin-top: 6px; }
  .toast { position: fixed; bottom: 20px; right: 20px; background: var(--ok); color: #fff; padding: 12px 20px; border-radius: 10px; font-weight: 600; display: none; box-shadow: 0 8px 20px rgba(0,0,0,0.4); }
</style>
</head>
<body>
<div class="container">
  <header>
    <h1>🎮 GameSir Bridge v5.2</h1>
    <div class="toolbar">
      <select id="langSelect" onchange="changeLang()">
        <option value="pt">Português</option>
        <option value="en">English</option>
        <option value="es">Español</option>
      </select>
      <select id="profileSelect" onchange="renderProfile()"></select>
      <button id="btnNew" onclick="createProfile()">+ Novo Perfil</button>
      <button id="btnDel" class="danger" onclick="deleteProfile()">Excluir</button>
      <button id="btnSave" class="primary" onclick="saveConfig()">Salvar Tudo</button>
    </div>
  </header>

  <div class="live-bar">
    <div id="liveStatus">● Waiting for controller...</div>
    <div id="liveButtons"></div>
    <div id="liveSticks" style="color: var(--muted); font-family: monospace;">LS: 0, 0 | RS: 0, 0</div>
  </div>

  <div class="grid">
    <div class="card">
      <h2 id="hSticks">Sticks & Triggers</h2>
      <div class="row"><label id="lblRsMode">Right Stick Mode</label>
        <select id="rightStickMode" onchange="toggleStickInputs()">
          <option id="optMouse" value="mouse">Mouse + Scroll (LB)</option>
          <option id="optKeys" value="keys">Directional Keys</option>
        </select>
      </div>
      <div class="row"><label id="lblDeadzone">Deadzone (0 - 30000)</label><input type="number" id="deadzone" step="500"></div>
      <div class="row"><label id="lblTrigger">Trigger Threshold (10 - 1000)</label><input type="number" id="triggerThreshold" step="25"></div>
      <div class="row"><label id="lblMouseSpeed">Mouse Speed</label><input type="number" id="mouseSpeed" step="1"></div>
      <div class="row"><label id="lblMouseCurve">Mouse Curve (1.0 - 3.0)</label><input type="number" id="mouseCurve" step="0.1"></div>
      <div class="row"><label id="lblScrollSpeed">Scroll Speed (LB)</label><input type="number" id="scrollSpeed" step="0.2"></div>
    </div>

    <div class="card">
      <h2 id="hMainBtns">Face & Shoulder Buttons</h2>
      <div id="mainButtons"></div>
    </div>

    <div class="card">
      <h2 id="hDpadBtns">D-Pad & System</h2>
      <div id="dpadButtons"></div>
    </div>

    <div class="card">
      <h2 id="hLeftStick">Left Stick</h2>
      <div id="leftStickKeys"></div>
    </div>

    <div class="card" id="rightStickCard">
      <h2 id="hRightStick">Right Stick (Keys Mode)</h2>
      <div id="rightStickKeys"></div>
    </div>

    <div class="card">
      <h2 id="hAppRules">Auto-Switch by App</h2>
      <textarea id="appRules" placeholder="pcsx2 = emulators&#10;safari = desktop_media"></textarea>
      <div id="hintAppRules" class="hint">Format: window_keyword = profile_name (1 per line)</div>
    </div>

    <div class="card">
      <h2 id="hCombos">Global Combos & Macros</h2>
      <textarea id="globalCombos" placeholder="VIEW+MENU = cmd+q&#10;LB+RB = cmd+shift+3"></textarea>
      <div id="hintCombos" class="hint">Format: BTN1+BTN2 = key1+key2 (1 per line)</div>
    </div>
  </div>
</div>
<div class="toast" id="toast">Saved!</div>

<script>
const I18N = {
  pt: {
    newProf: "+ Novo Perfil", delProf: "Excluir", saveAll: "Salvar Tudo",
    waiting: "Aguardando leitura do controle...", disconnected: "Controle desconectado",
    noBtns: "Nenhum botão pressionado",
    hSticks: "Analógicos & Gatilhos", lblRsMode: "Modo Analógico Direito",
    optMouse: "Mouse + Scroll (LB)", optKeys: "Teclas Direcionais",
    lblDeadzone: "Deadzone (0 - 30000)", lblTrigger: "Limiar Gatilho (10 - 1000)",
    lblMouseSpeed: "Velocidade Mouse", lblMouseCurve: "Curva Mouse (1.0 - 3.0)",
    lblScrollSpeed: "Velocidade Scroll (LB)",
    hMainBtns: "Botões Principais & Ombros", hDpadBtns: "D-Pad & Sistema",
    hLeftStick: "Analógico Esquerdo", hRightStick: "Analógico Direito (Modo Teclas)",
    hAppRules: "Troca Automática por App", hintAppRules: "Formato: palavra_chave_janela = nome_do_perfil (1 por linha)",
    hCombos: "Combos & Macros Globais", hintCombos: "Formato: BOTAO1+BOTAO2 = tecla1+tecla2 (1 por linha)",
    promptNew: "Nome do novo perfil (ex: Valorant, Premiere):",
    errExists: "Já existe um perfil com esse nome.",
    errMinOne: "Você precisa manter pelo menos 1 perfil.",
    confirmDel: "Excluir o perfil",
    toastSaved: "Configurações salvas e aplicadas!"
  },
  en: {
    newProf: "+ New Profile", delProf: "Delete", saveAll: "Save All",
    waiting: "Waiting for controller...", disconnected: "Controller disconnected",
    noBtns: "No buttons pressed",
    hSticks: "Sticks & Triggers", lblRsMode: "Right Stick Mode",
    optMouse: "Mouse + Scroll (LB)", optKeys: "Directional Keys",
    lblDeadzone: "Deadzone (0 - 30000)", lblTrigger: "Trigger Threshold (10 - 1000)",
    lblMouseSpeed: "Mouse Speed", lblMouseCurve: "Mouse Curve (1.0 - 3.0)",
    lblScrollSpeed: "Scroll Speed (LB)",
    hMainBtns: "Face & Shoulder Buttons", hDpadBtns: "D-Pad & System",
    hLeftStick: "Left Stick", hRightStick: "Right Stick (Keys Mode)",
    hAppRules: "Auto-Switch by App", hintAppRules: "Format: window_keyword = profile_name (1 per line)",
    hCombos: "Global Combos & Macros", hintCombos: "Format: BTN1+BTN2 = key1+key2 (1 per line)",
    promptNew: "New profile name (e.g. Valorant, Premiere):",
    errExists: "A profile with that name already exists.",
    errMinOne: "You must keep at least 1 profile.",
    confirmDel: "Delete profile",
    toastSaved: "Configuration saved and applied!"
  },
  es: {
    newProf: "+ Nuevo Perfil", delProf: "Eliminar", saveAll: "Guardar Todo",
    waiting: "Esperando lectura del control...", disconnected: "Control desconectado",
    noBtns: "Ningún botón presionado",
    hSticks: "Joysticks y Gatillos", lblRsMode: "Modo Joystick Derecho",
    optMouse: "Ratón + Scroll (LB)", optKeys: "Teclas Direccionales",
    lblDeadzone: "Zona Muerta (0 - 30000)", lblTrigger: "Umbral Gatillo (10 - 1000)",
    lblMouseSpeed: "Velocidad Ratón", lblMouseCurve: "Curva Ratón (1.0 - 3.0)",
    lblScrollSpeed: "Velocidad Scroll (LB)",
    hMainBtns: "Botones Principales y Superiores", hDpadBtns: "Cruceta y Sistema",
    hLeftStick: "Joystick Izquierdo", hRightStick: "Joystick Derecho (Modo Teclas)",
    hAppRules: "Cambio Automático por App", hintAppRules: "Formato: palabra_clave_ventana = nombre_perfil (1 por línea)",
    hCombos: "Combos y Macros Globales", hintCombos: "Formato: BOTON1+BOTON2 = tecla1+tecla2 (1 por línea)",
    promptNew: "Nombre del nuevo perfil (ej: Valorant, Premiere):",
    errExists: "Ya existe un perfil con ese nombre.",
    errMinOne: "Debes mantener al menos 1 perfil.",
    confirmDel: "¿Eliminar el perfil",
    toastSaved: "¡Configuración guardada y aplicada!"
  }
};

let cfg = {};
let lang = "en";
const MAIN_BTNS = ["A", "B", "X", "Y", "LB", "RB", "LT", "RT", "L3", "R3"];
const DPAD_BTNS = ["UP", "DOWN", "LEFT", "RIGHT", "MENU", "VIEW", "SHARE"];
const DIRS = ["up", "down", "left", "right"];

function t(k) { return (I18N[lang] || I18N.en)[k] || k; }

function applyLang() {
  document.documentElement.lang = lang;
  document.getElementById("langSelect").value = lang;
  document.getElementById("btnNew").textContent = t("newProf");
  document.getElementById("btnDel").textContent = t("delProf");
  document.getElementById("btnSave").textContent = t("saveAll");
  document.getElementById("hSticks").textContent = t("hSticks");
  document.getElementById("lblRsMode").textContent = t("lblRsMode");
  document.getElementById("optMouse").textContent = t("optMouse");
  document.getElementById("optKeys").textContent = t("optKeys");
  document.getElementById("lblDeadzone").textContent = t("lblDeadzone");
  document.getElementById("lblTrigger").textContent = t("lblTrigger");
  document.getElementById("lblMouseSpeed").textContent = t("lblMouseSpeed");
  document.getElementById("lblMouseCurve").textContent = t("lblMouseCurve");
  document.getElementById("lblScrollSpeed").textContent = t("lblScrollSpeed");
  document.getElementById("hMainBtns").textContent = t("hMainBtns");
  document.getElementById("hDpadBtns").textContent = t("hDpadBtns");
  document.getElementById("hLeftStick").textContent = t("hLeftStick");
  document.getElementById("hRightStick").textContent = t("hRightStick");
  document.getElementById("hAppRules").textContent = t("hAppRules");
  document.getElementById("hintAppRules").textContent = t("hintAppRules");
  document.getElementById("hCombos").textContent = t("hCombos");
  document.getElementById("hintCombos").textContent = t("hintCombos");
  document.getElementById("toast").textContent = t("toastSaved");
}

function changeLang() {
  lang = document.getElementById("langSelect").value;
  cfg.language = lang;
  applyLang();
}

async function load() {
  const res = await fetch("/api/config");
  cfg = await res.json();
  const nav = (navigator.language || "en").slice(0, 2).toLowerCase();
  lang = I18N[cfg.language] ? cfg.language : (I18N[nav] ? nav : "en");
  applyLang();
  populateSelect();
  renderGlobalRules();
  renderProfile();
}

function populateSelect() {
  const sel = document.getElementById("profileSelect");
  sel.innerHTML = "";
  Object.keys(cfg.profiles).forEach(name => {
    const opt = document.createElement("option");
    opt.value = name; opt.textContent = name;
    if (name === cfg.active_profile) opt.selected = true;
    sel.appendChild(opt);
  });
}

function renderGlobalRules() {
  const rules = cfg.app_rules || {};
  document.getElementById("appRules").value = Object.entries(rules).map(([k, v]) => `${k} = ${v}`).join("\\n");
  const combos = cfg.combos || {};
  document.getElementById("globalCombos").value = Object.entries(combos).map(([k, v]) => `${k} = ${v}`).join("\\n");
}

function parseLinesToMap(text) {
  const out = {};
  text.split("\\n").forEach(line => {
    const idx = line.indexOf("=");
    if (idx > 0) {
      const k = line.slice(0, idx).trim();
      const v = line.slice(idx + 1).trim();
      if (k && v) out[k] = v;
    }
  });
  return out;
}

function renderProfile() {
  const name = document.getElementById("profileSelect").value;
  cfg.active_profile = name;
  const p = cfg.profiles[name];
  document.getElementById("rightStickMode").value = p.right_stick_mode || "mouse";
  document.getElementById("deadzone").value = p.deadzone ?? cfg.deadzone ?? 10000;
  document.getElementById("triggerThreshold").value = p.trigger_threshold ?? cfg.trigger_threshold ?? 200;
  document.getElementById("mouseSpeed").value = p.mouse_speed ?? cfg.mouse_speed ?? 18;
  document.getElementById("mouseCurve").value = p.mouse_curve ?? cfg.mouse_curve ?? 1.8;
  document.getElementById("scrollSpeed").value = p.scroll_speed ?? 2.8;

  renderKeyGroup("mainButtons", MAIN_BTNS, p.buttons);
  renderKeyGroup("dpadButtons", DPAD_BTNS, p.buttons);
  renderKeyGroup("leftStickKeys", DIRS, p.left_stick);
  renderKeyGroup("rightStickKeys", DIRS, p.right_stick);
  toggleStickInputs();
}

function renderKeyGroup(elId, keys, obj) {
  const el = document.getElementById(elId);
  el.innerHTML = keys.map(k => `
    <div class="row">
      <label>${k.toUpperCase()}</label>
      <input type="text" data-key="${k}" value="${obj[k] || ""}">
    </div>
  `).join("");
}

function toggleStickInputs() {
  const isMouse = document.getElementById("rightStickMode").value === "mouse";
  document.getElementById("rightStickCard").style.opacity = isMouse ? "0.4" : "1";
}

function collectCurrentProfile() {
  const name = document.getElementById("profileSelect").value;
  const p = cfg.profiles[name];
  p.right_stick_mode = document.getElementById("rightStickMode").value;
  p.deadzone = parseInt(document.getElementById("deadzone").value) || 10000;
  p.trigger_threshold = parseInt(document.getElementById("triggerThreshold").value) || 200;
  p.mouse_speed = parseFloat(document.getElementById("mouseSpeed").value) || 18;
  p.mouse_curve = parseFloat(document.getElementById("mouseCurve").value) || 1.8;
  p.scroll_speed = parseFloat(document.getElementById("scrollSpeed").value) || 2.8;

  document.querySelectorAll("#mainButtons input, #dpadButtons input").forEach(inp => {
    p.buttons[inp.dataset.key] = inp.value.trim();
  });
  document.querySelectorAll("#leftStickKeys input").forEach(inp => {
    p.left_stick[inp.dataset.key] = inp.value.trim();
  });
  document.querySelectorAll("#rightStickKeys input").forEach(inp => {
    p.right_stick[inp.dataset.key] = inp.value.trim();
  });

  cfg.language = lang;
  cfg.app_rules = parseLinesToMap(document.getElementById("appRules").value);
  cfg.combos = parseLinesToMap(document.getElementById("globalCombos").value);
}

function createProfile() {
  const newName = prompt(t("promptNew"));
  if (!newName || !newName.trim()) return;
  const clean = newName.trim();
  if (cfg.profiles[clean]) return alert(t("errExists"));
  const base = cfg.profiles[document.getElementById("profileSelect").value];
  cfg.profiles[clean] = JSON.parse(JSON.stringify(base));
  cfg.active_profile = clean;
  populateSelect();
  renderProfile();
}

function deleteProfile() {
  const keys = Object.keys(cfg.profiles);
  if (keys.length <= 1) return alert(t("errMinOne"));
  const name = document.getElementById("profileSelect").value;
  if (!confirm(`${t("confirmDel")} "${name}"?`)) return;
  delete cfg.profiles[name];
  cfg.active_profile = Object.keys(cfg.profiles)[0];
  populateSelect();
  renderProfile();
}

async function saveConfig() {
  collectCurrentProfile();
  await fetch("/api/config", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(cfg)
  });
  const tEl = document.getElementById("toast");
  tEl.style.display = "block";
  setTimeout(() => tEl.style.display = "none", 2200);
}

async function pollLive() {
  try {
    const res = await fetch("/api/live");
    const live = await res.json();
    const st = document.getElementById("liveStatus");
    const btns = document.getElementById("liveButtons");
    const sticks = document.getElementById("liveSticks");
    if (live.connected) {
      st.innerHTML = `<span style="color:var(--ok)">● ${live.connected}</span> (${live.profile})`;
      btns.innerHTML = live.held && live.held.length
        ? live.held.map(b => `<span class="pill">${b}</span>`).join("")
        : `<span style="color:var(--muted)">${t("noBtns")}</span>`;
      sticks.textContent = `LS: ${live.lx}, ${live.ly} | RS: ${live.rx}, ${live.ry} | LT:${live.lt} RT:${live.rt}`;
    } else {
      st.innerHTML = `<span style="color:var(--muted)">○ ${t("disconnected")}</span>`;
      btns.innerHTML = "";
    }
  } catch (e) {}
}

load();
setInterval(pollLive, 120);
</script>
</body>
</html>
"""


class ConfigHandler(http.server.BaseHTTPRequestHandler):
    def log_message(self, format, *args):
        pass

    def do_GET(self):
        parsed = urllib.parse.urlparse(self.path)
        if parsed.path == "/":
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.end_headers()
            self.wfile.write(HTML_TEMPLATE.encode("utf-8"))
        elif parsed.path == "/api/config":
            self.send_response(200)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.end_headers()
            self.wfile.write(CONFIG_PATH.read_bytes())
        elif parsed.path == "/api/live":
            self.send_response(200)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.end_headers()
            if LIVE_STATE_PATH.exists():
                try:
                    self.wfile.write(LIVE_STATE_PATH.read_bytes())
                    return
                except Exception:
                    pass
            self.wfile.write(b'{"connected":null}')
        else:
            self.send_error(404)

    def do_POST(self):
        if self.path == "/api/config":
            length = int(self.headers.get("Content-Length", 0))
            body = self.rfile.read(length).decode("utf-8")
            data = json.loads(body)
            CONFIG_PATH.write_text(
                json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8"
            )
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(b'{"ok":true}')
        else:
            self.send_error(404)


def kill_previous_instance():
    if PID_PATH.exists():
        try:
            old_pid = int(PID_PATH.read_text().strip())
            if old_pid != os.getpid():
                os.kill(old_pid, signal.SIGTERM)
                time.sleep(0.25)
        except Exception:
            pass
    PID_PATH.write_text(str(os.getpid()))


class ReusableTCPServer(socketserver.TCPServer):
    allow_reuse_address = True


if __name__ == "__main__":
    kill_previous_instance()
    with ReusableTCPServer(("127.0.0.1", PORT), ConfigHandler) as httpd:
        threading.Timer(
            0.3, lambda: webbrowser.open(f"http://127.0.0.1:{PORT}")
        ).start()
        try:
            httpd.serve_forever()
        except KeyboardInterrupt:
            pass
        finally:
            if PID_PATH.exists():
                PID_PATH.unlink(missing_ok=True)