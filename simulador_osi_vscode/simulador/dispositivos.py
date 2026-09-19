from __future__ import annotations

from dataclasses import dataclass, field

from .camadas import (
    Camada1Fisica,
    Camada2Enlace,
    Camada3Rede,
    Camada4Transporte,
    Camada5Sessao,
    Camada6Apresentacao,
    Camada7Aplicacao,
)


@dataclass(slots=True)
class Computador:
    nome: str
    limiar_segmentacao: int = 64
    carga_maxima_segmento: int = 40
    l1: Camada1Fisica = field(init=False)
    l2: Camada2Enlace = field(init=False)
    l3: Camada3Rede = field(init=False)
    l4: Camada4Transporte = field(init=False)
    l5: Camada5Sessao = field(init=False)
    l6: Camada6Apresentacao = field(init=False)
    l7: Camada7Aplicacao = field(init=False)

    def __post_init__(self):
        self.l1 = Camada1Fisica()
        self.l2 = Camada2Enlace()
        self.l3 = Camada3Rede()
        self.l4 = Camada4Transporte(
            limiar_segmentacao=self.limiar_segmentacao,
            carga_maxima_segmento=self.carga_maxima_segmento,
        )
        self.l5 = Camada5Sessao()
        self.l6 = Camada6Apresentacao()
        self.l7 = Camada7Aplicacao()


@dataclass(slots=True)
class Roteador:
    """Roteador deliberadamente limitado às camadas 1, 2 e 3.

    O objeto não possui atributos l4, l5, l6 ou l7. Assim, não existe uma API
    pela qual o roteador possa consultar portas, sessão, cifra ou processo.
    """

    nome: str
    l1: Camada1Fisica = field(init=False)
    l2: Camada2Enlace = field(init=False)
    l3: Camada3Rede = field(init=False)

    def __post_init__(self):
        self.l1 = Camada1Fisica()
        self.l2 = Camada2Enlace()
        self.l3 = Camada3Rede()
