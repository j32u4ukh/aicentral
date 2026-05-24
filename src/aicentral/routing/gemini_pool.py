"""Gemini 多模型池：依 rpm/rpd 限流輪換，用盡時等待至下一分鐘。"""

from __future__ import annotations

import logging
import threading
import time
from dataclasses import dataclass, field

from aicentral.config.schema import GeminiPoolModelEntry, GeminiPoolSettings
from aicentral.core.errors import ProviderError

logger = logging.getLogger(__name__)

_POOLS: dict[str, GeminiPoolLimiter] = {}
_POOLS_LOCK = threading.Lock()


@dataclass(frozen=True)
class _EffectiveLimits:
    rpm: int | None
    rpd: int | None


@dataclass
class _UsageCounters:
    minute_epoch: int = 0
    minute_count: int = 0
    day_epoch: int = 0
    day_count: int = 0


@dataclass
class GeminiPoolLimiter:
    """單一命名池的限流與輪換（程序內全域計數）。"""

    name: str
    models: list[GeminiPoolModelEntry]
    wait_poll_seconds: float = 1.0
    _lock: threading.Lock = field(default_factory=threading.Lock, repr=False)
    _usage: dict[str, _UsageCounters] = field(default_factory=dict, repr=False)

    @classmethod
    def from_settings(cls, name: str, settings: GeminiPoolSettings) -> GeminiPoolLimiter:
        if not settings.models:
            raise ValueError(f"gemini_pools.{name!r} 的 models 不可為空")
        return cls(
            name=name,
            models=list(settings.models),
            wait_poll_seconds=settings.wait_poll_seconds,
        )

    @staticmethod
    def _effective_limits(entry: GeminiPoolModelEntry) -> _EffectiveLimits:
        """執行時以使用者自訂上限為準（較保守）；未設則用官方上限。"""
        rpm = entry.rpm_limit if entry.rpm_limit is not None else entry.rpm_official
        rpd = entry.rpd_limit if entry.rpd_limit is not None else entry.rpd_official
        return _EffectiveLimits(rpm=rpm, rpd=rpd)

    def _minute_epoch(self, now: float | None = None) -> int:
        t = now if now is not None else time.time()
        return int(t // 60)

    def _day_epoch(self, now: float | None = None) -> int:
        t = now if now is not None else time.time()
        return int(t // 86400)

    def _seconds_until_next_minute(self, now: float | None = None) -> float:
        t = now if now is not None else time.time()
        return max(0.0, 60.0 - (t % 60.0))

    def _counters_for(self, model_id: str) -> _UsageCounters:
        if model_id not in self._usage:
            self._usage[model_id] = _UsageCounters()
        return self._usage[model_id]

    def _sync_epochs(self, counters: _UsageCounters, *, now: float) -> None:
        minute_ep = self._minute_epoch(now)
        day_ep = self._day_epoch(now)
        if counters.minute_epoch != minute_ep:
            counters.minute_epoch = minute_ep
            counters.minute_count = 0
        if counters.day_epoch != day_ep:
            counters.day_epoch = day_ep
            counters.day_count = 0

    def _under_limit(self, entry: GeminiPoolModelEntry, *, now: float) -> bool:
        limits = self._effective_limits(entry)
        counters = self._counters_for(entry.model_id)
        self._sync_epochs(counters, now=now)
        if limits.rpm is not None and counters.minute_count >= limits.rpm:
            return False
        if limits.rpd is not None and counters.day_count >= limits.rpd:
            return False
        return True

    def _reserve(self, entry: GeminiPoolModelEntry, *, now: float) -> None:
        counters = self._counters_for(entry.model_id)
        self._sync_epochs(counters, now=now)
        counters.minute_count += 1
        counters.day_count += 1

    def mark_minute_exhausted(self, model_id: str, *, now: float | None = None) -> None:
        """API 回 429 或外部限流時，將該模型視為本分鐘已滿。"""
        t = now if now is not None else time.time()
        with self._lock:
            entry = next((m for m in self.models if m.model_id == model_id), None)
            if entry is None:
                return
            limits = self._effective_limits(entry)
            if limits.rpm is None:
                return
            counters = self._counters_for(model_id)
            self._sync_epochs(counters, now=t)
            counters.minute_count = limits.rpm

    def acquire(self) -> str:
        """
        依序選擇未達 rpm/rpd 上限的模型；皆滿則等待至下一分鐘再重試。
        單一模型時行為相同，僅會等待而不輪換。
        """
        while True:
            now = time.time()
            with self._lock:
                for entry in self.models:
                    if self._under_limit(entry, now=now):
                        self._reserve(entry, now=now)
                        logger.debug(
                            "gemini_pool %s 選用 %s (minute=%s day=%s)",
                            self.name,
                            entry.model_id,
                            self._counters_for(entry.model_id).minute_count,
                            self._counters_for(entry.model_id).day_count,
                        )
                        return entry.model_id

                all_daily_full = all(
                    not self._under_limit_for_daily(m, now=now) for m in self.models
                )
            if all_daily_full:
                raise ProviderError(
                    f"Gemini 池 {self.name!r} 內所有模型已達每日上限（rpd_limit），"
                    "請明日再試或調整設定",
                    failure_kind="rate_limit",
                )

            wait_s = self._seconds_until_next_minute(now)
            logger.info(
                "gemini_pool %s 本分鐘已用盡，等待 %.1fs 至下一分鐘",
                self.name,
                wait_s,
            )
            time.sleep(max(self.wait_poll_seconds, wait_s))

    def _under_limit_for_daily(self, entry: GeminiPoolModelEntry, *, now: float) -> bool:
        limits = self._effective_limits(entry)
        if limits.rpd is None:
            return True
        counters = self._counters_for(entry.model_id)
        self._sync_epochs(counters, now=now)
        return counters.day_count < limits.rpd


def get_gemini_pool(name: str, settings: GeminiPoolSettings) -> GeminiPoolLimiter:
    with _POOLS_LOCK:
        pool = _POOLS.get(name)
        if pool is None:
            pool = GeminiPoolLimiter.from_settings(name, settings)
            _POOLS[name] = pool
        return pool


def reset_gemini_pools() -> None:
    """測試用：清空已建立的池實例。"""
    with _POOLS_LOCK:
        _POOLS.clear()
