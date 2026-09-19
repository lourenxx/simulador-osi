from pathlib import Path
import unittest

from simulador.dispositivos import Roteador
from simulador.rede import Topologia
from simulador.simulador import SimuladorOSI

ROOT = Path(__file__).resolve().parents[1]


class TestCenarios(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.topo = Topologia.carregar(ROOT / "topologia.json")

    def sim(self, c):
        return SimuladorOSI(self.topo).simular(c)

    def test_roteador_nao_possui_camadas_superiores(self):
        r = Roteador("Rteste")
        self.assertFalse(hasattr(r, "l4"))
        self.assertFalse(hasattr(r, "l7"))

    def test_c1_entrega_direta(self):
        r = self.sim("C1")
        self.assertEqual(r["caminho"], ["H1", "H2"])
        self.assertEqual(r["total_transmitido"], 92)
        self.assertEqual(len({e["quadro"] for e in r["eventos"] if e["acao"] == "ENQUADRA"}), 1)

    def test_c2_referencia(self):
        r = self.sim("C2")
        self.assertEqual(r["caminho"], ["H1", "R1", "R4", "R3", "H4"])
        self.assertEqual(r["total_transmitido"], 368)
        self.assertAlmostEqual(r["eficiencia"], 42 / 368)
        quadros = [e["quadro"] for e in r["eventos"] if e["acao"] == "ENQUADRA"]
        self.assertEqual(quadros, ["Q1", "Q2", "Q3", "Q4"])
        logicos = {(e["logicos"]["origem"], e["logicos"]["destino"]) for e in r["eventos"] if e["logicos"]}
        self.assertEqual(logicos, {("10.0.1.10", "10.0.3.10")})
        fisicos = {(e["fisicos"]["origem"], e["fisicos"]["destino"]) for e in r["eventos"] if e["acao"] == "ENQUADRA"}
        self.assertEqual(len(fisicos), 4)

    def test_c3_fluxos_demultiplexados(self):
        r = self.sim("C3")
        quadros = [e["quadro"] for e in r["eventos"] if e["acao"] == "ENQUADRA"]
        self.assertEqual(len(quadros), len(set(quadros)))
        sessoes = [e["descricao"] for e in r["eventos"] if e["camada"] == 5 and e["acao"] == "ABRE"]
        self.assertTrue(any("S-0001" in s for s in sessoes))
        self.assertTrue(any("S-0002" in s for s in sessoes))
        self.assertTrue(any(e["dispositivo"] == "H4" and e["camada"] == 4 and e["acao"] == "DEMULTIPLEXA" for e in r["eventos"]))

    def test_c4_desvio(self):
        r = self.sim("C4")
        self.assertEqual(r["caminho"], ["H1", "R1", "R2", "R3", "H4"])

    def test_c5_sem_rota(self):
        r = self.sim("C5")
        self.assertFalse(r["entregue"])
        self.assertTrue(any(e["dispositivo"] == "R1" and e["camada"] == 3 and e["acao"] == "DESCARTA" for e in r["eventos"]))

    def test_c6_erro_para_na_camada_2(self):
        r = self.sim("C6")
        self.assertFalse(any(e["dispositivo"] == "R3" and e["camada"] == 3 for e in r["eventos"]))
        self.assertTrue(any(e["dispositivo"] == "R3" and e["camada"] == 2 and e["acao"] == "DESCARTA" for e in r["eventos"]))

    def test_c7_tres_segmentos(self):
        r = self.sim("C7")
        self.assertEqual(r["segmentos"], [40, 40, 24])
        self.assertTrue(r["entregue"])


if __name__ == "__main__":
    unittest.main()
