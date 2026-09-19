from __future__ import annotations

from http.server import ThreadingHTTPServer, SimpleHTTPRequestHandler
from pathlib import Path
import json
import sys
import os
import threading
import urllib.parse
import webbrowser

from simulador.rede import Topologia
from simulador.simulador import SimuladorOSI, MENSAGEM_42, MENSAGEM_100


SOURCE_DIR = Path(__file__).resolve().parent
EXEC_DIR = Path(sys.executable).resolve().parent if getattr(sys, "frozen", False) else SOURCE_DIR
RESOURCE_DIR = Path(getattr(sys, "_MEIPASS", SOURCE_DIR))
WEB_DIR = RESOURCE_DIR / "web"
TOPOLOGIA = EXEC_DIR / "topologia.json"


CENARIOS = [
    {"id": "C1", "nome": "C1/E1 - Entrega direta", "descricao": "H1 envia para H2 na Rede A; um único quadro e nenhum roteador."},
    {"id": "C2", "nome": "C2/E2 - Entrega indireta", "descricao": "H1:5210 (navegador) envia 42 B para H4:443 (servidorWeb) por R1-R4-R3."},
    {"id": "C3", "nome": "C3/E3 - Demultiplexação", "descricao": "H1 e H2 enviam fluxos concorrentes para a porta 443 de H4."},
    {"id": "C4", "nome": "C4/E4 - Falha de enlace", "descricao": "R1-R4 é derrubado; o caminho alternativo passa por R2, custo 3."},
    {"id": "C5", "nome": "C5/E5 - Destino inalcançável", "descricao": "H1 envia para 10.0.9.10; R1 descarta o pacote por ausência de rota."},
    {"id": "C6", "nome": "C6/E6 - Erro de transmissão", "descricao": "Um bit é alterado em R4-R3; R3/L2 descarta o quadro sem acionar L3."},
    {"id": "C7", "nome": "C7/E7 - Mensagem longa", "descricao": "100 B úteis + H5 formam 104 B e geram cargas de 40, 40 e 24 B."},
]


class Handler(SimpleHTTPRequestHandler):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, directory=str(WEB_DIR), **kwargs)

    def log_message(self, fmt, *args):
        # O executável usa pythonw.exe; evita depender de console.
        pass

    def _json(self, data, status=200):
        raw = json.dumps(data, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(raw)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(raw)

    def do_GET(self):
        path = urllib.parse.urlparse(self.path).path
        if path == "/api/health":
            return self._json({"ok": True})
        if path == "/api/topology":
            try:
                topo = Topologia.carregar(TOPOLOGIA)
                return self._json(topo.dados_publicos())
            except Exception as exc:
                return self._json({"erro": f"Falha ao carregar topologia.json: {exc}"}, 500)
        if path == "/api/scenarios":
            return self._json({
                "cenarios": CENARIOS,
                "mensagem_42": MENSAGEM_42,
                "mensagem_100": MENSAGEM_100,
            })
        return super().do_GET()

    def do_POST(self):
        path = urllib.parse.urlparse(self.path).path
        try:
            length = int(self.headers.get("Content-Length", "0"))
            body = self.rfile.read(length) if length else b"{}"
            data = json.loads(body.decode("utf-8"))
        except Exception as exc:
            return self._json({"erro": f"JSON inválido: {exc}"}, 400)

        if path == "/api/simulate":
            try:
                topo = Topologia.carregar(TOPOLOGIA)
                sim = SimuladorOSI(topo)
                resultado = sim.simular(data.get("cenario", "C2"), data.get("opcoes") or {})
                return self._json(resultado)
            except Exception as exc:
                return self._json({"erro": str(exc)}, 400)
        if path == "/api/shutdown":
            self._json({"ok": True, "mensagem": "Servidor encerrando."})
            threading.Thread(target=self.server.shutdown, daemon=True).start()
            return
        return self._json({"erro": "Endpoint inexistente"}, 404)


class Server(ThreadingHTTPServer):
    daemon_threads = True
    allow_reuse_address = True


def main():
    # Porta 0 deixa o Windows escolher uma porta local livre, evitando conflito.
    server = Server(("127.0.0.1", int(os.environ.get("SIMULADOR_PORT", "0"))), Handler)
    port = server.server_address[1]
    url = f"http://127.0.0.1:{port}/"
    try:
        (EXEC_DIR / "simulador_url.txt").write_text(url, encoding="utf-8")
    except OSError:
        pass
    if os.environ.get("SIMULADOR_NO_BROWSER") != "1":
        threading.Timer(0.35, lambda: webbrowser.open(url)).start()
    try:
        server.serve_forever()
    finally:
        server.server_close()


if __name__ == "__main__":
    try:
        main()
    except Exception as exc:
        try:
            (EXEC_DIR / "simulador_erro.log").write_text(
                f"Falha ao iniciar o Simulador OSI: {exc}\n", encoding="utf-8"
            )
        finally:
            raise
