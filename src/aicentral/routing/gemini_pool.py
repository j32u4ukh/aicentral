"""Gemini 多模型池：依 rpm/rpd 限流輪換，用盡時等待至下一分鐘。

計數來源（優先序）：
1. 平常 ``acquire()`` 預留 + 成功回應 Header 同步（方案三，可能偏低）
2. 收到 **429** 時：將本地計數**上調**至官方/自訂/Header 上限的較大者，避免 Header
   偏差導致同一分鐘內再次選到已觸發限流的模型（見 ``_apply_rate_limit_penalty_locked``）

全池滿等待：僅依 ``_last_success_time``（最近一次 HTTP 成功），不在預留或 429 時更新。
"""

from __future__ import annotations

import logging
import threading
import time
from collections.abc import Mapping
from dataclasses import dataclass, field
from pathlib import Path

from aicentral.config.schema import GeminiPoolModelEntry, GeminiPoolSettings
from aicentral.core.errors import ProviderError
from aicentral.routing.gemini_headers import (
    GeminiRateLimitInfo,
    log_rate_limit_info,
    parse_rate_limit_from_response,
)
from aicentral.routing.gemini_rate_limit_store import (
    GeminiRateLimitStore,
    resolve_store_path,
)

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
    retry_initial_seconds: float = 2.0
    retry_max_seconds: float = 32.0
    _store: GeminiRateLimitStore | None = field(default=None, repr=False)
    _model_index: int = field(default=0, repr=False)
    _total_calls: int = field(default=0, repr=False)
    _lock: threading.Lock = field(default_factory=threading.Lock, repr=False)
    _usage: dict[str, _UsageCounters] = field(default_factory=dict, repr=False)
    _consecutive_429: int = field(default=0, repr=False)
    # 最近一次**成功**請求（HTTP < 400）的時間；全池滿時依此推算「本分鐘」還需等多久
    # 不在 acquire 預留或 429 失敗時更新，避免失敗連打拉晚等待參考點
    _last_success_time: float | None = field(default=None, repr=False)

    @classmethod
    def from_settings(cls, name: str, settings: GeminiPoolSettings) -> GeminiPoolLimiter:
        if not settings.models:
            raise ValueError(f"gemini_pools.{name!r} 的 models 不可為空")
        pool = cls(
            name=name,
            models=list(settings.models),
            wait_poll_seconds=settings.wait_poll_seconds,
            retry_initial_seconds=settings.retry_initial_seconds,
            retry_max_seconds=settings.retry_max_seconds,
        )
        store_path = resolve_store_path(settings.rate_limit_store_path)
        if store_path is not None:
            pool._load_from_store(store_path)
        return pool

    def _model_ids(self) -> list[str]:
        return [m.model_id for m in self.models]

    def _load_from_store(self, path: Path) -> None:
        store = GeminiRateLimitStore(self.name, self._model_ids(), path)
        self._store = store
        rec = store.record
        self._model_index = int(rec.get("model_index", 0)) % max(len(self.models), 1)
        self._total_calls = int(rec.get("total_calls", 0))
        last = rec.get("last_success_time")
        if isinstance(last, (int, float)):
            self._last_success_time = float(last)
        models_map = rec.get("models", {})
        if isinstance(models_map, dict):
            for mid, row in models_map.items():
                if not isinstance(row, dict):
                    continue
                counters = self._counters_for(mid)
                counters.minute_epoch = int(row.get("minute_epoch", 0))
                counters.minute_count = int(row.get("minute_count", 0))
                counters.day_epoch = int(row.get("day_epoch", 0))
                counters.day_count = int(row.get("day_count", 0))
        logger.info(
            "gemini_pool %s 已載入 %s：model_index=%s next=%s total_calls=%s",
            self.name,
            path,
            self._model_index,
            rec.get("next_model_id"),
            self._total_calls,
        )

    def _usage_snapshot(self) -> dict[str, dict[str, int]]:
        rows: dict[str, dict[str, int]] = {}
        for mid in self._model_ids():
            c = self._counters_for(mid)
            rows[mid] = {
                "minute_epoch": c.minute_epoch,
                "minute_count": c.minute_count,
                "day_epoch": c.day_epoch,
                "day_count": c.day_count,
            }
        return rows

    def _persist_store(self) -> None:
        if self._store is None:
            return
        self._store.sync_from_limiter(
            self._usage_snapshot(),
            model_index=self._model_index,
            total_calls=self._total_calls,
            last_success_time=self._last_success_time,
        )
        self._store.persist()

    @staticmethod
    def _effective_limits(entry: GeminiPoolModelEntry) -> _EffectiveLimits:
        """日常選路：以 ``rpm_limit`` / ``rpd_limit`` 為準（較保守）；未設則用官方值。"""
        rpm = entry.rpm_limit if entry.rpm_limit is not None else entry.rpm_official
        rpd = entry.rpd_limit if entry.rpd_limit is not None else entry.rpd_official
        return _EffectiveLimits(rpm=rpm, rpd=rpd)

    @staticmethod
    def _minute_ceiling(
        entry: GeminiPoolModelEntry,
        header_info: GeminiRateLimitInfo | None = None,
    ) -> int | None:
        """本分鐘「視為已滿」時應對齊的上限（取官方、自訂、Header 三者較大者）。"""
        candidates: list[int] = []
        if entry.rpm_official is not None:
            candidates.append(entry.rpm_official)
        if entry.rpm_limit is not None:
            candidates.append(entry.rpm_limit)
        if header_info and header_info.limit_requests is not None:
            candidates.append(header_info.limit_requests)
        return max(candidates) if candidates else None

    @staticmethod
    def _day_ceiling(
        entry: GeminiPoolModelEntry,
        header_info: GeminiRateLimitInfo | None = None,
    ) -> int | None:
        candidates: list[int] = []
        if entry.rpd_official is not None:
            candidates.append(entry.rpd_official)
        if entry.rpd_limit is not None:
            candidates.append(entry.rpd_limit)
        return max(candidates) if candidates else None

    def _minute_epoch(self, now: float | None = None) -> int:
        t = now if now is not None else time.time()
        return int(t // 60)

    def _day_epoch(self, now: float | None = None) -> int:
        t = now if now is not None else time.time()
        return int(t // 86400)

    def _touch_last_success(self, when: float) -> None:
        """記錄最近一次成功回應的時刻（僅供全池滿時等待計算）。"""
        self._last_success_time = when

    def seconds_until_minute_reset_after(
        self, event_time: float, *, now: float | None = None
    ) -> float:
        """
        依 ``event_time`` 所在的曆法分鐘窗口，計算距離該分鐘結束還需等待的秒數。

        與 ``60 - (now % 60)`` 不同：以「上次請求所在分鐘」為準，避免全池用盡時
        用錯參考點導致多等或少等。
        """
        t_now = now if now is not None else time.time()
        minute_end = (self._minute_epoch(event_time) + 1) * 60
        return max(0.0, minute_end - t_now)

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

    def release_failed_attempt(
        self,
        model_id: str,
        *,
        now: float | None = None,
        reason: str = "503",
    ) -> None:
        """
        撤回 ``acquire()`` 對未成功請求的預留（如 503 UNAVAILABLE）。

        Google 端超載不計入 RPM/RPD；本地亦不得保留該次 ``minute_count`` / ``day_count``。
        """
        t = now if now is not None else time.time()
        with self._lock:
            entry = next((m for m in self.models if m.model_id == model_id), None)
            if entry is None:
                return
            counters = self._counters_for(model_id)
            self._sync_epochs(counters, now=t)
            before_min = counters.minute_count
            before_day = counters.day_count
            if counters.minute_count > 0:
                counters.minute_count -= 1
            if counters.day_count > 0:
                counters.day_count -= 1
            if self._total_calls > 0:
                self._total_calls -= 1
            if (
                before_min != counters.minute_count
                or before_day != counters.day_count
            ):
                logger.info(
                    "gemini_pool %s %s 撤回預留計數 %s: minute %s→%s, day %s→%s",
                    self.name,
                    reason,
                    model_id,
                    before_min,
                    counters.minute_count,
                    before_day,
                    counters.day_count,
                )
            self._persist_store()

    def acquire_excluding(self, exclude: set[str]) -> str | None:
        """
        自 ``model_index`` 起輪詢，跳過 ``exclude`` 內模型，選第一個未達上限者。

        用於 503 後立刻嘗試池內下一個模型（不 sleep）。
        """
        if not self.models:
            return None
        now = time.time()
        with self._lock:
            n = len(self.models)
            start = self._model_index % n
            for offset in range(n):
                idx = (start + offset) % n
                entry = self.models[idx]
                if entry.model_id in exclude:
                    continue
                if self._under_limit(entry, now=now):
                    self._reserve(entry, now=now)
                    self._model_index = (idx + 1) % n
                    self._total_calls += 1
                    self._persist_store()
                    logger.debug(
                        "gemini_pool %s 選用 %s（排除 %s）",
                        self.name,
                        entry.model_id,
                        sorted(exclude),
                    )
                    return entry.model_id
        return None

    def _apply_rate_limit_penalty_locked(
        self,
        model_id: str,
        *,
        now: float,
        header_info: GeminiRateLimitInfo | None = None,
        reason: str = "429",
    ) -> None:
        """
        429 / 限流懲罰：將本地計數**上調**至滿額，而非僅設為自訂 ``rpm_limit``。

        若 Header 顯示仍有剩餘次數但實際仍 429，必須用 ``max(目前, 官方上限, …)``
        對齊 Google 側狀態，否則 ``acquire()`` 會誤以為還有空位而重複撞牆。
        """
        entry = next((m for m in self.models if m.model_id == model_id), None)
        if entry is None:
            return
        counters = self._counters_for(model_id)
        self._sync_epochs(counters, now=now)
        before_min = counters.minute_count
        before_day = counters.day_count

        minute_cap = self._minute_ceiling(entry, header_info)
        if minute_cap is not None:
            counters.minute_count = max(counters.minute_count, minute_cap)
        else:
            limits = self._effective_limits(entry)
            if limits.rpm is not None:
                counters.minute_count = max(counters.minute_count, limits.rpm)

        if counters.minute_count != before_min or counters.day_count != before_day:
            logger.info(
                "gemini_pool %s %s 上調配額計數 %s: minute %s→%s (cap=%s), day %s→%s",
                self.name,
                reason,
                model_id,
                before_min,
                counters.minute_count,
                minute_cap,
                before_day,
                counters.day_count,
            )
        self._persist_store()

    def mark_minute_exhausted(
        self,
        model_id: str,
        *,
        now: float | None = None,
        header_info: GeminiRateLimitInfo | None = None,
    ) -> None:
        """API 回 429 或外部限流：對齊官方/Header 上限，避免 Header 偏差後再次 429。"""
        t = now if now is not None else time.time()
        with self._lock:
            self._apply_rate_limit_penalty_locked(
                model_id, now=t, header_info=header_info, reason="429"
            )

    def apply_headers(
        self,
        model_id: str,
        headers: Mapping[str, str],
        *,
        status_code: int,
        body: str = "",
    ) -> None:
        """
        依 Response Header 同步配額（gemini-limit.md 方案三）。

        成功回應：依 ``remaining`` 推算已用次數（可能低於 Google 實際值）。
        429：改走 ``_apply_rate_limit_penalty_locked`` 上調至官方滿額，不再信任 Header 剩餘次數。
        """
        info = parse_rate_limit_from_response(
            headers, status_code=status_code, body=body
        )
        log_rate_limit_info(model_id, info)
        with self._lock:
            if status_code == 429:
                self._apply_rate_limit_penalty_locked(
                    model_id,
                    now=time.time(),
                    header_info=info,
                    reason="429+headers",
                )
                return
            entry = next((m for m in self.models if m.model_id == model_id), None)
            if entry is None:
                return
            limits = self._effective_limits(entry)
            # 成功回應：以自訂上限為 cap 推算；若仍 429，懲罰邏輯會用 max(自訂, 官方, Header)
            rpm_cap = limits.rpm or info.limit_requests
            now = time.time()
            self._touch_last_success(now)
            if info.remaining_requests is None or rpm_cap is None:
                return
            counters = self._counters_for(model_id)
            self._sync_epochs(counters, now=now)
            used = max(0, rpm_cap - info.remaining_requests)
            counters.minute_count = min(used, rpm_cap)
            if info.remaining_requests <= 0:
                counters.minute_count = rpm_cap
            self._persist_store()

    def backoff_seconds_for_429(self, retry_after: float | None) -> float:
        """429 退讓秒數：優先 Retry-After，否則指數退讓（方案四）。"""
        if retry_after is not None and retry_after > 0:
            return min(retry_after, self.retry_max_seconds)
        self._consecutive_429 += 1
        delay = self.retry_initial_seconds * (2 ** (self._consecutive_429 - 1))
        return min(delay, self.retry_max_seconds)

    def reset_429_backoff(self) -> None:
        self._consecutive_429 = 0

    def acquire(self) -> str:
        """
        依序選擇未達 rpm/rpd 上限的模型；皆滿則等待至「上次請求所在分鐘」結束再重試。

        等待秒數 = 該分鐘窗口結束時刻 − 現在，**不**使用固定 ``wait_poll_seconds``。
        參考時刻為 ``_last_success_time``（最近一次成功回應），不含失敗/429。
        計數未達 ``rpm_limit`` 才會選用；若先前 429 已上調至 ``rpm_official``，
        通常 ``minute_count >= rpm_limit``，會自動跳過該模型。
        """
        while True:
            now = time.time()
            with self._lock:
                n = len(self.models)
                start = self._model_index % n if n else 0
                chosen_index: int | None = None
                chosen_id: str | None = None
                for offset in range(n):
                    idx = (start + offset) % n
                    entry = self.models[idx]
                    if self._under_limit(entry, now=now):
                        self._reserve(entry, now=now)
                        chosen_index = idx
                        chosen_id = entry.model_id
                        break

                if chosen_id is not None and chosen_index is not None:
                    self._model_index = (chosen_index + 1) % n
                    self._total_calls += 1
                    self._persist_store()
                    logger.debug(
                        "gemini_pool %s 選用 %s (index %s→next %s, minute=%s day=%s, total=%s)",
                        self.name,
                        chosen_id,
                        chosen_index,
                        self._model_index,
                        self._counters_for(chosen_id).minute_count,
                        self._counters_for(chosen_id).day_count,
                        self._total_calls,
                    )
                    return chosen_id

                all_daily_full = all(
                    not self._under_limit_for_daily(m, now=now) for m in self.models
                )
                last_success = self._last_success_time
            if all_daily_full:
                raise ProviderError(
                    f"Gemini 池 {self.name!r} 內所有模型已達每日上限（rpd_limit），"
                    "請明日再試或調整設定",
                    failure_kind="rate_limit",
                )

            reference = last_success if last_success is not None else now
            wait_s = self.seconds_until_minute_reset_after(reference, now=now)
            logger.info(
                "gemini_pool %s 全池本分鐘已滿，依上次成功請求 %s 等待 %.1fs（至該分鐘結束）",
                self.name,
                time.strftime("%H:%M:%S", time.localtime(reference)),
                wait_s,
            )
            if wait_s > 0:
                time.sleep(wait_s)

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
