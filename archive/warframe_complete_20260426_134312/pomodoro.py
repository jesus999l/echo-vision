"""Pomodoro timer module."""
import time, threading

class PomodoroTimer:
    def __init__(self, on_tick=None, on_complete=None):
        self.work_mins = 25
        self.break_mins = 5
        self.on_tick = on_tick
        self.on_complete = on_complete
        self._thread = None
        self._running = False
        self._paused = False
        self.mode = "work"  # work | break
        self.seconds_left = self.work_mins * 60
        self.sessions = 0
        self.linked_task = None

    def start(self):
        self._running = True
        self._paused = False
        self._thread = threading.Thread(target=self._loop, daemon=True)
        self._thread.start()

    def pause(self):
        self._paused = not self._paused

    def stop(self):
        self._running = False
        self.seconds_left = self.work_mins * 60
        self.mode = "work"

    def skip(self):
        self._switch_mode()

    def _switch_mode(self):
        if self.mode == "work":
            self.sessions += 1
            self.mode = "break"
            self.seconds_left = self.break_mins * 60
        else:
            self.mode = "work"
            self.seconds_left = self.work_mins * 60
        if self.on_complete:
            self.on_complete(self.mode, self.sessions)

    def _loop(self):
        while self._running and self.seconds_left > 0:
            if not self._paused:
                time.sleep(1)
                self.seconds_left -= 1
                if self.on_tick:
                    self.on_tick(self.seconds_left, self.mode)
            else:
                time.sleep(0.1)
        if self._running and self.seconds_left <= 0:
            self._switch_mode()
            self._loop()

    def fmt_time(self):
        m, s = divmod(self.seconds_left, 60)
        return f"{m:02d}:{s:02d}"

    @property
    def progress(self):
        total = (self.work_mins if self.mode=="work" else self.break_mins) * 60
        return 1 - (self.seconds_left / total)
