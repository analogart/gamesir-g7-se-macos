import http.server, json, pathlib, socketserver, urllib.parse, webbrowser

CONFIG_PATH = pathlib.Path(__file__).parent / "profiles.json"

HTML = """<!DOCTYPE html><html><head><meta charset="utf-8"><title>GameSir Config v4.0</title>
<style>body{font-family:-apple-system,sans-serif;max-width:560px;margin:24px auto;background:#1c1c1e;color:#fff;padding:20px}
h3{margin-top:24px;border-bottom:1px solid #3a3a3c;padding-bottom:6px;color:#30d158}
select,input,button{padding:8px;border-radius:6px;border:1px solid #444;background:#2c2c2e;color:#fff;font-size:14px}
.row{display:flex;justify-content:space-between;margin:8px 0;align-items:center;gap:8px}
button{background:#30d158;color:#000;font-weight:bold;cursor:pointer;width:100%;margin-top:20px;padding:12px}</style></head>
<body><h2>🎮 GameSir Bridge Config v4.0</h2><form method="POST">
<div class="row"><label>Perfil:</label><select name="profile" onchange="location.href='/?p='+this.value">__OPTS__</select></div>
<div class="row"><label><input type="checkbox" name="auto" __AUTO__> Auto-trocar perfil por app</label></div>
<div class="row"><label><input type="checkbox" name="rumble" __RUMBLE__> Vibrar ao conectar/trocar</label></div>
<h3>Botoes do Perfil</h3>__FIELDS__
<h3>Regras de Apps (Auto-Foco)</h3>__RULES__
<div class="row"><input name="new_app" placeholder="Nome do app (ex: dolphin)"><input name="new_app_prof" placeholder="Perfil (ex: emulators)"></div>
<h3>Combos / Macros</h3>__COMBOS__
<div class="row"><input name="new_combo" placeholder="Botoes (ex: LB+RB)"><input name="new_macro" placeholder="Atalho (ex: cmd+shift+3)"></div>
<button type="submit">Salvar Todas as Alteracoes</button></form></body></html>"""

class Handler(http.server.BaseHTTPRequestHandler):
    def log_message(self, *args): pass
    def do_GET(self):
        data = json.loads(CONFIG_PATH.read_text(encoding="utf-8"))
        qs = urllib.parse.parse_qs(urllib.parse.urlparse(self.path).query)
        prof = qs.get("p", [data["active_profile"]])[0]
        if prof not in data["profiles"]: prof = data["active_profile"]
        opts = "".join(f'<option value="{k}" {"selected" if k==prof else ""}>{k}</option>' for k in data["profiles"])
        fields = "".join(f'<div class="row"><span>Botao <b>{b}</b></span><input name="btn_{b}" value="{v}"></div>' for b, v in data["profiles"][prof]["buttons"].items())
        rules = "".join(f'<div class="row"><input name="rule_k_{i}" value="{k}"><input name="rule_v_{i}" value="{v}"></div>' for i, (k, v) in enumerate(data.get("app_rules", {}).items()))
        combos = "".join(f'<div class="row"><input name="cmb_k_{i}" value="{k}"><input name="cmb_v_{i}" value="{v}"></div>' for i, (k, v) in enumerate(data.get("combos", {}).items()))
        page = HTML.replace("__OPTS__", opts).replace("__FIELDS__", fields).replace("__RULES__", rules).replace("__COMBOS__", combos)
        page = page.replace("__AUTO__", "checked" if data.get("auto_switch", True) else "")
        page = page.replace("__RUMBLE__", "checked" if data.get("rumble_feedback", True) else "")
        self.send_response(200); self.send_header("Content-type", "text/html; charset=utf-8"); self.end_headers()
        self.wfile.write(page.encode("utf-8"))

    def do_POST(self):
        length = int(self.headers["Content-Length"])
        form = urllib.parse.parse_qs(self.rfile.read(length).decode("utf-8"), keep_blank_values=True)
        data = json.loads(CONFIG_PATH.read_text(encoding="utf-8"))
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
                if val: new_combos[v[0].strip().upper()] = val
        if form.get("new_combo", [""])[0].strip() and form.get("new_macro", [""])[0].strip():
            new_combos[form["new_combo"][0].strip().upper()] = form["new_macro"][0].strip()
        data["combos"] = new_combos

        CONFIG_PATH.write_text(json.dumps(data, indent=2), encoding="utf-8")
        self.send_response(303); self.send_header("Location", f"/?p={prof}"); self.end_headers()

if __name__ == "__main__":
    with socketserver.TCPServer(("127.0.0.1", 0), Handler) as httpd:
        port = httpd.server_address[1]
        webbrowser.open(f"http://127.0.0.1:{port}")
        httpd.serve_forever()
