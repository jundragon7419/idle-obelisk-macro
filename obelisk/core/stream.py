"""연속 캡처: `adb exec-out screenrecord` H.264 영상을 PyAV로 해독해 최신 프레임을 보관한다.

screencap처럼 캡처마다 새 프로세스를 띄우지 않는다. screenrecord는 한 번에 최대 3분까지만
녹화하므로 끝나면 다시 연결한다.

오래된 화면 방지
- 영상은 화면이 바뀔 때만 프레임이 온다. 그래서 마지막 탭/스와이프 뒤에 들어온 프레임만 쓴다.
- 기다려도 새 프레임이 없으면 None을 돌려주고, 호출한 쪽(Adb)이 그 한 번은 일반 캡처를 한다.
- BGR 이미지로 바꾸는 작업은 화면이 실제로 필요할 때만 해서 CPU를 아낀다.
"""
import subprocess
import threading
import time

_NO_WINDOW = getattr(subprocess, "CREATE_NO_WINDOW", 0)
SEGMENT_SEC = 170          # screenrecord 최대 180초보다 조금 짧게
INPUT_SETTLE = 0.25        # 탭 직후 화면이 바뀌어 영상에 반영되기까지 여유
MAX_FRAME_AGE = 5.0        # 이보다 오래된 프레임은 믿지 않고 일반 캡처로 확인


class StreamUnavailable(RuntimeError):
    pass


class _Pipe:
    """PyAV가 파이프를 파일처럼 읽도록 감싼다 (탐색 불가)."""

    def __init__(self, pipe):
        self.pipe = pipe

    def read(self, size=-1):
        return self.pipe.read(size)

    def seekable(self):
        return False

    def readable(self):
        return True


class AdbStream:
    def __init__(self, adb_path: str, serial: str, log=None, bit_rate: int = 4_000_000):
        try:
            import av  # noqa: F401
        except ImportError:
            raise StreamUnavailable("PyAV(av 패키지)가 설치되어 있지 않습니다. pip install av")
        self.adb_path, self.serial, self.bit_rate = adb_path, serial, bit_rate
        self.log = log or (lambda *a, **k: None)
        self._cond = threading.Condition()
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None
        self._proc: subprocess.Popen | None = None
        self._frame = None          # 최신 av.VideoFrame (아직 변환 전)
        self._frame_t = 0.0
        self._input_t = 0.0
        self.frames = 0             # 받은 프레임 수 (상태 표시용)
        self.failed = False

    # ── 수명 ─────────────────────────────────────
    def start(self):
        self._thread = threading.Thread(target=self._run, name="adb-stream", daemon=True)
        self._thread.start()

    def close(self):
        self._stop.set()
        self._kill()
        if self._thread is not None:
            self._thread.join(timeout=3)
        with self._cond:
            self._frame = None
            self._cond.notify_all()

    def restart(self):
        """현재 녹화를 끊는다. 스레드가 곧바로 다시 연결한다."""
        self._kill()

    def _kill(self):
        proc = self._proc
        if proc is not None and proc.poll() is None:
            try:
                proc.kill()
            except OSError:
                pass

    @property
    def alive(self) -> bool:
        return self._thread is not None and self._thread.is_alive() and not self.failed

    # ── 받기 ─────────────────────────────────────
    def _run(self):
        import av
        quick_failures = 0
        while not self._stop.is_set():
            started = time.monotonic()
            got = 0
            try:
                self._proc = subprocess.Popen(
                    [self.adb_path, "-s", self.serial, "exec-out", "screenrecord",
                     "--output-format=h264", "--bit-rate", str(self.bit_rate),
                     "--time-limit", str(SEGMENT_SEC), "-"],
                    stdout=subprocess.PIPE, stderr=subprocess.DEVNULL,
                    stdin=subprocess.DEVNULL, creationflags=_NO_WINDOW, bufsize=0)
                with av.open(_Pipe(self._proc.stdout), format="h264", mode="r",
                             options={"probesize": "32768", "analyzeduration": "0"}) as container:
                    for frame in container.decode(video=0):
                        if self._stop.is_set():
                            break
                        got += 1
                        with self._cond:
                            self._frame, self._frame_t = frame, time.monotonic()
                            self.frames += 1
                            self._cond.notify_all()
            except Exception as e:  # 연결 끊김, 해독 오류 등
                if not self._stop.is_set():
                    self.log(f"연속 캡처 끊김: {type(e).__name__}: {e}")
            finally:
                self._kill()
            if self._stop.is_set():
                break
            # 녹화 시간이 끝나서 끊긴 것은 정상. 몇 초 안에 프레임 없이 끊기는 일이 반복되면 포기
            if got == 0 and time.monotonic() - started < 5:
                quick_failures += 1
                if quick_failures >= 3:
                    self.failed = True
                    self.log("연속 캡처가 계속 바로 끊겨 일반 캡처로 바꿉니다. "
                             "LD플레이어가 screenrecord를 지원하지 않을 수 있습니다.", problem=True)
                    return
            else:
                quick_failures = 0
            self._stop.wait(1.0)

    # ── 읽기 ─────────────────────────────────────
    def mark_input(self):
        with self._cond:
            self._input_t = time.monotonic()

    def read_fresh(self, timeout: float = 1.0):
        """마지막 입력 뒤에 들어온 프레임을 BGR 배열로 돌려준다. 없으면 None."""
        if not self.alive:
            return None
        deadline = time.monotonic() + timeout
        with self._cond:
            while True:
                now = time.monotonic()
                ok = (self._frame is not None
                      and self._frame_t > self._input_t + INPUT_SETTLE
                      and now - self._frame_t <= MAX_FRAME_AGE)
                if ok:
                    frame = self._frame
                    break
                if now >= deadline or self._stop.is_set():
                    return None
                self._cond.wait(min(0.2, deadline - now))
        return frame.to_ndarray(format="bgr24")
