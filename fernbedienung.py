#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Handy-Fernbedienung für die Präsentation „Daten zum Sprechen bringen“.

Start (im Ordner Kolloquium/):   python3 fernbedienung.py
  Laptop:  die angezeigte Präsentations-Adresse öffnen
  Handy:   die angezeigte /remote-Adresse öffnen (gleiches WLAN oder Handy-Hotspot)

Nur Python-Standardbibliothek, kein Internet nötig. Beenden mit Strg+C.
Hinweis: keine Authentifizierung – wer die Adresse im lokalen Netz kennt,
kann blättern. Für den Vortrag unkritisch, danach Server einfach beenden.
"""
import json
import os
import socket
import threading
from functools import partial
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, unquote, urlparse

PORT = 8765

_lock = threading.Lock()
_commands = []  # Liste von (laufende_nr, "next"|"prev"|"home"|"end")
_status = {"page": "–", "total": "–", "notes": ""}

REMOTE_PAGE = """<!DOCTYPE html>
<html lang="de"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1,maximum-scale=1,user-scalable=no">
<title>Fernbedienung · Daten zum Sprechen bringen</title>
<style>
*{box-sizing:border-box;margin:0;padding:0;-webkit-tap-highlight-color:transparent}
html,body{height:100%}
body{font-family:-apple-system,"Segoe UI",Roboto,sans-serif;background:#0b1020;color:#e2e8f0;
  display:flex;flex-direction:column;padding:14px;gap:12px;touch-action:manipulation;
  user-select:none;-webkit-user-select:none}
header{text-align:center;padding:2px 0}
header .t{font-size:12px;letter-spacing:.14em;text-transform:uppercase;color:#818cf8;font-weight:700}
header .p{font-size:32px;font-weight:800;margin-top:2px;font-variant-numeric:tabular-nums}
.row{display:flex;gap:12px;flex:3;min-height:32vh}
button{border:none;border-radius:18px;color:#fff;font-weight:800;cursor:pointer}
.prev{flex:1;background:#1e293b;font-size:44px}
.next{flex:2;background:#4f46e5;font-size:56px;box-shadow:0 12px 30px -10px rgba(79,70,229,.7)}
button:active{transform:scale(.97);filter:brightness(1.15)}
.small{display:flex;gap:10px}
.small button{flex:1;background:#1e293b;color:#94a3b8;font-size:14px;font-weight:700;padding:12px;border-radius:12px}
.notes{flex:2;background:#0f172a;border:1px solid #1e293b;border-radius:14px;padding:12px 14px;
  font-size:15.5px;line-height:1.55;color:#cbd5e1;overflow:auto;min-height:18vh}
.notes .lbl{font-size:10.5px;letter-spacing:.14em;text-transform:uppercase;color:#818cf8;font-weight:800;margin-bottom:6px}
footer{font-size:11.5px;color:#475569;text-align:center;padding-bottom:4px}
.off{color:#f87171}
</style></head><body>
<header><div class="t">Fernbedienung</div><div class="p" id="page">– / –</div></header>
<div class="row">
  <button class="prev" id="prev" aria-label="zurück">‹</button>
  <button class="next" id="next" aria-label="weiter">›</button>
</div>
<div class="small"><button id="home">⏮ Titel</button><button id="end">Ende ⏭</button></div>
<div class="notes"><div class="lbl">Sprechernotizen</div><div id="notes">—</div></div>
<footer id="foot">verbinde …</footer>
<script>
function cmd(c){ fetch("cmd?c="+c).catch(function(){}); }
["prev","next","home","end"].forEach(function(id){
  document.getElementById(id).addEventListener("click", function(){ cmd(id); });
});
function tick(){
  fetch("state").then(function(r){ return r.json(); }).then(function(s){
    document.getElementById("page").textContent = s.page + " / " + s.total;
    document.getElementById("notes").textContent = s.notes || "—";
    var f = document.getElementById("foot");
    f.textContent = "verbunden · Tipp: Bildschirmsperre für den Vortrag ausschalten";
    f.classList.remove("off");
  }).catch(function(){
    var f = document.getElementById("foot");
    f.textContent = "keine Verbindung – läuft der Server noch?";
    f.classList.add("off");
  });
}
setInterval(tick, 1000); tick();
</script></body></html>
"""


class Handler(SimpleHTTPRequestHandler):
    def log_message(self, *args):  # Konsole ruhig halten
        pass

    def _send(self, data, ctype):
        body = data.encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", ctype + "; charset=utf-8")
        self.send_header("Cache-Control", "no-store")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        u = urlparse(self.path)
        q = parse_qs(u.query)
        if u.path.rstrip("/") == "/remote":
            self._send(REMOTE_PAGE, "text/html")
            return
        if u.path == "/cmd":
            c = (q.get("c") or [""])[0]
            if c in ("next", "prev", "home", "end"):
                with _lock:
                    _commands.append((len(_commands) + 1, c))
            self._send('{"ok":true}', "application/json")
            return
        if u.path == "/poll":
            since = int((q.get("since") or ["0"])[0])
            with _lock:
                if "page" in q:
                    _status["page"] = q["page"][0]
                    _status["total"] = (q.get("total") or ["?"])[0]
                    _status["notes"] = unquote((q.get("notes") or [""])[0])
                pending = [c for i, c in _commands if i > since]
                seq = len(_commands)
            self._send(json.dumps({"seq": seq, "cmds": pending}), "application/json")
            return
        if u.path == "/state":
            with _lock:
                snapshot = dict(_status)
            self._send(json.dumps(snapshot), "application/json")
            return
        super().do_GET()  # statische Dateien (Präsentation, Material …)


def local_addresses():
    addrs = set()
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect(("192.0.2.1", 80))  # kein Paketversand nötig, nur Routenwahl
        addrs.add(s.getsockname()[0])
        s.close()
    except OSError:
        pass
    try:
        for info in socket.getaddrinfo(socket.gethostname(), None, socket.AF_INET):
            ip = info[4][0]
            if not ip.startswith("127."):
                addrs.add(ip)
    except OSError:
        pass
    return sorted(addrs)


def main():
    here = os.path.dirname(os.path.abspath(__file__))
    handler = partial(Handler, directory=here)
    try:
        server = ThreadingHTTPServer(("0.0.0.0", PORT), handler)
    except OSError:
        print(f"Port {PORT} ist belegt – läuft der Server schon? (Beenden mit Strg+C)")
        return

    host = socket.gethostname()
    mdns = host if host.endswith(".local") else host + ".local"
    print("─" * 64)
    print("Fernbedienung läuft. Beenden mit Strg+C.")
    print()
    print(f"  Laptop (Präsentation):  http://localhost:{PORT}/01_Praesentation.html?remote=1")
    print()
    print("  Handy (Fernbedienung) – eine der Adressen im Browser öffnen:")
    print(f"    http://{mdns}:{PORT}/remote")
    for ip in local_addresses():
        print(f"    http://{ip}:{PORT}/remote")
    print()
    print("  Voraussetzung: Laptop und Handy im selben WLAN")
    print("  (am zuverlässigsten: Hotspot des Handys – Internet ist nicht nötig).")
    print("─" * 64, flush=True)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nServer beendet.")


if __name__ == "__main__":
    main()
