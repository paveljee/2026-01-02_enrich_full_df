from __future__ import annotations

import threading
import time

import psutil


class ResourceMonitor:
    def __init__(self) -> None:
        self.process = psutil.Process()
        self.running = False
        self.peak_memory = 0
        self.thread: threading.Thread | None = None

    def start(self) -> None:
        self.running = True
        self.thread = threading.Thread(target=self._monitor, daemon=True)
        self.thread.start()

    def _monitor(self) -> None:
        while self.running:
            mem = self.process.memory_info().rss
            if mem > self.peak_memory:
                self.peak_memory = mem
            time.sleep(0.1)

    def stop(self) -> float:
        self.running = False
        if self.thread:
            self.thread.join()
        return self.peak_memory / (1024**3)
