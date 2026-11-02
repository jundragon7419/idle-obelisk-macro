"""LD플레이어 ADB 연결, 화면 캡처, 탭."""
import random
import subprocess
import threading
import time

import cv2
import numpy as np

SCREEN_W, SCREEN_H = 720, 1280
_NO_WINDOW = getattr(subprocess, "CREATE_NO_WINDOW", 0)


class AdbError(RuntimeError):
    pass


class Adb:
    def __init__(self, adb_path: str, serial: str = "", press_ms: int = 0):
        self.adb_path = adb_path
        self.press_ms = press_ms
        self.serial = serial or self._find_device()
        # 디버그 스크린샷용: 마지막 캡처를 기억하고, 탭 이후에는 낡은 것으로 본다
        self._lock = threading.Lock()
        self._last_frame = None
        self._last_time = 0.0

    def _run(self, *args, serial=True, timeout=10) -> bytes:
        cmd = [self.adb_path]
        if serial:
            cmd += ["-s", self.serial]
        cmd += list(args)
        try:
            r = subprocess.run(cmd, capture_output=True, timeout=timeout,
                               creationflags=_NO_WINDOW)
        except FileNotFoundError:
            raise AdbError(f"adb.exe를 찾을 수 없습니다: {self.adb_path}")
        except subprocess.TimeoutExpired:
            raise AdbError(f"ADB 명령 시간 초과: {' '.join(args)}")
        if r.returncode != 0:
            raise AdbError(r.stderr.decode(errors="ignore").strip())
        return r.stdout

    def _list_devices(self) -> list[str]:
        out = self._run("devices", serial=False).decode(errors="ignore")
        return [l.split()[0] for l in out.splitlines()[1:]
                if l.strip().endswith("device")]

    def _find_device(self) -> str:
        devs = self._list_devices()
        if not devs:
            # LD플레이어 첫 인스턴스 기본 포트
            self._run("connect", "127.0.0.1:5555", serial=False)
            devs = self._list_devices()
        if not devs:
            raise AdbError("연결된 기기가 없습니다. LD플레이어 설정 → 기타 설정 → "
                           "ADB 디버깅을 '로컬 연결 열기'로 바꿨는지 확인하세요.")
        return devs[0]

    def screenshot(self) -> np.ndarray:
        png = self._run("exec-out", "screencap", "-p")
        img = cv2.imdecode(np.frombuffer(png, np.uint8), cv2.IMREAD_COLOR)
        if img is None:
            raise AdbError("화면 캡처 실패")
        h, w = img.shape[:2]
        if (w, h) != (SCREEN_W, SCREEN_H):
            raise AdbError(f"해상도가 {w}x{h}입니다. LD플레이어 해상도를 "
                           f"{SCREEN_W}x{SCREEN_H}(세로)로 맞춰주세요.")
        with self._lock:
            self._last_frame, self._last_time = img, time.monotonic()
        return img

    def current_frame(self, max_age: float = 1.0) -> np.ndarray:
        """최근 캡처가 있고 그 뒤로 탭이 없었으면 재사용, 아니면 새로 캡처."""
        with self._lock:
            frame, age = self._last_frame, time.monotonic() - self._last_time
        if frame is not None and age <= max_age:
            return frame
        return self.screenshot()

    def _invalidate(self):
        with self._lock:
            self._last_frame = None

    def tap(self, x: int, y: int, jitter: int = 0):
        if jitter:
            x += random.randint(-jitter, jitter)
            y += random.randint(-jitter, jitter)
        x, y = str(int(x)), str(int(y))
        if self.press_ms > 0:
            # 짧게 누르고 떼기. 순간 탭을 놓치는 UI가 있어 기본으로 쓴다
            self._run("shell", "input", "swipe", x, y, x, y, str(self.press_ms))
        else:
            self._run("shell", "input", "tap", x, y)
        self._invalidate()

    def swipe(self, x1: int, y1: int, x2: int, y2: int, ms: int = 500):
        self._run("shell", "input", "swipe", *(str(int(v)) for v in (x1, y1, x2, y2, ms)))
        self._invalidate()

    def back(self):
        self._run("shell", "input", "keyevent", "4")
        self._invalidate()
