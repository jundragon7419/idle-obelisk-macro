"""LD플레이어 ADB 연결, 화면 캡처, 탭.

캡처 방식
- raw (기본): `screencap` 결과를 압축 없이 받는다. PNG 압축을 하지 않아 에뮬레이터 CPU
  부담이 적고 해독도 빠르다. 형식을 알 수 없으면 png로 자동 전환한다.
- stream (선택): `screenrecord` 영상을 계속 받아 최신 프레임을 쓴다 (core/stream.py).
  캡처마다 새 프로세스를 띄우지 않는다. 쓸 수 없으면 raw로 돌아간다.

캡처가 실패하면 2, 5, 10, 20, 30초 간격으로 다시 시도하고 기기를 다시 연결한다.
탭과 스와이프는 실패해도 다시 실행하지 않는다 (같은 구매를 두 번 하지 않도록).
"""
import random
import struct
import subprocess
import threading
import time
from typing import Callable

import cv2
import numpy as np

SCREEN_W, SCREEN_H = 720, 1280   # 인식 코드와 견본이 쓰는 좌표계

# 게임은 540×960으로 그리고, LD플레이어를 720×1280으로 두면 4칸 중 한 칸을 복제해서 늘린다.
# 540×960으로 두면 같은 복제를 여기서 해서 720×1280 화면과 픽셀까지 똑같이 만든다
# (720 화면을 540으로 줄였다 다시 늘리면 원본과 완전히 같음을 확인함).
NATIVE_W, NATIVE_H = 540, 960
_UP = [0, 1, 1, 2]
_MAP_X = np.array([(i // 4) * 3 + _UP[i % 4] for i in range(SCREEN_W)])
_MAP_Y = np.array([(i // 4) * 3 + _UP[i % 4] for i in range(SCREEN_H)])
_NO_WINDOW = getattr(subprocess, "CREATE_NO_WINDOW", 0)
RETRY_DELAYS = (2, 5, 10, 20, 30)


class AdbError(RuntimeError):
    pass


class ConfigError(AdbError):
    """해상도나 경로처럼 다시 시도해도 해결되지 않는 오류."""


class Adb:
    def __init__(self, adb_path: str, serial: str = "", press_ms: int = 0,
                 log: Callable[..., object] | None = None,
                 sleep: Callable[[float], None] = time.sleep,
                 capture_mode: str = "raw"):
        self.adb_path = adb_path
        self.press_ms = press_ms
        self.log = log or (lambda *a, **k: None)
        self.sleep = sleep
        self.capture_mode = capture_mode if capture_mode in ("raw", "png") else "raw"
        self.stream = None            # stream.AdbStream (start_stream로 켬)
        self.capture_count = 0        # 메모리 감시 기록용
        self.input_scale = 1.0        # 540×960이면 0.75 (720 좌표 → 기기 좌표)
        self.device_size: tuple[int, int] | None = None
        self.serial = serial or self._find_device()
        # 디버그 스크린샷용: 마지막 캡처를 기억하고, 탭 이후에는 낡은 것으로 본다
        self._lock = threading.Lock()
        self._last_frame = None
        self._last_time = 0.0

    # ── 명령 실행 ────────────────────────────────
    def _run(self, *args, serial=True, timeout=10) -> bytes:
        cmd = [self.adb_path]
        if serial:
            cmd += ["-s", self.serial]
        cmd += list(args)
        try:
            r = subprocess.run(cmd, capture_output=True, timeout=timeout,
                               creationflags=_NO_WINDOW)
        except FileNotFoundError:
            raise ConfigError(f"adb.exe를 찾을 수 없습니다: {self.adb_path}")
        except subprocess.TimeoutExpired:
            raise AdbError(f"ADB 명령 시간 초과: {' '.join(args)}")
        if r.returncode != 0:
            raise AdbError(r.stderr.decode(errors="ignore").strip() or f"ADB 명령 실패: {' '.join(args)}")
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

    def _reconnect(self):
        """캡처 복구용 재연결. 실패해도 다음 재시도에서 다시 해 본다."""
        try:
            if ":" in self.serial:
                self._run("connect", self.serial, serial=False, timeout=8)
            elif self.serial not in self._list_devices():
                self.serial = self._find_device()
        except AdbError:
            pass

    # ── 캡처 ─────────────────────────────────────
    def _decode_raw(self, data: bytes) -> np.ndarray:
        """screencap raw: 머리말(너비, 높이, 형식[, 색공간]) + RGBA 픽셀."""
        if len(data) < 16:
            raise AdbError("화면 캡처 결과가 비어 있습니다")
        w, h, fmt = struct.unpack_from("<III", data, 0)
        pixels = w * h * 4
        header = len(data) - pixels
        if fmt != 1 or header not in (12, 16) or w <= 0 or h <= 0:
            raise ValueError(f"알 수 없는 raw 형식 (w={w}, h={h}, fmt={fmt}, 머리말 {header}바이트)")
        rgba = np.frombuffer(data, np.uint8, count=pixels, offset=header).reshape(h, w, 4)
        return cv2.cvtColor(rgba, cv2.COLOR_RGBA2BGR)

    def _capture_once(self, exact: bool = False) -> np.ndarray:
        if self.stream is not None and not exact:
            img = self.stream.read_fresh()
            if img is not None:
                return img
            # 새 프레임이 없으면 한 번만 직접 캡처 (오래된 화면으로 판단하지 않음)
        if self.capture_mode == "raw":
            data = self._run("exec-out", "screencap")
            try:
                return self._decode_raw(data)
            except ValueError as e:
                self.log(f"raw 캡처 형식을 읽을 수 없어 PNG 캡처로 바꿉니다: {e}", problem=True)
                self.capture_mode = "png"
        png = self._run("exec-out", "screencap", "-p")
        img = cv2.imdecode(np.frombuffer(png, np.uint8), cv2.IMREAD_COLOR)
        if img is None:
            raise AdbError("화면 캡처 결과를 읽을 수 없습니다")
        return img

    def screenshot(self, exact: bool = False) -> np.ndarray:
        """새 화면을 캡처한다. 실패하면 간격을 늘려 가며 다시 시도한다.

        exact=True면 연속 캡처(영상) 중이어도 screencap으로 압축 없는 화면을 받는다
        (숫자가 조금 바뀌었는지 비교할 때처럼 픽셀이 정확해야 할 때만 쓴다).
        """
        attempt = 0
        while True:
            try:
                img = self._capture_once(exact)
                break
            except ConfigError:
                raise
            except AdbError as e:
                if attempt >= len(RETRY_DELAYS):
                    raise AdbError(f"캡처 복구 실패 ({attempt}회 재시도): {e}")
                delay = RETRY_DELAYS[attempt]
                attempt += 1
                self.log(f"캡처 실패 ({e}). {delay}초 뒤 재연결 후 다시 캡처합니다 "
                         f"({attempt}/{len(RETRY_DELAYS)}). 탭은 다시 하지 않습니다.", problem=True)
                self.sleep(delay)   # 정지 요청 시 여기서 빠져나감
                self._reconnect()
                if self.stream is not None:
                    self.stream.restart()
        if attempt:
            self.log(f"캡처 복구 성공 ({attempt}회 재시도). 새 화면으로 다시 판단합니다.")
        h, w = img.shape[:2]
        if (w, h) == (NATIVE_W, NATIVE_H):
            img = img[_MAP_Y][:, _MAP_X]
            self.input_scale = NATIVE_W / SCREEN_W
        elif (w, h) == (SCREEN_W, SCREEN_H):
            self.input_scale = 1.0
        else:
            raise ConfigError(f"해상도가 {w}x{h}입니다. LD플레이어 해상도를 "
                              f"{NATIVE_W}x{NATIVE_H} 또는 {SCREEN_W}x{SCREEN_H}(세로)로 맞춰주세요.")
        self.device_size = (w, h)
        self.capture_count += 1
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
        if self.stream is not None:
            self.stream.mark_input()

    # ── 연속 캡처 ────────────────────────────────
    def start_stream(self) -> bool:
        from .stream import AdbStream, StreamUnavailable
        try:
            self.stream = AdbStream(self.adb_path, self.serial, log=self.log)
            self.stream.start()
            return True
        except StreamUnavailable as e:
            self.log(f"연속 캡처를 쓸 수 없어 일반 캡처로 진행합니다: {e}", problem=True)
            self.stream = None
            return False

    def close(self):
        if self.stream is not None:
            self.stream.close()
            self.stream = None

    # ── 입력 ─────────────────────────────────────
    def tap(self, x: int, y: int, jitter: int = 0):
        if jitter:
            x += random.randint(-jitter, jitter)
            y += random.randint(-jitter, jitter)
        self._ensure_size()
        x, y = self._to_device(x), self._to_device(y)
        if self.press_ms > 0:
            # 짧게 누르고 떼기. 순간 탭을 놓치는 UI가 있어 기본으로 쓴다
            self._run("shell", "input", "swipe", x, y, x, y, str(self.press_ms))
        else:
            self._run("shell", "input", "tap", x, y)
        self._invalidate()

    def swipe(self, x1: int, y1: int, x2: int, y2: int, ms: int = 500):
        self._ensure_size()
        self._run("shell", "input", "swipe", *(self._to_device(v) for v in (x1, y1, x2, y2)),
                  str(int(ms)))
        self._invalidate()

    def _ensure_size(self):
        if self.device_size is None:   # 배율을 알기 전에 입력하지 않도록 한 번 캡처
            self.screenshot()

    def _to_device(self, v) -> str:
        """720×1280 좌표를 기기 좌표로 (540×960이면 0.75배)."""
        return str(int(round(v * self.input_scale)))

    def back(self):
        self._run("shell", "input", "keyevent", "4")
        self._invalidate()
