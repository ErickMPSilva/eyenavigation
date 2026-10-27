# EyeNav – Navegação Web por Rastreamento Ocular

**TC II – Ciência da Computação | UNIP**
**Autor:** Erick Martins Paulino Silva
**Linha de pesquisa:** Tecnologia e Bem-Estar Social

---

## Sobre o projeto

Sistema de software que permite a pessoas com imobilidade física navegar
pela internet usando exclusivamente os movimentos dos olhos, via webcam
convencional e visão computacional (Python + MediaPipe + OpenCV).

O usuário move o cursor com o olhar e interage com a página sem uso das mãos:

- **Piscada lenta:** fechar os dois olhos e abrir ao ouvir o bipe — clique
  simples, duplo ou direito, conforme o tempo de olhos fechados.
- **Clique com zoom:** a primeira piscada amplia a região do olhar; a segunda,
  olhando o alvo ampliado, clica no ponto exato.
- **Scroll com trava:** destravar com uma piscada lenta na "alça" (meio da
  borda direita); depois, olhar para a faixa superior ou inferior rola a
  página. Começa travado, para não rolar sem querer.
- **Dwell click (opcional):** fixar o olhar em um ponto para clicar.

---

## Pré-requisitos

- Python **3.10** ou superior
- Webcam (integrada ou USB), preferencialmente **720p**
- Boa iluminação frontal (evite luz atrás de você)
- Sistema: Ubuntu 20.04+ (X11 ou Wayland), Windows 10/11 ou macOS 12+

### Backend de controle do mouse

O EyeNav precisa de um backend para mover o cursor e clicar. O módulo
`mouse_backend.py` detecta automaticamente o melhor disponível, nesta ordem:

| Prioridade | Backend   | Ambiente        | Instalação                                     |
| ---------- | --------- | --------------- | ---------------------------------------------- |
| 1          | `ydotool` | Linux (Wayland) | `sudo apt install ydotool` + daemon `ydotoold` |
| 2          | `xtest`   | Linux (X11)     | `libxtst6` (já presente em desktops X11)       |
| 3          | `xdotool` | Linux (X11)     | `sudo apt install xdotool`                     |
| 4          | `pynput`  | Windows, macOS  | instalado via `requirements.txt`               |

Ao iniciar, o sistema informa o backend escolhido:

```
[MouseBackend] Sessão: x11 (X11/outra) | Backend: xtest
```

O backend `xtest` usa a mesma extensão do X11 que o `xdotool`, mas chamada
diretamente pelo Python, sem abrir um processo externo a cada movimento.

> **Importante:** se aparecer `Backend: none`, os cliques são detectados
> (aparecem no console e no CSV), mas **não são executados** no sistema.

No Linux, recomenda-se também o `python3-tk` e um player de áudio para os
bipes (`paplay`, `pw-play` ou `aplay`, normalmente já instalados).

No macOS, conceda permissão de **Acessibilidade** ao terminal em
_Ajustes do Sistema → Privacidade e Segurança_, necessária para o `pynput`
controlar o mouse.

---

## Instalação

```bash
# 1. Clone ou extraia o projeto
cd eyenav/

# 2. Crie ambiente virtual (recomendado)
python -m venv .venv
source .venv/bin/activate      # Linux/macOS
.venv\Scripts\activate         # Windows

# 3. Instale as dependências
pip install -r requirements.txt
```

O modelo `models/face_landmarker.task` (~4 MB) acompanha o projeto e é
baixado automaticamente caso não exista.

---

## Execução

Na raiz do projeto:

```bash
python src/main.py
```

Os arquivos gerados (`calibration.pkl`, `eyenav_metrics.csv`, gravações e
screenshots) ficam no diretório de onde o comando foi executado.

### Fluxo de primeira execução

1. O sistema detecta o backend de mouse e abre a webcam.
2. Verifica se há calibração salva (`calibration.pkl`).
3. Se não houver, inicia a **calibração**.
4. **Validação obrigatória** (também ao carregar uma calibração salva): se a
   precisão medida for ruim, a calibração é refeita automaticamente.
5. O rastreamento ocular é ativado em tempo real.

> Calibrações feitas antes desta versão usam outras features e são
> recusadas automaticamente — será necessário recalibrar uma vez.

---

## Calibração

A calibração mapeia as features dos olhos e da cabeça para coordenadas da tela.

1. Sente-se a ~50–70 cm da câmera.
2. **Grade (16 pontos):** mantenha a cabeça parada e fixe o olhar em cada
   círculo até o arco completar.
3. **Movimento da cabeça (~10 s):** com os olhos no ponto central, gire a
   cabeça devagar seguindo as setas (esquerda, direita, cima, baixo). Essa
   etapa ensina o sistema a diferenciar "a cabeça mexeu" de "o olhar mexeu".
   Quem não movimenta a cabeça pode pular com **ESPAÇO**.
4. **Validação (5 pontos: centro e cantos):** fixe cada ponto enquanto o arco
   fecha. O sistema mede onde _acha_ que você está olhando — sem "ajudar" a
   medida — e mostra na tela os alvos, o olhar estimado e o erro.

### Validação obrigatória

- Com os 5 pontos, o sistema aprende uma **correção da sessão** (ganho e
  deslocamento por eixo): corrige a cabeça em posição diferente da
  calibração e o cursor que "não alcança" as bordas.
- A precisão é o erro médio após essa correção, medido deixando cada ponto
  de fora do ajuste (uma estimativa honesta, não otimista).
- Se o erro passar de `VALIDATION_MAX_ERROR_PX` (110 px), **a calibração é
  refeita automaticamente**, até `CALIB_MAX_ATTEMPTS` (3) vezes. Esgotadas as
  tentativas, o sistema segue com a **melhor** delas, para nunca prender em
  um ciclo sem fim quem não consegue usar o teclado.
- **R** recalibra; **F** refaz só a validação (e recalibra se ela falhar) —
  útil depois de mudar de posição.

---

## Controles (janela de debug)

| Tecla   | Ação                                              |
| ------- | ------------------------------------------------- |
| Q / ESC | Encerrar o sistema                                |
| R       | Recalibrar                                        |
| F       | Refazer a validação (recalibra se falhar)         |
| P       | Pausar / retomar cliques e scroll                 |
| Z       | Ativar / desativar clique com zoom                |
| L       | Travar / destravar o scroll                       |
| D       | Ativar / desativar dwell click                    |
| B       | Ativar / desativar blink click                    |
| G       | Iniciar / salvar gravação da sessão (diagnóstico) |
| M       | Exibir métricas da sessão no console e salvar CSV |
| S       | Salvar screenshot do debug                        |

---

## Mecanismos de interação

### Clique por piscada lenta

Feche **os dois olhos** e abra quando ouvir o bipe da ação desejada:

| Olhos fechados (padrão) | Retorno sonoro       | Ação                       |
| ----------------------- | -------------------- | -------------------------- |
| < 0,6 s                 | —                    | ignorada (piscada natural) |
| 0,6 – 1,3 s             | 1º bipe              | clique simples             |
| 1,3 – 2,1 s             | 2º bipe (mais agudo) | duplo clique               |
| 2,1 – 3,5 s             | 3º bipe              | clique direito             |
| > 3,5 s                 | bipe grave           | cancelado                  |

- O clique acontece **onde você olhava antes de fechar os olhos**.
- Piscadas naturais (100–400 ms) nunca clicam; fechar um olho só também não.
- Olhar para baixo abaixa a pálpebra, mas não é confundido com piscada: o
  sistema aprende a abertura normal do olho para cada faixa da tela.
- A bola do olhar fica **verde** quando um clique é executado.

Ajuste os tempos em `src/config.py` (`BLINK_CLICK_MS`, `BLINK_DOUBLE_MS`,
`BLINK_RIGHT_MS`, `BLINK_CANCEL_MS`).

### Clique com zoom (precisão) — ligado por padrão

Uma webcam estima o olhar com erro típico de 1,5–3° (60–120 px em um monitor
de 24" a 60 cm), e links têm 15–20 px de altura. Nenhum filtro ou calibração
leva o erro a zero — o próprio olho, fixando um ponto, enxerga nítida uma
área de ~1°. Rastreadores comerciais resolvem isso com ampliação; o EyeNav
faz o mesmo:

1. **1ª piscada lenta:** a região em volta do olhar é ampliada 2,5× em tela
   cheia (borda azul).
2. **Olhe para o alvo** dentro da imagem ampliada. O erro do olhar continua o
   mesmo em pixels, mas agora cada pixel vale 1/2,5 de pixel real.
3. **2ª piscada lenta:** o zoom fecha e o clique vai para o ponto real. O tempo
   dessa piscada escolhe o tipo de clique (1º, 2º ou 3º bipe), como no clique
   direto.

Feche os olhos até o bipe grave (ou espere 10 s) para cancelar. **Z** liga e
desliga o zoom; com ele desligado, a primeira piscada já clica.

**Cada clique com zoom também calibra:** o sistema sabe onde estimou o seu
olhar antes do zoom e onde você realmente clicou. A diferença atualiza a
correção da sessão — inclusive a **deriva** (a cabeça que foi se deslocando
desde a validação). O console mostra o erro medido em cada clique; com o uso,
ele diminui.

Requer a biblioteca `mss` (captura de tela; X11, Windows e macOS). Em
Wayland o zoom fica indisponível e os cliques são diretos.

### Scroll com trava

O scroll começa **TRAVADO**: olhar para o topo da tela (abas, barra de endereço)
ou ler as últimas linhas não rola nada.

**Destravar:** olhe para a **alça** — o meio da borda direita da tela, sobre a
barra de rolagem do navegador, marcada por uma barra fina cinza. Em 0,3 s a
bola do olhar começa a **pulsar com branco**; faça então uma **piscada lenta**
(o mesmo gesto do clique). No lugar do 1º bipe toca um tom **subindo**; abra
os olhos e a bola fica **violeta**: scroll livre.

**Rolar:** destravado, olhar para a faixa superior (12 % da altura) ou inferior
(12 %) rola a página, como antes: começa após 0,5 s na faixa, acelera
suavemente e é mais rápido quanto mais perto da borda (bola **laranja**).
Enquanto rola, o cursor fica sobre o conteúdo da página, longe das abas, da
barra de tarefas e da janela de debug.

**Travar de novo** (tom **descendo** no lugar do 1º bipe):

| Como                                                   | O que acontece                                                                      |
| ------------------------------------------------------ | ----------------------------------------------------------------------------------- |
| Piscada lenta com a página rolando (bola laranja)      | **Freio**: para e trava. Nunca clica, porque o conteúdo sob o olhar acabou de andar |
| Piscada lenta na alça (bola pulsando violeta e branco) | Trava                                                                               |
| Fechar os olhos até o bipe grave, em qualquer lugar    | Trava (parada universal)                                                            |
| Clicar ou abrir o zoom                                 | Trava, em silêncio (você terminou de rolar)                                         |
| 15 s sem rolar, ou 2 s sem rosto na câmera             | Trava sozinho (tom descendo, suave)                                                 |
| Tecla **L** (alterna), **P**, **R**, **F** ou **B**    | Trava                                                                               |

Nada destrava sozinho: um erro sempre cai para o lado seguro.

- **Não sei onde está a alça:** com o scroll travado, olhar uma faixa de scroll
  por 1,5 s faz a barra da alça piscar (dica, no máximo a cada 30 s).
- **A bola não pulsa na alça:** olhe um pouco **além** da borda direita da tela
  (para a moldura do monitor) — a região continua para fora da tela. A largura
  da alça (60–120 px) se ajusta ao erro medido na validação.
- **Sem blink click (tecla B):** fixar a alça por 2 s alterna a trava.
- Com `SCROLL_LOCK_ENABLED = False` o scroll volta a ser sempre ativo (para
  comparar no TC). `SCROLL_HANDLE_SIDE` aceita `'left'` ou `'both'`.

Salvaguardas do scroll destravado: no máximo 10 s de rolagem contínua por
entrada na faixa, e olhar muito fora da tela (teclado, colo) não rola.

### Dwell click (desligado por padrão)

Manter o olhar fixo por **1,5 s** dispara um clique esquerdo. Fica desligado
porque, ao ler, o olhar naturalmente para em um ponto por mais de 1 s e o
sistema clicaria sem querer. Ligue com a tecla **D** se preferir esse modo
(por exemplo, para quem não controla bem as piscadas). A bola muda
gradualmente para verde conforme o tempo de fixação.

### Bola do olhar (X11)

| Cor                         | Estado                                    |
| --------------------------- | ----------------------------------------- |
| vermelha (`GAZE_DOT_COLOR`) | seguindo o olhar                          |
| vermelha → verde            | dwell click em progresso                  |
| amarela                     | olhos fechados com clique armado          |
| verde                       | clique executado                          |
| laranja                     | rolando (piscar = frear e travar)         |
| violeta                     | scroll destravado                         |
| pulsando com branco         | olhar na alça (piscar = travar/destravar) |
| azul-claro                  | zoom de precisão aberto                   |
| cinza                       | pausado (tecla P)                         |

---

## Configuração

Todas as constantes ficam em `src/config.py`. As principais:

| Parâmetro                 | Padrão   | Descrição                                                  |
| ------------------------- | -------- | ---------------------------------------------------------- |
| `WEBCAM_INDEX`            | 0        | Índice da câmera                                           |
| `WEBCAM_WIDTH/HEIGHT`     | 1280×720 | Resolução solicitada à câmera                              |
| `CALIB_COLS/ROWS`         | 4×4      | Grade de calibração                                        |
| `CALIB_HEAD_MOTION`       | True     | Etapa de movimento da cabeça na calibração                 |
| `VALIDATION_MAX_ERROR_PX` | 110      | Erro médio aceitável na validação (após a correção)        |
| `CALIB_MAX_ATTEMPTS`      | 3        | Calibrações automáticas se a validação falhar              |
| `ZOOM_CLICK_ENABLED`      | True     | Clique com zoom ao iniciar                                 |
| `ZOOM_FACTOR`             | 2,5      | Ampliação do zoom (↑ = mais preciso, região menor)         |
| `CORR_DRIFT_HALF_LIFE_S`  | 120      | Quanto tempo a deriva aprendida nos cliques vale           |
| `SMOOTHER`                | fixation | `fixation`, `one_euro` ou `ema`                            |
| `FIX_WINDOW_MS`           | 1000     | Janela da média na fixação (↑ = cursor mais estável)       |
| `FIX_SACCADE_SIGMAS`      | 2,5      | Sensibilidade a sacadas (↓ = segue movimentos menores)     |
| `CURSOR_DEADZONE_PX`      | 3        | Movimentos menores não são enviados ao sistema             |
| `BLINK_CLICK_ENABLED`     | True     | Clique por piscada lenta ao iniciar                        |
| `BLINK_CLICK_MS` …        | 600 …    | Escada de tempos da piscada (ver acima)                    |
| `EYE_CLOSED_RATIO`        | 0,45     | Abertura relativa abaixo da qual o olho está fechado       |
| `DWELL_CLICK_ENABLED`     | False    | Dwell click ao iniciar                                     |
| `DWELL_TIME_MS`           | 1500     | Tempo de fixação para o dwell click                        |
| `SCROLL_LOCK_ENABLED`     | True     | Trava do scroll (False = sempre ativo, como antes)         |
| `SCROLL_HANDLE_SIDE`      | right    | Borda da alça: `right`, `left` ou `both`                   |
| `SCROLL_IDLE_LOCK_MS`     | 15000    | Destravado sem rolar por este tempo → trava                |
| `SCROLL_ZONE_TOP/BOTTOM`  | 0,12     | Altura das faixas de scroll (fração da tela)               |
| `SCROLL_ACTIVATE_MS`      | 500      | Tempo na faixa antes de rolar                              |
| `SCROLL_MIN/MAX_RATE`     | 2 / 9    | Passos da roda por segundo (borda interna / borda da tela) |
| `SOUND_ENABLED`           | True     | Bipes de retorno                                           |
| `CURSOR_MOVE`             | True     | False = apenas debug, sem mover o cursor                   |
| `SHOW_DEBUG_WINDOW`       | True     | Exibe a janela de debug                                    |

---

## Estrutura do projeto

```
eyenav/
├── src/
│   ├── main.py                  # Ponto de entrada — loop principal
│   ├── config.py                # Todas as constantes do sistema
│   ├── capture/
│   │   └── camera.py            # Captura da webcam em thread (sempre o frame mais recente)
│   ├── tracking/                # Do frame ao ponto de olhar
│   │   ├── gaze_estimator.py    # MediaPipe FaceLandmarker (modo VIDEO + blendshapes)
│   │   ├── gaze_features.py     # Olho no referencial do olho, pose da cabeça, abertura
│   │   ├── gaze_model.py        # Ridge polinomial + compensação de cabeça + validação cruzada
│   │   ├── smoother.py          # Filtro de fixação (e One Euro / EMA para comparação)
│   │   ├── correction.py        # Correção da sessão: ganho, deslocamento, local e deriva
│   │   └── eye_state.py         # Olho aberto / fechando / fechado, por faixa da tela
│   ├── calibration/
│   │   ├── calibration.py       # Calibração: grade + movimento da cabeça
│   │   └── validation.py        # Validação obrigatória (5 pontos) e critério de precisão
│   ├── interaction/             # O que o olhar faz
│   │   ├── blink_clicker.py     # Piscada lenta → clique simples / duplo / direito
│   │   ├── zoom.py              # Clique de precisão com zoom
│   │   ├── dwell_clicker.py     # Clique por fixação do olhar
│   │   ├── edge_scroller.py     # Scroll pelas bordas da tela (motor)
│   │   ├── scroll_lock.py       # Trava do scroll: alça, freio, travas automáticas
│   │   └── cursor_controller.py # Movimento do cursor do sistema
│   ├── desktop/                 # Integração com o sistema operacional
│   │   ├── mouse_backend.py     # Mouse (ydotool / XTest / xdotool / pynput)
│   │   ├── gaze_overlay.py      # Bola do olhar e barra da alça (X11)
│   │   └── feedback.py          # Bipes de retorno
│   └── diagnostics/
│       ├── metrics.py           # Métricas de desempenho (CSV)
│       └── recorder.py          # Gravação da sessão para diagnóstico (tecla G)
├── models/
│   └── face_landmarker.task     # Modelo do MediaPipe
├── tests/                       # Testes automatizados com usuário e olhar simulados
└── requirements.txt             # Dependências Python
```

---

## Pipeline técnico

```
Webcam (thread própria, sempre o frame mais recente)
    │
    ▼
FaceLandmarker — modo VIDEO (rastreia entre frames) + blendshapes
  • 478 landmarks faciais (com íris)
    │
    ▼
Features
  • olhos: íris e pálpebra no referencial do próprio olho   [lnx, lny, rnx, rny, l_lid, r_lid]
  • cabeça: yaw, pitch (plano dos pontos rígidos) e posição [yaw, pitch, hx, hy]
  • abertura dos olhos: 1 − eyeBlink (blendshapes)
    │
    ├──► EyeState: aberto / fechando / fechado (referência por faixa da tela)
    │       └─ fechando/fechado → olhar congelado
    ▼
GazeModel: Ridge sobre polinômio grau 2 (olhos) + termos lineares (cabeça)
    │
    ▼  (raw_x, raw_y)
    │
    ▼
Filtro de fixação: média na fixação, salto na sacada confirmada
    │
    ▼
GazeCorrection: ganho + deslocamento + local + deriva
  (aprendida na validação e em cada clique com zoom)
    │
    ▼  (x, y) estável e corrigido
    │
    ├──► CursorController ──┐
    ├──► BlinkClicker / Zoom┤
    ├──► DwellClicker ──────┼──► mouse_backend (fila única) ──► ydotool / XTest / xdotool / pynput
    └──► EdgeScroller ──────┘
```

Os módulos de interação decidem **quando** agir. O `mouse_backend` decide
**como** executar a ação no sistema operacional, em uma única thread e em
ordem.

---

## Diagnóstico e correções

### Scroll: "travar e destravar"

O scroll estava sempre ativo, e ler as últimas linhas ou olhar as abas rolava a
página. O desenho foi escolhido por um painel de quatro propostas (degrau novo
na escada de piscadas, alça na borda, modo joystick e segurança em primeiro
lugar), avaliado por usabilidade, robustez e risco de implementação. A alça na
borda direita venceu: usa o mesmo gesto do clique, a escada de piscadas não
muda, e todo erro cai para o lado seguro (travado).

### Precisão: "o cursor não fica onde eu olho"

| Problema                                                                                                                                            | Correção                                                                                                                                      |
| --------------------------------------------------------------------------------------------------------------------------------------------------- | --------------------------------------------------------------------------------------------------------------------------------------------- |
| O ajuste fino (3 pontos) só gravava frames em que o olhar já estava a < 200 px do ponto: o erro medido era otimista e uma calibração ruim "passava" | **Validação de 5 pontos** que mede o erro real, com critério de aprovação e **recalibração automática**                                       |
| Erros sistemáticos (deslocamento, ganho) deixavam o cursor estável, mas no lugar errado                                                             | **Correção da sessão** aprendida na validação (em simulação: 132 px → 6 px com um desvio de câmera/cabeça)                                    |
| A cabeça se desloca ao longo do uso                                                                                                                 | **Deriva** aprendida nos cliques com zoom (em simulação, com 120 px de desvio surgindo após a validação: erro medido 75 → 29 px em 3 cliques) |
| Precisão física de uma webcam (~1,5–3°) não permite acertar links pequenos                                                                          | **Clique com zoom**: o erro do clique fica dividido por 2,5                                                                                   |

### Versão anterior: tremor, cliques aleatórios e scroll

| Sintoma relatado    | Causa encontrada                                                                                                                            | Correção                                                                                                                         |
| ------------------- | ------------------------------------------------------------------------------------------------------------------------------------------- | -------------------------------------------------------------------------------------------------------------------------------- |
| Cursor tremendo     | O MediaPipe atual não tem mais a API `mp.solutions`; o código caía na Tasks API em modo **IMAGE**, que detecta o rosto do zero a cada frame | Modo **VIDEO** (rastreamento): tremor da íris ~4× menor em teste com ruído simulado                                              |
| Cursor tremendo     | Filtros passa-baixa (One Euro) confundem o ruído com movimento                                                                              | **Filtro de fixação**: em simulação, tremor 8 px (One Euro: 15 px), latência após sacada 100 ms (One Euro: 167 ms)               |
| Cursor tremendo     | Um processo `xdotool` por frame, sem esperar o término: movimentos fora de ordem                                                            | Fila única, movimentos condensados, XTest dentro do processo                                                                     |
| Imprecisão / deriva | Mexer a cabeça mudava a posição da íris e o modelo lia como olhar                                                                           | Features de pose da cabeça + etapa de calibração com movimento da cabeça (erro com cabeça em movimento: 72 → 29 px em simulação) |
| Imprecisão          | Cabeça inclinada vazava movimento horizontal para o vertical                                                                                | Íris medida nos eixos do próprio olho                                                                                            |
| Cliques aleatórios  | Dwell ligado por padrão clicava ao ler                                                                                                      | Dwell desligado por padrão; piscada lenta como clique principal                                                                  |
| Cliques aleatórios  | EAR cai ao olhar para baixo e parecia piscada                                                                                               | Blendshapes + referência de abertura por faixa da tela + exigência dos dois olhos fechados                                       |
| Duplo clique errado | Dois fechamentos → clique simples + duplo (3 cliques)                                                                                       | Escada de tempos: cada fechamento gera exatamente uma ação, com bipes                                                            |
| Scroll ruim         | Olhar para baixo bloqueava o olhar (EAR), parando o scroll inferior                                                                         | Referência por faixa no EyeState                                                                                                 |
| Scroll ruim         | Tremor na borda da faixa zerava a espera de ativação                                                                                        | Histerese na entrada e na saída                                                                                                  |
| Scroll ruim         | Roda enviada sobre as abas / barra de tarefas                                                                                               | Cursor estacionado sobre o conteúdo durante o scroll                                                                             |
| Scroll ruim         | ~20 passos/s fixos, página "pulando"                                                                                                        | Velocidade proporcional à profundidade, com aceleração gradual                                                                   |
| Atraso              | Frames enfileirados no buffer da câmera                                                                                                     | Captura em thread, sempre o frame mais recente                                                                                   |

---

## Testes

Os testes não precisam de câmera nem de tela: usam um usuário simulado
(geometria olho + cabeça com ruído) e sinais de olhar sintéticos.

```bash
pip install -r requirements-dev.txt
python -m pytest -q
```

Cobrem: filtro de fixação vs One Euro/EMA, escada de piscadas, olhar para
baixo, piscada de um olho só, scroll (histerese, velocidade, pausa), modelo
com e sem compensação de cabeça, correção da sessão, critério da validação,
mapeamento do zoom e sessões completas (calibração → validação → uso):
desvio corrigido pela validação, calibração ruim refeita automaticamente,
cliques com zoom aprendendo a deriva e a trava do scroll (travado não rola,
piscada na alça destrava, piscada rolando freia sem clicar, alça alcançável
com desvio para a esquerda).

---

## Gravação para diagnóstico (tecla G)

Se o cursor não estiver indo para onde você olha, grave uma sessão: pressione
**G**, olhe para alguns pontos conhecidos da tela (cantos, centro, links) e
clique em algumas coisas; pressione **G** de novo. O arquivo
`eyenav_record_AAAAMMDD_HHMMSS.npz` (sem imagens da câmera) guarda, a cada
frame, as features dos olhos e da cabeça, a previsão do modelo, o olhar final
e o estado dos olhos, mais o resultado da validação e cada clique com zoom
(estimado × real). Com ele dá para reprocessar a sessão fora do tempo real e
ajustar o sistema aos seus dados. O `calibration.pkl` também guarda as
amostras da calibração.

---

## Métricas coletadas (Capítulo 4 do TC II)

Ao encerrar o sistema (ou pressionar **M**), é exibido um resumo com duração,
frames processados, FPS médio, latência média por frame e total de cliques
por tipo. O arquivo `eyenav_metrics.csv` contém um registro por clique:

- `timestamp` — momento do evento (Unix time)
- `gaze_x`, `gaze_y` — ponto de olhar estimado
- `target_x`, `target_y` — alvo conhecido (apenas em modo de teste)
- `error_px` — erro euclidiano em pixels (`nan` quando não há alvo)
- `dwell_ms` — tempo de dwell (0 para cliques por piscada)
- `kind` — `dwell`, `single`, `double` ou `right`

Medidas de precisão independentes de alvos de teste:

- erro de validação cruzada da calibração;
- erro da validação de 5 pontos (antes e depois da correção);
- erro medido em cada clique com zoom (estimado × real), exibido no console
  e no resumo final.

---

## Solução de problemas

| Sintoma                                          | Causa provável / solução                                                                                         |
| ------------------------------------------------ | ---------------------------------------------------------------------------------------------------------------- |
| `Backend: none`, cursor não se move, sem cliques | Nenhum backend instalado. Veja _Backend de controle do mouse_.                                                   |
| `can't open camera by index`                     | Ajuste `WEBCAM_INDEX` em `src/config.py`.                                                                        |
| Câmera abre em 640×480                           | A câmera não suporta 720p no índice escolhido.                                                                   |
| Validação reprova sempre                         | Melhore a iluminação frontal, centralize o rosto, fique a 50–70 cm. Veja no console qual ponto erra mais.        |
| Cursor deslocado depois de mudar de posição      | Refaça a validação (F) ou recalibre (R). Com zoom, os cliques corrigem sozinhos.                                 |
| Clique cai na janela de debug                    | Ela fica sempre por cima, no canto inferior direito. Reduza `DEBUG_WINDOW_SCALE`.                                |
| Zoom não abre                                    | `pip install mss`; não funciona em Wayland.                                                                      |
| Cursor não segue movimentos pequenos             | Reduza `FIX_SACCADE_SIGMAS` (ex.: 2,0).                                                                          |
| Cursor ainda treme                               | Aumente `FIX_WINDOW_MS` ou `FIX_TAU_MS`.                                                                         |
| Piscada lenta não clica                          | Feche os **dois** olhos; observe "abertura" no debug (fechado < 0,45).                                           |
| Scroll dispara sem querer                        | Ele só rola destravado: trave com uma piscada enquanto rola. Reduza `SCROLL_IDLE_LOCK_MS` para travar mais cedo. |
| Não consigo destravar o scroll                   | Olhe além da borda direita até a bola pulsar; ou use `SCROLL_HANDLE_SIDE = 'both'`. A tecla L também alterna.    |
| Sem bipes                                        | Instale `pulseaudio-utils` (paplay) ou `alsa-utils` (aplay).                                                     |
| Avisos `QFontDatabase` no terminal               | Inofensivos (fontes do Qt do OpenCV); podem ser ignorados.                                                       |
| Wayland com `ydotool` não responde               | Verifique se o daemon `ydotoold` está em execução.                                                               |

---

## Dicas para melhores resultados

1. **Iluminação:** luz frontal difusa. Evite luz forte atrás de você.
2. **Distância:** 50–70 cm da câmera, rosto inteiro visível.
3. **Calibração:** recalibre (R) se mudar de lugar, de cadeira ou de iluminação.
4. **Piscada lenta:** feche os olhos com calma, sem apertar; abra no bipe.
5. **Alvos pequenos:** use o zoom; quanto mais você clica com ele, melhor o
   cursor acompanha o seu olhar.

---

## Dependências principais

| Biblioteca    | Versão mín. | Uso                                             |
| ------------- | ----------- | ----------------------------------------------- |
| mediapipe     | 0.10.0      | FaceLandmarker (landmarks + íris + blendshapes) |
| opencv-python | 4.8.0       | Captura, processamento e janelas de interface   |
| numpy         | 1.24.0      | Operações matriciais e regressão                |
| pynput        | 1.7.6       | Controle do mouse (Windows/macOS)               |
| screeninfo    | 0.8.1       | Detecção da resolução e posição do monitor      |
| mss           | 9.0.0       | Captura de tela para o clique com zoom          |

Ferramentas de sistema opcionais (Linux): `ydotool` (Wayland), `xdotool` (X11, fallback).

---

## Referências bibliográficas

- BRADSKI, G.; KAEHLER, A. _Learning OpenCV_. O'Reilly, 2008.
- CASIEZ, G.; ROUSSEL, N.; VOGEL, D. 1€ Filter: a simple speed-based low-pass filter for noisy input in interactive systems. _ACM CHI_, 2012.
- JACOB, R. J. K. What you look at is what you get: eye movement-based interaction techniques. _ACM CHI_, 1990.
- KRAFKA, K. et al. Eye tracking for everyone. _IEEE CVPR_, 2016.
- KUMAR, M. et al. Improving the accuracy of gaze input for interaction. _ETRA_, 2008.
- KUMAR, M.; PAEPCKE, A.; WINOGRAD, T. EyePoint: practical pointing and selection using gaze and keyboard. _ACM CHI_, 2007.
- MAJARANTA, P.; BULLING, A. Eye tracking and eye-based HCI. Springer, 2014.
- MUNN, S. M. et al. How do I fixate thee? _ETRA_, 2008.
- PAPOUTSAKI, A. et al. WebGazer: scalable webcam eye tracking using user interactions. _IJCAI_, 2016.
- SIBERT, J. L.; JACOB, R. J. K. Evaluation of eye gaze interaction. _ACM CHI_, 2000.
- SOUKUPOVÁ, T.; ČECH, J. Real-time eye blink detection using facial landmarks. _Computer Vision Winter Workshop_, 2016.
- ŠPAKOV, O. Comparison of eye movement filters used in HCI. _ETRA_, 2012.
- ZHANG, X. et al. Appearance-based gaze estimation in the wild. _IEEE CVPR_, 2015.
- ZHU, Z.; JI, Q. Eye and gaze tracking. _Machine Vision and Applications_, 2005.
