import http.server, json, locale, pathlib, socketserver, threading, urllib.parse, webbrowser

CONFIG_PATH = pathlib.Path(__file__).parent / "profiles.json"

UI_STRINGS = {
    "pt": {
        "title": "GameSir Bridge Config v4.0",
        "profile": "Perfil:",
        "lang": "Idioma:",
        "auto": "Auto-trocar perfil por app",
        "rumble": "Vibrar ao conectar/trocar",
        "buttons": "Botões do Perfil",
        "btn_lbl": "Botão",
        "rules": "Regras de Apps (Auto-Foco)",
        "new_app": "Nome do app (ex: dolphin)",
        "new_prof": "Perfil (ex: emulators)",
        "combos": "Combos / Macros",
        "new_combo": "Botões (ex: LB+RB)",
        "new_macro": "Atalho (ex: cmd+shift+3)",
        "save": "Salvar Todas as Alterações"
    },
    "en": {
        "title": "GameSir Bridge Config v4.0",
        "profile": "Profile:",
        "lang": "Language:",
        "auto": "Auto-switch profile per app",
        "rumble": "Vibrate on connect/switch",
        "buttons": "Profile Buttons",
        "btn_lbl": "Button",
        "rules": "App Rules (Auto-Focus)",
        "new_app": "App name (e.g. dolphin)",
        "new_prof": "Profile (e.g. emulators)",
        "combos": "Combos / Macros",
        "new_combo": "Buttons (e.g. LB+RB)",
        "new_macro": "Shortcut (e.g. cmd+shift+3)",
        "save": "Save All Changes"
    },
    "es": {
        "title": "GameSir Bridge Config v4.0",
        "profile": "Perfil:",
        "lang": "Idioma:",
        "auto": "Cambiar perfil automáticamente por app",
        "rumble": "Vibrar al conectar/cambiar",
        "buttons": "Botones del Perfil",
        "btn_lbl": "Botón",
        "rules": "Reglas de Apps (Auto-Enfoque)",
        "new_app": "Nombre de la app (ej: dolphin)",
        "new_prof": "Perfil (ej: emulators)",
        "combos": "Combos / Macros",
        "new_combo": "Botones (ej: LB+RB)",
        "new_macro": "Atajo (ej: cmd+shift+3)",
        "save": "Guardar Todos los Cambios"
    }
}

HTML = """<!DOCTYPE html><html><head><meta charset="utf-8"><title>__TITLE__</title>
<style>body{font-family:-apple-system,sans-serif;max-width:560px;margin:24px auto;background:#1c1c1e;color:#fff;padding:20px}
h3{margin-top:24px;border-bottom:1px solid #3a3a3c;padding-bottom:6px;color:#30d158}
select,input,button{padding:8px;border-radius:6px;border:1px solid #444;background:#2c2c2e;color:#fff;font-size:14px}
.row{display:flex;justify-content:space-between;margin:8px 0;align-items:center;gap:8px}
button{background:#30d158;color:#000;font-weight:bold;cursor:pointer;width:100%;margin-top:20px;padding:12px}</style></head>
<body><h2>__TITLE__</h2><form method="POST">
<div class="row"><label>__LANG_LBL__</label><select name="language" onchange="location.href='/?p=__CUR_PROF__&l='+this.value">__LANG_OPTS__</select></div>
<div class="row"><label>__PROF_LBL__</label><select name="profile" onchange="location.href='/?p='+this.value+'&l=__CUR_LANG__'">__OPTS__</select></div>
<div class="row"><label><input type="checkbox" name="auto" __AUTO__> __AUTO_LBL__</label></div>
<div class="row"><label><input type="checkbox" name="rumble" __RUMBLE__> __RUMBLE_LBL__</label></div>
<h3>__BTNS_H__</h3>__FIELDS__
<h3>__RULES_H__</h3>__RULES__
<div class="row"><input name="new_app" placeholder="__NEW_APP__"><input name="new_app_prof" placeholder="__NEW_PROF__"></div>
<h3>__COMBOS_H__</h3>__COMBOS__
<div class="row"><input name="new_combo" placeholder="__NEW_COMBO__"><input name="new_macro" placeholder="__NEW_MACRO__"></div>
<button type="submit">__SAVE__</button></form></body></html>"""

def get_lang(data, qs=None):
    if qs and "l" in qs and qs["l"][0] in UI_STRINGS:
        return qs["l"][0]
    if data.get("language") in UI_STRINGS:
        return data["language"]
    loc = (locale.getdefaultlocale()[0] or "en").lower()
    if loc.startswith("pt"): return "pt"
    if loc.startswith("es"): return "es"
    return "en"

class Handler(http.server.BaseHTTPRequestHandler):
    def log_message(self, *args): pass
    def do_GET(self):
        data = json.loads(CONFIG_PATH.read_text(encoding="utf-8"))
        qs = urllib.parse.parse_qs(urllib.parse.urlparse(self.path).query)
        lang = get_lang(data, qs)
        t = UI_STRINGS[lang]
        prof = qs.get("p", [data["active_profile"]])[0]
        if prof not in data["profiles"]: prof = data["active_profile"]
        opts = "".join(f'<option value="{k}" {"selected" if k==prof else ""}>{k}</option>' for k in data["profiles"])
        lang_opts = "".join(f'<option value="{c}" {"selected" if c==lang else ""}>{lbl}</option>' for c, lbl in [("pt","Português"),("en","English"),("es","Español")])
        fields = "".join(f'<div class="row"><span>{t["btn_lbl"]} <b>{b}</b></span><input name="btn_{b}" value="{v}"></div>' for b, v in data["profiles"][prof]["buttons"].items())
        rules = "".join(f'<div class="row"><input name="rule_k_{i}" value="{k}"><input name="rule_v_{i}" value="{v}"></div>' for i, (k, v) in enumerate(data.get("app_rules", {}).items()))
        combos = "".join(f'<div class="row"><input name="cmb_k_{i}" value="{k}"><input name="cmb_v_{i}" value="{v}"></div>' for i, (k, v) in enumerate(data.get("combos", {}).items()))
        page = (HTML
            .replace("__TITLE__", t["title"]).replace("__LANG_LBL__", t["lang"]).replace("__LANG_OPTS__", lang_opts)
            .replace("__PROF_LBL__", t["profile"]).replace("__CUR_PROF__", prof).replace("__CUR_LANG__", lang)
            .replace("__OPTS__", opts).replace("__AUTO_LBL__", t["auto"]).replace("__RUMBLE_LBL__", t["rumble"])
            .replace("__BTNS_H__", t["buttons"]).replace("__FIELDS__", fields)
            .replace("__RULES_H__", t["rules"]).replace("__RULES__", rules).replace("__NEW_APP__", t["new_app"]).replace("__NEW_PROF__", t["new_prof"])
            .replace("__COMBOS_H__", t["combos"]).replace("__COMBOS__", combos).replace("__NEW_COMBO__", t["new_combo"]).replace("__NEW_MACRO__", t["new_macro"])
            .replace("__SAVE__", t["save"])
            .replace("__AUTO__", "checked" if data.get("auto_switch", True) else "")
            .replace("__RUMBLE__", "checked" if data.get("rumble_feedback", True) else "")
        )
        self.send_response(200); self.send_header("Content-type", "text/html; charset=utf-8"); self.end_headers()
        self.wfile.write(page.encode("utf-8"))

    def do_POST(self):
        length = int(self.headers["Content-Length"])
        form = urllib.parse.parse_qs(self.rfile.read(length).decode("utf-8"), keep_blank_values=True)
        data = json.loads(CONFIG_PATH.read_text(encoding="utf-8"))
        lang = form.get("language", [get_lang(data)])[0]
        if lang in UI_STRINGS: data["language"] = lang
        prof = form.get("profile", [data["active_profile"]])[0]
        data["active_profile"] = prof
        data["auto_switch"] = "auto" in form
        data["rumble_feedback"] = "rumble" in form
        for k, v in form.items():
            if k.startswith("btn_"):
                data["profiles"][prof]["buttons"][k[4:]] = v[0].strip()
        new_rules = {}
        for k, v in form.items():
            if k.startswith("rule_k_") and v[0].strip():
                idx = k[7:]
                val = form.get(f"rule_v_{idx}", [""])[0].strip()
                if val: new_rules[v[0].strip().lower()] = val
        if form.get("new_app", [""])[0].strip() and form.get("new_app_prof", [""])[0].strip():
            new_rules[form["new_app"][0].strip().lower()] = form["new_app_prof"][0].strip()
        data["app_rules"] = new_rules
        new_combos = {}
        for k, v in form.items():
            if k.startswith("cmb_k_") and v[0].strip():
                idx = k[6:]
                val = form.get(f"cmb_v_{idx}", [""])[0].strip()
                if val: new_combos[v[0].strip()] = val
        if form.get("new_combo", [""])[0].strip() and form.get("new_macro", [""])[0].strip():
            new_combos[form["new_combo"][0].strip()] = form["new_macro"][0].strip()
        data["combos"] = new_combos
        CONFIG_PATH.write_text(json.dumps(data, indent=2), encoding="utf-8")
        self.send_response(303); self.send_header("Location", f"/?p={prof}&l={lang}"); self.end_headers()

if __name__ == "__main__":
    with socketserver.TCPServer(("127.0.0.1", 0), Handler) as httpd:
        port = httpd.server_address[1]
        threading.Timer(0.2, lambda: webbrowser.open(f"http://127.0.0.1:{port}")).start()
        httpd.serve_forever()
