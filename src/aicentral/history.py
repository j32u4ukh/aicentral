"""
對話歷史：儲存、裁剪、向量分群壓縮與 MCP 整輪刪除。

``Chat`` 在每次 ``record_turn`` 後呼叫 ``maybe_trim``；超出 ``max_messages`` 時
依 ``HistoryPolicy`` 執行對應策略。``SEGMENT_COMPRESS`` 需 ``chat_session`` 提供
``get_embedding`` 與 ``call_summary_api`` 回呼。
"""

from __future__ import annotations

import math
from collections.abc import Iterable
from enum import StrEnum
from typing import TYPE_CHECKING, Any

from aicentral.core.errors import HistoryOverflowError
from aicentral.core.types import Message

if TYPE_CHECKING:
    from aicentral.chat import Chat

# 傳統摘要壓縮（無 embedding）時，一次處理的最舊訊息數上限
_LEGACY_SEGMENT_WINDOW = 5


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
    ) -> None:
        self.max_messages = max_messages
        self.policy = policy
        self.include_tool_messages = include_tool_messages
        # 相鄰訊息歸為同一主題群組的餘弦相似度門檻
        self.similarity_threshold = similarity_threshold
        # 最舊群組與最新群組低於此值視為無關主題，直接丟棄
        self.relevance_threshold = relevance_threshold
        self._storage: list[Message] = []

    def __len__(self) -> int:
        return len(self._storage)

    @property
    def messages(self) -> list[Message]:
        """返回當前儲存的歷史訊息列表快照（複本，修改不影響內部）。"""
        return list(self._storage)

    def append(self, message: Message) -> None:
        self._storage.append(message)

    def extend(self, messages: Iterable[Message]) -> None:
        self._storage.extend(messages)

    def clear(self) -> None:
        self._storage.clear()

    def delete(self, indices: Iterable[int]) -> None:
        """依索引刪除訊息（由大到小刪除，避免索引位移）。"""
        for index in sorted(set(indices), reverse=True):
            if 0 <= index < len(self._storage):
                del self._storage[index]

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
        chat_session: Chat | None = None,
    ) -> None:
        """追加一輪對話，並動態觸發歷史修剪政策。

        ``trail`` 為 MCP 本輪訊息（assistant / tool / 最終 assistant）；若提供則不再另建單則 assistant。
        ``chat_session`` 供 ``SEGMENT_COMPRESS`` 回呼 embedding 與摘要 API。
        """
        self.append(user_msg)
        if trail:
            self.extend(trail)
        else:
            self.append({"role": "assistant", "content": reply})
        self.maybe_trim(chat_session)

    def maybe_trim(self, chat_session: Chat | None = None) -> None:
        """檢查記憶長度上限並執行對應的裁剪或語意壓縮。

        可能多次迴圈，直到 ``turn_count() <= max_messages`` 或策略無法再縮減。
        """
        while self.turn_count() > self.max_messages:
            if self.policy == HistoryPolicy.MANUAL:
                raise HistoryOverflowError(
                    f"歷史訊息數 {self.turn_count()} 超過上限 {self.max_messages}；"
                    "請使用 delete()、trim() 或更換 history_policy。"
                )
            if self.policy == HistoryPolicy.DROP_OLDEST:
                self._drop_oldest_turn() if self.include_tool_messages else self._drop_oldest_one()
            elif self.policy == HistoryPolicy.DROP_OLDEST_PAIR:
                self._drop_oldest_turn() if self.include_tool_messages else self._drop_oldest_pair()
            elif self.policy == HistoryPolicy.SEGMENT_COMPRESS:
                # 向量分群 → 傳統視窗摘要 → 固定裁切，避免無窮迴圈
                if not self._segment_compress_by_vector(chat_session):
                    if not self._segment_compress_legacy(chat_session):
                        self._drop_oldest_turn() if self.include_tool_messages else self._drop_oldest_pair()
            else:
                self._drop_oldest_turn() if self.include_tool_messages else self._drop_oldest_pair()

    def _drop_oldest_one(self) -> None:
        """刪除儲存列表最前端一則訊息。"""
        if self._storage:
            self._storage.pop(0)

    def _drop_oldest_pair(self) -> None:
        """刪除最舊一組 user + 緊隨其後的 assistant（若存在）。"""
        if not self._storage:
            return
        first_user = next(
            (i for i, m in enumerate(self._storage) if m["role"] == "user"),
            None,
        )
        if first_user is None:
            self._storage.pop(0)
            return
        end = first_user + 1
        if end < len(self._storage) and self._storage[end]["role"] == "assistant":
            end += 1
        del self._storage[first_user:end]

    def _drop_oldest_turn(self) -> None:
        """移除最舊一輪（自第一則 user 至下一則 user 之前），含 MCP tool 訊息。"""
        if not self._storage:
            return
        first_user = next(
            (i for i, m in enumerate(self._storage) if m["role"] == "user"),
            None,
        )
        if first_user is None:
            self._storage.pop(0)
            return
        next_user = next(
            (i for i, m in enumerate(self._storage) if i > first_user and m["role"] == "user"),
            None,
        )
        if next_user is None:
            del self._storage[first_user:]
        else:
            del self._storage[first_user:next_user]

    def _segment_compress_legacy(self, chat: Chat | None) -> bool:
        """依固定視窗將最舊訊息壓成單則摘要（無需 embedding，相容 v1.1）。

        成功時以 ``[摘要]`` 前綴的 assistant 訊息取代視窗內原文。
        """
        if not self._storage or chat is None:
            return False
        window = min(_LEGACY_SEGMENT_WINDOW, len(self._storage))
        if window < 1:
            return False
        segment = self._storage[:window]
        lines = [f"{m['role']}: {m['content']}" for m in segment]
        summary = chat.call_summary_api("\n".join(lines))
        compressed: Message = {
            "role": "assistant",
            "content": f"[摘要] {summary.strip()}",
        }
        self._storage = [compressed, *self._storage[window:]]
        return True

    def _segment_compress_by_vector(self, chat: Chat | None) -> bool:
        """基於時間序列向量距離的動態分群、摘要與冷熱清除。

        流程概要：
          1. 對每則訊息取向量，依時間順序串流分群（相鄰語意相近則同組）。
          2. 比較最舊群組與最新群組的中心向量相似度。
          3. 無關則直接刪除最舊群組；弱關聯則 LLM 摘要為 ``[前情摘要]``。
          4. 不切到最後 4 則「熱記憶」，避免壓縮進行中的對話。
        """
        if len(self._storage) < 6 or chat is None:
            return False

        try:
            # 僅對前 200 字做向量化，降低 embedding API 成本
            embeddings = [
                chat.get_embedding(f"{msg['role']}: {str(msg.get('content', ''))[:200]}")
                for msg in self._storage
            ]
        except Exception as exc:
            print(f"[Embedding Error] 語意分群失敗 ({exc})，改用傳統摘要。")
            return False

        # 線上串流時間序列分群：groups 內為 (訊息索引, 向量)
        groups: list[list[tuple[int, list[float]]]] = [[[0, embeddings[0]]]]
        for i in range(1, len(embeddings)):
            current_emb = embeddings[i]
            last_group = groups[-1]
            avg_last_emb = self._calculate_avg_embedding(last_group)
            sim = self._cosine_similarity(current_emb, avg_last_emb)
            if sim >= self.similarity_threshold:
                last_group.append((i, current_emb))
            else:
                groups.append([(i, current_emb)])

        # 整段歷史仍屬同一連續話題時，暫不執行分段壓縮
        if len(groups) < 2:
            return False

        # 跨時空主題分析：最舊群組 vs 最新群組
        oldest_group, latest_group = groups[0], groups[-1]
        avg_oldest = self._calculate_avg_embedding(oldest_group)
        avg_latest = self._calculate_avg_embedding(latest_group)
        core_sim = self._cosine_similarity(avg_oldest, avg_latest)
        cut_idx = oldest_group[-1][0] + 1

        # 安全界線：不壓縮、不刪除進行中的最後 4 則訊息
        if cut_idx > len(self._storage) - 4:
            return False

        if core_sim < self.relevance_threshold:
            # 冷記憶：舊主題與當前話題無關 → 直接物理刪除
            print(
                f"♻️ [Memory Tiering] 舊主題與當前無關 (相似度: {core_sim:.2f})，"
                f"清除前 {cut_idx} 條。"
            )
            self._storage = self._storage[cut_idx:]
        else:
            # 溫記憶：仍有弱關聯 → 打包 LLM 摘要
            print(
                f"📦 [Memory Tiering] 舊主題弱關聯 (相似度: {core_sim:.2f})，"
                f"壓縮前 {cut_idx} 條。"
            )
            segment = self._storage[:cut_idx]
            lines = [f"{msg['role']}: {msg['content']}" for msg in segment]
            summary = chat.call_summary_api("\n".join(lines))
            compressed: Message = {
                "role": "assistant",
                "content": f"[前情摘要] {summary.strip()}",
            }
            self._storage = [compressed, *self._storage[cut_idx:]]
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
