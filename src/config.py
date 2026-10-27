"""
Configurações do EyeNav: ajuste aqui hardware, tempos e preferências.
"""

# Câmera
WEBCAM_INDEX  = 0       # Índice da câmera (0 = padrão, 1 = segunda câmera)
WEBCAM_WIDTH  = 1280
WEBCAM_HEIGHT = 720
TARGET_FPS    = 30
CAMERA_MIRROR = True    # Espelha a imagem (movimento natural no debug)

# Calibração
CALIB_COLS         = 4      # Colunas da grade de calibração
CALIB_ROWS         = 4      # Linhas  (total = COLS × ROWS = 16 pontos)
CALIB_MARGIN_X     = 0.08   # Margem lateral (proporção da largura)
CALIB_MARGIN_Y     = 0.06   # Margem vertical (pontos perto das zonas de scroll)
CALIB_FACE_WAIT_MS = 2000   # Rosto estável antes de começar
CALIB_PULSE_MS     = 1000   # Pulso: olho chega ao ponto (sem coleta)
CALIB_CAPTURE_MS   = 1200   # Captura: cada frame vira uma amostra
CALIB_HEAD_MOTION  = True   # Etapa de movimento da cabeça (ESPAÇO pula)
CALIB_HEAD_STEP_MS = 1300   # Duração de cada etapa (8 etapas)
CALIB_RIDGE_ALPHAS = (0.3, 3.0, 30.0, 300.0)   # Regularizações testadas (validação cruzada)

# Validação (5 pontos; se reprovar, recalibra até CALIB_MAX_ATTEMPTS vezes)
VALIDATION_ENABLED       = True
VALIDATION_PULSE_MS      = 1000   # Pulso: olho chega ao ponto (sem coleta)
VALIDATION_CAPTURE_MS    = 1500   # Tempo de coleta com rosto detectado
VALIDATION_TIMEOUT_MS    = 8000   # Sem rosto/olho aberto nesse tempo → ponto falhou
VALIDATION_MAX_ERROR_PX  = 110    # Erro médio aceitável (após a correção)
VALIDATION_RESULT_MS     = 3000   # Tempo mostrando o resultado na tela
CALIB_MAX_ATTEMPTS       = 3      # Calibrações seguidas antes de desistir
ONE_EURO_TARGET_JITTER_PX = 12    # (One Euro) tremor residual desejado
ONE_EURO_MIN_CUTOFF_FLOOR = 0.15  # (One Euro) Hz. Nunca suavizar mais que isso

# Correção do olhar na sessão (aprendida na validação e nos cliques com zoom)
CORR_HALF_LIFE_S     = 900    # Amostras perdem metade do peso a cada 15 min
CORR_DRIFT_HALF_LIFE_S = 120  # Deriva segue os cliques dos últimos ~2 min
CORR_MAX_SAMPLES     = 40
CORR_LOCAL_MIN       = 6      # Amostras para ativar a correção local (por região)
CORR_LOCAL_SIGMA     = 0.18   # Alcance da correção local (fração da largura)
CORR_MAX_GAIN_CHANGE = 0.5    # Ganho limitado a 0,5–1,5

FEATURE_VERSION  = 3       # Muda quando as features mudam (invalida calibração antiga)
CALIB_FILE       = 'calibration.pkl'

# Suavização do olhar
SMOOTHER            = 'fixation'  # 'fixation' (recomendado), 'one_euro' ou 'ema'

# Filtro de fixação (SMOOTHER = 'fixation')
FIX_WINDOW_MS       = 1000   # Janela da média durante a fixação (↑ = mais estável)
FIX_SACCADE_SIGMAS  = 2.5    # Distância (em desvios do ruído) que indica possível sacada
FIX_SACCADE_FRAMES  = 3      # Amostras consistentes para confirmar a sacada
FIX_NOISE_INIT_PX   = (35, 50)   # Ruído inicial (x, y); a validação mede o real
FIX_NOISE_MIN_PX    = 10     # Limites do ruído estimado
FIX_NOISE_MAX_PX    = 140
FIX_TAU_MS          = 250    # Suavização visual do cursor durante a fixação
FIX_TAU_SACCADE_MS  = 35     # ... e logo após uma sacada (resposta rápida)

# One Euro / EMA (comparação)
MEDIAN_WINDOW       = 7      # Frames da mediana (remove picos isolados)
ONE_EURO_MIN_CUTOFF = 0.15   # Hz. ↓ = menos tremor com o olhar parado
ONE_EURO_BETA       = 0.001  # ↑ = menos atraso quando o olhar se move
ONE_EURO_D_CUTOFF   = 1.0    # Hz. Suavização da estimativa de velocidade
SMOOTH_ALPHA        = 0.12   # Usado apenas se SMOOTHER = 'ema'

# Mapeamento final do cursor (o ganho agora é aprendido na validação)
EDGE_SNAP_PX       = 40    # A menos disso da borda, o cursor "gruda" na borda
CURSOR_DEADZONE_PX = 3     # Movimentos menores que isso não são enviados ao SO

# Estado dos olhos (abertura relativa à normal da faixa da tela olhada)
EYE_BANDS          = 3      # Faixas verticais da tela com referência própria
EYE_GATE_RATIO     = 0.72   # Algum olho abaixo disso → olhar ignorado
EYE_CLOSED_RATIO   = 0.45   # Os dois olhos abaixo disso → olhos fechados
EYE_REOPEN_RATIO   = 0.60   # Algum olho acima disso → reabriu
EYE_GRACE_MS       = 150    # Olhar continua ignorado por este tempo após reabrir
EYE_PARTIAL_MAX_MS = 800    # Semifechado por mais que isso não é piscada (nova referência)

# Blink Click (olhos fechados por: clique → duplo → direito → cancela)
BLINK_CLICK_ENABLED   = True   # Liga/desliga com a tecla B
BLINK_CLICK_MS        = 600    # Abaixo disso: piscada natural, ignorada
BLINK_DOUBLE_MS       = 1300
BLINK_RIGHT_MS        = 2100
BLINK_CANCEL_MS       = 3500
BLINK_COOLDOWN_MS     = 400    # Pausa mínima entre cliques por piscada
BLINK_POS_LOOKBACK_MS = 120    # O clique usa a posição do olhar de antes da piscada

# Dwell Click (fixação)
DWELL_CLICK_ENABLED = False  # Desligado: ao ler, clicaria sem querer (tecla D)
DWELL_TIME_MS       = 1500   # Milissegundos fixando para acionar clique
DWELL_RADIUS_PX     = 70     # Raio de tolerância (pixels)
DWELL_REARM_PX      = 120    # Após clicar, distância para permitir novo clique

# Edge Scroll
SCROLL_ENABLED        = True
SCROLL_ZONE_TOP       = 0.12   # Faixa do topo (fração da altura da tela)
SCROLL_ZONE_BOTTOM    = 0.12   # Faixa da base
SCROLL_ACTIVATE_MS    = 500    # Tempo na faixa antes de começar a rolar
SCROLL_HYSTERESIS_PX  = 40     # Para sair, o olhar precisa ir este tanto além da faixa
SCROLL_MIN_RATE       = 2.0    # "Cliques" da roda por segundo na borda interna da faixa
SCROLL_MAX_RATE       = 9.0    # ... e na borda da tela
SCROLL_RAMP_MS        = 600    # Aceleração gradual após começar
SCROLL_PARK_CURSOR    = True   # Durante o scroll, o cursor fica sobre o conteúdo
SCROLL_PARK_OFFSET_PX = 80     # (e não sobre abas/barra de tarefas) a esta distância da faixa
SCROLL_PARK_AVOID_DEBUG = True # ... e fora da janela de debug (senão a roda vai para ela)
SCROLL_MAX_RUN_MS     = 10000  # Rolagem contínua máxima por entrada na faixa (0 = sem limite)
SCROLL_OFFSCREEN_MARGIN = 0.20 # Olhar além disso fora da tela (teclado, colo) não rola (0 = desliga)
SCROLL_OFFSCREEN_MS   = 400    # ... por pelo menos este tempo

# Trava do scroll (alça no meio da borda direita; ver README)
SCROLL_LOCK_ENABLED        = True    # False = scroll sempre ativo (como antes)
SCROLL_START_LOCKED        = True
SCROLL_HANDLE_SIDE         = 'right' # 'right', 'left' ou 'both'
SCROLL_HANDLE_WIDTH_PX     = 60      # Largura mínima da região (a partir da borda)
SCROLL_HANDLE_MAX_WIDTH_PX = 120     # Largura máxima (cresce com o erro da validação)
SCROLL_HANDLE_CY           = 0.50    # Centro vertical (fração da altura)
SCROLL_HANDLE_HALF_H       = 0.20    # Meia altura mínima (fração da altura)
SCROLL_HANDLE_MAX_HALF_H   = 0.25    # Meia altura máxima
SCROLL_HANDLE_FIT_ERROR    = True    # Ajusta o tamanho ao erro medido na validação
SCROLL_HANDLE_MARGIN_PX    = 30      # Histerese para o olhar sair da alça
SCROLL_HANDLE_MIN_FIX_MS   = 300     # Olhar na alça por este tempo para ela "acender"
SCROLL_HANDLE_DWELL_MS     = 2000    # Sem blink click (tecla B): fixar a alça alterna a trava
SCROLL_HANDLE_BAR          = True    # Barra visível marcando a alça (X11)
SCROLL_HANDLE_BAR_PX       = 6
SCROLL_HANDLE_PULSE_HZ     = 2       # Pulso da bola com a alça acesa (0 = cor sólida)
SCROLL_BRAKE_MS            = 500     # Rolou há menos disso: a piscada só freia e trava
SCROLL_IDLE_LOCK_MS        = 15000   # Destravado sem rolar por este tempo → trava (0 = nunca)
SCROLL_LOCK_ON_CLICK       = True    # Clique e abertura do zoom travam
SCROLL_LOCK_ON_CANCEL      = True    # Olhos fechados até o bipe grave travam
SCROLL_LOCK_FACE_LOST_MS   = 2000    # Rosto ausente por este tempo → trava (0 = nunca)
SCROLL_HINT_MS             = 1500    # Travado e olhando uma faixa por este tempo → a barra pisca
SCROLL_HINT_DURATION_MS    = 1000
SCROLL_HINT_EVERY_S        = 30      # Intervalo mínimo entre dicas

# Clique com zoom (1ª piscada amplia, 2ª clica)
ZOOM_CLICK_ENABLED = True   # Liga/desliga com a tecla Z
ZOOM_FACTOR        = 2.5    # O erro do clique fica dividido por este fator
ZOOM_TIMEOUT_S     = 10     # Sem 2ª piscada nesse tempo → zoom fecha

# Interface
SHOW_DEBUG_WINDOW  = True  # Janela OpenCV com feed da câmera e métricas
DEBUG_WINDOW_SCALE = 0.55  # Escala da janela de debug
CURSOR_MOVE        = True  # False = só debug, sem mover cursor do SO
GAZE_DOT_ENABLED   = True  # Bola sobre a tela no ponto de olhar (X11)
GAZE_DOT_RADIUS    = 12    # Raio da bola (px)
GAZE_DOT_COLOR     = (255, 0, 0)  # RGB
GAZE_DOT_UNLOCKED_COLOR = (170, 80, 255)  # Scroll destravado
GAZE_DOT_HANDLE_COLOR   = (255, 255, 255) # Pulso com o olhar na alça
SOUND_ENABLED      = True  # Bipes de confirmação (piscada lenta, clique)

# Landmarks do MediaPipe (478 pontos com íris)
LEFT_IRIS_CENTER  = 468
RIGHT_IRIS_CENTER = 473
LEFT_EYE_OUTER    = 33
LEFT_EYE_INNER    = 133
LEFT_EYE_TOP      = 159
LEFT_EYE_BOTTOM   = 145

RIGHT_EYE_INNER   = 362
RIGHT_EYE_OUTER   = 263
RIGHT_EYE_TOP     = 386
RIGHT_EYE_BOTTOM  = 374
