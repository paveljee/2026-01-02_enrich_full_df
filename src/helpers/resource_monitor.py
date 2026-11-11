from __future__ import annotations

import threading
import time

import psutil


def occupied_ram_plus_swap_bytes() -> int:
    vm = psutil.virtual_memory()
    return vm.total - vm.free + psutil.swap_memory().used


class ResourceMonitor:
    def __init__(self) -> None:
        self.running = False
        self.peak_memory = 0
        self.thread: threading.Thread | None = None

    def start(self) -> None:
        self.peak_memory = occupied_ram_plus_swap_bytes()
        self.running = True
        self.thread = threading.Thread(target=self._monitor, daemon=True)
        self.thread.start()

    def _monitor(self) -> None:
        while self.running:
            mem = occupied_ram_plus_swap_bytes()
            if mem > self.peak_memory:
                self.peak_memory = mem
            time.sleep(0.1)

    def stop(self) -> float:
        self.running = False
        if self.thread:
            self.thread.join()
        self.peak_memory = max(self.peak_memory, occupied_ram_plus_swap_bytes())
        return self.peak_memory / (1024**3)
