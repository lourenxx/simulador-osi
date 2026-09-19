# Simulador do Modelo OSI

**Disciplina:** Comunicação de Dados  
**Professor:** Prof. Vinícius S. Borges  
**Semestre:** 2º semestre de 2026

## Autoria

| Integrante | R.A. |
|---|---:|
| Guilherme Pexiririle Lourenço | 082230011 |
| Beatriz Carvalho Sousa | 082230027 |
| Yuri Villaco de Souza | 082230036 |
| Rhyu Costa de Souza | 082230023 |
| Lucas da Silva Macêdo | 082230037 |


## Como executar

1. Descompacte a pasta da entrega em qualquer diretório do Windows.
2. Confirme que `SimuladorOSI.exe` e `topologia.json` estão na mesma pasta.
3. Dê **dois cliques em `SimuladorOSI.exe`**.
4. Aguarde alguns segundos. O simulador inicia um servidor somente no computador local e abre a interface no navegador padrão.
5. Para encerrar corretamente, use o botão **Encerrar servidor** na própria interface.

**Não é necessário instalar Python, bibliotecas Python ou preparar ambiente.** O executável entregue é um aplicativo Windows 64 bits empacotado com o interpretador e os módulos necessários.

> Se o Windows SmartScreen exibir uma advertência por o executável não possuir assinatura digital, confirme que o arquivo veio da pasta oficial do projeto e use **Mais informações > Executar assim mesmo**. Essa etapa é uma proteção do Windows para aplicativos sem assinatura, não uma dependência do simulador.

## Descrição

O projeto simula, passo a passo, a comunicação entre computadores em uma rede com três redes locais, quatro roteadores e cinco hosts. Os computadores possuem as sete camadas do modelo OSI; os roteadores possuem somente as camadas 1, 2 e 3.

A interface permite observar encapsulamento e desencapsulamento, unidades de dados de protocolo (PDUs), endereços lógicos e físicos, escolha de rotas, segmentação e remontagem, demultiplexação, descarte por destino inalcançável, falha de enlace, detecção de erro de transmissão e custo de empilhamento.

## Estrutura do repositório

```text
simulador-osi/
|-- SimuladorOSI.exe          Aplicativo Windows pronto para uso
|-- topologia.json            Topologia, endereços, custos e parâmetros externos
|-- README.md                 Orientação inicial e navegação da entrega
|-- main.py                   Servidor local, API e ponto de entrada do código-fonte
|-- SimuladorOSI.spec         Configuração de empacotamento com PyInstaller
|-- build_windows.bat         Script usado pelo grupo para gerar o executável
|-- requirements.txt          Dependências de execução do código-fonte
|-- requirements-build.txt    Dependência usada apenas no processo de build
|-- simulador/
|   |-- __init__.py
|   |-- pdu.py                Estruturas e serialização das PDUs
|   |-- camadas.py            Implementação das sete camadas
|   |-- dispositivos.py       Computador e roteador
|   |-- rede.py               Topologia, interfaces, enlaces e roteamento
|   `-- simulador.py          Cenários, eventos e motor da simulação
|-- web/
|   |-- index.html            Estrutura da interface
|   |-- styles.css            Apresentação visual
|   `-- app.js                Reprodução dos eventos e interação com a API
|-- tests/
|   |-- __init__.py
|   `-- test_cenarios.py      Testes dos cenários obrigatórios
|-- docs/
|   |-- tutorial_execucao_e_uso.pdf
|   `-- documentacao_projeto.pdf
|-- .github/workflows/
|   `-- build-windows.yml     Build automatizado do executável em Windows
`-- .vscode/
    `-- launch.json           Atalho de desenvolvimento no VS Code
```

## Arquivos de código

- `main.py` - inicia o servidor HTTP local, disponibiliza topologia e cenários pela API, executa a simulação e abre a interface no navegador.
- `simulador/pdu.py` - define mensagem de sessão, segmento, pacote e quadro; serializa e desserializa as PDUs; calcula e verifica o FCS.
- `simulador/camadas.py` - implementa as camadas 1 a 7 e as operações `descer()` e `subir()` de cada camada.
- `simulador/dispositivos.py` - compõe a pilha completa dos computadores e limita os roteadores às camadas 1, 2 e 3.
- `simulador/rede.py` - lê `topologia.json`, representa interfaces e enlaces, calcula caminhos de menor custo e gera tabelas de encaminhamento.
- `simulador/simulador.py` - implementa os sete cenários, gera eventos, controla encapsulamento, encaminhamento, remontagem, falhas e métricas.
- `web/index.html` - define os controles, o mapa, as pilhas, a PDU, o registro e o quadro numérico.
- `web/app.js` - consome os eventos do núcleo, destaca a camada ativa, controla passo/execução/pausa, alterna OSI/TCP-IP e salva o registro.
- `web/styles.css` - define layout e destaques visuais da interface.
- `tests/test_cenarios.py` - verifica as propriedades obrigatórias dos sete cenários de referência.

## Funcionalidades e onde estão implementadas

| Funcionalidade | Implementação principal |
|---|---|
| Encapsulamento e desencapsulamento | `simulador/camadas.py`, `simulador/pdu.py` |
| Sete camadas nos computadores | `simulador/dispositivos.py`, `simulador/camadas.py` |
| Roteadores limitados às camadas 1 a 3 | `simulador/dispositivos.py` |
| Roteamento por menor custo | `simulador/rede.py` |
| Tabelas de encaminhamento | `simulador/rede.py` |
| Novo quadro em cada salto | `simulador/simulador.py`, `simulador/pdu.py` |
| Endereços lógicos fixos e físicos por salto | `simulador/simulador.py` |
| Cifra e decifra na camada 6 | `simulador/camadas.py` |
| Sessão e identificador de sessão | `simulador/camadas.py`, `simulador/simulador.py` |
| Segmentação e remontagem | `simulador/camadas.py`, `simulador/simulador.py` |
| Demultiplexação | `simulador/simulador.py` |
| Falha de enlace, destino inalcançável e erro de bit | `simulador/simulador.py` |
| Verificação FCS | `simulador/pdu.py` |
| Registro de eventos e métricas | `simulador/simulador.py`, `web/app.js` |
| Visualização OSI/TCP-IP | `web/app.js` |
| Mapa e interface | `web/index.html`, `web/app.js`, `web/styles.css` |

## Cenários disponíveis

- **C1/E1 - Entrega direta:** H1 envia para H2 na Rede A, sem roteador e com um único quadro.
- **C2/E2 - Entrega indireta:** H1:5210 envia 42 B a H4:443 pelo caminho H1 - R1 - R4 - R3 - H4.
- **C3/E3 - Demultiplexação:** H1 e H2 enviam fluxos independentes para a porta 443 de H4.
- **C4/E4 - Falha de enlace:** R1-R4 é indisponibilizado e o caminho passa por R2.
- **C5/E5 - Destino inalcançável:** R1 descarta o pacote destinado a 10.0.9.10 por ausência de rota.
- **C6/E6 - Erro de transmissão:** um bit é alterado no enlace R4-R3 e R3 descarta o quadro na camada 2.
- **C7/E7 - Mensagem longa:** 100 B úteis + H5 geram 104 B para L4 e cargas de 40, 40 e 24 B.

## Requisitos de ambiente

### Para usar a entrega final

- Windows 10 ou Windows 11, 64 bits.
- Navegador web instalado.
- `SimuladorOSI.exe` e `topologia.json` na mesma pasta.
- **Python não é necessário.**

### Para executar o código-fonte

- Python 3.10 ou superior.
- Não existem bibliotecas externas de execução; o simulador usa apenas a biblioteca padrão.

```bash
python main.py
```

### Para executar os testes

```bash
python -m unittest discover -s tests -p "test_*.py" -t . -v
```

## Topologia externa

A rede é definida em `topologia.json`. O arquivo contém redes, dispositivos, interfaces, endereços IP, endereços físicos, enlaces, custos, processos e parâmetros de tamanho. Ele permanece fora do executável e é lido em tempo de execução.

Na entrega Windows, `topologia.json` fica ao lado de `SimuladorOSI.exe`. A troca do arquivo permite simular outra rede sem modificar o código-fonte e sem gerar outro executável, desde que o novo arquivo preserve o formato esperado pelo simulador.

## Documentação

- [Tutorial completo de execução e uso](./docs/tutorial_execucao_e_uso.pdf) - reúne em um único documento duas partes claramente separadas: a Parte I explica como abrir o aplicativo e confirmar o primeiro resultado; a Parte II mostra como operar os controles e reproduzir todas as funções avaliadas.
- [Documentação técnica](./docs/documentacao_projeto.pdf) - arquitetura, módulos, PDUs, parâmetros, fluxo interno e convenções da simulação.

## Por onde começar

1. Abra o **Tutorial completo de execução e uso** e siga a **Parte I - Execução do aplicativo** para iniciar `SimuladorOSI.exe`.
2. Continue na **Parte II - Uso do simulador**, reproduza C2/E2 e confira 368 B transmitidos e eficiência de 11,4%.
3. Consulte a **Documentação técnica** para compreender a arquitetura e as convenções adotadas.

## Geração do executável

Esta seção se destina ao desenvolvimento; o professor recebe o `.exe` já pronto.

O executável é gerado com PyInstaller em Windows. O empacotamento inclui o interpretador Python e os recursos de `web/`, por isso o usuário final não instala Python. `topologia.json` permanece externo de propósito.

Há duas formas previstas no repositório:

- `build_windows.bat` - cria um ambiente de build, executa os testes e gera o aplicativo localmente em Windows;
- `.github/workflows/build-windows.yml` - executa o mesmo processo em uma máquina Windows do GitHub Actions.

## Documentos de referência da disciplina

A implementação e a documentação seguem o **Enunciado do Projeto 1**, os **Critérios de Avaliação**, o **Guia de Documentação** e o **Guia de entrega pelo GitHub** disponibilizados na disciplina de Comunicação de Dados.
