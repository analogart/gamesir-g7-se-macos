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
<html lang="pt">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>GameSir Bridge</title>
<style>
  :root {
    --bg: #161618;
    --sidebar: rgba(30, 30, 34, 0.88);
    --surface: #222226;
    --surface-2: #2c2c32;
    --border: rgba(255, 255, 255, 0.10);
    --text: #f5f5f7;
    --muted: #98989f;
    --accent: #0a84ff;
    --accent-soft: rgba(10, 132, 255, 0.16);
    --shift: #bf5af2;
    --ok: #30d158;
    --warn: #ff9f0a;
    --danger: #ff453a;
    --stage-bg: radial-gradient(circle at 50% 42%, #252832 0%, #14151a 100%);
    --shadow: 0 8px 28px rgba(0, 0, 0, 0.35);
  }
  @media (prefers-color-scheme: light) {
    :root {
      --bg: #f5f5f7;
      --sidebar: rgba(242, 242, 247, 0.92);
      --surface: #ffffff;
      --surface-2: #e5e5ea;
      --border: rgba(0, 0, 0, 0.09);
      --text: #1d1d1f;
      --muted: #6e6e73;
      --accent: #007aff;
      --accent-soft: rgba(0, 122, 255, 0.12);
      --shift: #af52de;
      --ok: #28cd41;
      --warn: #ff9500;
      --danger: #ff3b30;
      --stage-bg: radial-gradient(circle at 50% 42%, #e8ecf4 0%, #d5dce8 100%);
      --shadow: 0 6px 22px rgba(0, 0, 0, 0.08);
    }
  }

  * { box-sizing: border-box; -webkit-font-smoothing: antialiased; }
  body {
    font-family: -apple-system, BlinkMacSystemFont, "SF Pro Text", "SF Pro Display", sans-serif;
    background: var(--bg);
    color: var(--text);
    margin: 0;
    height: 100vh;
    overflow: hidden;
    display: flex;
    user-select: none;
  }

  .sidebar {
    width: 252px;
    min-width: 252px;
    background: var(--sidebar);
    backdrop-filter: blur(20px);
    border-right: 1px solid var(--border);
    display: flex;
    flex-direction: column;
    padding: 16px 12px;
    gap: 16px;
  }
  .brand {
    display: flex;
    align-items: center;
    justify-content: space-between;
    padding: 2px 8px;
  }
  .brand-title { font-size: 15px; font-weight: 700; letter-spacing: -0.2px; }
  .version-pill {
    font-size: 11px;
    font-weight: 600;
    color: var(--muted);
    background: var(--surface-2);
    padding: 2px 7px;
    border-radius: 6px;
  }
  .sb-section-label {
    font-size: 11px;
    font-weight: 600;
    color: var(--muted);
    padding: 0 10px 6px;
    letter-spacing: 0.2px;
  }
  .nav-list { display: flex; flex-direction: column; gap: 3px; }
  .nav-item {
    display: flex;
    align-items: center;
    justify-content: space-between;
    padding: 8px 10px;
    border-radius: 8px;
    font-size: 13px;
    font-weight: 500;
    color: var(--text);
    cursor: pointer;
    border: none;
    background: transparent;
    text-align: left;
    width: 100%;
    transition: background 0.12s;
  }
  .nav-item:hover { background: rgba(128, 128, 128, 0.12); }
  .nav-item.active { background: var(--accent); color: #fff; font-weight: 600; }
  .nav-item.active .dot { background: #fff !important; }
  .profile-left { display: flex; align-items: center; gap: 8px; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
  .dot { width: 7px; height: 7px; border-radius: 50%; background: var(--muted); opacity: 0.45; flex-shrink: 0; }
  .dot.on { background: var(--ok); opacity: 1; }

  .sb-actions { display: flex; gap: 6px; padding: 4px 4px 0; }
  .sb-btn {
    flex: 1;
    padding: 6px 8px;
    font-size: 12px;
    font-weight: 500;
    border-radius: 7px;
    border: 1px solid var(--border);
    background: var(--surface);
    color: var(--text);
    cursor: pointer;
  }
  .sb-btn:hover { filter: brightness(1.06); }
  .sb-select {
    width: 100%;
    padding: 7px 9px;
    font-size: 12px;
    border-radius: 8px;
    border: 1px solid var(--border);
    background: var(--surface);
    color: var(--text);
    margin-top: 6px;
  }

  .sb-footer {
    margin-top: auto;
    padding-top: 10px;
    border-top: 1px solid var(--border);
    display: flex;
    gap: 6px;
  }

  .main { flex: 1; display: flex; flex-direction: column; overflow: hidden; }
  .topbar {
    height: 52px;
    padding: 0 20px;
    border-bottom: 1px solid var(--border);
    display: flex;
    align-items: center;
    justify-content: space-between;
    gap: 12px;
    flex-shrink: 0;
  }
  .status-pill {
    display: inline-flex;
    align-items: center;
    gap: 8px;
    padding: 5px 12px;
    border-radius: 99px;
    background: var(--surface);
    border: 1px solid var(--border);
    font-size: 12px;
    font-weight: 500;
  }
  .status-led { width: 8px; height: 8px; border-radius: 50%; background: var(--muted); }
  .status-led.connected { background: var(--ok); box-shadow: 0 0 8px var(--ok); }
  .topbar-right { display: flex; align-items: center; gap: 10px; }
  .save-badge { font-size: 12px; font-weight: 500; color: var(--ok); opacity: 0.92; }

  .workspace { flex: 1; display: flex; overflow: hidden; }
  .stage-col {
    flex: 1;
    display: flex;
    flex-direction: column;
    padding: 16px 20px;
    gap: 12px;
    overflow-y: auto;
  }
  .stage-card {
    position: relative;
    flex: 1;
    min-height: 340px;
    border-radius: 16px;
    background: var(--stage-bg);
    border: 1px solid var(--border);
    box-shadow: var(--shadow);
    overflow: hidden;
  }
  #pad3dCanvas { width: 100%; height: 100%; display: block; cursor: grab; }
  .stage-hint {
    position: absolute;
    top: 12px;
    left: 14px;
    font-size: 12px;
    color: #cbd5e1;
    background: rgba(15, 23, 42, 0.58);
    backdrop-filter: blur(10px);
    padding: 5px 11px;
    border-radius: 99px;
    pointer-events: none;
    max-width: calc(100% - 210px);
    white-space: nowrap;
    overflow: hidden;
    text-overflow: ellipsis;
  }
  .stage-telemetry {
    position: absolute;
    top: 12px;
    right: 14px;
    font-size: 11px;
    font-family: ui-monospace, SFMono-Regular, Menlo, monospace;
    color: #cbd5e1;
    background: rgba(15, 23, 42, 0.58);
    backdrop-filter: blur(10px);
    padding: 5px 10px;
    border-radius: 99px;
  }
  .hover-tag {
    position: absolute;
    padding: 5px 10px;
    border-radius: 8px;
    background: rgba(10, 132, 255, 0.92);
    color: #fff;
    font-size: 12px;
    font-weight: 600;
    pointer-events: none;
    display: none;
    box-shadow: 0 4px 14px rgba(0, 0, 0, 0.35);
    z-index: 10;
  }
  .cam-bar {
    position: absolute;
    bottom: 12px;
    left: 14px;
    right: 14px;
    display: flex;
    justify-content: space-between;
    align-items: center;
    gap: 8px;
    pointer-events: none;
  }
  .cam-group { display: flex; gap: 6px; pointer-events: auto; flex-wrap: wrap; }
  .glass-btn {
    padding: 6px 11px;
    font-size: 12px;
    font-weight: 500;
    color: #f8fafc;
    background: rgba(15, 23, 42, 0.65);
    backdrop-filter: blur(12px);
    border: 1px solid rgba(255, 255, 255, 0.14);
    border-radius: 8px;
    cursor: pointer;
    transition: 0.15s;
  }
  .glass-btn:hover { background: rgba(30, 41, 59, 0.85); }
  .glass-btn.active { background: var(--accent); border-color: var(--accent); }

  .quick-pad-grid {
    background: var(--surface);
    border: 1px solid var(--border);
    border-radius: 14px;
    padding: 12px 14px;
  }
  .quick-pad-header {
    display: flex;
    justify-content: space-between;
    align-items: center;
    margin-bottom: 10px;
  }
  .segmented {
    display: inline-flex;
    background: var(--surface-2);
    padding: 2px;
    border-radius: 8px;
    border: 1px solid var(--border);
  }
  .seg-btn {
    padding: 4px 12px;
    font-size: 12px;
    font-weight: 500;
    border: none;
    background: transparent;
    color: var(--muted);
    border-radius: 6px;
    cursor: pointer;
  }
  .seg-btn.active { background: var(--surface); color: var(--text); font-weight: 600; box-shadow: 0 1px 3px rgba(0,0,0,0.2); }
  .seg-btn.shift.active { background: var(--shift); color: #fff; }

  .chips-wrap { display: flex; flex-wrap: wrap; gap: 6px; }
  .btn-chip {
    display: inline-flex;
    align-items: center;
    gap: 6px;
    padding: 6px 10px;
    border-radius: 8px;
    background: var(--surface-2);
    border: 1px solid transparent;
    font-size: 12px;
    color: var(--text);
    cursor: pointer;
    transition: 0.12s;
  }
  .btn-chip:hover { border-color: var(--accent); }
  .btn-chip.selected { background: var(--accent-soft); border-color: var(--accent); font-weight: 600; }
  .btn-chip.live-hit { background: var(--accent); color: #fff; }
  .chip-key { color: var(--muted); font-size: 11px; }
  .btn-chip.selected .chip-key { color: var(--accent); }

  .inspector {
    width: 340px;
    min-width: 340px;
    background: var(--surface);
    border-left: 1px solid var(--border);
    padding: 18px;
    overflow-y: auto;
    display: flex;
    flex-direction: column;
    gap: 16px;
  }
  .insp-title { font-size: 17px; font-weight: 700; margin: 0; letter-spacing: -0.2px; }
  .insp-sub { font-size: 12px; color: var(--muted); margin: 3px 0 0; line-height: 1.4; }
  .group-box {
    background: var(--bg);
    border: 1px solid var(--border);
    border-radius: 12px;
    padding: 12px 14px;
    display: flex;
    flex-direction: column;
    gap: 12px;
  }
  .field-row { display: flex; align-items: center; justify-content: space-between; gap: 10px; }
  .field-label { font-size: 13px; font-weight: 500; }
  .field-desc { font-size: 11px; color: var(--muted); margin-top: 2px; line-height: 1.35; }

  .record-btn {
    width: 100%;
    padding: 11px 14px;
    border-radius: 10px;
    border: 1px solid var(--accent);
    background: var(--accent-soft);
    color: var(--accent);
    font-size: 13px;
    font-weight: 600;
    cursor: pointer;
    display: flex;
    align-items: center;
    justify-content: space-between;
  }
  .record-btn.listening { background: var(--warn); border-color: var(--warn); color: #000; }
  .key-cap {
    background: var(--surface);
    color: var(--text);
    padding: 3px 9px;
    border-radius: 6px;
    font-size: 12px;
    font-weight: 600;
    border: 1px solid var(--border);
  }

  .preset-keys { display: flex; flex-wrap: wrap; gap: 5px; }
  .mini-pill {
    padding: 4px 8px;
    font-size: 11px;
    font-weight: 500;
    border-radius: 6px;
    border: 1px solid var(--border);
    background: var(--surface);
    color: var(--text);
    cursor: pointer;
  }
  .mini-pill:hover { border-color: var(--accent); color: var(--accent); }

  .apple-switch { position: relative; width: 40px; height: 24px; flex-shrink: 0; }
  .apple-switch input { opacity: 0; width: 0; height: 0; }
  .slider-track {
    position: absolute;
    inset: 0;
    background: var(--surface-2);
    border-radius: 99px;
    transition: 0.2s;
    cursor: pointer;
  }
  .slider-track:before {
    content: "";
    position: absolute;
    height: 18px;
    width: 18px;
    left: 3px;
    bottom: 3px;
    background: #fff;
    border-radius: 50%;
    transition: 0.2s;
    box-shadow: 0 1px 3px rgba(0,0,0,0.3);
  }
  .apple-switch input:checked + .slider-track { background: var(--ok); }
  .apple-switch input:checked + .slider-track:before { transform: translateX(16px); }

  .range-wrap { display: flex; flex-direction: column; gap: 6px; }
  .range-top { display: flex; justify-content: space-between; font-size: 13px; font-weight: 500; }
  .range-val { color: var(--accent); font-weight: 600; font-variant-numeric: tabular-nums; }
  input[type="range"] { width: 100%; accent-color: var(--accent); cursor: pointer; }

  .rule-item {
    display: flex;
    align-items: center;
    justify-content: space-between;
    padding: 7px 10px;
    background: var(--surface);
    border: 1px solid var(--border);
    border-radius: 8px;
    font-size: 12px;
  }
  .del-x { border: none; background: transparent; color: var(--danger); font-weight: 700; cursor: pointer; padding: 2px 6px; }
  .tab-pane { display: none; flex-direction: column; gap: 14px; }
  .tab-pane.active { display: flex; }
</style>
</head>
<body>

  <aside class="sidebar">
    <div class="brand">
      <span class="brand-title">GameSir Bridge</span>
      <span class="version-pill">v7.0.0</span>
    </div>

    <div>
      <div class="sb-section-label" id="lblProfiles">Perfis</div>
      <div class="nav-list" id="profileList"></div>
      <div class="sb-actions">
        <button class="sb-btn" onclick="createProfile()" id="btnNew">+ Novo</button>
        <button class="sb-btn" onclick="exportProfile()" id="btnExport">Exportar</button>
        <button class="sb-btn" onclick="document.getElementById('importFile').click()" id="btnImport">Importar</button>
        <input type="file" id="importFile" accept=".json" style="display:none" onchange="importProfile(event)">
      </div>
      <select class="sb-select" id="templateSelect" onchange="applyTemplate()">
        <option value="" id="optTplDefault">Aplicar modelo pronto...</option>
        <option value="desktop_media">Mídia &amp; Navegação no Mac</option>
        <option value="pcsx2">PlayStation 2 (PCSX2)</option>
        <option value="dolphin">GameCube / Wii (Dolphin)</option>
        <option value="retroarch">RetroArch / Clássicos</option>
        <option value="ppsspp">PSP (PPSSPP)</option>
        <option value="hollow_knight">Hollow Knight / Metroidvania</option>
        <option value="minecraft_mac">Minecraft Java (Mac)</option>
        <option value="dj_control">DJ / Rekordbox / Serato</option>
      </select>
    </div>

    <div>
      <div class="sb-section-label" id="lblSections">Ajustes</div>
      <div class="nav-list">
        <button class="nav-item active" data-tab="buttons" onclick="switchTab('buttons', this)" id="navButtons">Botões e Mapeamento</button>
        <button class="nav-item" data-tab="sticks" onclick="switchTab('sticks', this)" id="navSticks">Analógicos e Gatilhos</button>
        <button class="nav-item" data-tab="automation" onclick="switchTab('automation', this)" id="navAuto">Automação e Atalhos</button>
      </div>
    </div>

    <div class="sb-footer">
      <select id="langSelect" onchange="changeLang()" class="sb-select" style="margin-top:0;">
        <option value="pt">Português</option>
        <option value="en">English</option>
        <option value="es">Español</option>
      </select>
      <button class="sb-btn" style="color:var(--danger);" onclick="deleteProfile()" id="btnDel">Excluir</button>
    </div>
  </aside>

  <main class="main">
    <header class="topbar">
      <div class="status-pill">
        <span class="status-led" id="statusLed"></span>
        <span id="liveStatus">Procurando controle USB...</span>
      </div>
      <div class="topbar-right">
        <span class="save-badge" id="saveBadge">✓ Salvo automaticamente</span>
        <button class="sb-btn" onclick="testRumble()" id="btnTestRumble">Testar Motores</button>
        <button class="sb-btn" onclick="calibrateZeroDrift()" id="btnCalibrate">Centralizar Analógicos</button>
        <button class="sb-btn" onclick="resetZeroDrift()" title="Restaurar calibração">↺</button>
      </div>
    </header>

    <div class="workspace">
      <section class="stage-col">
        <div class="stage-card" id="pad3dWrap">
          <div class="stage-hint" id="stageHint">Clique em um botão no 3D • Arraste para girar</div>
          <div class="stage-telemetry" id="liveSticks">LS: 0, 0 • RS: 0, 0</div>
          <div class="hover-tag" id="hoverTag"></div>
          <canvas id="pad3dCanvas"></canvas>
          <div class="cam-bar">
            <div class="cam-group">
              <button type="button" class="glass-btn" onclick="setCamPreset('front')" id="camFront">Frente</button>
              <button type="button" class="glass-btn" onclick="setCamPreset('back')" id="camBack">Traseira (L4 / R4)</button>
              <button type="button" class="glass-btn" onclick="setCamPreset('top')" id="camTop">Topo (LT / RT)</button>
              <button type="button" class="glass-btn" id="btnAutoSpin" onclick="toggleAutoSpin()">Girar</button>
            </div>
          </div>
        </div>

        <div class="quick-pad-grid">
          <div class="quick-pad-header">
            <span style="font-size:12px; font-weight:600; color:var(--muted);" id="lblQuickPick">Todos os Botões</span>
            <div class="segmented">
              <button type="button" class="seg-btn active" id="btnLayerBase" onclick="setEditLayer('base')">Camada Normal</button>
              <button type="button" class="seg-btn shift" id="btnLayerShift" onclick="setEditLayer('shift')">Camada Shift</button>
            </div>
          </div>
          <div class="chips-wrap" id="buttonChips"></div>
        </div>
      </section>

      <aside class="inspector">
        <div class="tab-pane active" id="pane-buttons">
          <div>
            <h2 class="insp-title" id="inspBtnTitle">Botão A</h2>
            <p class="insp-sub" id="inspBtnSub">Escolha o que acontece no Mac quando você pressiona este botão.</p>
          </div>

          <div class="group-box">
            <button type="button" class="record-btn" id="recordKeyBtn" onclick="startInspectorBind()">
              <span id="lblRecordAction">Gravar Tecla do Mac</span>
              <span class="key-cap" id="currentKeyLabel">Espaço</span>
            </button>

            <div>
              <div class="field-desc" style="margin-bottom:6px;" id="lblQuickActions">Atalhos rápidos:</div>
              <div class="preset-keys" id="quickKeyPresets"></div>
            </div>
          </div>

          <div class="group-box">
            <div class="field-row">
              <div>
                <div class="field-label" id="lblTurboTitle">Disparo Rápido (Turbo)</div>
                <div class="field-desc" id="lblTurboDesc">Repete o clique automaticamente enquanto você segura o botão.</div>
              </div>
              <label class="apple-switch">
                <input type="checkbox" id="chkInspTurbo" onchange="toggleButtonFlag('turbo')">
                <span class="slider-track"></span>
              </label>
            </div>

            <div class="field-row">
              <div>
                <div class="field-label" id="lblToggleTitle">Manter Pressionado (Travar)</div>
                <div class="field-desc" id="lblToggleDesc">Aperte uma vez para segurar a tecla e aperte de novo para soltar.</div>
              </div>
              <label class="apple-switch">
                <input type="checkbox" id="chkInspToggle" onchange="toggleButtonFlag('toggle')">
                <span class="slider-track"></span>
              </label>
            </div>
          </div>

          <div class="group-box">
            <div class="field-row">
              <div>
                <div class="field-label" id="lblShiftModTitle">Botão Shift (Função Extra)</div>
                <div class="field-desc" id="lblShiftModDesc">Segure este botão para ativar uma segunda função nos outros botões.</div>
              </div>
              <select id="shiftButtonSelect" onchange="updateShiftModifier()" class="sb-select" style="width:110px; margin:0;"></select>
            </div>
          </div>
        </div>

        <div class="tab-pane" id="pane-sticks">
          <div>
            <h2 class="insp-title" id="inspSticksTitle">Analógicos e Gatilhos</h2>
            <p class="insp-sub" id="inspSticksSub">Ajuste a precisão e o comportamento dos analógicos.</p>
          </div>

          <div class="group-box">
            <div class="field-row">
              <span class="field-label" id="lblRsMode">Analógico Direito</span>
              <select id="rightStickMode" onchange="onStickSettingChange()" class="sb-select" style="width:155px; margin:0;">
                <option value="mouse" id="optMouse">Controlar Mouse</option>
                <option value="keys" id="optKeys">Teclas Direcionais</option>
              </select>
            </div>

            <div class="range-wrap">
              <div class="range-top">
                <span id="lblDeadzone">Zona Morta</span>
                <span class="range-val" id="valDeadzone">30%</span>
              </div>
              <input type="range" id="deadzoneRange" min="0" max="25000" step="500" oninput="onStickSettingChange()">
            </div>

            <div class="range-wrap">
              <div class="range-top">
                <span id="lblTrigger">Sensibilidade dos Gatilhos</span>
                <span class="range-val" id="valTrigger">20%</span>
              </div>
              <input type="range" id="triggerRange" min="20" max="950" step="10" oninput="onStickSettingChange()">
            </div>

            <div class="range-wrap">
              <div class="range-top">
                <span id="lblMouseSpeed">Velocidade do Cursor</span>
                <span class="range-val" id="valMouseSpeed">18</span>
              </div>
              <input type="range" id="mouseSpeedRange" min="4" max="45" step="1" oninput="onStickSettingChange()">
            </div>

            <div class="range-wrap">
              <div class="range-top">
                <span id="lblTurboRate">Velocidade do Turbo</span>
                <span class="range-val" id="valTurboRate">12/s</span>
              </div>
              <input type="range" id="turboRateRange" min="2" max="30" step="1" oninput="onStickSettingChange()">
            </div>
          </div>

          <div class="group-box">
            <div class="field-label" id="lblLeftStickDirs">Direções do Analógico Esquerdo</div>
            <div id="leftStickList" style="display:flex; flex-direction:column; gap:6px;"></div>
          </div>
        </div>

        <div class="tab-pane" id="pane-automation">
          <div>
            <h2 class="insp-title" id="inspAutoTitle">Automação e Atalhos</h2>
            <p class="insp-sub" id="inspAutoSub">Troque de perfil automaticamente ao abrir um jogo ou app.</p>
          </div>

          <div class="group-box">
            <div class="field-label" id="lblAutoAppBox">Troca Automática por App</div>
            <div style="display:flex; gap:6px;">
              <input type="text" id="newAppKeyword" placeholder="Ex: pcsx2, steam, safari" style="flex:1; padding:6px 9px; border-radius:7px; border:1px solid var(--border); background:var(--surface); color:var(--text); font-size:12px;">
              <select id="newAppProfile" class="sb-select" style="width:115px; margin:0;"></select>
              <button class="sb-btn" style="flex:0;" onclick="addAppRule()">+</button>
            </div>
            <div id="appRulesList" style="display:flex; flex-direction:column; gap:6px;"></div>
          </div>

          <div class="group-box">
            <div class="field-label" id="lblCombosBox">Combinações de 2 Botões</div>
            <div style="display:flex; gap:5px; flex-wrap:wrap;">
              <select id="comboBtn1" class="sb-select" style="width:82px; margin:0;"></select>
              <span style="align-self:center; color:var(--muted);">+</span>
              <select id="comboBtn2" class="sb-select" style="width:82px; margin:0;"></select>
              <select id="comboAction" class="sb-select" style="flex:1; margin:0;">
                <option value="cmd+q">Fechar App (⌘Q)</option>
                <option value="cmd+tab">Trocar Janela (⌘Tab)</option>
                <option value="cmd+shift+3">Print da Tela</option>
                <option value="play_pause">Play / Pause Mídia</option>
                <option value="vol_up">Aumentar Volume</option>
                <option value="vol_down">Diminuir Volume</option>
              </select>
              <button class="sb-btn" style="flex:0;" onclick="addComboRule()">+</button>
            </div>
            <div id="combosList" style="display:flex; flex-direction:column; gap:6px;"></div>
          </div>
        </div>
      </aside>
    </div>
  </main>

<script src="/three.min.js"></script>
<script>
const I18N = {
  pt: {
    profiles: "Perfis", new: "+ Novo", export: "Exportar", import: "Importar", del: "Excluir",
    tplDefault: "Aplicar modelo pronto...", sections: "Ajustes",
    navButtons: "Botões e Mapeamento", navSticks: "Analógicos e Gatilhos", navAuto: "Automação e Atalhos",
    searching: "Procurando controle USB...", saved: "✓ Salvo automaticamente", saving: "Salvando...",
    rumble: "Testar Motores", calibrate: "Centralizar Analógicos",
    hint: "Clique em um botão no 3D • Arraste para girar",
    camFront: "Frente", camBack: "Traseira (L4 / R4)", camTop: "Topo (LT / RT)", spin: "Girar",
    quickPick: "Todos os Botões", layerBase: "Camada Normal", layerShift: "Camada Shift",
    btnSub: "Escolha o que acontece no Mac quando você pressiona este botão.",
    record: "Gravar Tecla do Mac", listening: "Aperte uma tecla no Mac...", quickActions: "Atalhos rápidos:",
    turboTitle: "Disparo Rápido (Turbo)", turboDesc: "Repete o clique automaticamente enquanto você segura o botão.",
    toggleTitle: "Manter Pressionado (Travar)", toggleDesc: "Aperte uma vez para segurar a tecla e aperte de novo para soltar.",
    shiftTitle: "Botão Shift (Função Extra)", shiftDesc: "Segure este botão para ativar uma segunda função nos outros botões.",
    sticksTitle: "Analógicos e Gatilhos", sticksSub: "Ajuste a precisão e o comportamento dos analógicos.",
    rsMode: "Analógico Direito", optMouse: "Controlar Mouse", optKeys: "Teclas Direcionais",
    deadzone: "Zona Morta", trigger: "Sensibilidade dos Gatilhos", mouseSpeed: "Velocidade do Cursor",
    turboRate: "Velocidade do Turbo", leftDirs: "Direções do Analógico Esquerdo",
    autoTitle: "Automação e Atalhos", autoSub: "Troque de perfil automaticamente ao abrir um jogo ou app.",
    autoBox: "Troca Automática por App", combosBox: "Combinações de 2 Botões",
    profMap: { emulators: "Emuladores", mac_games: "Jogos Mac", desktop_media: "Mídia & Desktop" }
  },
  en: {
    profiles: "Profiles", new: "+ New", export: "Export", import: "Import", del: "Delete",
    tplDefault: "Apply preset template...", sections: "Settings",
    navButtons: "Buttons & Mapping", navSticks: "Sticks & Triggers", navAuto: "Automation & Shortcuts",
    searching: "Searching for USB controller...", saved: "✓ Auto-saved", saving: "Saving...",
    rumble: "Test Rumble", calibrate: "Center Sticks",
    hint: "Click any button in 3D • Drag to orbit",
    camFront: "Front", camBack: "Back (L4 / R4)", camTop: "Top (LT / RT)", spin: "Spin",
    quickPick: "All Buttons", layerBase: "Normal Layer", layerShift: "Shift Layer",
    btnSub: "Choose what happens on your Mac when you press this button.",
    record: "Record Mac Key", listening: "Press any key on Mac...", quickActions: "Quick actions:",
    turboTitle: "Turbo Rapid Fire", turboDesc: "Repeats input automatically while holding the button.",
    toggleTitle: "Toggle Hold", toggleDesc: "Press once to hold down, press again to release.",
    shiftTitle: "Shift Modifier", shiftDesc: "Hold this button to trigger secondary actions on other buttons.",
    sticksTitle: "Sticks & Triggers", sticksSub: "Fine-tune stick precision and trigger sensitivity.",
    rsMode: "Right Stick", optMouse: "Control Mouse", optKeys: "Directional Keys",
    deadzone: "Deadzone", trigger: "Trigger Sensitivity", mouseSpeed: "Cursor Speed",
    turboRate: "Turbo Rate", leftDirs: "Left Stick Directions",
    autoTitle: "Automation & Shortcuts", autoSub: "Switch profiles automatically when an app opens.",
    autoBox: "Auto-Switch by App", combosBox: "2-Button Combos",
    profMap: { emulators: "Emulators", mac_games: "Mac Games", desktop_media: "Media & Desktop" }
  },
  es: {
    profiles: "Perfiles", new: "+ Nuevo", export: "Exportar", import: "Importar", del: "Eliminar",
    tplDefault: "Aplicar plantilla...", sections: "Ajustes",
    navButtons: "Botones y Mapeo", navSticks: "Sticks y Gatillos", navAuto: "Automatización y Atajos",
    searching: "Buscando control USB...", saved: "✓ Guardado automáticamente", saving: "Guardando...",
    rumble: "Probar Motores", calibrate: "Centrar Sticks",
    hint: "Haz clic en un botón 3D • Arrastra para girar",
    camFront: "Frente", camBack: "Trasera (L4 / R4)", camTop: "Arriba (LT / RT)", spin: "Girar",
    quickPick: "Todos los Botones", layerBase: "Capa Normal", layerShift: "Capa Shift",
    btnSub: "Elige qué ocurre en el Mac al pulsar este botón.",
    record: "Grabar Tecla del Mac", listening: "Pulsa una tecla en el Mac...", quickActions: "Atajos rápidos:",
    turboTitle: "Disparo Rápido (Turbo)", turboDesc: "Repite la pulsación mientras mantienes el botón.",
    toggleTitle: "Mantener Pulsado", toggleDesc: "Pulsa una vez para mantener y otra para soltar.",
    shiftTitle: "Botón Shift (Función Extra)", shiftDesc: "Mantén este botón para activar una segunda función.",
    sticksTitle: "Sticks y Gatillos", sticksSub: "Ajusta la precisión de los sticks y gatillos.",
    rsMode: "Stick Derecho", optMouse: "Controlar Ratón", optKeys: "Teclas Direccionales",
    deadzone: "Zona Muerta", trigger: "Sensibilidad de Gatillos", mouseSpeed: "Velocidad del Cursor",
    turboRate: "Velocidad del Turbo", leftDirs: "Direcciones del Stick Izquierdo",
    autoTitle: "Automatización y Atajos", autoSub: "Cambia de perfil automáticamente al abrir una app.",
    autoBox: "Cambio Automático por App", combosBox: "Combinaciones de 2 Botones",
    profMap: { emulators: "Emuladores", mac_games: "Juegos Mac", desktop_media: "Multimedia y Escritorio" }
  }
};

function t(key) {
  const dict = I18N[lang] || I18N.pt;
  return dict[key] !== undefined ? dict[key] : (I18N.pt[key] || key);
}

function prettyProfileName(raw) {
  const map = (I18N[lang] && I18N[lang].profMap) || {};
  return map[raw] || raw.replace(/_/g, " ").replace(/\b\w/g, c => c.toUpperCase());
}

function applyLocaleStrings() {
  document.getElementById("lblProfiles").textContent = t("profiles");
  document.getElementById("btnNew").textContent = t("new");
  document.getElementById("btnExport").textContent = t("export");
  document.getElementById("btnImport").textContent = t("import");
  document.getElementById("btnDel").textContent = t("del");
  document.getElementById("optTplDefault").textContent = t("tplDefault");
  document.getElementById("lblSections").textContent = t("sections");
  document.getElementById("navButtons").textContent = t("navButtons");
  document.getElementById("navSticks").textContent = t("navSticks");
  document.getElementById("navAuto").textContent = t("navAuto");
  document.getElementById("saveBadge").textContent = t("saved");
  document.getElementById("btnTestRumble").textContent = t("rumble");
  document.getElementById("btnCalibrate").textContent = t("calibrate");
  document.getElementById("stageHint").textContent = t("hint");
  document.getElementById("camFront").textContent = t("camFront");
  document.getElementById("camBack").textContent = t("camBack");
  document.getElementById("camTop").textContent = t("camTop");
  document.getElementById("btnAutoSpin").textContent = t("spin");
  document.getElementById("lblQuickPick").textContent = t("quickPick");
  document.getElementById("btnLayerBase").textContent = t("layerBase");
  document.getElementById("btnLayerShift").textContent = t("layerShift");
  document.getElementById("inspBtnSub").textContent = t("btnSub");
  document.getElementById("lblQuickActions").textContent = t("quickActions");
  document.getElementById("lblTurboTitle").textContent = t("turboTitle");
  document.getElementById("lblTurboDesc").textContent = t("turboDesc");
  document.getElementById("lblToggleTitle").textContent = t("toggleTitle");
  document.getElementById("lblToggleDesc").textContent = t("toggleDesc");
  document.getElementById("lblShiftModTitle").textContent = t("shiftTitle");
  document.getElementById("lblShiftModDesc").textContent = t("shiftDesc");
  document.getElementById("inspSticksTitle").textContent = t("sticksTitle");
  document.getElementById("inspSticksSub").textContent = t("sticksSub");
  document.getElementById("lblRsMode").textContent = t("rsMode");
  document.getElementById("optMouse").textContent = t("optMouse");
  document.getElementById("optKeys").textContent = t("optKeys");
  document.getElementById("lblDeadzone").textContent = t("deadzone");
  document.getElementById("lblTrigger").textContent = t("trigger");
  document.getElementById("lblMouseSpeed").textContent = t("mouseSpeed");
  document.getElementById("lblTurboRate").textContent = t("turboRate");
  document.getElementById("lblLeftStickDirs").textContent = t("leftDirs");
  document.getElementById("inspAutoTitle").textContent = t("autoTitle");
  document.getElementById("inspAutoSub").textContent = t("autoSub");
  document.getElementById("lblAutoAppBox").textContent = t("autoBox");
  document.getElementById("lblCombosBox").textContent = t("combosBox");
}

const FRIENDLY_KEYS = {
  "": "Desativado", "space": "Espaço", "enter": "Enter ↵", "esc": "Esc",
  "tab": "Tab ⇥", "backspace": "Apagar ⌫", "up": "Seta ↑", "down": "Seta ↓",
  "left": "Seta ←", "right": "Seta →", "mouse_left": "Clique Esquerdo",
  "mouse_right": "Clique Direito", "scroll_mod": "Modo Scroll",
  "cmd+q": "⌘Q Fechar App", "cmd+w": "⌘W Fechar Aba", "cmd+tab": "⌘Tab Trocar App",
  "cmd+c": "⌘C Copiar", "cmd+v": "⌘V Colar",
  "play_pause": "Play / Pause", "vol_up": "Volume +", "vol_down": "Volume -"
};

const QUICK_PRESET_ACTIONS = [
  { val: "space", label: "Espaço" }, { val: "enter", label: "Enter" },
  { val: "esc", label: "Esc" }, { val: "mouse_left", label: "Clique Esq." },
  { val: "mouse_right", label: "Clique Dir." }, { val: "cmd+q", label: "⌘Q" },
  { val: "", label: "Desativar" }
];

const BTN_LABELS = {
  A: "Botão A", B: "Botão B", X: "Botão X", Y: "Botão Y",
  LB: "Ombro Esquerdo (LB)", RB: "Ombro Direito (RB)",
  LT: "Gatilho Esquerdo (LT)", RT: "Gatilho Direito (RT)",
  L3: "Clique Analógico Esq. (L3)", R3: "Clique Analógico Dir. (R3)",
  UP: "Direcional Cima", DOWN: "Direcional Baixo",
  LEFT: "Direcional Esquerda", RIGHT: "Direcional Direita",
  VIEW: "Botão View", MENU: "Botão Menu", SHARE: "Botão Share",
  L4: "Paddle Traseiro Esq. (L4)", R4: "Paddle Traseiro Dir. (R4)",
  M: "Botão Perfil (M)"
};

const ALL_BTNS = ["A", "B", "X", "Y", "LB", "RB", "LT", "RT", "L3", "R3", "UP", "DOWN", "LEFT", "RIGHT", "VIEW", "MENU", "SHARE", "L4", "R4", "M"];

let cfg = {};
let lang = "pt";
let editLayer = "base";
let selectedBtn = "A";
let listeningBind = false;
let listeningStickDir = null;
let lastRaw = { lx: 0, ly: 0, rx: 0, ry: 0 };
let saveTimer = null;

function formatKey(k) {
  if (!k) return "Desativado";
  return FRIENDLY_KEYS[k] || k.toUpperCase();
}

function scheduleAutoSave() {
  const badge = document.getElementById("saveBadge");
  if (badge) { badge.textContent = t("saving"); badge.style.color = "var(--muted)"; }
  clearTimeout(saveTimer);
  saveTimer = setTimeout(async () => {
    try {
      await fetch("/api/config", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(cfg)
      });
      if (badge) { badge.textContent = t("saved"); badge.style.color = "var(--ok)"; }
    } catch (e) {}
  }, 320);
}

async function testRumble() {
  try { await fetch("/api/rumble", { method: "POST" }); } catch (e) {}
}

function switchTab(tab, el) {
  document.querySelectorAll(".nav-item").forEach(n => n.classList.remove("active"));
  if (el) el.classList.add("active");
  document.querySelectorAll(".tab-pane").forEach(p => p.classList.remove("active"));
  const pane = document.getElementById("pane-" + tab);
  if (pane) pane.classList.add("active");
}

function selectButton(btnName) {
  selectedBtn = btnName;
  listeningBind = false;
  switchTab("buttons", document.getElementById("navButtons"));
  renderInspector();
  renderButtonChips();
  if (typeof pad3dState !== "undefined") {
    pad3dState.selected = btnName;
    if (btnName === "L4" || btnName === "R4") setCamPreset("back");
    else if (btnName === "LT" || btnName === "RT") setCamPreset("top");
  }
}

function renderProfileList() {
  const list = document.getElementById("profileList");
  list.innerHTML = Object.keys(cfg.profiles).map(name => {
    const active = name === cfg.active_profile;
    return `
      <button class="nav-item ${active ? "active" : ""}" onclick="switchProfile('${name}')">
        <span class="profile-left"><span class="dot ${active ? "on" : ""}"></span>${prettyProfileName(name)}</span>
      </button>
    `;
  }).join("");
}

function switchProfile(name) {
  cfg.active_profile = name;
  renderProfileList();
  renderAll();
  scheduleAutoSave();
}

function setEditLayer(layer) {
  editLayer = layer;
  document.getElementById("btnLayerBase").classList.toggle("active", layer === "base");
  document.getElementById("btnLayerShift").classList.toggle("active", layer === "shift");
  renderInspector();
  renderButtonChips();
}

function renderButtonChips() {
  const p = cfg.profiles[cfg.active_profile];
  const map = editLayer === "shift" ? (p.shift_buttons || {}) : (p.buttons || {});
  const wrap = document.getElementById("buttonChips");
  wrap.innerHTML = ALL_BTNS.map(b => {
    const isSel = b === selectedBtn;
    const isHit = typeof pad3dState !== "undefined" && pad3dState.held.has(b);
    return `
      <button type="button" class="btn-chip ${isSel ? "selected" : ""} ${isHit ? "live-hit" : ""}" onclick="selectButton('${b}')">
        <strong>${b}</strong>
        <span class="chip-key">${formatKey(map[b])}</span>
      </button>
    `;
  }).join("");
}

function renderInspector() {
  const p = cfg.profiles[cfg.active_profile];
  if (!p.shift_buttons) p.shift_buttons = {};
  if (!p.turbo_buttons) p.turbo_buttons = [];
  if (!p.toggle_buttons) p.toggle_buttons = [];

  document.getElementById("inspBtnTitle").textContent = BTN_LABELS[selectedBtn] || selectedBtn;
  const map = editLayer === "shift" ? p.shift_buttons : p.buttons;
  const curVal = map[selectedBtn] || "";

  const recBtn = document.getElementById("recordKeyBtn");
  recBtn.classList.toggle("listening", listeningBind);
  document.getElementById("lblRecordAction").textContent = listeningBind ? t("listening") : t("record");
  document.getElementById("currentKeyLabel").textContent = listeningBind ? "..." : formatKey(curVal);

  document.getElementById("quickKeyPresets").innerHTML = QUICK_PRESET_ACTIONS.map(a => `
    <button type="button" class="mini-pill" onclick="setButtonAction('${a.val}')">${a.label}</button>
  `).join("");

  document.getElementById("chkInspTurbo").checked = p.turbo_buttons.includes(selectedBtn);
  document.getElementById("chkInspToggle").checked = p.toggle_buttons.includes(selectedBtn);

  const shiftSel = document.getElementById("shiftButtonSelect");
  shiftSel.innerHTML = `<option value="">Desativado</option>` +
    ALL_BTNS.map(b => `<option value="${b}" ${p.shift_button === b ? "selected" : ""}>${b}</option>`).join("");
}

function startInspectorBind() {
  listeningBind = true;
  listeningStickDir = null;
  renderInspector();
}

function setButtonAction(val) {
  const p = cfg.profiles[cfg.active_profile];
  const map = editLayer === "shift" ? p.shift_buttons : p.buttons;
  map[selectedBtn] = val;
  listeningBind = false;
  renderInspector();
  renderButtonChips();
  scheduleAutoSave();
}

function toggleButtonFlag(flag) {
  const p = cfg.profiles[cfg.active_profile];
  const arrName = flag === "turbo" ? "turbo_buttons" : "toggle_buttons";
  const set = new Set(p[arrName] || []);
  if (set.has(selectedBtn)) set.delete(selectedBtn);
  else set.add(selectedBtn);
  p[arrName] = Array.from(set);
  scheduleAutoSave();
}

function updateShiftModifier() {
  const p = cfg.profiles[cfg.active_profile];
  p.shift_button = document.getElementById("shiftButtonSelect").value;
  scheduleAutoSave();
}

function renderSticksPane() {
  const p = cfg.profiles[cfg.active_profile];
  document.getElementById("rightStickMode").value = p.right_stick_mode || "mouse";
  const dz = p.deadzone ?? 10000;
  const tr = p.trigger_threshold ?? 200;
  const ms = p.mouse_speed ?? 18;
  const tb = p.turbo_rate ?? 12;

  document.getElementById("deadzoneRange").value = dz;
  document.getElementById("valDeadzone").textContent = Math.round((dz / 25000) * 100) + "%";

  document.getElementById("triggerRange").value = tr;
  document.getElementById("valTrigger").textContent = Math.round((tr / 1000) * 100) + "%";

  document.getElementById("mouseSpeedRange").value = ms;
  document.getElementById("valMouseSpeed").textContent = ms;

  document.getElementById("turboRateRange").value = tb;
  document.getElementById("valTurboRate").textContent = tb + "/s";

  const dirs = [
    { k: "up", label: "Cima ↑" },
    { k: "down", label: "Baixo ↓" },
    { k: "left", label: "Esquerda ←" },
    { k: "right", label: "Direita →" }
  ];
  document.getElementById("leftStickList").innerHTML = dirs.map(d => `
    <div class="rule-item">
      <span>${d.label}</span>
      <button type="button" class="mini-pill" onclick="bindStickDir('${d.k}')">
        ${listeningStickDir === d.k ? "..." : formatKey((p.left_stick || {})[d.k])}
      </button>
    </div>
  `).join("");
}

function bindStickDir(dir) {
  listeningStickDir = dir;
  listeningBind = false;
  renderSticksPane();
}

function onStickSettingChange() {
  const p = cfg.profiles[cfg.active_profile];
  p.right_stick_mode = document.getElementById("rightStickMode").value;
  p.deadzone = parseInt(document.getElementById("deadzoneRange").value);
  p.trigger_threshold = parseInt(document.getElementById("triggerRange").value);
  p.mouse_speed = parseInt(document.getElementById("mouseSpeedRange").value);
  p.turbo_rate = parseInt(document.getElementById("turboRateRange").value);
  renderSticksPane();
  scheduleAutoSave();
}

function renderAutomationPane() {
  const profSel = document.getElementById("newAppProfile");
  profSel.innerHTML = Object.keys(cfg.profiles).map(n => `<option value="${n}">${prettyProfileName(n)}</option>`).join("");

  const rules = cfg.app_rules || {};
  document.getElementById("appRulesList").innerHTML = Object.entries(rules).map(([app, prof]) => `
    <div class="rule-item">
      <span><strong>${app}</strong> → ${prettyProfileName(prof)}</span>
      <button class="del-x" onclick="removeAppRule('${app}')">✕</button>
    </div>
  `).join("") || `<div class="field-desc">—</div>`;

  const btnOpts = ALL_BTNS.map(b => `<option value="${b}">${b}</option>`).join("");
  document.getElementById("comboBtn1").innerHTML = btnOpts;
  document.getElementById("comboBtn2").innerHTML = btnOpts;
  document.getElementById("comboBtn2").value = "MENU";

  const combos = cfg.combos || {};
  document.getElementById("combosList").innerHTML = Object.entries(combos).map(([keys, act]) => `
    <div class="rule-item">
      <span><strong>${keys}</strong> → ${formatKey(act)}</span>
      <button class="del-x" onclick="removeComboRule('${keys}')">✕</button>
    </div>
  `).join("") || `<div class="field-desc">—</div>`;
}

function addAppRule() {
  const kw = document.getElementById("newAppKeyword").value.trim().toLowerCase();
  const prof = document.getElementById("newAppProfile").value;
  if (!kw || !prof) return;
  if (!cfg.app_rules) cfg.app_rules = {};
  cfg.app_rules[kw] = prof;
  document.getElementById("newAppKeyword").value = "";
  renderAutomationPane();
  scheduleAutoSave();
}

function removeAppRule(kw) {
  if (cfg.app_rules) delete cfg.app_rules[kw];
  renderAutomationPane();
  scheduleAutoSave();
}

function addComboRule() {
  const b1 = document.getElementById("comboBtn1").value;
  const b2 = document.getElementById("comboBtn2").value;
  const act = document.getElementById("comboAction").value;
  if (!b1 || !b2 || b1 === b2) return;
  if (!cfg.combos) cfg.combos = {};
  cfg.combos[`${b1}+${b2}`] = act;
  renderAutomationPane();
  scheduleAutoSave();
}

function removeComboRule(keys) {
  if (cfg.combos) delete cfg.combos[keys];
  renderAutomationPane();
  scheduleAutoSave();
}

function mapDomKey(e) {
  const map = {
    " ": "space", "Enter": "enter", "Escape": "esc", "Tab": "tab",
    "Backspace": "backspace", "ArrowUp": "up", "ArrowDown": "down",
    "ArrowLeft": "left", "ArrowRight": "right", "Shift": "shift",
    "Control": "ctrl", "Meta": "cmd"
  };
  if (map[e.key]) return map[e.key];
  if (/^F\d{1,2}$/i.test(e.key)) return e.key.toLowerCase();
  if (e.key.length === 1) return e.key.toLowerCase();
  return null;
}

window.addEventListener("keydown", e => {
  if (!listeningBind && !listeningStickDir) return;
  e.preventDefault();
  e.stopPropagation();
  const mapped = mapDomKey(e);
  if (!mapped) return;
  if (listeningBind) {
    setButtonAction(mapped);
  } else if (listeningStickDir) {
    const p = cfg.profiles[cfg.active_profile];
    if (!p.left_stick) p.left_stick = {};
    p.left_stick[listeningStickDir] = mapped;
    listeningStickDir = null;
    renderSticksPane();
    scheduleAutoSave();
  }
}, true);

function createProfile() {
  let idx = Object.keys(cfg.profiles).length + 1;
  let name = "Perfil " + idx;
  while (cfg.profiles[name]) { idx++; name = "Perfil " + idx; }
  cfg.profiles[name] = JSON.parse(JSON.stringify(cfg.profiles[cfg.active_profile] || {}));
  cfg.active_profile = name;
  renderProfileList();
  renderAll();
  scheduleAutoSave();
}

function deleteProfile() {
  const keys = Object.keys(cfg.profiles);
  if (keys.length <= 1) return;
  delete cfg.profiles[cfg.active_profile];
  cfg.active_profile = Object.keys(cfg.profiles)[0];
  renderProfileList();
  renderAll();
  scheduleAutoSave();
}

function exportProfile() {
  const name = cfg.active_profile;
  const blob = new Blob([JSON.stringify({ name, profile: cfg.profiles[name] }, null, 2)], { type: "application/json" });
  const a = document.createElement("a");
  a.href = URL.createObjectURL(blob);
  a.download = `gamesir_${name.replace(/\s+/g, "_")}.json`;
  a.click();
}

function importProfile(event) {
  const file = event.target.files[0];
  if (!file) return;
  const reader = new FileReader();
  reader.onload = e => {
    try {
      const parsed = JSON.parse(e.target.result);
      const profObj = parsed.profile || parsed;
      if (!profObj.buttons) return;
      const name = (parsed.name || file.name.replace(".json", "")).trim();
      cfg.profiles[name] = profObj;
      cfg.active_profile = name;
      renderProfileList();
      renderAll();
      scheduleAutoSave();
    } catch (err) {}
  };
  reader.readAsText(file);
  event.target.value = "";
}

function applyTemplate() {
  const sel = document.getElementById("templateSelect");
  const key = sel.value;
  const PRESETS = {
    pcsx2: { right_stick_mode: "keys", deadzone: 9000, trigger_threshold: 200, shift_button: "SHARE", buttons: { A:"k", B:"l", X:"j", Y:"i", MENU:"enter", VIEW:"z", SHARE:"", UP:"up", DOWN:"down", LEFT:"left", RIGHT:"right", LB:"q", RB:"e", LT:"1", RT:"3", L3:"2", R3:"4" }, shift_buttons: { A:"f1", B:"f3", X:"tab", Y:"esc" }, left_stick: { up:"w", down:"s", left:"a", right:"d" } },
    dolphin: { right_stick_mode: "keys", deadzone: 9000, trigger_threshold: 200, shift_button: "SHARE", buttons: { A:"x", B:"z", X:"c", Y:"s", MENU:"enter", VIEW:"tab", UP:"up", DOWN:"down", LEFT:"left", RIGHT:"right", LB:"q", RB:"w", LT:"a", RT:"d", L3:"1", R3:"2" }, shift_buttons: { A:"f1", B:"f2" }, left_stick: { up:"w", down:"s", left:"a", right:"d" } },
    retroarch: { right_stick_mode: "keys", deadzone: 9500, trigger_threshold: 250, shift_button: "SHARE", buttons: { A:"x", B:"z", X:"s", Y:"a", MENU:"enter", VIEW:"rshift", UP:"up", DOWN:"down", LEFT:"left", RIGHT:"right", LB:"q", RB:"w", LT:"1", RT:"2" }, shift_buttons: { A:"f2", B:"f4", MENU:"f1" }, left_stick: { up:"up", down:"down", left:"left", right:"right" } },
    ppsspp: { right_stick_mode: "keys", deadzone: 9000, trigger_threshold: 200, shift_button: "SHARE", buttons: { A:"x", B:"z", X:"s", Y:"a", MENU:"enter", VIEW:"space", UP:"up", DOWN:"down", LEFT:"left", RIGHT:"right", LB:"q", RB:"w", LT:"1", RT:"2" }, shift_buttons: { A:"f2", B:"f4" }, left_stick: { up:"w", down:"s", left:"a", right:"d" } },
    hollow_knight: { right_stick_mode: "keys", deadzone: 8500, trigger_threshold: 200, shift_button: "SHARE", buttons: { A:"z", B:"x", X:"c", Y:"a", MENU:"esc", VIEW:"tab", UP:"up", DOWN:"down", LEFT:"left", RIGHT:"right", LB:"q", RB:"s", LT:"f", RT:"d" }, shift_buttons: {}, left_stick: { up:"up", down:"down", left:"left", right:"right" } },
    minecraft_mac: { right_stick_mode: "mouse", deadzone: 8000, trigger_threshold: 180, shift_button: "SHARE", mouse_speed: 18, buttons: { A:"space", B:"q", X:"e", Y:"f", MENU:"esc", VIEW:"tab", UP:"f5", DOWN:"t", LEFT:"1", RIGHT:"2", LB:"mouse_left", RB:"mouse_right", LT:"shift", RT:"ctrl" }, shift_buttons: {}, left_stick: { up:"w", down:"s", left:"a", right:"d" } },
    desktop_media: { right_stick_mode: "mouse", deadzone: 8000, trigger_threshold: 200, shift_button: "SHARE", mouse_speed: 16, buttons: { A:"enter", B:"esc", X:"space", Y:"cmd+w", MENU:"cmd+tab", VIEW:"ctrl+up", UP:"up", DOWN:"down", LEFT:"left", RIGHT:"right", LB:"scroll_mod", RB:"mouse_left", LT:"mouse_right" }, shift_buttons: { B:"cmd+q" }, left_stick: { up:"up", down:"down", left:"left", right:"right" } },
    dj_control: { right_stick_mode: "mouse", deadzone: 8500, trigger_threshold: 180, shift_button: "SHARE", mouse_speed: 14, buttons: { A:"space", B:"c", X:"s", Y:"l", MENU:"enter", VIEW:"tab", UP:"up", DOWN:"down", LEFT:"left", RIGHT:"right", LB:"scroll_mod", RB:"mouse_left", LT:"q", RT:"w" }, shift_buttons: {}, left_stick: { up:"up", down:"down", left:"left", right:"right" } }
  };
  if (!key || !PRESETS[key]) return;
  cfg.profiles[cfg.active_profile] = JSON.parse(JSON.stringify(PRESETS[key]));
  sel.value = "";
  renderAll();
  scheduleAutoSave();
}

function calibrateZeroDrift() {
  cfg.calibration = { lx_offset: lastRaw.lx, ly_offset: lastRaw.ly, rx_offset: lastRaw.rx, ry_offset: lastRaw.ry };
  scheduleAutoSave();
}

function resetZeroDrift() {
  cfg.calibration = { lx_offset: 0, ly_offset: 0, rx_offset: 0, ry_offset: 0 };
  scheduleAutoSave();
}

function changeLang() {
  lang = document.getElementById("langSelect").value;
  cfg.language = lang;
  applyLocaleStrings();
  renderProfileList();
  renderAll();
  scheduleAutoSave();
}

function renderAll() {
  renderButtonChips();
  renderInspector();
  renderSticksPane();
  renderAutomationPane();
}

async function load() {
  const res = await fetch("/api/config");
  cfg = await res.json();
  lang = cfg.language || "pt";
  document.getElementById("langSelect").value = lang;
  applyLocaleStrings();
  renderProfileList();
  renderAll();
}

let pad3dState = {
  held: new Set(),
  selected: "A",
  hovered: null,
  lx: 0, ly: 0, rx: 0, ry: 0, lt: 0, rt: 0,
  profile: "emulators",
  autoSpin: false,
  targetYaw: 0, targetPitch: 0.42, targetDist: 5.55,
  yaw: 0, pitch: 0.42, dist: 5.55
};

function setCamPreset(mode) {
  pad3dState.autoSpin = false;
  const spinBtn = document.getElementById("btnAutoSpin");
  if (spinBtn) spinBtn.classList.remove("active");
  if (mode === "front") { pad3dState.targetYaw = 0; pad3dState.targetPitch = 0.38; pad3dState.targetDist = 5.45; }
  else if (mode === "back") { pad3dState.targetYaw = Math.PI; pad3dState.targetPitch = 0.22; pad3dState.targetDist = 5.45; }
  else if (mode === "top") { pad3dState.targetYaw = 0; pad3dState.targetPitch = 1.28; pad3dState.targetDist = 5.25; }
}

function toggleAutoSpin() {
  pad3dState.autoSpin = !pad3dState.autoSpin;
  const btn = document.getElementById("btnAutoSpin");
  if (btn) btn.classList.toggle("active", pad3dState.autoSpin);
}

(function init3DController() {
  try {
  const canvas = document.getElementById("pad3dCanvas");
  const wrap = document.getElementById("pad3dWrap");
  const hoverTag = document.getElementById("hoverTag");
  if (!canvas || !wrap || typeof THREE === "undefined") return;
  const w = Math.max(320, wrap.clientWidth || 640);
  const h = Math.max(240, wrap.clientHeight || 420);

  const scene = new THREE.Scene();
  const camera = new THREE.PerspectiveCamera(35, w / h, 0.1, 100);
  const renderer = new THREE.WebGLRenderer({ canvas, antialias: true, alpha: true });
  renderer.setPixelRatio(Math.min(window.devicePixelRatio || 1, 2));
  renderer.setSize(w, h);
  renderer.toneMapping = THREE.ACESFilmicToneMapping;
  renderer.toneMappingExposure = 1.06;

  scene.add(new THREE.AmbientLight(0x94a3b8, 0.65));
  const keyLight = new THREE.DirectionalLight(0xffffff, 1.65);
  keyLight.position.set(4.5, 9.0, 6.0);
  scene.add(keyLight);
  const rimLight = new THREE.DirectionalLight(0xbae6fd, 0.85);
  rimLight.position.set(-6.0, 5.0, -4.0);
  scene.add(rimLight);
  const backLight = new THREE.DirectionalLight(0xe2e8f0, 1.15);
  backLight.position.set(0, 2.0, -8.0);
  scene.add(backLight);

  // Sombra de contato suave em estúdio abaixo do controle
  const shCanvas = document.createElement("canvas");
  shCanvas.width = 256; shCanvas.height = 256;
  const shCtx = shCanvas.getContext("2d");
  const shGrad = shCtx.createRadialGradient(128, 128, 20, 128, 128, 122);
  shGrad.addColorStop(0, "rgba(0, 0, 0, 0.36)");
  shGrad.addColorStop(0.65, "rgba(0, 0, 0, 0.12)");
  shGrad.addColorStop(1, "rgba(0, 0, 0, 0.0)");
  shCtx.fillStyle = shGrad;
  shCtx.fillRect(0, 0, 256, 256);
  const shadowPlane = new THREE.Mesh(
    new THREE.PlaneGeometry(5.2, 3.6),
    new THREE.MeshBasicMaterial({ map: new THREE.CanvasTexture(shCanvas), transparent: true, depthWrite: false })
  );
  shadowPlane.rotation.x = -Math.PI / 2;
  shadowPlane.position.set(0, -0.52, 0.05);
  scene.add(shadowPlane);

  function prepTopTex(c, rot = Math.PI / 2) {
    const tex = new THREE.CanvasTexture(c);
    tex.anisotropy = 4;
    tex.center.set(0.5, 0.5);
    tex.rotation = rot;
    return tex;
  }

  function makeFaceCapTexture(letter, color) {
    const c = document.createElement("canvas");
    c.width = 256; c.height = 256;
    const ctx = c.getContext("2d");
    const g = ctx.createRadialGradient(110, 105, 18, 128, 128, 125);
    g.addColorStop(0, "#ffffff"); g.addColorStop(0.78, "#e2e8f0"); g.addColorStop(1, "#94a3b8");
    ctx.fillStyle = g; ctx.fillRect(0, 0, 256, 256);
    ctx.strokeStyle = "#475569"; ctx.lineWidth = 14;
    ctx.beginPath(); ctx.arc(128, 128, 118, 0, Math.PI * 2); ctx.stroke();
    ctx.fillStyle = color;
    ctx.font = "800 144px -apple-system, BlinkMacSystemFont, sans-serif";
    ctx.textAlign = "center"; ctx.textBaseline = "middle";
    ctx.fillText(letter, 128, 138);
    return prepTopTex(c, Math.PI / 2);
  }

  function makeSmallIconTexture(type) {
    const c = document.createElement("canvas");
    c.width = 192; c.height = 192;
    const ctx = c.getContext("2d");
    ctx.fillStyle = "#e2e8f0"; ctx.fillRect(0, 0, 192, 192);
    ctx.strokeStyle = "#475569"; ctx.lineWidth = 12;
    ctx.strokeRect(6, 6, 180, 180);
    ctx.strokeStyle = "#334155"; ctx.fillStyle = "#334155"; ctx.lineWidth = 11; ctx.lineCap = "round";
    if (type === "VIEW") {
      ctx.strokeRect(52, 68, 52, 42); ctx.strokeRect(86, 84, 52, 42);
    } else if (type === "MENU") {
      [68, 96, 124].forEach(y => { ctx.beginPath(); ctx.moveTo(52, y); ctx.lineTo(140, y); ctx.stroke(); });
    } else if (type === "SHARE") {
      ctx.beginPath();
      ctx.moveTo(62, 108); ctx.lineTo(62, 128); ctx.lineTo(130, 128); ctx.lineTo(130, 108);
      ctx.moveTo(96, 112); ctx.lineTo(96, 62);
      ctx.moveTo(76, 80); ctx.lineTo(96, 60); ctx.lineTo(116, 80);
      ctx.stroke();
    } else if (type === "M") {
      ctx.font = "800 84px -apple-system, sans-serif";
      ctx.textAlign = "center"; ctx.textBaseline = "middle";
      ctx.fillText("M", 96, 102);
    }
    return prepTopTex(c, (type === "SHARE" || type === "M") ? 0 : Math.PI / 2);
  }

  function makeXboxTexture() {
    const c = document.createElement("canvas");
    c.width = 256; c.height = 256;
    const ctx = c.getContext("2d");
    const grad = ctx.createRadialGradient(100, 90, 16, 128, 128, 125);
    grad.addColorStop(0, "#334155"); grad.addColorStop(0.55, "#0f172a"); grad.addColorStop(1, "#020617");
    ctx.fillStyle = grad; ctx.fillRect(0, 0, 256, 256);
    ctx.strokeStyle = "#f8fafc"; ctx.lineWidth = 22; ctx.lineCap = "round";
    ctx.beginPath();
    ctx.moveTo(64, 68); ctx.quadraticCurveTo(128, 128, 192, 196);
    ctx.moveTo(192, 68); ctx.quadraticCurveTo(128, 128, 64, 196);
    ctx.stroke();
    return prepTopTex(c, Math.PI / 2);
  }

  function makeLogoTexture() {
    const c = document.createElement("canvas");
    c.width = 512; c.height = 96;
    const ctx = c.getContext("2d");
    ctx.fillStyle = "#64748b";
    ctx.font = "800 44px -apple-system, BlinkMacSystemFont, sans-serif";
    ctx.textAlign = "center"; ctx.textBaseline = "middle";
    ctx.fillText("GAMESIR", 256, 48);
    return new THREE.CanvasTexture(c);
  }

  const root = new THREE.Group();
  scene.add(root);

  const whiteShellMat = new THREE.MeshStandardMaterial({ color: 0xe6ebf2, roughness: 0.42, metalness: 0.05 });
  const bezelDarkMat = new THREE.MeshStandardMaterial({ color: 0x334155, roughness: 0.55, metalness: 0.25 });
  const btnContrastMat = new THREE.MeshStandardMaterial({ color: 0xcbd5e1, roughness: 0.36, metalness: 0.12 });
  const bumperMat = new THREE.MeshStandardMaterial({ color: 0xd8e0ea, roughness: 0.38, metalness: 0.14 });
  const triggerMat = new THREE.MeshStandardMaterial({ color: 0xb8c4d4, roughness: 0.42, metalness: 0.18 });
  const antiFrictionRingMat = new THREE.MeshStandardMaterial({ color: 0x10b981, roughness: 0.25, metalness: 0.18 });
  const stickGrayMat = new THREE.MeshStandardMaterial({ color: 0x64748b, roughness: 0.55, metalness: 0.12 });
  const stickCapMat = new THREE.MeshStandardMaterial({ color: 0x94a3b8, roughness: 0.62, metalness: 0.08 });

  const bodyShape = new THREE.Shape();
  bodyShape.moveTo(0, -1.04);
  bodyShape.bezierCurveTo(0.68, -1.04, 1.18, -0.96, 1.48, -0.74);
  bodyShape.bezierCurveTo(1.76, -0.52, 2.04, 0.22, 2.06, 0.88);
  bodyShape.bezierCurveTo(2.07, 1.32, 1.76, 1.50, 1.48, 1.38);
  bodyShape.bezierCurveTo(1.22, 1.24, 1.05, 0.74, 0.68, 0.64);
  bodyShape.bezierCurveTo(0.32, 0.56, -0.32, 0.56, -0.68, 0.64);
  bodyShape.bezierCurveTo(-1.05, 0.74, -1.22, 1.24, -1.48, 1.38);
  bodyShape.bezierCurveTo(-1.76, 1.50, -2.07, 1.32, -2.06, 0.88);
  bodyShape.bezierCurveTo(-2.04, 0.22, -1.76, -0.52, -1.48, -0.74);
  bodyShape.bezierCurveTo(-1.18, -0.96, -0.68, -1.04, 0, -1.04);

  const chassisGeo = new THREE.ExtrudeGeometry(bodyShape, {
    steps: 2, depth: 0.44, bevelEnabled: true, bevelThickness: 0.14, bevelSize: 0.12, bevelSegments: 10, curveSegments: 36
  });
  chassisGeo.rotateX(Math.PI / 2); chassisGeo.translate(0, 0.22, 0);
  root.add(new THREE.Mesh(chassisGeo, whiteShellMat));

  const seamGeo = new THREE.ExtrudeGeometry(bodyShape, {
    steps: 1, depth: 0.025, bevelEnabled: true, bevelThickness: 0.01, bevelSize: 0.123, bevelSegments: 2, curveSegments: 36
  });
  seamGeo.rotateX(Math.PI / 2); seamGeo.translate(0, 0.04, 0);
  root.add(new THREE.Mesh(seamGeo, bezelDarkMat));

  const logoPlane = new THREE.Mesh(
    new THREE.PlaneGeometry(0.82, 0.15),
    new THREE.MeshBasicMaterial({ map: makeLogoTexture(), transparent: true, opacity: 0.95 })
  );
  logoPlane.rotation.x = -Math.PI / 2; logoPlane.position.set(0, 0.365, 0.50);
  root.add(logoPlane);

  const cableGroup = new THREE.Group();
  cableGroup.position.set(0, 0.10, -1.16);
  cableGroup.add(new THREE.Mesh(new THREE.BoxGeometry(0.32, 0.16, 0.26), bumperMat));
  const cordCurve = new THREE.CatmullRomCurve3([
    new THREE.Vector3(0, 0, -0.15), new THREE.Vector3(0, 0.03, -0.85), new THREE.Vector3(0.06, 0.06, -1.45)
  ]);
  cableGroup.add(new THREE.Mesh(new THREE.TubeGeometry(cordCurve, 20, 0.042, 12, false), whiteShellMat));
  root.add(cableGroup);

  const btnMeshes = {};
  const clickableObjects = [];
  function addButton(name, mesh, pressAxis = "y", pressDelta = -0.055) {
    mesh.userData.btnName = name;
    clickableObjects.push(mesh);
    root.add(mesh);
    btnMeshes[name] = { mesh, basePos: [mesh.position.x, mesh.position.y, mesh.position.z], pressAxis, pressDelta };
    return mesh;
  }

  const faceSpecs = [
    { name: "Y", letter: "Y", color: "#ca8a04", x: 1.24, z: -0.44 },
    { name: "B", letter: "B", color: "#dc2626", x: 1.50, z: -0.20 },
    { name: "X", letter: "X", color: "#2563eb", x: 0.98, z: -0.20 },
    { name: "A", letter: "A", color: "#16a34a", x: 1.24, z: 0.04 }
  ];
  faceSpecs.forEach(spec => {
    const bezel = new THREE.Mesh(new THREE.CylinderGeometry(0.162, 0.166, 0.02, 28), bezelDarkMat);
    bezel.position.set(spec.x, 0.362, spec.z); root.add(bezel);
    const mats = [
      new THREE.MeshStandardMaterial({ color: 0x64748b, roughness: 0.4 }),
      new THREE.MeshStandardMaterial({ map: makeFaceCapTexture(spec.letter, spec.color), roughness: 0.28 }),
      new THREE.MeshStandardMaterial({ color: 0x64748b, roughness: 0.4 })
    ];
    const btn = new THREE.Mesh(new THREE.CylinderGeometry(0.148, 0.155, 0.11, 28), mats);
    btn.position.set(spec.x, 0.39, spec.z);
    addButton(spec.name, btn, "y", -0.055);
  });

  const xboxBezel = new THREE.Mesh(new THREE.CylinderGeometry(0.195, 0.205, 0.055, 32), bezelDarkMat);
  xboxBezel.position.set(0, 0.365, -0.46); root.add(xboxBezel);
  const xboxBtn = new THREE.Mesh(
    new THREE.CylinderGeometry(0.162, 0.162, 0.075, 32),
    new THREE.MeshStandardMaterial({ map: makeXboxTexture(), emissive: 0x0a84ff, emissiveIntensity: 0.32, roughness: 0.22 })
  );
  xboxBtn.position.set(0, 0.382, -0.46); root.add(xboxBtn);

  [{ name: "VIEW", x: -0.42 }, { name: "MENU", x: 0.42 }].forEach(s => {
    const ring = new THREE.Mesh(new THREE.CylinderGeometry(0.102, 0.106, 0.02, 24), bezelDarkMat);
    ring.position.set(s.x, 0.362, -0.46); root.add(ring);
    const mats = [btnContrastMat, new THREE.MeshStandardMaterial({ map: makeSmallIconTexture(s.name), roughness: 0.3 }), btnContrastMat];
    const b = new THREE.Mesh(new THREE.CylinderGeometry(0.09, 0.095, 0.085, 24), mats);
    b.position.set(s.x, 0.385, -0.46);
    addButton(s.name, b, "y", -0.045);
  });

  [{ name: "SHARE", z: -0.14, w: 0.24, d: 0.14 }, { name: "M", z: 0.33, w: 0.22, d: 0.13 }].forEach(s => {
    const frame = new THREE.Mesh(new THREE.BoxGeometry(s.w + 0.03, 0.02, s.d + 0.03), bezelDarkMat);
    frame.position.set(0, 0.362, s.z); root.add(frame);
    const topMat = new THREE.MeshStandardMaterial({ map: makeSmallIconTexture(s.name), roughness: 0.32 });
    const b = new THREE.Mesh(new THREE.BoxGeometry(s.w, 0.085, s.d), [btnContrastMat, btnContrastMat, topMat, btnContrastMat, btnContrastMat, btnContrastMat]);
    b.position.set(0, 0.385, s.z);
    addButton(s.name, b, "y", -0.045);
  });

  const dpadWell = new THREE.Mesh(new THREE.CylinderGeometry(0.37, 0.38, 0.025, 32), bezelDarkMat);
  dpadWell.position.set(-0.62, 0.362, 0.22); root.add(dpadWell);
  const dpadCenter = new THREE.Mesh(new THREE.BoxGeometry(0.20, 0.105, 0.20), btnContrastMat);
  dpadCenter.position.set(-0.62, 0.39, 0.22); root.add(dpadCenter);

  const dpadArmMat = () => new THREE.MeshStandardMaterial({ color: 0xdbe3ee, roughness: 0.34, metalness: 0.1 });
  const upMesh = new THREE.Mesh(new THREE.BoxGeometry(0.19, 0.11, 0.20), dpadArmMat());
  upMesh.position.set(-0.62, 0.395, 0.04); addButton("UP", upMesh, "y", -0.045);
  const downMesh = new THREE.Mesh(new THREE.BoxGeometry(0.19, 0.11, 0.20), dpadArmMat());
  downMesh.position.set(-0.62, 0.395, 0.40); addButton("DOWN", downMesh, "y", -0.045);
  const leftMesh = new THREE.Mesh(new THREE.BoxGeometry(0.20, 0.11, 0.19), dpadArmMat());
  leftMesh.position.set(-0.80, 0.395, 0.22); addButton("LEFT", leftMesh, "y", -0.045);
  const rightMesh = new THREE.Mesh(new THREE.BoxGeometry(0.20, 0.11, 0.19), dpadArmMat());
  rightMesh.position.set(-0.44, 0.395, 0.22); addButton("RIGHT", rightMesh, "y", -0.045);

  const lbMesh = new THREE.Mesh(new THREE.BoxGeometry(0.86, 0.16, 0.25), bumperMat);
  lbMesh.position.set(-1.12, 0.22, -0.94); lbMesh.rotation.set(0.12, 0.28, -0.06);
  addButton("LB", lbMesh, "z", 0.055);
  const rbMesh = new THREE.Mesh(new THREE.BoxGeometry(0.86, 0.16, 0.25), bumperMat);
  rbMesh.position.set(1.12, 0.22, -0.94); rbMesh.rotation.set(0.12, -0.28, 0.06);
  addButton("RB", rbMesh, "z", 0.055);

  const trigPivotL = new THREE.Group();
  trigPivotL.position.set(-1.08, 0.08, -0.98); trigPivotL.rotation.y = 0.22;
  const ltMesh = new THREE.Mesh(new THREE.BoxGeometry(0.70, 0.30, 0.30), triggerMat.clone());
  ltMesh.position.set(0, -0.06, -0.08); ltMesh.userData.btnName = "LT";
  clickableObjects.push(ltMesh); trigPivotL.add(ltMesh); root.add(trigPivotL);

  const trigPivotR = new THREE.Group();
  trigPivotR.position.set(1.08, 0.08, -0.98); trigPivotR.rotation.y = -0.22;
  const rtMesh = new THREE.Mesh(new THREE.BoxGeometry(0.70, 0.30, 0.30), triggerMat.clone());
  rtMesh.position.set(0, -0.06, -0.08); rtMesh.userData.btnName = "RT";
  clickableObjects.push(rtMesh); trigPivotR.add(rtMesh); root.add(trigPivotR);

  const paddleShape = new THREE.Shape();
  paddleShape.moveTo(0, -0.24);
  paddleShape.quadraticCurveTo(0.22, -0.12, 0.22, 0);
  paddleShape.quadraticCurveTo(0.22, 0.14, 0, 0.24);
  paddleShape.quadraticCurveTo(-0.22, 0.14, -0.22, 0);
  paddleShape.quadraticCurveTo(-0.22, -0.12, 0, -0.24);

  const paddleFrameGeo = new THREE.ExtrudeGeometry(paddleShape, { depth: 0.02, bevelEnabled: true, bevelThickness: 0.01, bevelSize: 0.032, bevelSegments: 3 });
  paddleFrameGeo.rotateX(Math.PI / 2);
  const paddleGeo = new THREE.ExtrudeGeometry(paddleShape, { depth: 0.055, bevelEnabled: true, bevelThickness: 0.02, bevelSize: 0.02, bevelSegments: 4 });
  paddleGeo.rotateX(Math.PI / 2);

  const l4Frame = new THREE.Mesh(paddleFrameGeo, bezelDarkMat);
  l4Frame.position.set(-1.32, -0.358, 0.26); l4Frame.rotation.y = -0.25; root.add(l4Frame);
  const l4Mesh = new THREE.Mesh(paddleGeo, bumperMat.clone());
  l4Mesh.position.set(-1.32, -0.348, 0.26); l4Mesh.rotation.y = -0.25;
  addButton("L4", l4Mesh, "y", 0.05);

  const r4Frame = new THREE.Mesh(paddleFrameGeo, bezelDarkMat);
  r4Frame.position.set(1.32, -0.358, 0.26); r4Frame.rotation.y = 0.25; root.add(r4Frame);
  const r4Mesh = new THREE.Mesh(paddleGeo, bumperMat.clone());
  r4Mesh.position.set(1.32, -0.348, 0.26); r4Mesh.rotation.y = 0.25;
  addButton("R4", r4Mesh, "y", 0.05);

  function makeG7Stick(x, z, clickName) {
    const antiRing = new THREE.Mesh(new THREE.TorusGeometry(0.31, 0.036, 16, 40), antiFrictionRingMat);
    antiRing.rotation.x = Math.PI / 2; antiRing.position.set(x, 0.366, z); root.add(antiRing);
    const well = new THREE.Mesh(new THREE.CylinderGeometry(0.285, 0.285, 0.02, 32), bezelDarkMat);
    well.position.set(x, 0.356, z); root.add(well);
    const pivot = new THREE.Group(); pivot.position.set(x, 0.34, z);
    const stem = new THREE.Mesh(new THREE.CylinderGeometry(0.085, 0.11, 0.24, 20), stickGrayMat);
    stem.position.y = 0.12; pivot.add(stem);
    const capMat = stickCapMat.clone();
    const cap = new THREE.Mesh(new THREE.CylinderGeometry(0.255, 0.23, 0.09, 32), capMat);
    cap.position.y = 0.25; cap.userData.btnName = clickName; clickableObjects.push(cap); pivot.add(cap);
    const rim = new THREE.Mesh(new THREE.TorusGeometry(0.235, 0.024, 12, 32), stickGrayMat);
    rim.rotation.x = Math.PI / 2; rim.position.y = 0.295; pivot.add(rim);
    root.add(pivot);
    return { pivot, capMat };
  }

  const stickL = makeG7Stick(-1.24, -0.20, "L3");
  const stickR = makeG7Stick(0.62, 0.22, "R3");

  const raycaster = new THREE.Raycaster();
  const pointer = new THREE.Vector2();
  let downPos = { x: 0, y: 0 };
  let dragging = false, prevX = 0, prevY = 0;

  canvas.addEventListener("pointerdown", e => {
    dragging = true;
    downPos = { x: e.clientX, y: e.clientY };
    prevX = e.clientX; prevY = e.clientY;
    canvas.style.cursor = "grabbing";
  });

  window.addEventListener("pointerup", e => {
    if (dragging) {
      if (Math.hypot(e.clientX - downPos.x, e.clientY - downPos.y) < 5) {
        const rect = canvas.getBoundingClientRect();
        pointer.x = ((e.clientX - rect.left) / rect.width) * 2 - 1;
        pointer.y = -((e.clientY - rect.top) / rect.height) * 2 + 1;
        raycaster.setFromCamera(pointer, camera);
        const hits = raycaster.intersectObjects(clickableObjects, false);
        if (hits.length > 0 && hits[0].object.userData.btnName) {
          selectButton(hits[0].object.userData.btnName);
        }
      }
    }
    dragging = false;
    canvas.style.cursor = pad3dState.hovered ? "pointer" : "grab";
  });

  window.addEventListener("pointermove", e => {
    const rect = canvas.getBoundingClientRect();
    if (!dragging && e.clientX >= rect.left && e.clientX <= rect.right && e.clientY >= rect.top && e.clientY <= rect.bottom) {
      pointer.x = ((e.clientX - rect.left) / rect.width) * 2 - 1;
      pointer.y = -((e.clientY - rect.top) / rect.height) * 2 + 1;
      raycaster.setFromCamera(pointer, camera);
      const hits = raycaster.intersectObjects(clickableObjects, false);
      const hitName = (hits.length > 0 && hits[0].object.userData.btnName) ? hits[0].object.userData.btnName : null;
      pad3dState.hovered = hitName;
      canvas.style.cursor = hitName ? "pointer" : "grab";
      if (hitName && cfg.profiles && cfg.profiles[cfg.active_profile]) {
        const p = cfg.profiles[cfg.active_profile];
        const map = editLayer === "shift" ? (p.shift_buttons || {}) : (p.buttons || {});
        hoverTag.textContent = `${hitName} → ${formatKey(map[hitName])}`;
        hoverTag.style.left = (e.clientX - rect.left + 14) + "px";
        hoverTag.style.top = (e.clientY - rect.top - 28) + "px";
        hoverTag.style.display = "block";
      } else {
        hoverTag.style.display = "none";
      }
    } else if (!dragging) {
      pad3dState.hovered = null;
      hoverTag.style.display = "none";
    }

    if (!dragging) return;
    const dx = e.clientX - prevX;
    const dy = e.clientY - prevY;
    prevX = e.clientX; prevY = e.clientY;
    pad3dState.autoSpin = false;
    pad3dState.targetYaw -= dx * 0.012;
    pad3dState.targetPitch = Math.max(-1.25, Math.min(1.40, pad3dState.targetPitch + dy * 0.01));
  });

  canvas.addEventListener("wheel", e => {
    e.preventDefault();
    pad3dState.targetDist = Math.max(3.8, Math.min(8.5, pad3dState.targetDist + e.deltaY * 0.004));
  }, { passive: false });

  window.addEventListener("resize", () => {
    if (!wrap.clientWidth || !wrap.clientHeight) return;
    camera.aspect = wrap.clientWidth / wrap.clientHeight;
    camera.updateProjectionMatrix();
    renderer.setSize(wrap.clientWidth, wrap.clientHeight);
  });

  function animate() {
    requestAnimationFrame(animate);
    if (pad3dState.autoSpin) pad3dState.targetYaw += 0.012;
    pad3dState.yaw += (pad3dState.targetYaw - pad3dState.yaw) * 0.14;
    pad3dState.pitch += (pad3dState.targetPitch - pad3dState.pitch) * 0.14;
    pad3dState.dist += (pad3dState.targetDist - pad3dState.dist) * 0.14;

    camera.position.x = pad3dState.dist * Math.sin(pad3dState.yaw) * Math.cos(pad3dState.pitch);
    camera.position.y = pad3dState.dist * Math.sin(pad3dState.pitch);
    camera.position.z = pad3dState.dist * Math.cos(pad3dState.yaw) * Math.cos(pad3dState.pitch);
    camera.lookAt(0, 0.02, 0.10);

    for (const [name, item] of Object.entries(btnMeshes)) {
      const pressed = pad3dState.held.has(name);
      const isSelected = pad3dState.selected === name;
      const isHovered = pad3dState.hovered === name;
      const targetOffset = pressed ? item.pressDelta : 0;
      if (item.pressAxis === "y") item.mesh.position.y += (item.basePos[1] + targetOffset - item.mesh.position.y) * 0.36;
      else item.mesh.position.z += (item.basePos[2] + targetOffset - item.mesh.position.z) * 0.36;

      const mats = Array.isArray(item.mesh.material) ? item.mesh.material : [item.mesh.material];
      mats.forEach(m => {
        if (!m || !m.emissive) return;
        if (pressed) { m.emissive.setHex(0x30d158); m.emissiveIntensity = 0.85; }
        else if (isSelected) { m.emissive.setHex(0x0a84ff); m.emissiveIntensity = 0.34; }
        else if (isHovered) { m.emissive.setHex(0x38bdf8); m.emissiveIntensity = 0.24; }
        else m.emissiveIntensity *= 0.82;
      });
    }

    const maxTilt = 0.40;
    stickL.pivot.rotation.z = -(pad3dState.lx / 32768) * maxTilt;
    stickL.pivot.rotation.x = -(pad3dState.ly / 32768) * maxTilt;
    stickL.pivot.position.y = pad3dState.held.has("L3") ? 0.28 : 0.34;

    stickR.pivot.rotation.z = -(pad3dState.rx / 32768) * maxTilt;
    stickR.pivot.rotation.x = -(pad3dState.ry / 32768) * maxTilt;
    stickR.pivot.position.y = pad3dState.held.has("R3") ? 0.28 : 0.34;

    trigPivotL.rotation.x = Math.max(0, Math.min(1, (pad3dState.lt || 0) / 1023)) * 0.45;
    trigPivotR.rotation.x = Math.max(0, Math.min(1, (pad3dState.rt || 0) / 1023)) * 0.45;

    renderer.render(scene, camera);
  }
  animate();
  } catch (err3d) {
    console.error("3D init error:", err3d);
  }
})();

async function pollLive() {
  try {
    const res = await fetch("/api/live");
    const live = await res.json();
    const led = document.getElementById("statusLed");
    const st = document.getElementById("liveStatus");
    const sticks = document.getElementById("liveSticks");
    const heldSet = new Set(live.held || []);

    if (typeof pad3dState !== "undefined") {
      pad3dState.held = heldSet;
      pad3dState.lx = live.lx || 0; pad3dState.ly = live.ly || 0;
      pad3dState.rx = live.rx || 0; pad3dState.ry = live.ry || 0;
      pad3dState.lt = live.lt || 0; pad3dState.rt = live.rt || 0;
      if (live.profile) pad3dState.profile = live.profile;
    }

    if (live.connected) {
      lastRaw = { lx: live.raw_lx ?? live.lx ?? 0, ly: live.raw_ly ?? live.ly ?? 0, rx: live.raw_rx ?? live.rx ?? 0, ry: live.raw_ry ?? live.ry ?? 0 };
      led.classList.add("connected");
      st.textContent = `${live.connected} • ${prettyProfileName(live.profile || "")}`;
      sticks.textContent = `LS: ${live.lx}, ${live.ly} • RS: ${live.rx}, ${live.ry}`;
      if (live.held && live.held.length === 1 && !listeningBind) {
        const hit = live.held[0];
        if (ALL_BTNS.includes(hit) && hit !== selectedBtn) {
          selectedBtn = hit;
          renderInspector();
        }
      }
    } else {
      led.classList.remove("connected");
      st.textContent = t("searching");
    }
    renderButtonChips();
  } catch (e) {}
}

load();
setInterval(pollLive, 95);
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
        elif parsed.path == "/three.min.js":
            candidates = [
                pathlib.Path("/Users/arthur/gamesir-g7-se-macos/assets/three.min.js"),
                pathlib.Path(__file__).resolve().parent / "assets" / "three.min.js",
                pathlib.Path(__file__).resolve().parent.parent / "Resources" / "assets" / "three.min.js",
            ]
            found = next((c for c in candidates if c.is_file()), None)
            if found:
                data = found.read_bytes()
                self.send_response(200)
                self.send_header("Content-Type", "application/javascript; charset=utf-8")
                self.send_header("Content-Length", str(len(data)))
                self.end_headers()
                self.wfile.write(data)
            else:
                self.send_response(404)
                self.end_headers()
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
        elif self.path == "/api/rumble":
            try:
                pathlib.Path("/tmp/gamesir_rumble_test.json").write_text("1", encoding="utf-8")
            except Exception:
                pass
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
