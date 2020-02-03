from time import sleep


class LongSleepLoop:
    def __init__(self, timeout: int, func=None, args: tuple = None):
        self._timeout = timeout
        self._timer = 0
        self._active = True
        self._func = func
        self._args = args
        self._loop()

    def _loop(self):
        while self._active:
            if not self._timer:
                self._run()
                self._timer = self._timeout
            else:
                self._timer -= 1
                sleep(1)

    def _run(self):
        self.func(*self.args)

    def stop(self):
        self._active = False
