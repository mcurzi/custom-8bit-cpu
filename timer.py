# Generador de interrupciones, timer de tiempo real

import time

class Timer:
    def __init__(self, freq_hz):
        self.timer_enabled = freq_hz > 0    # Si la frecuencia es 0, el timer se desactiva

        if self.timer_enabled:
            self.period = 1.0 / freq_hz
            self.next_fire = time.perf_counter() + self.period
        else:
            self.period = float('inf')    # Período infinito, no manda interrupciones
            self.next_fire = float('inf')

        self.state = False

    def update(self):
        if not self.timer_enabled: # Si está desactivado, sale sin calcular nada
            return

        now = time.perf_counter()
        fired = False

        while now >= self.next_fire:   # Verifica si pasó el tiempo del período
            self.next_fire += self.period
            fired = True

        if fired:
            self.state = True   # Envia la señal, que puede ser a una linea IRQ o NMI por ejemplo.
