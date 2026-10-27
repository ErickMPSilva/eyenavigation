"""
Métricas da sessão (FPS, latência, cliques, trava do scroll) e exportação em CSV.
"""

import csv
import time
import statistics
from dataclasses import dataclass, asdict


@dataclass
class ClickEvent:
    timestamp:  float
    gaze_x:     int
    gaze_y:     int
    target_x:   int | None
    target_y:   int | None
    error_px:   float
    dwell_ms:   float
    kind:       str


class MetricsCollector:
    def __init__(self):
        self._frame_times_ms: list[float] = []
        self._clicks:         list[ClickEvent] = []
        self._scroll_locks:   list[tuple] = []
        self._session_start = time.time()

    def record_frame(self, dt_ms: float):
        self._frame_times_ms.append(dt_ms)

    def record_click(self, gx: int, gy: int,
                     dwell_ms: float,
                     target_x: int | None = None,
                     target_y: int | None = None,
                     kind: str = 'dwell'):
        if target_x is not None and target_y is not None:
            err = ((gx - target_x) ** 2 + (gy - target_y) ** 2) ** 0.5
        else:
            err = float('nan')

        self._clicks.append(ClickEvent(
            timestamp=time.time(),
            gaze_x=gx, gaze_y=gy,
            target_x=target_x, target_y=target_y,
            error_px=err, dwell_ms=dwell_ms, kind=kind
        ))

    def record_scroll_lock(self, locked: bool, reason: str, notches: int = 0):
        self._scroll_locks.append((locked, reason, notches))

    def summary(self) -> dict:
        ft = self._frame_times_ms
        errs = [c.error_px for c in self._clicks
                if not (c.error_px != c.error_px)]

        def safe_mean(lst):  return statistics.mean(lst) if lst else 0.0
        def safe_stdev(lst): return statistics.stdev(lst) if len(lst) > 1 else 0.0

        return {
            'duracao_sessao_s':    round(time.time() - self._session_start, 1),
            'frames_processados':  len(ft),
            'latencia_media_ms':   round(safe_mean(ft),  2),
            'latencia_stdev_ms':   round(safe_stdev(ft), 2),
            'fps_medio':           round(1000 / safe_mean(ft), 1) if ft else 0,
            'total_clicks':        len(self._clicks),
            'clicks_por_tipo':     {k: sum(c.kind == k for c in self._clicks)
                                    for k in sorted({c.kind for c in self._clicks})},
            'scroll_destravamentos': sum(not lk for lk, _, _ in self._scroll_locks),
            'scroll_sem_rolagem':  sum(lk and n == 0 for lk, _, n in self._scroll_locks),
            'scroll_travas_por_motivo': {
                r: sum(lk and m == r for lk, m, _ in self._scroll_locks)
                for r in sorted({m for lk, m, _ in self._scroll_locks if lk})},
            'erro_medio_px':       round(safe_mean(errs),  1),
            'erro_stdev_px':       round(safe_stdev(errs), 1),
        }

    def print_summary(self):
        s = self.summary()
        print()
        print('═' * 50)
        print('  EyeNav – Métricas da Sessão')
        print('═' * 50)
        print(f'  Duração               : {s["duracao_sessao_s"]} s')
        print(f'  Frames processados    : {s["frames_processados"]}')
        print(f'  FPS médio             : {s["fps_medio"]}')
        print(f'  Latência média        : {s["latencia_media_ms"]} ms '
              f'(±{s["latencia_stdev_ms"]} ms)')
        print(f'  Total de clicks       : {s["total_clicks"]}  '
              f'{s["clicks_por_tipo"] or ""}')
        if s['scroll_destravamentos']:
            print(f'  Scroll destravado     : {s["scroll_destravamentos"]}x '
                  f'({s["scroll_sem_rolagem"]} sem rolar) | travas: '
                  f'{s["scroll_travas_por_motivo"]}')
        if s['total_clicks'] > 0:
            print(f'  Erro médio (gaze→alvo): {s["erro_medio_px"]} px '
                  f'(±{s["erro_stdev_px"]} px)')
        print('═' * 50)
        print()

    def save_csv(self, path: str = 'eyenav_metrics.csv'):
        if not self._clicks:
            print('[Metrics] Nenhum click registrado para salvar.')
            return
        with open(path, 'w', newline='', encoding='utf-8') as f:
            writer = csv.DictWriter(f, fieldnames=asdict(self._clicks[0]).keys())
            writer.writeheader()
            for c in self._clicks:
                writer.writerow(asdict(c))
        print(f'[Metrics] CSV salvo → {path}')
