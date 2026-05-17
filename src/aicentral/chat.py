"""
Chat 工作階段：有狀態 / 無狀態多輪對話與歷史修剪（v1.1）。
"""

from __future__ import annotations

from collections.abc import Iterable
from enum import StrEnum
from typing import Any

from aicentral.client import complete
from aicentral.exceptions import HistoryOverflowError
from aicentral.types import Message


class ChatMode(StrEnum):
    STATEFUL = "stateful"
    STATELESS = "stateless"


class HistoryPolicy(StrEnum):
    DROP_OLDEST = "drop_oldest"
    DROP_OLDEST_PAIR = "drop_oldest_pair"
    SEGMENT_COMPRESS = "segment_compress"
    MANUAL = "manual"


_SEGMENT_WINDOW = 5
_SUMMARY_SYSTEM = (
    "將以下對話摘要為一段繁體中文，保留事實與決策，刪除贅詞。只輸出摘要正文。"
)


class Chat:
    """可切換有狀態 / 無狀態的聊天工作階段。"""

    def __init__(
        self,
        *,
        mode: ChatMode = ChatMode.STATEFUL,
        system: str | None = None,
        model: str | None = None,
        max_messages: int = 40,
        history_policy: HistoryPolicy = HistoryPolicy.DROP_OLDEST_PAIR,
        base_url: str | None = None,
        api_key: str | None = None,
    ) -> None:
        self._mode = mode
        self._system = system
        self._model = model
        self._max_messages = max_messages
        self._history_policy = history_policy
        self._base_url = base_url
        self._api_key = api_key
        self._history: list[Message] = []

    @classmethod
    def stateful(cls, **kwargs: Any) -> Chat:
        return cls(mode=ChatMode.STATEFUL, **kwargs)

    @classmethod
    def stateless(cls, **kwargs: Any) -> Chat:
        return cls(mode=ChatMode.STATELESS, **kwargs)

    @property
    def mode(self) -> ChatMode:
        return self._mode

    @property
    def messages(self) -> list[Message]:
        if self._mode == ChatMode.STATELESS:
            return []
        return list(self._history)

    def set_mode(self, mode: ChatMode, *, clear_on_stateless: bool = True) -> None:
        self._mode = mode
        if mode == ChatMode.STATELESS and clear_on_stateless:
            self.clear()

    def complete(
        self,
        user_input: str,
        *,
        context: list[Message] | None = None,
        **kwargs: Any,
    ) -> str:
        user_msg: Message = {"role": "user", "content": user_input}

        if self._mode == ChatMode.STATELESS:
            prefix = list(context) if context else []
            request_messages = [*prefix, user_msg]
            return complete(
                messages=request_messages,
                model=self._model,
                system=self._system,
                base_url=self._base_url,
                api_key=self._api_key,
                **kwargs,
            )

        request_messages = [*self._history, user_msg]
        reply = complete(
            messages=request_messages,
            model=self._model,
            system=self._system,
            base_url=self._base_url,
            api_key=self._api_key,
            **kwargs,
        )
        assistant_msg: Message = {"role": "assistant", "content": reply}
        self._history.append(user_msg)
        self._history.append(assistant_msg)
        self._maybe_trim_history()
        return reply

    def clear(self) -> None:
        self._history.clear()

    def delete(self, indices: Iterable[int]) -> None:
        if self._mode != ChatMode.STATEFUL:
            return
        for index in sorted(set(indices), reverse=True):
            if 0 <= index < len(self._history):
                del self._history[index]

    def trim(self, *, keep_last: int) -> None:
        if self._mode != ChatMode.STATEFUL or keep_last < 0:
            return
        if keep_last == 0:
            self.clear()
            return
        if self._turn_count() <= keep_last:
            return
        self._history = self._history[-keep_last:]

    def _turn_count(self) -> int:
        return sum(1 for message in self._history if message["role"] in ("user", "assistant"))

    def _maybe_trim_history(self) -> None:
        while self._turn_count() > self._max_messages:
            if self._history_policy == HistoryPolicy.MANUAL:
                raise HistoryOverflowError(
                    f"歷史訊息數 {self._turn_count()} 超過上限 {self._max_messages}；"
                    "請使用 delete()、trim() 或更換 history_policy。"
                )
            if self._history_policy == HistoryPolicy.DROP_OLDEST:
                self._drop_oldest_one()
            elif self._history_policy == HistoryPolicy.DROP_OLDEST_PAIR:
                self._drop_oldest_pair()
            elif self._history_policy == HistoryPolicy.SEGMENT_COMPRESS:
                if not self._segment_compress():
                    self._drop_oldest_pair()
            else:
                self._drop_oldest_pair()

    def _drop_oldest_one(self) -> None:
        if self._history:
            self._history.pop(0)

    def _drop_oldest_pair(self) -> None:
        if not self._history:
            return
        first_user = next(
            (index for index, message in enumerate(self._history) if message["role"] == "user"),
            None,
        )
        if first_user is None:
            self._history.pop(0)
            return
        end = first_user + 1
        if end < len(self._history) and self._history[end]["role"] == "assistant":
            end += 1
        del self._history[first_user:end]

    def _segment_compress(self) -> bool:
        """壓縮最舊區段；成功回傳 True，無法壓縮回傳 False。"""
        if not self._history:
            return False
        window = min(_SEGMENT_WINDOW, len(self._history))
        if window < 1:
            return False
        segment = self._history[:window]
        lines = [f"{message['role']}: {message['content']}" for message in segment]
        summary = complete(
            messages=[{"role": "user", "content": "\n".join(lines)}],
            model=self._model,
            system=_SUMMARY_SYSTEM,
            base_url=self._base_url,
            api_key=self._api_key,
        )
        compressed: Message = {
            "role": "assistant",
            "content": f"[摘要] {summary.strip()}",
        }
        self._history = [compressed, *self._history[window:]]
        return True
