"""
Chat 工作階段：有狀態 / 無狀態多輪對話、歷史修剪與串流（v1.1）。

串流與歷史寫入（有狀態）：
  complete(stream=True) 回傳迭代器，呼叫方每 consume 一個 delta 就收到一段文字；
  底層 SSE 有封包即 yield，不會等全文收齊才開始輸出。
  歷史寫入發生在迭代器**耗盡之後**：_complete_stateful_stream._iter 的 for 迴圈結束時
  呼叫 _record_turn，將 user 與拼接後的完整 assistant 寫入 _history。
  若中途例外或呼叫方提前停止迭代，_record_turn 不會執行，該輪不會進入歷史。
"""

from __future__ import annotations

from collections.abc import Iterable, Iterator
from enum import StrEnum
from typing import Any, TypeVar, overload

from pydantic import BaseModel

from aicentral.core.client import complete, complete_structured
from aicentral.core.errors import HistoryOverflowError
from aicentral.core.types import Message


class ChatMode(StrEnum):
    STATEFUL = "stateful"
    STATELESS = "stateless"


class HistoryPolicy(StrEnum):
    DROP_OLDEST = "drop_oldest"
    DROP_OLDEST_PAIR = "drop_oldest_pair"
    SEGMENT_COMPRESS = "segment_compress"
    MANUAL = "manual"


T = TypeVar("T", bound=BaseModel)

_SEGMENT_WINDOW = 5
_SUMMARY_SYSTEM = (
    "將以下對話摘要為一段繁體中文，保留事實與決策，刪除贅詞。只輸出摘要正文。"
)


class Chat:
    """可切換有狀態 / 無狀態的聊天工作階段。

    有狀態時，多輪紀錄保存在 ``_history``（僅 user/assistant，不含 system）。
    system 由 ``complete()`` 在每次請求時透過參數或環境變數注入，不計入 ``max_messages``。
    """

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
        # 有狀態模式下的對話歷史；串流與非串流皆在 _record_turn 寫入此列表
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

    @overload
    def complete(
        self,
        user_input: str,
        *,
        stream: bool = False,
        context: list[Message] | None = None,
        **kwargs: Any,
    ) -> str: ...

    @overload
    def complete(
        self,
        user_input: str,
        *,
        stream: bool = True,
        context: list[Message] | None = None,
        **kwargs: Any,
    ) -> Iterator[str]: ...

    def complete(
        self,
        user_input: str,
        *,
        stream: bool = False,
        context: list[Message] | None = None,
        **kwargs: Any,
    ) -> str | Iterator[str]:
        user_msg: Message = {"role": "user", "content": user_input}
        request_messages = self._build_request_messages(user_msg, context=context)

        if self._mode == ChatMode.STATELESS:
            # 無狀態：不寫入 _history；串流直接轉發底層迭代器
            if stream:
                return complete(
                    messages=request_messages,
                    model=self._model,
                    system=self._system,
                    base_url=self._base_url,
                    api_key=self._api_key,
                    stream=True,
                    **kwargs,
                )
            return complete(
                messages=request_messages,
                model=self._model,
                system=self._system,
                base_url=self._base_url,
                api_key=self._api_key,
                **kwargs,
            )

        if stream:
            # 有狀態串流：回傳包裝迭代器，歷史在迭代結束後寫入（見 _complete_stateful_stream）
            return self._complete_stateful_stream(user_msg, request_messages, **kwargs)

        # 有狀態、非串流：取得全文後立即寫入歷史
        reply = complete(
            messages=request_messages,
            model=self._model,
            system=self._system,
            base_url=self._base_url,
            api_key=self._api_key,
            **kwargs,
        )
        self._record_turn(user_msg, reply)
        return reply

    def complete_structured(
        self,
        user_input: str,
        *,
        response_model: type[T],
        context: list[Message] | None = None,
        **kwargs: Any,
    ) -> T:
        """結構化完成一輪：只需傳入使用者文字，由函式庫處理 schema / tools / 驗證。

        有狀態時成功後將 ``response_model`` 的 JSON 寫入歷史。
        """
        user_msg: Message = {"role": "user", "content": user_input}
        request_messages = self._build_request_messages(user_msg, context=context)
        result = complete_structured(
            messages=request_messages,
            response_model=response_model,
            model=self._model,
            system=self._system,
            base_url=self._base_url,
            api_key=self._api_key,
            **kwargs,
        )
        if self._mode == ChatMode.STATEFUL:
            self._record_turn(user_msg, result.model_dump_json())
        return result

    def _build_request_messages(
        self,
        user_msg: Message,
        *,
        context: list[Message] | None,
    ) -> list[Message]:
        if self._mode == ChatMode.STATELESS:
            prefix = list(context) if context else []
            return [*prefix, user_msg]
        return [*self._history, user_msg]

    def _complete_stateful_stream(
        self,
        user_msg: Message,
        request_messages: list[Message],
        **kwargs: Any,
    ) -> Iterator[str]:
        """有狀態串流：邊收 SSE delta 邊 yield；全文收齊後才寫入 _history。"""
        stream = complete(
            messages=request_messages,
            model=self._model,
            system=self._system,
            base_url=self._base_url,
            api_key=self._api_key,
            stream=True,
            **kwargs,
        )

        def _iter() -> Iterator[str]:
            chunks: list[str] = []
            # 每收到一個 delta 立刻轉給呼叫方（終端可即時印出）
            for delta in stream:
                chunks.append(delta)
                yield delta
            # ★ 串流跑完、迭代器耗盡後，在此將本輪寫回歷史（非逐 delta 寫入）
            self._record_turn(user_msg, "".join(chunks))

        return _iter()

    def _record_turn(self, user_msg: Message, reply: str) -> None:
        """將一輪 user + assistant 追加至 _history，並依 policy 修剪。"""
        assistant_msg: Message = {"role": "assistant", "content": reply}
        self._history.append(user_msg)
        self._history.append(assistant_msg)
        self._maybe_trim_history()

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
