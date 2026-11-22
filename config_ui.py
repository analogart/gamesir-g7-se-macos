import http.server
import fcntl
import json
import os
import pathlib
import signal
import socketserver
import sys
import threading
import time
import urllib.parse
import webbrowser

from app_paths import get_config_path, get_pid_path

PORT = 58492
CONFIG_PATH = get_config_path()
PID_PATH = get_pid_path()
LIVE_STATE_PATH = pathlib.Path("/tmp/gamesir_live.json")
_server_started = False

HTML_TEMPLATE = r"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>GameSir Bridge v6.1 — Visual Configurator</title>
<style>
  :root { --bg: #0c0e12; --card: #161922; --border: #262b38; --accent: #3b82f6; --shift: #a855f7; --ok: #10b981; --warn: #f59e0b; --danger: #ef4444; --text: #f3f4f6; --muted: #9ca3af; }
  body { font-family: -apple-system, BlinkMacSystemFont, "SF Pro Text", sans-serif; background: var(--bg); color: var(--text); margin: 0; padding: 22px; }
  .container { max-width: 1120px; margin: 0 auto; }
  header { display: flex; justify-content: space-between; align-items: center; margin-bottom: 18px; border-bottom: 1px solid var(--border); padding-bottom: 14px; gap: 10px; flex-wrap: wrap; }
  h1 { font-size: 21px; margin: 0; display: flex; align-items: center; gap: 8px; }
  .badge { font-size: 11px; background: rgba(59,130,246,0.2); color: var(--accent); padding: 2px 8px; border-radius: 99px; border: 1px solid rgba(59,130,246,0.4); }
  .toolbar { display: flex; gap: 8px; align-items: center; flex-wrap: wrap; }
  select, input[type="text"], input[type="number"], textarea, button { background: var(--card); color: var(--text); border: 1px solid var(--border); border-radius: 8px; padding: 7px 11px; font-size: 13px; font-family: inherit; }
  button { cursor: pointer; font-weight: 600; transition: 0.15s; }
  button:hover { border-color: #4b5563; }
  button.primary { background: var(--accent); border-color: var(--accent); color: #fff; }
  button.shift-active { background: var(--shift); border-color: var(--shift); color: #fff; }
  button.danger { background: rgba(239,68,68,0.14); border-color: var(--danger); color: var(--danger); }
  .visualizer-card { background: var(--card); border: 1px solid var(--border); border-radius: 14px; padding: 16px; margin-bottom: 18px; display: flex; flex-direction: column; align-items: center; }
  .vis-header { width: 100%; display: flex; justify-content: space-between; align-items: center; font-size: 13px; margin-bottom: 8px; flex-wrap: wrap; gap: 8px; }
  .vis-actions { display: flex; gap: 8px; align-items: center; }
  svg.pad { width: 100%; max-width: 520px; height: auto; user-select: none; }
  .pad-body { fill: #1e222d; stroke: #333a4d; stroke-width: 2.5; }
  .pad-btn { fill: #282e3d; stroke: #465069; stroke-width: 1.5; transition: fill 0.06s; }
  .pad-btn.active { fill: var(--accent); stroke: #93c5fd; filter: drop-shadow(0 0 6px rgba(59,130,246,0.8)); }
  .pad-txt { fill: #cbd5e1; font-size: 10px; font-weight: 700; text-anchor: middle; dominant-baseline: central; pointer-events: none; }
  .stick-well { fill: #12151c; stroke: #3b4254; stroke-width: 1.5; }
  .dz-ring { fill: rgba(59,130,246,0.08); stroke: rgba(59,130,246,0.45); stroke-width: 1; stroke-dasharray: 3 2; }
  .stick-dot { fill: var(--ok); stroke: #fff; stroke-width: 1.5; }
  .trig-bg { fill: #12151c; stroke: #3b4254; stroke-width: 1.5; rx: 4; }
  .trig-fill { fill: var(--accent); rx: 3; }
  .layer-bar { background: var(--card); border: 1px solid var(--border); border-radius: 12px; padding: 12px 16px; margin-bottom: 18px; display: flex; justify-content: space-between; align-items: center; flex-wrap: wrap; gap: 12px; }
  .grid { display: grid; grid-template-columns: repeat(auto-fit, minmax(335px, 1fr)); gap: 16px; margin-bottom: 20px; }
  .card { background: var(--card); border: 1px solid var(--border); border-radius: 12px; padding: 16px; }
  .card h2 { font-size: 13px; margin: 0 0 14px 0; color: var(--accent); text-transform: uppercase; letter-spacing: 0.6px; display: flex; justify-content: space-between; align-items: center; }
  .card.shift-mode h2 { color: var(--shift); }
  .row { display: flex; justify-content: space-between; align-items: center; margin-bottom: 9px; gap: 6px; }
  .row label { font-size: 13px; color: var(--muted); flex: 1; }
  .row input[type="text"], .row input[type="number"], .row select { width: 112px; text-align: center; }
  .bind-wrap { display: flex; gap: 4px; align-items: center; }
  .bind-btn { padding: 5px 7px; font-size: 11px; color: var(--muted); }
  .bind-btn.listening { background: var(--warn); color: #000; border-color: var(--warn); animation: pulse 1s infinite; }
  .flag-pill { display: inline-flex; align-items: center; gap: 2px; font-size: 10px; font-weight: 700; color: var(--muted); background: #10131a; border: 1px solid var(--border); padding: 4px 6px; border-radius: 6px; cursor: pointer; user-select: none; }
  .flag-pill input { margin: 0; accent-color: var(--accent); cursor: pointer; }
  @keyframes pulse { 0%, 100% { opacity: 1; } 50% { opacity: 0.65; } }
  textarea { width: 100%; box-sizing: border-box; min-height: 92px; font-family: ui-monospace, SFMono-Regular, monospace; font-size: 12px; line-height: 1.5; }
  .hint { font-size: 11px; color: var(--muted); margin-top: 6px; }
  .toast { position: fixed; bottom: 20px; right: 20px; background: var(--ok); color: #fff; padding: 12px 20px; border-radius: 10px; font-weight: 600; display: none; box-shadow: 0 8px 20px rgba(0,0,0,0.4); z-index: 99; }
</style>
</head>
<body>
<div class="container">
  <header>
    <h1> GameSir Bridge <span class="badge">v6.1</span></h1>
    <div class="toolbar">
      <select id="langSelect" onchange="changeLang()">
        <option value="pt">Português</option>
        <option value="en">English</option>
        <option value="es">Español</option>
      </select>
      <select id="profileSelect" onchange="renderProfile()"></select>
      <select id="templateSelect" onchange="applyTemplate()">
          <option id="optTplDefault" value="">+ Preset Pronto...</option>
          <option value="pcsx2">PCSX2 (PS2)</option>
          <option value="dolphin">Dolphin (GC / Wii)</option>
          <option value="retroarch">RetroArch (SNES / GBA)</option>
          <option value="ppsspp">PPSSPP (PSP)</option>
          <option value="hollow_knight">Hollow Knight / 2D</option>
          <option value="minecraft_mac">Minecraft (macOS)</option>
          <option value="desktop_media">Desktop & Media (macOS)</option>
          <option value="dj_control">DJ / Audio Control</option>
        </select>
      <button id="btnNew" onclick="createProfile()">+ Novo</button>
      <button id="btnExport" onclick="exportProfile()">Exportar</button>
      <button id="btnImport" onclick="document.getElementById('importFile').click()">Importar</button>
      <input type="file" id="importFile" accept=".json" style="display:none" onchange="importProfile(event)">
      <button id="btnDel" class="danger" onclick="deleteProfile()">Excluir</button>
      <button id="btnSave" class="primary" onclick="saveConfig()">Salvar Tudo</button>
    </div>
  </header>

  <div class="visualizer-card">
    <div class="vis-header">
      <div id="liveStatus"> Waiting for controller...</div>
      <div class="vis-actions">
        <span id="liveSticks" style="color: var(--muted); font-family: monospace;">LS: 0, 0 | RS: 0, 0 | LT: 0 RT: 0</span>
        <button id="btnCalibrate" onclick="calibrateZeroDrift()"> Zero-Drift</button>
        <button id="btnResetCal" onclick="resetZeroDrift()" title="Reset calibration">↺</button>
      </div>
    </div>
    <svg class="pad" viewBox="0 0 520 260">
      <rect x="85" y="12" width="70" height="14" class="trig-bg"/>
      <rect id="bar-LT" x="86" y="13" width="0" height="12" class="trig-fill"/>
      <text x="65" y="19" class="pad-txt">LT</text>

      <rect x="365" y="12" width="70" height="14" class="trig-bg"/>
      <rect id="bar-RT" x="366" y="13" width="0" height="12" class="trig-fill"/>
      <text x="455" y="19" class="pad-txt">RT</text>

      <rect id="svg-LB" x="75" y="34" width="90" height="20" rx="8" class="pad-btn"/>
      <text x="120" y="44" class="pad-txt">LB</text>
      <rect id="svg-RB" x="355" y="34" width="90" height="20" rx="8" class="pad-btn"/>
      <text x="400" y="44" class="pad-txt">RB</text>

      <path d="M90,56 L430,56 C468,56 492,115 486,185 C482,226 452,244 432,232 C406,216 392,185 352,185 L168,185 C128,185 114,216 88,232 C68,244 38,226 34,185 C28,115 52,56 90,56 Z" class="pad-body"/>

      <rect id="svg-VIEW" x="212" y="96" width="24" height="14" rx="7" class="pad-btn"/>
      <text x="224" y="85" class="pad-txt">VIEW</text>
      <rect id="svg-MENU" x="284" y="96" width="24" height="14" rx="7" class="pad-btn"/>
      <text x="296" y="85" class="pad-txt">MENU</text>
      <rect id="svg-SHARE" x="248" y="122" width="24" height="14" rx="7" class="pad-btn"/>
      <text x="260" y="146" class="pad-txt">SHARE</text>

      <circle id="svg-L3" cx="130" cy="108" r="30" class="stick-well"/>
      <circle id="dz-L" cx="130" cy="108" r="10" class="dz-ring"/>
      <circle id="dot-L" cx="130" cy="108" r="6" class="stick-dot"/>

      <rect id="svg-UP" x="178" y="136" width="20" height="20" rx="4" class="pad-btn"/>
      <text x="188" y="146" class="pad-txt">▲</text>
      <rect id="svg-DOWN" x="178" y="176" width="20" height="20" rx="4" class="pad-btn"/>
      <text x="188" y="186" class="pad-txt">▼</text>
      <rect id="svg-LEFT" x="158" y="156" width="20" height="20" rx="4" class="pad-btn"/>
      <text x="168" y="166" class="pad-txt">◀</text>
      <rect id="svg-RIGHT" x="198" y="156" width="20" height="20" rx="4" class="pad-btn"/>
      <text x="208" y="166" class="pad-txt">▶</text>

      <circle id="svg-R3" cx="332" cy="162" r="30" class="stick-well"/>
      <circle id="dz-R" cx="332" cy="162" r="10" class="dz-ring"/>
      <circle id="dot-R" cx="332" cy="162" r="6" class="stick-dot"/>

      <circle id="svg-Y" cx="390" cy="84" r="13" class="pad-btn"/>
      <text x="390" y="84" class="pad-txt">Y</text>
      <circle id="svg-A" cx="390" cy="132" r="13" class="pad-btn"/>
      <text x="390" y="132" class="pad-txt">A</text>
      <circle id="svg-X" cx="366" cy="108" r="13" class="pad-btn"/>
      <text x="366" y="108" class="pad-txt">X</text>
      <circle id="svg-B" cx="414" cy="108" r="13" class="pad-btn"/>
      <text x="414" y="108" class="pad-txt">B</text>
    </svg>
  </div>

  <div class="layer-bar">
    <div style="display:flex; gap:10px; align-items:center; flex-wrap:wrap;">
      <strong id="lblShiftModifier" style="font-size:13px;">Shift Layer Button:</strong>
      <select id="shiftButtonSelect" onchange="updateShiftModifier()"></select>
      <span id="hintLegend" style="font-size:12px; color:var(--muted);">T = Turbo (Rapid-Fire) | L = Toggle (Lock)</span>
    </div>
    <div style="display:flex; gap:8px;">
      <button id="btnLayerBase" class="primary" onclick="setEditLayer('base')">Base Layer</button>
      <button id="btnLayerShift" onclick="setEditLayer('shift')">Shift Layer</button>
    </div>
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
      <div class="row"><label id="lblDeadzone">Deadzone (0 - 30000)</label><input type="number" id="deadzone" step="500" oninput="renderProfileDeadzone()"></div>
      <div class="row"><label id="lblTrigger">Trigger Threshold (10 - 1000)</label><input type="number" id="triggerThreshold" step="25"></div>
      <div class="row"><label id="lblTurboRate">Turbo Speed (Hz)</label><input type="number" id="turboRate" min="2" max="40" step="1"></div>
      <div class="row"><label id="lblMouseSpeed">Mouse Speed</label><input type="number" id="mouseSpeed" step="1"></div>
      <div class="row"><label id="lblMouseCurve">Mouse Curve (1.0 - 3.0)</label><input type="number" id="mouseCurve" step="0.1"></div>
      <div class="row"><label id="lblScrollSpeed">Scroll Speed (LB)</label><input type="number" id="scrollSpeed" step="0.2"></div>
    </div>

    <div class="card" id="cardMainBtns">
      <h2><span id="hMainBtns">Face & Shoulder Buttons</span><span id="badgeLayer1" style="font-size:10px;">BASE</span></h2>
      <div id="mainButtons"></div>
    </div>

    <div class="card" id="cardDpadBtns">
      <h2><span id="hDpadBtns">D-Pad & System</span><span id="badgeLayer2" style="font-size:10px;">BASE</span></h2>
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
      <div id="hintCombos" class="hint">Format: BTN1+BTN2 = key1+key2 or shortcut:Name (1 per line)</div>
    </div>
  </div>
</div>
<div class="toast" id="toast">Saved!</div>

<script>
const I18N = {
  pt: {
    optTplDefault: "+ Preset Pronto...",
    newProf: "+ Novo", exportProf: "Exportar", importProf: "Importar", delProf: "Excluir", saveAll: "Salvar Tudo",
    disconnected: "Controle desconectado",
    btnCalibrate: " Calibrar Zero-Drift",
    lblShiftModifier: "Botão Modificador (Shift Layer):",
    shiftNone: "Desativado",
    hintLegend: "T = Turbo (Disparo Rápido) | L = Toggle (Travar Tecla)",
    btnLayerBase: "Camada Normal", btnLayerShift: "Camada Shift",
    hSticks: "Analógicos, Gatilhos & Turbo", lblRsMode: "Modo Analógico Direito",
    optMouse: "Mouse + Scroll (LB)", optKeys: "Teclas Direcionais",
    lblDeadzone: "Deadzone (0 - 30000)", lblTrigger: "Limiar Gatilho (10 - 1000)",
    lblTurboRate: "Velocidade Turbo (cliques/s)",
    lblMouseSpeed: "Velocidade Mouse", lblMouseCurve: "Curva Mouse (1.0 - 3.0)",
    lblScrollSpeed: "Velocidade Scroll (LB)",
    hMainBtns: "Botões Principais & Ombros", hDpadBtns: "D-Pad & Sistema",
    hLeftStick: "Analógico Esquerdo", hRightStick: "Analógico Direito (Modo Teclas)",
    hAppRules: "Troca Automática por App", hintAppRules: "Formato: palavra_chave_janela = nome_do_perfil (1 por linha)",
    hCombos: "Combos, Macros & Shortcuts", hintCombos: "Formato: BTN1+BTN2 = tecla1+tecla2 ou shortcut:Nome (1 por linha)",
    promptNew: "Nome do novo perfil (ex: Valorant, Premiere):",
    errExists: "Já existe um perfil com esse nome.",
    errMinOne: "Você precisa manter pelo menos 1 perfil.",
    confirmDel: "Excluir o perfil",
    toastSaved: "Configurações salvas e aplicadas!",
    toastCalibrated: "Centro Zero-Drift calibrado! Clique em Salvar Tudo.",
    toastCalReset: "Calibração zerada! Clique em Salvar Tudo.",
    toastImported: "Perfil importado! Clique em Salvar Tudo para aplicar.",
    bindBtn: "⌨️", bindWait: "..."
  },
  en: {
    optTplDefault: "+ Load Preset...",
    newProf: "+ New", exportProf: "Export", importProf: "Import", delProf: "Delete", saveAll: "Save All",
    disconnected: "Controller disconnected",
    btnCalibrate: " Calibrate Zero-Drift",
    lblShiftModifier: "Shift Layer Modifier Button:",
    shiftNone: "Disabled",
    hintLegend: "T = Turbo (Rapid-Fire) | L = Toggle (Hold Lock)",
    btnLayerBase: "Base Layer", btnLayerShift: "Shift Layer",
    hSticks: "Sticks, Triggers & Turbo", lblRsMode: "Right Stick Mode",
    optMouse: "Mouse + Scroll (LB)", optKeys: "Directional Keys",
    lblDeadzone: "Deadzone (0 - 30000)", lblTrigger: "Trigger Threshold (10 - 1000)",
    lblTurboRate: "Turbo Rate (clicks/s)",
    lblMouseSpeed: "Mouse Speed", lblMouseCurve: "Mouse Curve (1.0 - 3.0)",
    lblScrollSpeed: "Scroll Speed (LB)",
    hMainBtns: "Face & Shoulder Buttons", hDpadBtns: "D-Pad & System",
    hLeftStick: "Left Stick", hRightStick: "Right Stick (Keys Mode)",
    hAppRules: "Auto-Switch by App", hintAppRules: "Format: window_keyword = profile_name (1 per line)",
    hCombos: "Global Combos, Macros & Shortcuts", hintCombos: "Format: BTN1+BTN2 = key1+key2 or shortcut:Name (1 per line)",
    promptNew: "New profile name (e.g. Valorant, Premiere):",
    errExists: "A profile with that name already exists.",
    errMinOne: "You must keep at least 1 profile.",
    confirmDel: "Delete profile",
    toastSaved: "Configuration saved and applied!",
    toastCalibrated: "Zero-Drift center calibrated! Click Save All.",
    toastCalReset: "Calibration reset! Click Save All.",
    toastImported: "Profile imported! Click Save All to apply.",
    bindBtn: "⌨️", bindWait: "..."
  },
  es: {
    optTplDefault: "+ Plantilla...",
    newProf: "+ Nuevo", exportProf: "Exportar", importProf: "Importar", delProf: "Eliminar", saveAll: "Guardar Todo",
    disconnected: "Control desconectado",
    btnCalibrate: " Calibrar Zero-Drift",
    lblShiftModifier: "Botón Modificador (Shift Layer):",
    shiftNone: "Desactivado",
    hintLegend: "T = Turbo (Disparo Rápido) | L = Toggle (Bloqueo)",
    btnLayerBase: "Capa Normal", btnLayerShift: "Capa Shift",
    hSticks: "Joysticks, Gatillos y Turbo", lblRsMode: "Modo Joystick Derecho",
    optMouse: "Ratón + Scroll (LB)", optKeys: "Teclas Direccionales",
    lblDeadzone: "Zona Muerta (0 - 30000)", lblTrigger: "Umbral Gatillo (10 - 1000)",
    lblTurboRate: "Velocidad Turbo (clics/s)",
    lblMouseSpeed: "Velocidad Ratón", lblMouseCurve: "Curva Ratón (1.0 - 3.0)",
    lblScrollSpeed: "Velocidad Scroll (LB)",
    hMainBtns: "Botones Principales y Superiores", hDpadBtns: "Cruceta y Sistema",
    hLeftStick: "Joystick Izquierdo", hRightStick: "Joystick Derecho (Modo Teclas)",
    hAppRules: "Cambio Automático por App", hintAppRules: "Formato: palabra_clave_ventana = nombre_perfil (1 por línea)",
    hCombos: "Combos, Macros y Shortcuts", hintCombos: "Formato: BOTON1+BOTON2 = tecla1+tecla2 o shortcut:Nombre (1 por línea)",
    promptNew: "Nombre del nuevo perfil (ej: Valorant, Premiere):",
    errExists: "Ya existe un perfil con ese nombre.",
    errMinOne: "Debes mantener al menos 1 perfil.",
    confirmDel: "¿Eliminar el perfil",
    toastSaved: "¡Configuración guardada y aplicada!",
    toastCalibrated: "¡Centro Zero-Drift calibrado! Haz clic en Guardar Todo.",
    toastCalReset: "¡Calibración reiniciada! Haz clic en Guardar Todo.",
    toastImported: "¡Perfil importado! Haz clic en Guardar Todo.",
    bindBtn: "⌨️", bindWait: "..."
  }
};

const PRESETS = {
  pcsx2: {
    right_stick_mode: "keys", deadzone: 9000, trigger_threshold: 200, shift_button: "SHARE",
    buttons: { A:"k", B:"l", X:"j", Y:"i", MENU:"enter", VIEW:"z", SHARE:"", UP:"up", DOWN:"down", LEFT:"left", RIGHT:"right", LB:"q", RB:"e", LT:"1", RT:"3", LS:"2", RS:"4" },
    shift_buttons: { A:"f1", B:"f3", X:"tab", Y:"esc", LB:"f2", RB:"f4" },
    right_stick_keys: { UP:"w", DOWN:"s", LEFT:"a", RIGHT:"d" }
  },
  dolphin: {
    right_stick_mode: "keys", deadzone: 9000, trigger_threshold: 200, shift_button: "SHARE",
    buttons: { A:"x", B:"z", X:"c", Y:"s", MENU:"enter", VIEW:"tab", SHARE:"", UP:"up", DOWN:"down", LEFT:"left", RIGHT:"right", LB:"q", RB:"w", LT:"a", RT:"d", LS:"1", RS:"2" },
    shift_buttons: { A:"f1", B:"f2", X:"tab", Y:"esc" },
    right_stick_keys: { UP:"i", DOWN:"k", LEFT:"j", RIGHT:"l" }
  },
  retroarch: {
    right_stick_mode: "keys", deadzone: 9500, trigger_threshold: 250, shift_button: "SHARE",
    buttons: { A:"x", B:"z", X:"s", Y:"a", MENU:"enter", VIEW:"rshift", SHARE:"", UP:"up", DOWN:"down", LEFT:"left", RIGHT:"right", LB:"q", RB:"w", LT:"1", RT:"2", LS:"f1", RS:"space" },
    shift_buttons: { A:"f2", B:"f4", X:"space", Y:"backspace", MENU:"f1" },
    right_stick_keys: { UP:"up", DOWN:"down", LEFT:"left", RIGHT:"right" }
  },
  ppsspp: {
    right_stick_mode: "keys", deadzone: 9000, trigger_threshold: 200, shift_button: "SHARE",
    buttons: { A:"x", B:"z", X:"s", Y:"a", MENU:"enter", VIEW:"space", SHARE:"", UP:"up", DOWN:"down", LEFT:"left", RIGHT:"right", LB:"q", RB:"w", LT:"1", RT:"2", LS:"tab", RS:"esc" },
    shift_buttons: { A:"f2", B:"f4", X:"tab", Y:"esc" },
    right_stick_keys: { UP:"i", DOWN:"k", LEFT:"j", RIGHT:"l" }
  },
  hollow_knight: {
    right_stick_mode: "keys", deadzone: 8500, trigger_threshold: 200, shift_button: "SHARE",
    buttons: { A:"z", B:"x", X:"c", Y:"a", MENU:"esc", VIEW:"tab", SHARE:"", UP:"up", DOWN:"down", LEFT:"left", RIGHT:"right", LB:"q", RB:"s", LT:"f", RT:"d", LS:"m", RS:"i" },
    shift_buttons: { A:"enter", B:"esc", VIEW:"m" },
    right_stick_keys: { UP:"up", DOWN:"down", LEFT:"left", RIGHT:"right" }
  },
  minecraft_mac: {
    right_stick_mode: "mouse", deadzone: 8000, trigger_threshold: 180, shift_button: "SHARE",
    mouse_speed: 18, scroll_speed: 12,
    buttons: { A:"space", B:"q", X:"e", Y:"f", MENU:"esc", VIEW:"tab", SHARE:"", UP:"f5", DOWN:"t", LEFT:"1", RIGHT:"2", LB:"mouse_left", RB:"mouse_right", LT:"lshift", RT:"lctrl", LS:"lctrl", RS:"f3" },
    shift_buttons: { A:"enter", B:"cmd+q", X:"3", Y:"4" },
    left_stick_keys: { UP:"w", DOWN:"s", LEFT:"a", RIGHT:"d" }
  },
  desktop_media: {
    right_stick_mode: "mouse", deadzone: 8000, trigger_threshold: 200, shift_button: "SHARE",
    mouse_speed: 16, scroll_speed: 14,
    buttons: { A:"enter", B:"esc", X:"space", Y:"cmd+w", MENU:"cmd+tab", VIEW:"ctrl+up", SHARE:"", UP:"up", DOWN:"down", LEFT:"left", RIGHT:"right", LB:"scroll_mod", RB:"mouse_left", LT:"mouse_right", RT:"cmd+l", LS:"cmd+c", RS:"cmd+v" },
    shift_buttons: { A:"f11", B:"cmd+q", X:"cmd+shift+3", Y:"cmd+t", LEFT:"cmd+[", RIGHT:"cmd+]" },
    left_stick_keys: { UP:"up", DOWN:"down", LEFT:"left", RIGHT:"right" }
  },
  dj_control: {
    right_stick_mode: "mouse", deadzone: 8500, trigger_threshold: 180, shift_button: "SHARE",
    mouse_speed: 14, scroll_speed: 16,
    buttons: { A:"space", B:"c", X:"s", Y:"l", MENU:"enter", VIEW:"tab", SHARE:"", UP:"up", DOWN:"down", LEFT:"left", RIGHT:"right", LB:"scroll_mod", RB:"mouse_left", LT:"q", RT:"w", LS:"1", RS:"2" },
    shift_buttons: { A:"b", B:"r", X:"i", Y:"o" },
    left_stick_keys: { UP:"up", DOWN:"down", LEFT:"left", RIGHT:"right" }
  }
};

let cfg = {};
let lang = "en";
let editLayer = "base";
let activeBindTarget = null;
let lastRaw = { lx: 0, ly: 0, rx: 0, ry: 0 };
const MAIN_BTNS = ["A", "B", "X", "Y", "LB", "RB", "LT", "RT", "L3", "R3"];
const DPAD_BTNS = ["UP", "DOWN", "LEFT", "RIGHT", "MENU", "VIEW", "SHARE"];
const ALL_BTNS = [...MAIN_BTNS, ...DPAD_BTNS];
const DIRS = ["up", "down", "left", "right"];

function t(k) { return (I18N[lang] || I18N.en)[k] || k; }

function showToast(msg) {
  const el = document.getElementById("toast");
  el.textContent = msg;
  el.style.display = "block";
  setTimeout(() => el.style.display = "none", 2600);
}

function applyLang() {
  document.documentElement.lang = lang;
  document.getElementById("langSelect").value = lang;
  document.getElementById("optTplDefault").textContent = t("optTplDefault");
  document.getElementById("btnNew").textContent = t("newProf");
  document.getElementById("btnExport").textContent = t("exportProf");
  document.getElementById("btnImport").textContent = t("importProf");
  document.getElementById("btnDel").textContent = t("delProf");
  document.getElementById("btnSave").textContent = t("saveAll");
  document.getElementById("btnCalibrate").textContent = t("btnCalibrate");
  document.getElementById("lblShiftModifier").textContent = t("lblShiftModifier");
  document.getElementById("hintLegend").textContent = t("hintLegend");
  document.getElementById("btnLayerBase").textContent = t("btnLayerBase");
  document.getElementById("btnLayerShift").textContent = t("btnLayerShift");
  document.getElementById("hSticks").textContent = t("hSticks");
  document.getElementById("lblRsMode").textContent = t("lblRsMode");
  document.getElementById("optMouse").textContent = t("optMouse");
  document.getElementById("optKeys").textContent = t("optKeys");
  document.getElementById("lblDeadzone").textContent = t("lblDeadzone");
  document.getElementById("lblTrigger").textContent = t("lblTrigger");
  document.getElementById("lblTurboRate").textContent = t("lblTurboRate");
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
}

function changeLang() {
  lang = document.getElementById("langSelect").value;
  cfg.language = lang;
  applyLang();
  populateShiftModifier();
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

function showToast(msg, isErr = false) {
  let el = document.getElementById("gsToast");
  if (!el) {
    el = document.createElement("div");
    el.id = "gsToast";
    el.style.cssText = "position:fixed;bottom:18px;right:18px;padding:10px 16px;border-radius:10px;font-size:13px;font-weight:600;z-index:9999;box-shadow:0 8px 24px rgba(0,0,0,0.45);transition:opacity .25s;";
    document.body.appendChild(el);
  }
  el.style.background = isErr ? "#dc2626" : "#0284c7";
  el.style.color = "#fff";
  el.style.opacity = "1";
  el.textContent = msg;
  clearTimeout(window._gsToastTimer);
  window._gsToastTimer = setTimeout(() => { el.style.opacity = "0"; }, 3200);
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

function populateShiftModifier() {
  const p = cfg.profiles[document.getElementById("profileSelect").value];
  const sel = document.getElementById("shiftButtonSelect");
  sel.innerHTML = `<option value="">${t("shiftNone")}</option>` +
    ALL_BTNS.map(b => `<option value="${b}" ${p.shift_button === b ? "selected" : ""}>${b}</option>`).join("");
}

function updateShiftModifier() {
  const p = cfg.profiles[document.getElementById("profileSelect").value];
  p.shift_button = document.getElementById("shiftButtonSelect").value;
  renderProfile();
}

function setEditLayer(layer) {
  collectCurrentProfile();
  editLayer = layer;
  document.getElementById("btnLayerBase").className = layer === "base" ? "primary" : "";
  document.getElementById("btnLayerShift").className = layer === "shift" ? "shift-active" : "";
  document.getElementById("cardMainBtns").classList.toggle("shift-mode", layer === "shift");
  document.getElementById("cardDpadBtns").classList.toggle("shift-mode", layer === "shift");
  document.getElementById("badgeLayer1").textContent = layer.toUpperCase();
  document.getElementById("badgeLayer2").textContent = layer.toUpperCase();
  renderProfile();
}

function renderGlobalRules() {
  const rules = cfg.app_rules || {};
  document.getElementById("appRules").value = Object.entries(rules).map(([k, v]) => `${k} = ${v}`).join("\n");
  const combos = cfg.combos || {};
  document.getElementById("globalCombos").value = Object.entries(combos).map(([k, v]) => `${k} = ${v}`).join("\n");
}

function parseLinesToMap(text) {
  const out = {};
  text.split("\n").forEach(line => {
    const idx = line.indexOf("=");
    if (idx > 0) {
      const k = line.slice(0, idx).trim();
      const v = line.slice(idx + 1).trim();
      if (k && v) out[k] = v;
    }
  });
  return out;
}

function renderProfileDeadzone() {
  const dz = parseInt(document.getElementById("deadzone").value) || 10000;
  const r = Math.min(28, Math.max(2, (dz / 32768) * 28));
  document.getElementById("dz-L").setAttribute("r", r.toFixed(1));
  document.getElementById("dz-R").setAttribute("r", r.toFixed(1));
}

function renderProfile() {
  const name = document.getElementById("profileSelect").value;
  cfg.active_profile = name;
  const p = cfg.profiles[name];
  if (!p.shift_buttons) p.shift_buttons = {};
  if (!p.turbo_buttons) p.turbo_buttons = [];
  if (!p.toggle_buttons) p.toggle_buttons = [];

  populateShiftModifier();
  document.getElementById("rightStickMode").value = p.right_stick_mode || "mouse";
  document.getElementById("deadzone").value = p.deadzone ?? cfg.deadzone ?? 10000;
  document.getElementById("triggerThreshold").value = p.trigger_threshold ?? cfg.trigger_threshold ?? 200;
  document.getElementById("turboRate").value = p.turbo_rate ?? 12;
  document.getElementById("mouseSpeed").value = p.mouse_speed ?? cfg.mouse_speed ?? 18;
  document.getElementById("mouseCurve").value = p.mouse_curve ?? cfg.mouse_curve ?? 1.8;
  document.getElementById("scrollSpeed").value = p.scroll_speed ?? 2.8;

  const targetMap = editLayer === "shift" ? p.shift_buttons : p.buttons;
  renderButtonGroup("mainButtons", MAIN_BTNS, targetMap, p);
  renderButtonGroup("dpadButtons", DPAD_BTNS, targetMap, p);
  renderKeyGroup("leftStickKeys", DIRS, p.left_stick);
  renderKeyGroup("rightStickKeys", DIRS, p.right_stick);
  toggleStickInputs();
  renderProfileDeadzone();
}

function renderButtonGroup(elId, keys, obj, prof) {
  const el = document.getElementById(elId);
  const turboSet = new Set(prof.turbo_buttons || []);
  const toggleSet = new Set(prof.toggle_buttons || []);
  el.innerHTML = keys.map(k => {
    const isModifier = prof.shift_button === k;
    return `
      <div class="row" style="${isModifier ? "opacity:0.45;" : ""}">
        <label>${k}${isModifier ? " (SHIFT)" : ""}</label>
        <div class="bind-wrap">
          <input type="text" id="inp-${elId}-${k}" data-key="${k}" value="${obj[k] || ""}" ${isModifier ? "disabled" : ""}>
          <button type="button" class="bind-btn" onclick="startBind(this, 'inp-${elId}-${k}')" ${isModifier ? "disabled" : ""}>${t("bindBtn")}</button>
          <label class="flag-pill" title="Turbo"><input type="checkbox" class="chk-turbo" data-key="${k}" ${turboSet.has(k) ? "checked" : ""}>T</label>
          <label class="flag-pill" title="Toggle"><input type="checkbox" class="chk-toggle" data-key="${k}" ${toggleSet.has(k) ? "checked" : ""}>L</label>
        </div>
      </div>
    `;
  }).join("");
}

function renderKeyGroup(elId, keys, obj) {
  const el = document.getElementById(elId);
  el.innerHTML = keys.map(k => `
    <div class="row">
      <label>${k.toUpperCase()}</label>
      <div class="bind-wrap">
        <input type="text" id="inp-${elId}-${k}" data-key="${k}" value="${obj[k] || ""}">
        <button type="button" class="bind-btn" onclick="startBind(this, 'inp-${elId}-${k}')">${t("bindBtn")}</button>
      </div>
    </div>
  `).join("");
}

function startBind(btnEl, inputId) {
  if (activeBindTarget) {
    activeBindTarget.btn.classList.remove("listening");
    activeBindTarget.btn.textContent = t("bindBtn");
  }
  const inp = document.getElementById(inputId);
  btnEl.classList.add("listening");
  btnEl.textContent = t("bindWait");
  activeBindTarget = { btn: btnEl, inp };
}

function mapDomKey(e) {
  const map = {
    " ": "space", "Enter": "enter", "Escape": "esc", "Tab": "tab",
    "Backspace": "backspace", "ArrowUp": "up", "ArrowDown": "down",
    "ArrowLeft": "left", "ArrowRight": "right", "PageUp": "page_up",
    "PageDown": "page_down", "Shift": "shift", "Control": "ctrl",
    "Meta": "cmd", "AudioVolumeUp": "vol_up", "AudioVolumeDown": "vol_down",
    "AudioVolumeMute": "mute", "MediaPlayPause": "play_pause"
  };
  if (map[e.key]) return map[e.key];
  if (/^F\d{1,2}$/i.test(e.key)) return e.key.toLowerCase();
  if (e.key.length === 1) return e.key.toLowerCase();
  return null;
}

window.addEventListener("keydown", (e) => {
  if (!activeBindTarget) return;
  e.preventDefault();
  e.stopPropagation();
  const mapped = mapDomKey(e);
  if (!mapped) return;
  activeBindTarget.inp.value = mapped;
  activeBindTarget.btn.classList.remove("listening");
  activeBindTarget.btn.textContent = t("bindBtn");
  activeBindTarget = null;
}, true);

function toggleStickInputs() {
  const isMouse = document.getElementById("rightStickMode").value === "mouse";
  document.getElementById("rightStickCard").style.opacity = isMouse ? "0.4" : "1";
}

function calibrateZeroDrift() {
  cfg.calibration = {
    lx_offset: lastRaw.lx,
    ly_offset: lastRaw.ly,
    rx_offset: lastRaw.rx,
    ry_offset: lastRaw.ry
  };
  showToast(t("toastCalibrated"));
}

function resetZeroDrift() {
  cfg.calibration = { lx_offset: 0, ly_offset: 0, rx_offset: 0, ry_offset: 0 };
  showToast(t("toastCalReset"));
}

function collectCurrentProfile() {
  const name = document.getElementById("profileSelect").value;
  const p = cfg.profiles[name];
  if (!p.shift_buttons) p.shift_buttons = {};
  p.shift_button = document.getElementById("shiftButtonSelect").value;
  p.right_stick_mode = document.getElementById("rightStickMode").value;
  p.deadzone = parseInt(document.getElementById("deadzone").value) || 10000;
  p.trigger_threshold = parseInt(document.getElementById("triggerThreshold").value) || 200;
  p.turbo_rate = parseInt(document.getElementById("turboRate").value) || 12;
  p.mouse_speed = parseFloat(document.getElementById("mouseSpeed").value) || 18;
  p.mouse_curve = parseFloat(document.getElementById("mouseCurve").value) || 1.8;
  p.scroll_speed = parseFloat(document.getElementById("scrollSpeed").value) || 2.8;

  const targetMap = editLayer === "shift" ? p.shift_buttons : p.buttons;
  document.querySelectorAll("#mainButtons input[type='text'], #dpadButtons input[type='text']").forEach(inp => {
    targetMap[inp.dataset.key] = inp.value.trim();
  });

  const turbos = [];
  document.querySelectorAll(".chk-turbo:checked").forEach(chk => turbos.push(chk.dataset.key));
  p.turbo_buttons = turbos;

  const toggles = [];
  document.querySelectorAll(".chk-toggle:checked").forEach(chk => toggles.push(chk.dataset.key));
  p.toggle_buttons = toggles;

  document.querySelectorAll("#leftStickKeys input[type='text']").forEach(inp => {
    p.left_stick[inp.dataset.key] = inp.value.trim();
  });
  document.querySelectorAll("#rightStickKeys input[type='text']").forEach(inp => {
    p.right_stick[inp.dataset.key] = inp.value.trim();
  });

  cfg.language = lang;
  cfg.app_rules = parseLinesToMap(document.getElementById("appRules").value);
  cfg.combos = parseLinesToMap(document.getElementById("globalCombos").value);
}

function applyTemplate() {
  const sel = document.getElementById("templateSelect");
  const key = sel.value;
  if (!key || !PRESETS[key]) return;
  const current = document.getElementById("profileSelect").value || cfg.active_profile;
  if (!current) return;
  const existingApps = (cfg.profiles[current] && cfg.profiles[current].apps) || [];
  const presetData = JSON.parse(JSON.stringify(PRESETS[key]));
  if (existingApps.length && (!presetData.apps || !presetData.apps.length)) {
    presetData.apps = existingApps;
  }
  cfg.profiles[current] = presetData;
  cfg.active_profile = current;
  populateSelect();
  renderProfile();
}

function exportProfile() {
  collectCurrentProfile();
  const name = document.getElementById("profileSelect").value;
  const blob = new Blob([JSON.stringify({ name, profile: cfg.profiles[name] }, null, 2)], { type: "application/json" });
  const a = document.createElement("a");
  a.href = URL.createObjectURL(blob);
  a.download = `gamesir_${name}.json`;
  a.click();
}

function importProfile(event) {
  const file = event.target.files[0];
  if (!file) return;
  const reader = new FileReader();
  reader.onload = (e) => {
    try {
      const parsed = JSON.parse(e.target.result);
      const profObj = parsed.profile || parsed;
      if (!profObj.buttons || !profObj.left_stick) throw new Error("Invalid");
      const name = (parsed.name || file.name.replace(".json", "")).trim();
      cfg.profiles[name] = profObj;
      cfg.active_profile = name;
      populateSelect();
      renderProfile();
      showToast(t("toastImported"));
    } catch (err) {
      showToast("Invalid profile JSON");
    }
  };
  reader.readAsText(file);
  event.target.value = "";
}

function createProfile() {
  collectCurrentProfile();
  let idx = Object.keys(cfg.profiles).length + 1;
  let clean = "perfil_" + idx;
  while (cfg.profiles[clean]) { idx++; clean = "perfil_" + idx; }
  const base = cfg.profiles[cfg.active_profile]
    ? JSON.parse(JSON.stringify(cfg.profiles[cfg.active_profile]))
    : JSON.parse(JSON.stringify(PRESETS.desktop_media));
  base.apps = [];
  cfg.profiles[clean] = base;
  cfg.active_profile = clean;
  populateSelect();
  renderProfile();
  showToast(`Perfil "${clean}" criado. Clique em Salvar Tudo para gravar.`);
}

function deleteProfile() {
  const keys = Object.keys(cfg.profiles);
  if (keys.length <= 1) {
    showToast("Não é possível excluir o único perfil restante.", true);
    return;
  }
  const cur = document.getElementById("profileSelect").value;
  delete cfg.profiles[cur];
  cfg.active_profile = Object.keys(cfg.profiles)[0];
  populateSelect();
  renderProfile();
  showToast(`Perfil "${cur}" removido. Clique em Salvar Tudo para confirmar.`);
}

async function saveConfig() {
  collectCurrentProfile();
  await fetch("/api/config", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(cfg)
  });
  showToast(t("toastSaved"));
}

async function pollLive() {
  try {
    const res = await fetch("/api/live");
    const live = await res.json();
    const st = document.getElementById("liveStatus");
    const sticks = document.getElementById("liveSticks");
    const heldSet = new Set(live.held || []);

    document.querySelectorAll("[id^='svg-']").forEach(el => {
      const btnName = el.id.replace("svg-", "");
      el.classList.toggle("active", heldSet.has(btnName));
    });

    if (live.connected) {
      lastRaw = {
        lx: live.raw_lx ?? live.lx ?? 0,
        ly: live.raw_ly ?? live.ly ?? 0,
        rx: live.raw_rx ?? live.rx ?? 0,
        ry: live.raw_ry ?? live.ry ?? 0
      };
      const shiftTag = live.shift_active ? ` <span class="badge" style="background:rgba(168,85,247,0.2);color:#c084fc;border-color:#a855f7;">SHIFT</span>` : "";
      st.innerHTML = `<span style="color:var(--ok)">● ${live.connected}</span> (${live.profile})${shiftTag}`;
      sticks.textContent = `LS: ${live.lx}, ${live.ly} | RS: ${live.rx}, ${live.ry} | LT: ${live.lt} RT: ${live.rt}`;
      const lxOff = (live.lx / 32768) * 22;
      const lyOff = -(live.ly / 32768) * 22;
      const rxOff = (live.rx / 32768) * 22;
      const ryOff = -(live.ry / 32768) * 22;
      document.getElementById("dot-L").setAttribute("cx", (130 + lxOff).toFixed(1));
      document.getElementById("dot-L").setAttribute("cy", (108 + lyOff).toFixed(1));
      document.getElementById("dot-R").setAttribute("cx", (332 + rxOff).toFixed(1));
      document.getElementById("dot-R").setAttribute("cy", (162 + ryOff).toFixed(1));
      document.getElementById("bar-LT").setAttribute("width", Math.min(68, (live.lt / 1023) * 68).toFixed(1));
      document.getElementById("bar-RT").setAttribute("width", Math.min(68, (live.rt / 1023) * 68).toFixed(1));
    } else {
      st.innerHTML = `<span style="color:var(--muted)">○ ${t("disconnected")}</span>`;
    }
  } catch (e) {}
}

load();
setInterval(pollLive, 90);
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
            self.send_header("Cache-Control", "no-store, no-cache, must-revalidate")
            self.end_headers()
            self.wfile.write(HTML_TEMPLATE.encode("utf-8"))
        elif parsed.path == "/api/config":
            self.send_response(200)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.end_headers()
            self.wfile.write(get_config_path().read_bytes())
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
            get_config_path().write_text(
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


def start_background_server():
    """Inicia o servidor HTTP em uma thread daemon interna (compatível com .app standalone)."""
    global _server_started
    if _server_started:
        return
    kill_previous_instance()

    def _serve():
        try:
            with ReusableTCPServer(("127.0.0.1", PORT), ConfigHandler) as httpd:
                httpd.serve_forever()
        except OSError:
            pass

    threading.Thread(target=_serve, daemon=True).start()
    _server_started = True


if __name__ == "__main__":
    kill_previous_instance()
    with ReusableTCPServer(("127.0.0.1", PORT), ConfigHandler) as httpd:
        if "--no-browser" not in sys.argv:
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
