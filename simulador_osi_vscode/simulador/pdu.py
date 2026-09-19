from __future__ import annotations

from dataclasses import dataclass
import ipaddress
import struct
import zlib


class PDUError(ValueError):
    pass


def mac_to_bytes(mac: str) -> bytes:
    parts = mac.split(":")
    if len(parts) != 6:
        raise PDUError(f"MAC inválido: {mac}")
    return bytes(int(p, 16) for p in parts)


def bytes_to_mac(raw: bytes) -> str:
    if len(raw) != 6:
        raise PDUError("MAC deve ter 6 octetos")
    return ":".join(f"{b:02X}" for b in raw)


@dataclass(slots=True)
class SessionMessage:
    session_id: int
    payload: bytes

    HEADER_SIZE = 4

    def to_bytes(self) -> bytes:
        return struct.pack("!I", self.session_id) + self.payload

    @classmethod
    def from_bytes(cls, raw: bytes) -> "SessionMessage":
        if len(raw) < cls.HEADER_SIZE:
            raise PDUError("Mensagem de sessão truncada")
        sid = struct.unpack("!I", raw[:4])[0]
        return cls(sid, raw[4:])


@dataclass(slots=True)
class Segment:
    src_port: int
    dst_port: int
    sequence: int
    total: int
    payload: bytes

    HEADER_SIZE = 8

    def to_bytes(self) -> bytes:
        return struct.pack("!HHHH", self.src_port, self.dst_port, self.sequence, self.total) + self.payload

    @classmethod
    def from_bytes(cls, raw: bytes) -> "Segment":
        if len(raw) < cls.HEADER_SIZE:
            raise PDUError("Segmento truncado")
        src, dst, seq, total = struct.unpack("!HHHH", raw[:8])
        return cls(src, dst, seq, total, raw[8:])


@dataclass(slots=True)
class Packet:
    src_ip: str
    dst_ip: str
    packet_id: int
    payload: bytes
    ttl: int = 64

    HEADER_SIZE = 20

    def to_bytes(self) -> bytes:
        src = ipaddress.ip_address(self.src_ip).packed
        dst = ipaddress.ip_address(self.dst_ip).packed
        # 4 src + 4 dst + 4 id + 1 ttl + 1 flags + 6 reservados = 20 bytes
        header = src + dst + struct.pack("!IBB6s", self.packet_id, self.ttl, 0, b"\x00" * 6)
        return header + self.payload

    @classmethod
    def from_bytes(cls, raw: bytes) -> "Packet":
        if len(raw) < cls.HEADER_SIZE:
            raise PDUError("Pacote truncado")
        src = str(ipaddress.ip_address(raw[0:4]))
        dst = str(ipaddress.ip_address(raw[4:8]))
        pid, ttl, _flags, _reserved = struct.unpack("!IBB6s", raw[8:20])
        return cls(src, dst, pid, raw[20:], ttl)


@dataclass(slots=True)
class Frame:
    src_mac: str
    dst_mac: str
    frame_id: int
    payload: bytes
    fcs: int | None = None

    HEADER_SIZE = 14
    TRAILER_SIZE = 4
    ETHERTYPE = 0x0800

    def header_bytes(self) -> bytes:
        # Ethernet: destino vem antes da origem.
        return mac_to_bytes(self.dst_mac) + mac_to_bytes(self.src_mac) + struct.pack("!H", self.ETHERTYPE)

    def body_for_crc(self) -> bytes:
        return self.header_bytes() + self.payload

    def computed_fcs(self) -> int:
        return zlib.crc32(self.body_for_crc()) & 0xFFFFFFFF

    def to_bytes(self) -> bytes:
        fcs = self.computed_fcs() if self.fcs is None else self.fcs
        return self.body_for_crc() + struct.pack("!I", fcs)

    @classmethod
    def from_bytes(cls, raw: bytes, frame_id: int) -> "Frame":
        if len(raw) < cls.HEADER_SIZE + cls.TRAILER_SIZE:
            raise PDUError("Quadro truncado")
        dst = bytes_to_mac(raw[0:6])
        src = bytes_to_mac(raw[6:12])
        ethertype = struct.unpack("!H", raw[12:14])[0]
        if ethertype != cls.ETHERTYPE:
            raise PDUError(f"EtherType não suportado: {ethertype:#06x}")
        payload = raw[14:-4]
        fcs = struct.unpack("!I", raw[-4:])[0]
        return cls(src, dst, frame_id, payload, fcs)

    def fcs_ok(self) -> bool:
        return self.fcs == self.computed_fcs()
