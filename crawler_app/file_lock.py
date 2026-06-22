from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
import os
import time


# 파일 lock timeout 관련 데이터를 표현하는 객체다.
class FileLockTimeout(TimeoutError):
    pass


# 파일 lock의 상태와 실행 동작을 관리한다.
@dataclass(slots=True)
class FileLock:
    target_path: Path
    timeout_seconds: float = 10.0
    stale_seconds: float = 300.0
    poll_seconds: float = 0.1
    lock_path: Path | None = None
    _acquired: bool = False

    # 객체 생성 직후 lock 파일 경로를 확정한다.
    def __post_init__(self) -> None:
        self.target_path = Path(self.target_path)
        self.lock_path = self.target_path.with_name(f".{self.target_path.name}.lock")

    # with 블록 진입 시 파일 lock을 획득한다.
    def __enter__(self) -> "FileLock":
        deadline = time.monotonic() + max(0.0, self.timeout_seconds)
        while True:
            assert self.lock_path is not None
            self.lock_path.parent.mkdir(parents=True, exist_ok=True)
            try:
                fd = os.open(str(self.lock_path), os.O_CREAT | os.O_EXCL | os.O_WRONLY)
                with os.fdopen(fd, "w", encoding="utf-8") as handle:
                    handle.write(f"pid={os.getpid()}\n")
                    handle.write(f"created_at={datetime.now(timezone.utc).isoformat()}\n")
                    handle.write(f"target={self.target_path}\n")
                self._acquired = True
                return self
            except FileExistsError:
                self._remove_stale_lock()
                if time.monotonic() >= deadline:
                    raise FileLockTimeout(f"Timed out waiting for lock: {self.lock_path}")
                time.sleep(max(0.01, self.poll_seconds))

    # with 블록 종료 시 획득한 파일 lock을 해제한다.
    def __exit__(self, exc_type, exc, tb) -> None:
        if not self._acquired:
            return
        try:
            self.lock_path.unlink()
        except FileNotFoundError:
            pass
        finally:
            self._acquired = False

    # stale lock을 제거한다.
    def _remove_stale_lock(self) -> None:
        if self.stale_seconds <= 0:
            return
        try:
            mtime = datetime.fromtimestamp(self.lock_path.stat().st_mtime, tz=timezone.utc)
        except FileNotFoundError:
            return
        if datetime.now(timezone.utc) - mtime <= timedelta(seconds=self.stale_seconds):
            return
        try:
            self.lock_path.unlink()
        except FileNotFoundError:
            return
