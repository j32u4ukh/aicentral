"""
對話歷史：儲存、裁剪、向量分群壓縮與 MCP 整輪刪除。

``Chat`` 在每次 ``record_turn`` 後呼叫 ``maybe_trim``；超出 ``max_messages`` 時
依 ``HistoryPolicy`` 執行對應策略。

``SEGMENT_COMPRESS`` 時，``Chat`` 每輪在回傳前先完成 **對話 API + 向量化 API**（``embed_turn``），
向量快取於 ``_embeddings``；壓縮時優先使用快取，不再對整段歷史重新請求 embedding。
"""

from __future__ import annotations

import logging
import math
from collections.abc import Iterable
from enum import StrEnum
from typing import Any

from aicentral.core.client import complete, embedding
from aicentral.core.errors import HistoryOverflowError
from aicentral.core.types import Message

_logger = logging.getLogger(__name__)

_SUMMARY_SYSTEM = (
    "將以下對話摘要為一段繁體中文，保留事實與決策，刪除贅詞。只輸出摘要正文。"
)

# 傳統摘要壓縮（無 embedding）時，一次處理的最舊訊息數上限
_LEGACY_SEGMENT_WINDOW = 5
# 壓縮日誌中單則 content 預覽字元上限
_LOG_CONTENT_WIDTH = 120
_EMBEDDING_TEXT_WIDTH = 8192


class HistoryPolicy(StrEnum):
    """歷史超出上限時的處理方式。"""

    DROP_OLDEST = "drop_oldest"  # 刪最舊一則（或 MCP 整輪）
    DROP_OLDEST_PAIR = "drop_oldest_pair"  # 刪最舊一組 user+assistant
    SEGMENT_COMPRESS = "segment_compress"  # 向量分群後丟棄或摘要，失敗則降級
    MANUAL = "manual"  # 不自動修剪，改拋 HistoryOverflowError


class History:
    """負責管理、裁剪、分群與壓縮對話歷史的獨立記憶模組。

    ``max_messages`` 計的是 ``turn_count()``（預設為 user+assistant 則數；
    ``include_tool_messages=True`` 時改以 user 則數計算，以涵蓋 MCP 多則 tool 訊息）。
    """

    def __init__(
        self,
        *,
        max_messages: int = 40,
        policy: HistoryPolicy = HistoryPolicy.DROP_OLDEST_PAIR,
        include_tool_messages: bool = False,
        similarity_threshold: float = 0.65,
        relevance_threshold: float = 0.40,
        embedding_model: str | None = None,
        summary_model: str | None = None,
        base_url: str | None = None,
        api_key: str | None = None,
    ) -> None:
        self.max_messages = max_messages
        self.policy = policy
        self.include_tool_messages = include_tool_messages
        # 相鄰訊息歸為同一主題群組的餘弦相似度門檻
        self.similarity_threshold = similarity_threshold
        # 最舊群組與最新群組低於此值視為無關主題，直接丟棄
        self.relevance_threshold = relevance_threshold
        # 向量分群用輕量 embedding 模型（見 defaults.embedding_model / local-embed）
        self.embedding_model = embedding_model
        # LLM 摘要用對話模型（可與 embedding 不同）
        self.summary_model = summary_model
        self.base_url = base_url
        self.api_key = api_key
        self._storage: list[Message] = []
        # 與 _storage 同索引；SEGMENT_COMPRESS 每輪寫入時預先填入，壓縮分群時優先使用
        self._embeddings: list[list[float] | None] = []

    def __len__(self) -> int:
        return len(self._storage)

    @property
    def messages(self) -> list[Message]:
        """返回當前儲存的歷史訊息列表快照（複本，修改不影響內部）。"""
        return list(self._storage)

    def append(self, message: Message) -> None:
        self._append_message(message, None)

    def extend(self, messages: Iterable[Message]) -> None:
        for message in messages:
            self._append_message(message, None)

    def clear(self) -> None:
        self._storage.clear()
        self._embeddings.clear()

    def _append_message(self, message: Message, embedding_vec: list[float] | None) -> None:
        self._storage.append(message)
        self._embeddings.append(embedding_vec)

    def delete(self, indices: Iterable[int]) -> None:
        """依索引刪除訊息（由大到小刪除，避免索引位移）。"""
        for index in sorted(set(indices), reverse=True):
            if 0 <= index < len(self._storage):
                del self._storage[index]
                if index < len(self._embeddings):
                    del self._embeddings[index]

    def trim(self, keep_last: int) -> None:
        """保留最後 ``keep_last`` 則**原始訊息**（非 turn_count 語意）。"""
        if keep_last < 0:
            return
        if keep_last == 0:
            self.clear()
            return
        if self.turn_count() <= keep_last:
            return
        self._storage = self._storage[-keep_last:]
        self._embeddings = self._embeddings[-keep_last:]

    def turn_count(self) -> int:
        """依 MCP 設定計算有效的對話輪數，供 ``max_messages`` 比較。"""
        if self.include_tool_messages:
            return sum(1 for msg in self._storage if msg["role"] == "user")
        return sum(1 for msg in self._storage if msg["role"] in ("user", "assistant"))

    def record_turn(
        self,
        user_msg: Message,
        reply: str,
        *,
        trail: list[Message] | None = None,
        turn_embedding: list[float] | None = None,
    ) -> None:
        """追加一輪對話，並動態觸發歷史修剪政策。

        ``trail`` 為 MCP 本輪訊息（assistant / tool / 最終 assistant）；若提供則不再另建單則 assistant。
        ``turn_embedding`` 為本輪預先取得的向量（``SEGMENT_COMPRESS`` 時由 ``Chat`` 在回傳前呼叫 ``embed_turn``）。
        """
        if trail:
            self._append_message(user_msg, turn_embedding)
            for message in trail:
                self._append_message(message, None)
        else:
            self._append_message(user_msg, turn_embedding)
            self._append_message({"role": "assistant", "content": reply}, turn_embedding)
        self.maybe_trim()

    def _log_trim_check(self) -> None:
        """輸出本輪修剪檢查狀態（不論是否實際壓縮）。"""
        turns = self.turn_count()
        raw = len(self._storage)
        _logger.info(
            "歷史修剪檢查：policy=%s | turn_count=%d / max_messages=%d | 原始訊息數=%d",
            self.policy.value,
            turns,
            self.max_messages,
            raw,
        )
        if turns <= self.max_messages:
            _logger.info(
                "尚不需壓縮（turn_count=%d <= max_messages=%d）",
                turns,
                self.max_messages,
            )

    def maybe_trim(self) -> None:
        """檢查記憶長度上限並執行對應的裁剪或語意壓縮。

        可能多次迴圈，直到 ``turn_count() <= max_messages`` 或策略無法再縮減。
        每次 ``record_turn`` 後都會輸出檢查日誌；未超限時說明尚不需壓縮。
        """
        self._log_trim_check()
        if self.turn_count() <= self.max_messages:
            return

        round_no = 0
        while self.turn_count() > self.max_messages:
            round_no += 1
            _logger.info(
                "開始壓縮第 %d 輪：turn_count=%d > max_messages=%d",
                round_no,
                self.turn_count(),
                self.max_messages,
            )
            self._log_full_history(f"壓縮第 {round_no} 輪—觸發時")
            if self.policy == HistoryPolicy.MANUAL:
                raise HistoryOverflowError(
                    f"歷史訊息數 {self.turn_count()} 超過上限 {self.max_messages}；"
                    "請使用 delete()、trim() 或更換 history_policy。"
                )
            if self.policy == HistoryPolicy.DROP_OLDEST:
                _logger.info("執行 DROP_OLDEST 裁切")
                self._log_full_history("DROP_OLDEST—裁切前")
                self._drop_oldest_turn() if self.include_tool_messages else self._drop_oldest_one()
                self._log_full_history("DROP_OLDEST—裁切後")
            elif self.policy == HistoryPolicy.DROP_OLDEST_PAIR:
                _logger.info("執行 DROP_OLDEST_PAIR 裁切")
                self._log_full_history("DROP_OLDEST_PAIR—裁切前")
                self._drop_oldest_turn() if self.include_tool_messages else self._drop_oldest_pair()
                self._log_full_history("DROP_OLDEST_PAIR—裁切後")
            elif self.policy == HistoryPolicy.SEGMENT_COMPRESS:
                # SEGMENT_COMPRESS 三階降級（任一步成功則 turn_count 下降，while 可能再跑一輪）：
                #
                # 1) _segment_compress_by_vector：優先語意分群（需 embedding_model、≥6 則訊息、向量快取可用）。
                #    回傳 False 表示「本輪未壓縮」，日誌會說明跳過原因（訊息太少、無關主題群、熱記憶保護等）。
                #
                # 2) _segment_compress_legacy：向量不可用或條件不足時，改用最舊 N 則固定視窗 + LLM 摘要（[摘要]）。
                #
                # 3) _drop_oldest_*：前兩者皆無法縮減時，最後降級為刪最舊一輪／一組，避免 while 無窮迴圈。
                if self._segment_compress_by_vector():
                    continue
                if self._segment_compress_legacy():
                    continue
                _logger.info("向量／傳統摘要皆未執行，降級為 DROP_OLDEST 裁切")
                self._log_full_history("降級裁切—執行前")
                self._drop_oldest_turn() if self.include_tool_messages else self._drop_oldest_pair()
                self._log_full_history("降級裁切—執行後")
            else:
                self._drop_oldest_turn() if self.include_tool_messages else self._drop_oldest_pair()

        _logger.info(
            "壓縮完成：turn_count=%d / max_messages=%d | 原始訊息數=%d",
            self.turn_count(),
            self.max_messages,
            len(self._storage),
        )

    @staticmethod
    def _content_preview(content: Any, *, width: int = _LOG_CONTENT_WIDTH) -> str:
        text = str(content).replace("\n", " ")
        if len(text) <= width:
            return text
        return text[: width - 3] + "..."

    @classmethod
    def _format_message_line(cls, index: int, msg: Message) -> str:
        role = msg.get("role", "?")
        extra = ""
        if role == "assistant" and msg.get("tool_calls"):
            extra = " [tool_calls]"
        preview = cls._content_preview(msg.get("content", ""))
        return f"  [{index:02d}] {role}{extra}: {preview}"

    def _log_full_history(self, title: str) -> None:
        """輸出 ``_storage`` 內全部訊息（含索引），供壓縮前對照。"""
        _logger.info("【%s】完整歷史（共 %d 則）", title, len(self._storage))
        for index, msg in enumerate(self._storage):
            _logger.info("%s", self._format_message_line(index, msg))

    def _log_compress_snapshot(
        self,
        *,
        action: str,
        before_segment: list[Message],
        after_storage: list[Message],
    ) -> None:
        """輸出壓縮／清除前後的訊息內容，供除錯與示範腳本對照。

        先印出觸發當下**全部**歷史，再標示本輪實際處理的區段（可能僅最舊 N 則），最後印壓縮後結果。
        """
        self._log_full_history(f"{action}—壓縮前")

        seg_len = len(before_segment)
        full_len = len(self._storage)
        if seg_len < full_len:
            end_idx = seg_len - 1
            _logger.info(
                "【%s】本輪將處理區段（索引 0～%d，共 %d 則；其餘 %d 則保留為熱記憶）",
                action,
                end_idx,
                seg_len,
                full_len - seg_len,
            )
            for index, msg in enumerate(before_segment):
                _logger.info("%s", self._format_message_line(index, msg))

        _logger.info("【%s】壓縮後（共 %d 則）", action, len(after_storage))
        for index, msg in enumerate(after_storage):
            _logger.info("%s", self._format_message_line(index, msg))

    @staticmethod
    def _turn_embedding_text(user_msg: Message, reply: str) -> str:
        user_part = str(user_msg.get("content", ""))[:_EMBEDDING_TEXT_WIDTH]
        reply_part = str(reply)[:_EMBEDDING_TEXT_WIDTH]
        return f"user: {user_part}\nassistant: {reply_part}"

    def embed_turn(self, user_msg: Message, reply: str) -> list[float]:
        """本輪向量化 API（與對話 API 分開；每輪各呼叫一次）。"""
        text = self._turn_embedding_text(user_msg, reply)
        _logger.info("向量化 API：model=%s", self.embedding_model)
        return self._get_embedding(text)

    def _get_embedding(self, text: str) -> list[float]:
        """呼叫 ``core.client.embedding``（使用 ``embedding_model``，非對話模型）。"""
        if not self.embedding_model:
            raise ValueError("embedding_model 未設定，無法執行向量分群")
        return embedding(
            text=text,
            model=self.embedding_model,
            base_url=self.base_url,
            api_key=self.api_key,
        )

    def _embedding_text_for_message(self, msg: Message) -> str:
        return f"{msg['role']}: {str(msg.get('content', ''))[:_EMBEDDING_TEXT_WIDTH]}"

    def _resolve_embeddings(self) -> list[list[float]] | None:
        """彙整每則訊息的向量；優先使用 ``_embeddings`` 快取，缺漏時才補請求 API。"""
        vectors: list[list[float]] = []
        for index, msg in enumerate(self._storage):
            cached = self._embeddings[index] if index < len(self._embeddings) else None
            if cached is not None:
                vectors.append(cached)
                continue
            try:
                vectors.append(self._get_embedding(self._embedding_text_for_message(msg)))
            except Exception as exc:
                _logger.warning("補齊缺失向量失敗 (%s)", exc)
                return None
        return vectors

    def _call_summary_api(self, text: str) -> str:
        """呼叫 ``core.client.complete`` 產生歷史段落摘要。"""
        if not self.summary_model:
            raise ValueError("summary_model 未設定，無法執行 LLM 摘要壓縮")
        return complete(
            messages=[{"role": "user", "content": text}],
            model=self.summary_model,
            system=_SUMMARY_SYSTEM,
            base_url=self.base_url,
            api_key=self.api_key,
        )

    def _drop_oldest_one(self) -> None:
        """刪除儲存列表最前端一則訊息。"""
        if self._storage:
            self._storage.pop(0)
            if self._embeddings:
                self._embeddings.pop(0)

    def _drop_oldest_pair(self) -> None:
        """刪除最舊一組 user + 緊隨其後的 assistant（若存在）。"""
        if not self._storage:
            return
        first_user = next(
            (i for i, m in enumerate(self._storage) if m["role"] == "user"),
            None,
        )
        if first_user is None:
            if self._storage:
                self._storage.pop(0)
            if self._embeddings:
                self._embeddings.pop(0)
            return
        end = first_user + 1
        if end < len(self._storage) and self._storage[end]["role"] == "assistant":
            end += 1
        del self._storage[first_user:end]
        if first_user < len(self._embeddings):
            del self._embeddings[first_user : min(end, len(self._embeddings))]

    def _drop_oldest_turn(self) -> None:
        """移除最舊一輪（自第一則 user 至下一則 user 之前），含 MCP tool 訊息。"""
        if not self._storage:
            return
        first_user = next(
            (i for i, m in enumerate(self._storage) if m["role"] == "user"),
            None,
        )
        if first_user is None:
            if self._storage:
                self._storage.pop(0)
            if self._embeddings:
                self._embeddings.pop(0)
            return
        next_user = next(
            (i for i, m in enumerate(self._storage) if i > first_user and m["role"] == "user"),
            None,
        )
        if next_user is None:
            del self._storage[first_user:]
            if first_user < len(self._embeddings):
                del self._embeddings[first_user:]
        else:
            del self._storage[first_user:next_user]
            if first_user < len(self._embeddings):
                del self._embeddings[first_user:next_user]

    def _segment_compress_legacy(self) -> bool:
        """依固定視窗將最舊訊息壓成單則摘要（無需 embedding，相容 v1.1）。

        成功時以 ``[摘要]`` 前綴的 assistant 訊息取代視窗內原文。
        """
        if not self._storage:
            _logger.info("傳統視窗摘要：跳過（歷史為空）")
            return False
        if not self.summary_model:
            _logger.info("傳統視窗摘要：跳過（未設定 summary_model）")
            return False
        window = min(_LEGACY_SEGMENT_WINDOW, len(self._storage))
        if window < 1:
            _logger.info("傳統視窗摘要：跳過（視窗為 0）")
            return False
        segment = self._storage[:window]
        _logger.info("傳統視窗摘要：壓縮 %d 則訊息（無向量）", window)
        lines = [f"{m['role']}: {m['content']}" for m in segment]
        summary = self._call_summary_api("\n".join(lines))
        compressed: Message = {
            "role": "assistant",
            "content": f"[摘要] {summary.strip()}",
        }
        after_storage = [compressed, *self._storage[window:]]
        after_embeddings: list[list[float] | None] = [None, *self._embeddings[window:]]
        self._log_compress_snapshot(
            action="傳統視窗摘要",
            before_segment=segment,
            after_storage=after_storage,
        )
        self._storage = after_storage
        self._embeddings = after_embeddings
        return True

    def _segment_compress_by_vector(self) -> bool:
        """基於時間序列向量距離的動態分群、摘要與冷熱清除。

        流程概要：
          1. 彙整每則訊息的向量（優先 ``_embeddings`` 快取，見 ``Chat.embed_turn``）。
          2. 依時間順序做**線上串流分群**：與上一群組中心向量相似度 ≥ ``similarity_threshold`` 則併入同組。
          3. 比較**最舊群組**與**最新群組**的中心向量（``core_sim``）。
          4. 依 ``relevance_threshold`` 決定冷清除（刪除）或溫壓縮（``[前情摘要]``）。
          5. ``cut_idx`` 不得侵入最後 4 則熱記憶。

        回傳 True 表示本輪已成功縮減 history；False 則由 ``maybe_trim`` 改試傳統摘要或 DROP_OLDEST。
        """
        # --- 前置條件：無法分群時直接放棄（由外層降級） ---
        if not self.embedding_model:
            _logger.info("向量分群：跳過（未設定 embedding_model）")
            return False
        if len(self._storage) < 6:
            # 訊息太少時分群結果不可靠，且切點難以避開熱記憶
            _logger.info(
                "向量分群：跳過（訊息數 %d < 6，累積不足）",
                len(self._storage),
            )
            return False

        # 與 _storage 等長；缺漏者會補打 embedding API（理論上 SEGMENT_COMPRESS 每輪已預先寫入）
        embeddings = self._resolve_embeddings()
        if embeddings is None:
            _logger.warning("向量分群：跳過（無法取得完整向量，改試傳統摘要）")
            return False

        # --- 階段 1：時間序列串流分群（Online Stream Clustering） ---
        # groups 元素為一群主題；群內為 (訊息在 _storage 的索引, 向量)
        groups: list[list[tuple[int, list[float]]]] = [[[0, embeddings[0]]]]
        for i in range(1, len(embeddings)):
            current_emb = embeddings[i]
            last_group = groups[-1]
            # 與「目前最後一群」的平均向量比較，而非只與上一則比（較穩定）
            avg_last_emb = self._calculate_avg_embedding(last_group)
            sim = self._cosine_similarity(current_emb, avg_last_emb)
            if sim >= self.similarity_threshold:
                # 語意延續同一主題 → 併入現有群組
                last_group.append((i, current_emb))
            else:
                # 語意突變 → 開新群組（代表話題切換）
                groups.append([(i, current_emb)])

        # 若從頭到尾只有一群，表示仍在同一話題深挖，暫不壓最舊段落
        if len(groups) < 2:
            _logger.info(
                "向量分群：跳過（僅 %d 個主題群組，話題尚未分化）",
                len(groups),
            )
            return False

        # --- 階段 2：跨時空決策（最舊主題 vs 當前主題） ---
        oldest_group, latest_group = groups[0], groups[-1]
        avg_oldest = self._calculate_avg_embedding(oldest_group)
        avg_latest = self._calculate_avg_embedding(latest_group)
        core_sim = self._cosine_similarity(avg_oldest, avg_latest)
        # cut_idx：僅處理「最舊那一群」涵蓋的訊息（不含索引 cut_idx 之後的較新主題）
        cut_idx = oldest_group[-1][0] + 1

        # --- 階段 3：熱記憶保護（進行中對話不切） ---
        # 例如共 8 則時 cut_idx 最多為 4，保留 index 4..7
        if cut_idx > len(self._storage) - 4:
            _logger.info(
                "向量分群：跳過（切點 %d 會侵入熱記憶，保留最後 4 則）",
                cut_idx,
            )
            return False

        segment = self._storage[:cut_idx]
        if core_sim < self.relevance_threshold:
            # --- 冷記憶：舊主題與當前話題無關 → 直接刪除，不浪費摘要 token ---
            _logger.info(
                "向量冷清除：舊主題與當前無關 (相似度=%.2f < %.2f)，移除前 %d 則",
                core_sim,
                self.relevance_threshold,
                cut_idx,
            )
            after_storage = self._storage[cut_idx:]
            self._log_compress_snapshot(
                action="向量冷清除",
                before_segment=segment,
                after_storage=after_storage,
            )
            self._storage = after_storage
            self._embeddings = self._embeddings[cut_idx:]
        else:
            # --- 溫記憶：仍有弱關聯 → LLM 壓成單則 [前情摘要]，供模型銜接上下文 ---
            _logger.info(
                "向量溫壓縮：舊主題弱關聯 (相似度=%.2f)，LLM 摘要前 %d 則",
                core_sim,
                cut_idx,
            )
            lines = [f"{msg['role']}: {msg['content']}" for msg in segment]
            summary = self._call_summary_api("\n".join(lines))
            compressed: Message = {
                "role": "assistant",
                "content": f"[前情摘要] {summary.strip()}",
            }
            after_storage = [compressed, *self._storage[cut_idx:]]
            self._log_compress_snapshot(
                action="向量溫壓縮",
                before_segment=segment,
                after_storage=after_storage,
            )
            self._storage = after_storage
            # 摘要訊息尚無對應向量，標 None；其後保留原快取
            self._embeddings = [None, *self._embeddings[cut_idx:]]
        return True

    @staticmethod
    def _cosine_similarity(v1: list[float], v2: list[float]) -> float:
        """純 Python 計算餘弦相似度，避免 NumPy 依賴。"""
        dot_product = sum(a * b for a, b in zip(v1, v2))
        norm_a = math.sqrt(sum(a * a for a in v1))
        norm_b = math.sqrt(sum(b * b for b in v2))
        return dot_product / (norm_a * norm_b) if norm_a and norm_b else 0.0

    @staticmethod
    def _calculate_avg_embedding(group: list[tuple[int, list[float]]]) -> list[float]:
        """計算單一時間主題群組內所有向量的中心點（算術平均）。"""
        vec_len = len(group[0][1])
        avg_vec = [0.0] * vec_len
        for _, vec in group:
            for i in range(vec_len):
                avg_vec[i] += vec[i]
        return [v / len(group) for v in avg_vec]
