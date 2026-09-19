from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import heapq
import ipaddress
import json
from typing import Any


@dataclass(frozen=True, slots=True)
class Interface:
    dispositivo: str
    nome: str
    ip: str
    mac: str
    rede: str | None = None
    para: str | None = None


@dataclass(frozen=True, slots=True)
class Enlace:
    a: str
    ia: str
    b: str
    ib: str
    custo: int
    tipo: str = "wan"

    @property
    def chave(self) -> frozenset[str]:
        return frozenset((self.a, self.b))


class Topologia:
    def __init__(self, dados: dict[str, Any]):
        self.dados = dados
        self.nome = dados.get("nome", "Topologia")
        self.dispositivos: dict[str, dict[str, Any]] = dados["dispositivos"]
        self.redes = {r["id"]: ipaddress.ip_network(r["prefixo"]) for r in dados.get("redes", [])}
        self.enlaces = [Enlace(**e) for e in dados["enlaces"]]
        self.processos = dados.get("processos", {})
        self.parametros = dados.get("parametros", {})
        self._interfaces: dict[tuple[str, str], Interface] = {}
        for dnome, dev in self.dispositivos.items():
            for inome, i in dev.get("interfaces", {}).items():
                self._interfaces[(dnome, inome)] = Interface(
                    dnome, inome, i["ip"], i["mac"], i.get("rede"), i.get("para")
                )

    @classmethod
    def carregar(cls, caminho: str | Path) -> "Topologia":
        with open(caminho, "r", encoding="utf-8") as f:
            return cls(json.load(f))

    def tipo(self, dispositivo: str) -> str:
        return self.dispositivos[dispositivo]["tipo"]

    def interfaces(self, dispositivo: str) -> list[Interface]:
        return [i for (d, _), i in self._interfaces.items() if d == dispositivo]

    def interface(self, dispositivo: str, nome: str) -> Interface:
        return self._interfaces[(dispositivo, nome)]

    def interface_para(self, dispositivo: str, vizinho: str) -> Interface:
        # Primeiro procura enlace explícito.
        for e in self.enlaces:
            if e.a == dispositivo and e.b == vizinho:
                return self.interface(dispositivo, e.ia)
            if e.b == dispositivo and e.a == vizinho:
                return self.interface(dispositivo, e.ib)
        # Entrega direta em uma LAN compartilhada: a interface local da rede.
        if self.tipo(dispositivo) == "host":
            return self.interfaces(dispositivo)[0]
        raise KeyError(f"Sem interface de {dispositivo} para {vizinho}")

    def interface_recebedora(self, dispositivo: str, remetente: str) -> Interface:
        for e in self.enlaces:
            if e.a == remetente and e.b == dispositivo:
                return self.interface(dispositivo, e.ib)
            if e.b == remetente and e.a == dispositivo:
                return self.interface(dispositivo, e.ia)
        if self.tipo(dispositivo) == "host":
            return self.interfaces(dispositivo)[0]
        raise KeyError(f"Sem interface receptora de {dispositivo} a partir de {remetente}")

    def ip_host(self, host: str) -> str:
        return self.interfaces(host)[0].ip

    def mac_host(self, host: str) -> str:
        return self.interfaces(host)[0].mac

    def host_por_ip(self, ip: str) -> str | None:
        for nome, dev in self.dispositivos.items():
            if dev["tipo"] != "host":
                continue
            if any(i.ip == ip for i in self.interfaces(nome)):
                return nome
        return None

    def rede_do_ip(self, ip: str) -> str | None:
        addr = ipaddress.ip_address(ip)
        for nome, net in self.redes.items():
            if addr in net:
                return nome
        return None

    def rede_do_host(self, host: str) -> str | None:
        intf = self.interfaces(host)[0]
        if intf.rede:
            return intf.rede
        return self.rede_do_ip(intf.ip)

    def hosts_mesma_rede(self, a: str, b: str) -> bool:
        return self.rede_do_host(a) == self.rede_do_host(b)

    def router_da_rede(self, rede: str) -> str | None:
        for nome, dev in self.dispositivos.items():
            if dev["tipo"] != "router":
                continue
            for i in self.interfaces(nome):
                if i.rede == rede:
                    return nome
        return None

    def gateway_do_host(self, host: str) -> str:
        rede = self.rede_do_host(host)
        if not rede:
            raise KeyError(f"Host {host} não está associado a uma rede")
        r = self.router_da_rede(rede)
        if not r:
            raise KeyError(f"Rede {rede} não possui roteador")
        return r

    def _adj_routers(self, enlaces_indisponiveis: set[frozenset[str]] | None = None):
        bloqueados = enlaces_indisponiveis or set()
        adj: dict[str, list[tuple[str, int]]] = {
            d: [] for d, v in self.dispositivos.items() if v["tipo"] == "router"
        }
        for e in self.enlaces:
            if e.chave in bloqueados:
                continue
            if self.tipo(e.a) == "router" and self.tipo(e.b) == "router":
                adj[e.a].append((e.b, e.custo))
                adj[e.b].append((e.a, e.custo))
        for v in adj.values():
            v.sort(key=lambda x: x[0])
        return adj

    def caminho_roteadores(self, origem: str, destino: str,
                           enlaces_indisponiveis: set[frozenset[str]] | None = None) -> tuple[list[str], int] | None:
        if origem == destino:
            return [origem], 0
        adj = self._adj_routers(enlaces_indisponiveis)
        heap: list[tuple[int, tuple[str, ...], str]] = [(0, (origem,), origem)]
        melhor: dict[str, tuple[int, tuple[str, ...]]] = {}
        while heap:
            custo, caminho_tuple, atual = heapq.heappop(heap)
            if atual in melhor and melhor[atual] <= (custo, caminho_tuple):
                continue
            melhor[atual] = (custo, caminho_tuple)
            if atual == destino:
                return list(caminho_tuple), custo
            for viz, peso in adj.get(atual, []):
                novo = (custo + peso, caminho_tuple + (viz,), viz)
                heapq.heappush(heap, novo)
        return None

    def caminho_hosts(self, origem: str, destino: str,
                      enlaces_indisponiveis: set[frozenset[str]] | None = None) -> tuple[list[str], int] | None:
        if self.hosts_mesma_rede(origem, destino):
            return [origem, destino], 0
        ro = self.gateway_do_host(origem)
        rd = self.gateway_do_host(destino)
        cr = self.caminho_roteadores(ro, rd, enlaces_indisponiveis)
        if cr is None:
            return None
        routers, custo = cr
        return [origem] + routers + [destino], custo

    def proximo_salto_para_ip(self, roteador: str, dst_ip: str,
                              enlaces_indisponiveis: set[frozenset[str]] | None = None) -> tuple[str, int, str] | None:
        rede_destino = self.rede_do_ip(dst_ip)
        if rede_destino is None:
            return None
        router_destino = self.router_da_rede(rede_destino)
        if router_destino is None:
            return None
        if roteador == router_destino:
            host = self.host_por_ip(dst_ip)
            if host is None:
                return None
            intf = next((i for i in self.interfaces(roteador) if i.rede == rede_destino), None)
            if intf is None:
                return None
            return host, 0, intf.nome
        caminho = self.caminho_roteadores(roteador, router_destino, enlaces_indisponiveis)
        if caminho is None:
            return None
        routers, custo = caminho
        viz = routers[1]
        intf = self.interface_para(roteador, viz)
        return viz, custo, intf.nome

    def tabela_encaminhamento(self, roteador: str,
                              enlaces_indisponiveis: set[frozenset[str]] | None = None) -> list[dict[str, Any]]:
        linhas = []
        for rede_nome, net in self.redes.items():
            router_dest = self.router_da_rede(rede_nome)
            if router_dest is None:
                continue
            if router_dest == roteador:
                intf = next(i for i in self.interfaces(roteador) if i.rede == rede_nome)
                linhas.append({
                    "rede": str(net), "via": "direto", "custo": 0, "interface": intf.nome
                })
            else:
                caminho = self.caminho_roteadores(roteador, router_dest, enlaces_indisponiveis)
                if caminho:
                    routers, custo = caminho
                    viz = routers[1]
                    intf = self.interface_para(roteador, viz)
                    linhas.append({
                        "rede": str(net), "via": viz, "custo": custo, "interface": intf.nome
                    })
        return linhas

    def dados_publicos(self) -> dict[str, Any]:
        # Retorna o JSON original para a interface. É uma cópia por serialização.
        return json.loads(json.dumps(self.dados, ensure_ascii=False))
