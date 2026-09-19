from __future__ import annotations

from dataclasses import asdict, dataclass, field
from itertools import zip_longest
from pathlib import Path
from typing import Any

from .dispositivos import Computador, Roteador
from .pdu import Frame, Packet, Segment
from .rede import Topologia


MENSAGEM_42 = "Solicitacao HTTP simulada de H1 para H4..."  # 42 octetos ASCII
MENSAGEM_100 = (
    "Mensagem longa OSI para testar segmentacao e remontagem. "
    "Mensagem longa OSI para testar segmentacao "
)  # 100 octetos ASCII


@dataclass(slots=True)
class Evento:
    passo: int
    dispositivo: str
    camada: int
    acao: str
    descricao: str
    tamanho: int
    unidade: str
    blocos: list[dict[str, Any]] = field(default_factory=list)
    logicos: dict[str, str] | None = None
    fisicos: dict[str, str] | None = None
    enlace: list[str] | None = None
    caminho: list[str] | None = None
    quadro: str | None = None
    pacote: str | None = None
    fluxo: str | None = None
    status: str = "normal"

    @property
    def linha(self) -> str:
        return (
            f"{self.passo:03d} | {self.dispositivo} | L{self.camada} | "
            f"{self.acao} | {self.descricao} {self.tamanho} B"
        )

    def publico(self) -> dict[str, Any]:
        d = asdict(self)
        d["linha"] = self.linha
        return d


class SimuladorOSI:
    def __init__(self, topologia: Topologia):
        self.topologia = topologia
        p = topologia.parametros
        self.limiar_segmentacao = int(p.get("limiar_segmentacao", 64))
        self.carga_maxima_segmento = int(p.get("carga_maxima_segmento", 40))
        self.eventos: list[Evento] = []
        self._passo = 0
        self._frame_counter = 0
        self._packet_counter = 0
        self._session_counter = 0
        self.total_transmitido = 0
        self._hosts: dict[str, Computador] = {}
        self._routers: dict[str, Roteador] = {}
        for nome, dev in topologia.dispositivos.items():
            if dev["tipo"] == "host":
                self._hosts[nome] = Computador(nome, self.limiar_segmentacao, self.carga_maxima_segmento)
            elif dev["tipo"] == "router":
                self._routers[nome] = Roteador(nome)

    # ---------- utilidades ----------
    def _novo_frame(self) -> int:
        self._frame_counter += 1
        return self._frame_counter

    def _novo_pacote(self) -> int:
        self._packet_counter += 1
        return self._packet_counter

    def _nova_sessao(self) -> int:
        self._session_counter += 1
        return self._session_counter

    def _registrar(self, dispositivo: str, camada: int, acao: str, descricao: str,
                   tamanho: int, unidade: str, *, blocos=None, logicos=None,
                   fisicos=None, enlace=None, caminho=None, quadro=None,
                   pacote=None, fluxo=None, status="normal") -> Evento:
        self._passo += 1
        ev = Evento(
            self._passo, dispositivo, camada, acao, descricao, tamanho, unidade,
            blocos or [], logicos, fisicos, enlace, caminho, quadro, pacote, fluxo, status,
        )
        self.eventos.append(ev)
        return ev

    @staticmethod
    def _bloco(label: str, n: int, layer: int | None, kind="header") -> dict[str, Any]:
        return {"label": label, "bytes": n, "layer": layer, "kind": kind}

    def _layout_sessao(self, app_len: int) -> list[dict[str, Any]]:
        return [self._bloco("H5", 4, 5), self._bloco("DADOS", app_len, None, "data")]

    def _layout_carga_segmento(self, app_len: int, seq: int, payload_len: int) -> list[dict[str, Any]]:
        # A camada 5 é serializada uma vez antes da segmentação. Assim H5 aparece
        # apenas no primeiro segmento e ocupa os primeiros 4 octetos do fluxo.
        inicio = (seq - 1) * self.carga_maxima_segmento
        fim = inicio + payload_len
        out: list[dict[str, Any]] = []
        h5_ini, h5_fim = 0, 4
        overlap_h5 = max(0, min(fim, h5_fim) - max(inicio, h5_ini))
        if overlap_h5:
            out.append(self._bloco("H5", overlap_h5, 5))
        dados_ini, dados_fim = 4, 4 + app_len
        overlap_dados = max(0, min(fim, dados_fim) - max(inicio, dados_ini))
        if overlap_dados:
            out.append(self._bloco("DADOS", overlap_dados, None, "data"))
        # Para mensagens personalizadas fora da convenção, conserva qualquer byte
        # restante como carga opaca, sem atribuí-lo indevidamente a outra camada.
        usado = sum(b["bytes"] for b in out)
        if usado < payload_len:
            out.append(self._bloco("CARGA", payload_len - usado, None, "data"))
        return out

    def _layout_segmento(self, app_len: int, seg: Segment) -> list[dict[str, Any]]:
        return [self._bloco("H4", 8, 4)] + self._layout_carga_segmento(app_len, seg.sequence, len(seg.payload))

    def _layout_pacote(self, app_len: int, seg: Segment) -> list[dict[str, Any]]:
        return [self._bloco("H3", 20, 3)] + self._layout_segmento(app_len, seg)

    def _layout_quadro(self, app_len: int, seg: Segment) -> list[dict[str, Any]]:
        return [self._bloco("H2", 14, 2)] + self._layout_pacote(app_len, seg) + [self._bloco("T2", 4, 2, "trailer")]

    def _comparacao_padrao(self) -> dict[str, Any]:
        # Caso de referência com 42 B: 42+4+8+20+14+4 = 92 B por enlace.
        quadro = 42 + 4 + 8 + 20 + 14 + 4
        e1 = 42 / quadro
        e2 = 42 / (quadro * 4)
        return {
            "mensagem_referencia": 42,
            "quadro_referencia": quadro,
            "C1": {"transmitido": quadro, "eficiencia": e1, "overhead": 1 - e1},
            "C2": {"transmitido": quadro * 4, "eficiencia": e2, "overhead": 1 - e2},
        }

    def _renumerar_eventos(self):
        for i, ev in enumerate(self.eventos, 1):
            ev.passo = i
        self._passo = len(self.eventos)

    # ---------- fluxo principal ----------
    def simular(self, cenario: str, opcoes: dict[str, Any] | None = None) -> dict[str, Any]:
        opcoes = opcoes or {}
        self.eventos.clear()
        self._passo = self._frame_counter = self._packet_counter = self._session_counter = 0
        self.total_transmitido = 0

        c = cenario.upper().replace("E", "C")
        if c == "C1":
            resultado = self._cenario_c1(opcoes)
        elif c == "C2":
            resultado = self._cenario_c2(opcoes)
        elif c == "C3":
            resultado = self._cenario_c3(opcoes)
        elif c == "C4":
            resultado = self._cenario_c4(opcoes)
        elif c == "C5":
            resultado = self._cenario_c5(opcoes)
        elif c == "C6":
            resultado = self._cenario_c6(opcoes)
        elif c == "C7":
            resultado = self._cenario_c7(opcoes)
        else:
            raise ValueError(f"Cenário inválido: {cenario}")

        self._renumerar_eventos()
        dados_uteis = resultado["dados_uteis"]
        eficiencia = dados_uteis / self.total_transmitido if self.total_transmitido else 0.0
        resultado.update({
            "cenario": c,
            "eventos": [e.publico() for e in self.eventos],
            "total_transmitido": self.total_transmitido,
            "eficiencia": eficiencia,
            "overhead": 1.0 - eficiencia if self.total_transmitido else 0.0,
            "comparacao": self._comparacao_padrao(),
            "tabelas_encaminhamento": {
                r: self.topologia.tabela_encaminhamento(r, resultado.get("enlaces_indisponiveis", set()))
                for r in self._routers
            },
        })
        # conjuntos não são serializáveis e não precisam sair pela API.
        resultado.pop("enlaces_indisponiveis", None)
        return resultado

    def _cenario_c1(self, opcoes: dict[str, Any]) -> dict[str, Any]:
        msg = opcoes.get("mensagem") or MENSAGEM_42
        return self._simular_fluxo(
            origem="H1", destino_host="H2", destino_ip=self.topologia.ip_host("H2"),
            mensagem=msg, processo_origem="navegador", processo_destino="navegador2",
            porta_origem=5210, porta_destino=5211, fluxo="A",
        )

    def _cenario_c2(self, opcoes: dict[str, Any]) -> dict[str, Any]:
        msg = opcoes.get("mensagem") or MENSAGEM_42
        return self._simular_fluxo(
            origem="H1", destino_host="H4", destino_ip=self.topologia.ip_host("H4"),
            mensagem=msg, processo_origem="navegador", processo_destino="servidorWeb",
            porta_origem=5210, porta_destino=443, fluxo="A",
        )

    def _cenario_c3(self, opcoes: dict[str, Any]) -> dict[str, Any]:
        # Os dois fluxos usam o mesmo relógio de identificadores para que sessão,
        # pacote e quadro permaneçam únicos. As listas de eventos são geradas
        # separadamente e depois intercaladas, simulando concorrência.
        a = self._simular_fluxo(
            "H1", "H4", self.topologia.ip_host("H4"),
            opcoes.get("mensagem_a") or "Fluxo simultaneo de H1 para H4.",
            "navegador", "servidorWeb", 5210, 443, "A",
        )
        eventos_a = list(self.eventos)
        tx_a = self.total_transmitido

        self.eventos = []
        self._passo = 0
        self.total_transmitido = 0
        b = self._simular_fluxo(
            "H2", "H4", self.topologia.ip_host("H4"),
            opcoes.get("mensagem_b") or "Fluxo simultaneo de H2 para H4.",
            "navegador2", "servidorWeb", 5310, 443, "B",
        )
        eventos_b = list(self.eventos)
        tx_b = self.total_transmitido

        self.eventos = []
        for ea, eb in zip_longest(eventos_a, eventos_b):
            if ea is not None:
                self.eventos.append(ea)
            if eb is not None:
                self.eventos.append(eb)
        self.total_transmitido = tx_a + tx_b

        # Torna explícita a demultiplexação: os dois fluxos chegam à mesma porta
        # de servidor, mas conservam portas de origem e sessões distintas.
        for ev in self.eventos:
            if ev.dispositivo == "H4" and ev.camada == 4 and ev.acao == "RECEBE":
                ev.acao = "DEMULTIPLEXA"
                ev.descricao = "porta de destino 443 separa o fluxo e o associa à sessão correta; " + ev.descricao
        return {
            "dados_uteis": a["dados_uteis"] + b["dados_uteis"],
            "caminho": a["caminho"],
            "caminhos": {"A": a["caminho"], "B": b["caminho"]},
            "entregue": a["entregue"] and b["entregue"],
            "observacao": "Dois fluxos chegam à porta 443 e são separados pela camada 4 de H4.",
        }

    def _cenario_c4(self, opcoes: dict[str, Any]) -> dict[str, Any]:
        msg = opcoes.get("mensagem") or MENSAGEM_42
        bloqueados = {frozenset(("R1", "R4"))}
        r = self._simular_fluxo(
            "H1", "H4", self.topologia.ip_host("H4"), msg,
            "navegador", "servidorWeb", 5210, 443, "A",
            enlaces_indisponiveis=bloqueados,
        )
        r["enlaces_indisponiveis"] = bloqueados
        r["observacao"] = "Enlace R1-R4 indisponível; rota alternativa passa por R2 e tem custo 3."
        return r

    def _cenario_c5(self, opcoes: dict[str, Any]) -> dict[str, Any]:
        msg = opcoes.get("mensagem") or MENSAGEM_42
        return self._simular_fluxo(
            "H1", None, opcoes.get("destino_ip") or "10.0.9.10", msg,
            "navegador", "servidorWeb", 5210, 443, "A",
        )

    def _cenario_c6(self, opcoes: dict[str, Any]) -> dict[str, Any]:
        msg = opcoes.get("mensagem") or MENSAGEM_42
        return self._simular_fluxo(
            "H1", "H4", self.topologia.ip_host("H4"), msg,
            "navegador", "servidorWeb", 5210, 443, "A",
            enlace_erro=frozenset(("R4", "R3")),
        )

    def _cenario_c7(self, opcoes: dict[str, Any]) -> dict[str, Any]:
        msg = opcoes.get("mensagem") or MENSAGEM_100
        r = self._simular_fluxo(
            "H1", "H4", self.topologia.ip_host("H4"), msg,
            "navegador", "servidorWeb", 5210, 443, "A",
        )
        return r

    def _simular_fluxo(self, origem: str, destino_host: str | None, destino_ip: str,
                       mensagem: str, processo_origem: str, processo_destino: str,
                       porta_origem: int, porta_destino: int, fluxo: str,
                       enlaces_indisponiveis: set[frozenset[str]] | None = None,
                       enlace_erro: frozenset[str] | None = None) -> dict[str, Any]:
        bloqueados = enlaces_indisponiveis or set()
        host_o = self._hosts[origem]
        app_text = host_o.l7.descer(mensagem)
        app_bytes = app_text.encode("utf-8")
        app_len = len(app_bytes)
        sessao = self._nova_sessao()
        caminho = None
        if destino_host:
            cp = self.topologia.caminho_hosts(origem, destino_host, bloqueados)
            caminho = cp[0] if cp else None
        else:
            caminho = [origem, self.topologia.gateway_do_host(origem)]

        self._registrar(origem, 7, "GERA",
                        f"processo {processo_origem}, destino {processo_destino}", app_len,
                        "Mensagem", blocos=[self._bloco("DADOS", app_len, None, "data")],
                        caminho=caminho, fluxo=fluxo)

        cifrado = host_o.l6.descer(app_text)
        self._registrar(origem, 6, "CODIFICA",
                        "octetos UTF-8, conteúdo cifrado (XOR-5A)", len(cifrado),
                        "Mensagem", blocos=[self._bloco("D6 CIFRADO", len(cifrado), 6, "data")],
                        caminho=caminho, fluxo=fluxo)

        dados_sessao = host_o.l5.descer(cifrado, sessao)
        self._registrar(origem, 5, "ABRE",
                        f"sessão S-{sessao:04d} estabelecida", len(dados_sessao),
                        "Mensagem", blocos=self._layout_sessao(app_len), caminho=caminho, fluxo=fluxo)

        segmentos = host_o.l4.descer(dados_sessao, porta_origem, porta_destino)
        entregue = True
        for seg in segmentos:
            seg_raw = seg.to_bytes()
            self._registrar(
                origem, 4, "SEGMENTA",
                f"porta {porta_origem} → {porta_destino}, segmento {seg.sequence} de {seg.total}",
                len(seg_raw), "Segmento", blocos=self._layout_segmento(app_len, seg),
                caminho=caminho, fluxo=fluxo,
            )
            ok = self._transportar_segmento(
                origem, destino_host, destino_ip, seg, app_len, caminho, fluxo,
                bloqueados, enlace_erro,
            )
            if not ok:
                entregue = False
                break

        # As camadas 5-7 de destino só são acionadas quando todos os segmentos foram
        # entregues e remontados pela camada 4.
        if entregue and destino_host:
            host_d = self._hosts[destino_host]
            # A remontagem já aconteceu dentro de _transportar_segmento; a última
            # carga completa fica guardada nesta variável de instância temporária.
            completo = getattr(self, "_ultimo_reassemblado", None)
            if completo is not None:
                sid, cifrado_dest = host_d.l5.subir(completo)
                self._registrar(destino_host, 5, "ENCERRA",
                                f"sessão S-{sid:04d} encerrada; cabeçalho H5 removido",
                                len(cifrado_dest), "Mensagem",
                                blocos=[self._bloco("D6 CIFRADO", len(cifrado_dest), 6, "data")],
                                caminho=caminho, fluxo=fluxo)
                texto = host_d.l6.subir(cifrado_dest)
                self._registrar(destino_host, 6, "DECODIFICA",
                                "conteúdo decifrado somente na camada 6 do destino; UTF-8 restaurado",
                                len(cifrado_dest), "Mensagem",
                                blocos=[self._bloco("DADOS", len(cifrado_dest), None, "data")],
                                caminho=caminho, fluxo=fluxo)
                host_d.l7.subir(texto)
                self._registrar(destino_host, 7, "ENTREGA",
                                f"mensagem entregue ao processo {processo_destino}",
                                len(texto.encode("utf-8")), "Mensagem",
                                blocos=[self._bloco("DADOS", len(texto.encode('utf-8')), None, "data")],
                                caminho=caminho, fluxo=fluxo, status="success")
        return {
            "dados_uteis": app_len,
            "caminho": caminho,
            "entregue": entregue and destino_host is not None,
            "segmentos": [len(s.payload) for s in segmentos],
            "segmentos_totais": [len(s.to_bytes()) for s in segmentos],
            "sessao": f"S-{sessao:04d}",
        }

    def _transportar_segmento(self, origem: str, destino_host: str | None, destino_ip: str,
                              seg: Segment, app_len: int, caminho: list[str] | None,
                              fluxo: str, bloqueados: set[frozenset[str]],
                              enlace_erro: frozenset[str] | None) -> bool:
        host_o = self._hosts[origem]
        src_ip = self.topologia.ip_host(origem)
        packet_id = self._novo_pacote()
        packet = host_o.l3.descer(seg.to_bytes(), src_ip, destino_ip, packet_id)
        raw_packet = packet.to_bytes()
        logicos = {"origem": src_ip, "destino": destino_ip}
        self._registrar(origem, 3, "ENCAPSULA",
                        f"{src_ip} → {destino_ip}; pacote P{packet_id}", len(raw_packet),
                        "Pacote", blocos=self._layout_pacote(app_len, seg), logicos=logicos,
                        caminho=caminho, pacote=f"P{packet_id}", fluxo=fluxo)

        # Primeiro salto escolhido pela camada 3 do host.
        if destino_host and self.topologia.hosts_mesma_rede(origem, destino_host):
            proximo = destino_host
            iface = self.topologia.interfaces(origem)[0]
            desc = f"destino na rede local; entrega direta a {destino_host} pela interface {iface.nome}"
        else:
            proximo = self.topologia.gateway_do_host(origem)
            iface = self.topologia.interfaces(origem)[0]
            desc = f"próximo salto {self.topologia.interface_recebedora(proximo, origem).ip} pela interface {iface.nome}"
        self._registrar(origem, 3, "ROTEIA", desc, len(raw_packet), "Pacote",
                        blocos=self._layout_pacote(app_len, seg), logicos=logicos,
                        caminho=caminho, pacote=f"P{packet_id}", fluxo=fluxo)

        atual = origem
        while True:
            # A camada 2 recebe da camada 3 apenas o próximo vizinho escolhido.
            intf_saida = self.topologia.interface_para(atual, proximo)
            if self.topologia.tipo(proximo) == "host":
                intf_dest = self.topologia.interfaces(proximo)[0]
            else:
                intf_dest = self.topologia.interface_recebedora(proximo, atual)
            frame_id = self._novo_frame()
            quadro = (self._hosts[atual].l2 if self.topologia.tipo(atual) == "host" else self._routers[atual].l2).descer(
                raw_packet, intf_saida.mac, intf_dest.mac, frame_id
            )
            raw_frame = quadro.to_bytes()
            fisicos = {"origem": intf_saida.mac, "destino": intf_dest.mac}
            qnome = f"Q{frame_id}"
            self._registrar(atual, 2, "ENQUADRA",
                            f"{intf_saida.mac} → {intf_dest.mac}, quadro {qnome}", len(raw_frame),
                            "Quadro", blocos=self._layout_quadro(app_len, seg), logicos=logicos,
                            fisicos=fisicos, enlace=[atual, proximo], caminho=caminho,
                            quadro=qnome, pacote=f"P{packet_id}", fluxo=fluxo)

            # L1 transmite. O quadro é serializado em bits; o projeto contabiliza os
            # octetos do quadro, sem preâmbulo adicional na convenção de custos.
            self._registrar(atual, 1, "TRANSMITE",
                            f"{len(raw_frame) * 8} bits no enlace {atual}–{proximo}", len(raw_frame),
                            "Bit", blocos=self._layout_quadro(app_len, seg), logicos=logicos,
                            fisicos=fisicos, enlace=[atual, proximo], caminho=caminho,
                            quadro=qnome, pacote=f"P{packet_id}", fluxo=fluxo)
            self.total_transmitido += len(raw_frame)

            wire = raw_frame
            erro_neste_enlace = enlace_erro is not None and frozenset((atual, proximo)) == enlace_erro
            if erro_neste_enlace and len(wire) > Frame.HEADER_SIZE + Frame.TRAILER_SIZE:
                mut = bytearray(wire)
                mut[Frame.HEADER_SIZE] ^= 0x01  # altera um único bit da carga
                wire = bytes(mut)

            # receptor L1
            self._registrar(proximo, 1, "RECEBE",
                            f"{len(wire) * 8} bits do enlace {atual}–{proximo}" + ("; um bit foi alterado" if erro_neste_enlace else ""),
                            len(wire), "Bit", blocos=self._layout_quadro(app_len, seg), logicos=logicos,
                            fisicos=fisicos, enlace=[atual, proximo], caminho=caminho,
                            quadro=qnome, pacote=f"P{packet_id}", fluxo=fluxo,
                            status="error" if erro_neste_enlace else "normal")

            recebido = Frame.from_bytes(wire, frame_id)
            camada2_dest = self._hosts[proximo].l2 if self.topologia.tipo(proximo) == "host" else self._routers[proximo].l2
            pacote_bytes = camada2_dest.subir(recebido)
            if pacote_bytes is None:
                self._registrar(proximo, 2, "DESCARTA",
                                f"verificação de erro inconsistente; quadro {qnome} descartado e nenhuma camada superior é acionada",
                                len(wire), "Quadro", blocos=self._layout_quadro(app_len, seg),
                                logicos=logicos, fisicos=fisicos, enlace=[atual, proximo], caminho=caminho,
                                quadro=qnome, pacote=f"P{packet_id}", fluxo=fluxo, status="error")
                return False

            self._registrar(proximo, 2, "DESENQUADRA",
                            f"verificação de erro correta, quadro {qnome} descartado",
                            len(pacote_bytes), "Pacote", blocos=self._layout_pacote(app_len, seg),
                            logicos=logicos, fisicos=fisicos, enlace=[atual, proximo], caminho=caminho,
                            quadro=qnome, pacote=f"P{packet_id}", fluxo=fluxo)

            recebido_pacote = Packet.from_bytes(pacote_bytes)
            # Se chegou ao host final, L3 remove H3 e entrega à L4.
            if self.topologia.tipo(proximo) == "host":
                if recebido_pacote.dst_ip != self.topologia.ip_host(proximo):
                    self._registrar(proximo, 3, "DESCARTA",
                                    f"IP de destino {recebido_pacote.dst_ip} não pertence a {proximo}",
                                    len(pacote_bytes), "Pacote", blocos=self._layout_pacote(app_len, seg),
                                    logicos=logicos, fisicos=fisicos, caminho=caminho,
                                    pacote=f"P{packet_id}", fluxo=fluxo, status="error")
                    return False
                seg_bytes = self._hosts[proximo].l3.subir(recebido_pacote)
                seg_dest = Segment.from_bytes(seg_bytes)
                self._registrar(proximo, 3, "DESENCAPSULA",
                                f"destino lógico confirmado; H3 removido do pacote P{packet_id}",
                                len(seg_bytes), "Segmento", blocos=self._layout_segmento(app_len, seg_dest),
                                logicos=logicos, fisicos=fisicos, caminho=caminho,
                                pacote=f"P{packet_id}", fluxo=fluxo)
                completo = self._hosts[proximo].l4.subir(seg_dest)
                desc = f"porta {seg_dest.dst_port}, segmento {seg_dest.sequence} de {seg_dest.total} recebido"
                if completo is None:
                    desc += "; aguardando os demais segmentos"
                    tam = len(seg_dest.payload)
                    blocos = self._layout_carga_segmento(app_len, seg_dest.sequence, len(seg_dest.payload))
                else:
                    desc += "; todos os segmentos remontados em ordem"
                    tam = len(completo)
                    blocos = self._layout_sessao(app_len)
                    self._ultimo_reassemblado = completo
                self._registrar(proximo, 4, "RECEBE", desc, tam, "Mensagem" if completo is not None else "Segmento",
                                blocos=blocos, logicos=logicos, fisicos=fisicos, caminho=caminho,
                                pacote=f"P{packet_id}", fluxo=fluxo,
                                status="success" if completo is not None else "normal")
                return True

            # Nó intermediário: somente L1-L3 existem no objeto Roteador.
            roteador = self._routers[proximo]
            rota = self.topologia.proximo_salto_para_ip(proximo, recebido_pacote.dst_ip, bloqueados)
            if rota is None:
                self._registrar(proximo, 3, "DESCARTA",
                                f"nenhuma rota para {recebido_pacote.dst_ip}; pacote P{packet_id} descartado",
                                len(pacote_bytes), "Pacote", blocos=self._layout_pacote(app_len, seg),
                                logicos=logicos, fisicos=fisicos, caminho=caminho,
                                pacote=f"P{packet_id}", fluxo=fluxo, status="error")
                return False
            novo_proximo, custo, iface_nome = rota
            rede_nome = self.topologia.rede_do_ip(recebido_pacote.dst_ip)
            prefixo = str(self.topologia.redes[rede_nome]) if rede_nome else recebido_pacote.dst_ip
            via = novo_proximo if self.topologia.tipo(novo_proximo) == "router" else "direto"
            self._registrar(proximo, 3, "ROTEIA",
                            f"{prefixo} via {via}, custo {custo}, interface {iface_nome}",
                            len(pacote_bytes), "Pacote", blocos=self._layout_pacote(app_len, seg),
                            logicos=logicos, fisicos=fisicos, caminho=caminho,
                            pacote=f"P{packet_id}", fluxo=fluxo)
            # R2: o quadro recebido não é reescrito. pacote_bytes permanece idêntico;
            # no próximo ciclo será criado um novo Frame com novo frame_id/MAC.
            raw_packet = pacote_bytes
            atual, proximo = proximo, novo_proximo
