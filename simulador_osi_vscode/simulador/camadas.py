from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, Tuple

from .pdu import Frame, Packet, Segment, SessionMessage


class Camada7Aplicacao:
    numero = 7
    nome = "Aplicação"

    def descer(self, texto: str) -> str:
        return texto

    def subir(self, texto: str) -> str:
        return texto


class Camada6Apresentacao:
    numero = 6
    nome = "Apresentação"
    CODIFICACAO = "UTF-8"
    CIFRA = "XOR-5A"
    _CHAVE = 0x5A

    def descer(self, texto: str) -> bytes:
        bruto = texto.encode("utf-8")
        return bytes(b ^ self._CHAVE for b in bruto)

    def subir(self, cifrado: bytes) -> str:
        bruto = bytes(b ^ self._CHAVE for b in cifrado)
        return bruto.decode("utf-8")


class Camada5Sessao:
    numero = 5
    nome = "Sessão"

    def descer(self, dados: bytes, session_id: int) -> bytes:
        return SessionMessage(session_id, dados).to_bytes()

    def subir(self, dados: bytes) -> tuple[int, bytes]:
        msg = SessionMessage.from_bytes(dados)
        return msg.session_id, msg.payload


@dataclass
class Camada4Transporte:
    numero: int = 4
    nome: str = "Transporte"
    limiar_segmentacao: int = 64
    carga_maxima_segmento: int = 40
    _buffers: Dict[Tuple[int, int, int], Dict[int, bytes]] = field(default_factory=dict)
    _totais: Dict[Tuple[int, int, int], int] = field(default_factory=dict)

    def descer(self, dados_sessao: bytes, src_port: int, dst_port: int) -> list[Segment]:
        if len(dados_sessao) > self.limiar_segmentacao:
            partes = [
                dados_sessao[i:i + self.carga_maxima_segmento]
                for i in range(0, len(dados_sessao), self.carga_maxima_segmento)
            ]
        else:
            partes = [dados_sessao]
        total = len(partes)
        return [Segment(src_port, dst_port, i + 1, total, parte) for i, parte in enumerate(partes)]

    def subir(self, segmento: Segment) -> bytes | None:
        # O session_id fica nos quatro primeiros octetos da carga remontada. Para
        # separar fluxos antes da remontagem usamos o par de portas e o total.
        chave = (segmento.src_port, segmento.dst_port, segmento.total)
        self._buffers.setdefault(chave, {})[segmento.sequence] = segmento.payload
        self._totais[chave] = segmento.total
        if len(self._buffers[chave]) != segmento.total:
            return None
        partes = self._buffers.pop(chave)
        self._totais.pop(chave, None)
        return b"".join(partes[i] for i in range(1, segmento.total + 1))


class Camada3Rede:
    numero = 3
    nome = "Rede"

    def descer(self, segmento_serializado: bytes, src_ip: str, dst_ip: str, packet_id: int) -> Packet:
        return Packet(src_ip, dst_ip, packet_id, segmento_serializado)

    def subir(self, pacote: Packet) -> bytes:
        # A camada 3 remove apenas o seu próprio cabeçalho. O conteúdo de L4
        # permanece opaco e só será interpretado pela camada 4.
        return pacote.payload


class Camada2Enlace:
    numero = 2
    nome = "Enlace"

    def descer(self, pacote_serializado: bytes, src_mac: str, dst_mac: str, frame_id: int) -> Frame:
        return Frame(src_mac, dst_mac, frame_id, pacote_serializado)

    def subir(self, quadro: Frame) -> bytes | None:
        if not quadro.fcs_ok():
            return None
        # A camada 2 remove apenas H2/T2. O pacote é entregue opaco à camada 3.
        return quadro.payload


class Camada1Fisica:
    numero = 1
    nome = "Física"

    def descer(self, quadro: Frame) -> bytes:
        return quadro.to_bytes()

    def subir(self, bits: bytes) -> bytes:
        return bits
