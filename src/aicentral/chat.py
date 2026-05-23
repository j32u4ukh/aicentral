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

    有狀態時，多輪紀錄保存在 ``_history``（預設僅 user/assistant，不含 system）。
    ``include_tool_messages_in_history=True`` 且啟用 MCP 時，每輪另寫入
    assistant（含 tool_calls）、``role: tool`` 與最終 assistant。
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
        mcp_servers: list[str] | str | None = None,
        max_tool_rounds: int = 5,
        include_tool_messages_in_history: bool = False,
    ) -> None:
        self._mode = mode
        self._system = system
        self._model = model
        self._max_messages = max_messages
        self._history_policy = history_policy
        self._base_url = base_url
        self._api_key = api_key
        self._mcp_servers = mcp_servers
        self._max_tool_rounds = max_tool_rounds
        self._include_tool_messages_in_history = include_tool_messages_in_history
        # 有狀態模式下的對話歷史；串流與非串流皆在 _record_turn 寫入此列表
        self._history: list[Message] = []

    @classmethod
    def stateful(cls, **kwargs: Any) -> Chat:
        return cls(mode=ChatMode.STATEFUL, **kwargs)

    @classmethod
    def stateless(cls, **kwargs: Any) -> Chat:
        return cls(mode=ChatMode.STATELESS, **kwargs)

    @classmethod
    def with_mcp(
        cls,
        mcp_servers: list[str] | str,
        /,
        *,
        max_tool_rounds: int = 5,
        **kwargs: Any,
    ) -> Chat:
        """建立已啟用 MCP tool loop 的 Chat；呼叫 ``ask()`` 或 ``complete()`` 即可，無需自行組 messages。"""
        return cls(
            mcp_servers=mcp_servers,
            max_tool_rounds=max_tool_rounds,
            **kwargs,
        )

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

    def ask(self, user_input: str, **kwargs: Any) -> str:
        """提問並回覆文字（等同 ``complete(..., stream=False)``）；MCP 時由函式庫處理 tool loop。"""
        return self.complete(user_input, stream=False, **kwargs)

    def complete(
        self,
        user_input: str,
        *,
        stream: bool = False,
        context: list[Message] | None = None,
        **kwargs: Any,
    ) -> str | Iterator[str]:
        """完成一輪對話：組裝訊息、委派 ``complete()``，有狀態時寫入 ``_history``。

        - **無狀態**：不累積 ``_history``；串流回傳底層迭代器。
        - **有狀態 + 串流**：包裝迭代器，全文收齊後才 ``_record_turn``（見 ``_complete_stateful_stream``）。
        - **有狀態 + 非串流**：取得回覆後寫入歷史；MCP 且 ``include_tool_messages_in_history``
          時可能收到 ``(reply, trail)`` 並一併寫入 tool 軌跡。
        """
        # 本輪 user 訊息，並與既有 _history（或 stateless 的 context）合併成送 API 的列表
        user_msg: Message = {"role": "user", "content": user_input}
        request_messages = self._build_request_messages(
            user_msg, context=context)

        # MCP 相關參數（mcp_servers、max_tool_rounds、return_message_trail 等）
        mcp_kw = self._mcp_complete_kwargs()

        # MCP tool loop 不支援串流；在組裝請求後、呼叫底層前檢查
        if self._mcp_servers is not None and stream:
            raise ValueError(
                "Chat.complete(stream=True) 不支援 mcp_servers；請使用 stream=False")

        if self._mode == ChatMode.STATELESS:
            # 無狀態：不寫入 _history；直接轉發 complete（串流或非串流）
            if stream:
                return complete(
                    messages=request_messages,
                    model=self._model,
                    system=self._system,
                    base_url=self._base_url,
                    api_key=self._api_key,
                    stream=True,
                    **mcp_kw,
                    **kwargs,
                )
            return complete(
                messages=request_messages,
                model=self._model,
                system=self._system,
                base_url=self._base_url,
                api_key=self._api_key,
                **mcp_kw,
                **kwargs,
            )

        if stream:
            # 有狀態串流：回傳包裝迭代器，歷史在迭代結束後寫入（見 _complete_stateful_stream）
            return self._complete_stateful_stream(user_msg, request_messages, **kwargs)

        # 有狀態、非串流：呼叫底層取得全文（或 MCP trail）
        result = complete(
            messages=request_messages,
            model=self._model,
            system=self._system,
            base_url=self._base_url,
            api_key=self._api_key,
            **mcp_kw,
            **kwargs,
        )

        # 解析回傳：一般為 str；MCP + include_tool_messages_in_history 時為 (reply, trail)
        trail: list[Message] | None = None
        if isinstance(result, tuple):
            reply, trail = result
        else:
            reply = result

        # 寫入 _history（trail 含 assistant/tool_calls、tool、最終 assistant）並依 policy 修剪
        self._record_turn(user_msg, reply, trail=trail)
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
        request_messages = self._build_request_messages(
            user_msg, context=context)
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

    def _mcp_complete_kwargs(self) -> dict[str, Any]:
        if self._mcp_servers is None:
            return {}
        kw: dict[str, Any] = {
            "mcp_servers": self._mcp_servers,
            "max_tool_rounds": self._max_tool_rounds,
        }
        if self._include_tool_messages_in_history:
            kw["return_message_trail"] = True
        return kw

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

    def _record_turn(
        self,
        user_msg: Message,
        reply: str,
        *,
        trail: list[Message] | None = None,
    ) -> None:
        """將一輪對話追加至 ``_history``，並依 policy 修剪。

        ``trail`` 為 MCP 本輪訊息（assistant / tool / 最終 assistant）；若提供則不再另建單則 assistant。
        """
        self._history.append(user_msg)
        if trail:
            self._history.extend(trail)
        else:
            self._history.append({"role": "assistant", "content": reply})
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
        if self._include_tool_messages_in_history:
            return sum(1 for message in self._history if message["role"] == "user")
        return sum(1 for message in self._history if message["role"] in ("user", "assistant"))

    def _maybe_trim_history(self) -> None:
        """
        檢查聊天歷史記錄的數量是否超過最大限制，並根據歷史政策進行清理。
        """
        while self._turn_count() > self._max_messages:
            if self._history_policy == HistoryPolicy.MANUAL:
                # 如果策略是手動管理，則拋出溢出錯誤，要求使用者手動處理。
                raise HistoryOverflowError(
                    f"歷史訊息數 {self._turn_count()} 超過上限 {self._max_messages}；"
                    "請使用 delete()、trim() 或更換 history_policy。"
                )
            if self._history_policy == HistoryPolicy.DROP_OLDEST:
                if self._include_tool_messages_in_history:
                    self._drop_oldest_turn()
                else:
                    self._drop_oldest_one()
            elif self._history_policy == HistoryPolicy.DROP_OLDEST_PAIR:
                if self._include_tool_messages_in_history:
                    self._drop_oldest_turn()
                else:
                    self._drop_oldest_pair()
            elif self._history_policy == HistoryPolicy.SEGMENT_COMPRESS:
                if not self._segment_compress():
                    if self._include_tool_messages_in_history:
                        self._drop_oldest_turn()
                    else:
                        self._drop_oldest_pair()
            else:
                if self._include_tool_messages_in_history:
                    self._drop_oldest_turn()
                else:
                    self._drop_oldest_pair()

    def _drop_oldest_one(self) -> None:
        if self._history:
            self._history.pop(0)

    def _drop_oldest_turn(self) -> None:
        """移除最舊一輪（自第一則 user 至下一則 user 之前），含 MCP tool 訊息。"""
        if not self._history:
            return
        first_user = next(
            (index for index, message in enumerate(self._history) if message["role"] == "user"),
            None,
        )
        if first_user is None:
            self._history.pop(0)
            return
        next_user = next(
            (
                index
                for index, message in enumerate(self._history)
                if index > first_user and message["role"] == "user"
            ),
            None,
        )
        if next_user is None:
            del self._history[first_user:]
        else:
            del self._history[first_user:next_user]

    def _drop_oldest_pair(self) -> None:
        if not self._history:
            return
        first_user = next(
            (index for index, message in enumerate(
                self._history) if message["role"] == "user"),
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
        """
        對歷史訊息進行分段和摘要壓縮。
        """
        # 如果歷史記錄為空，則無法進行壓縮。
        if not self._history:
            return False

        # 計算要壓縮的視窗大小，取歷史記錄長度和分段窗口大小的最小值。
        window = min(_SEGMENT_WINDOW, len(self._history))

        if window < 1:
            # 如果視窗大小小於 1，則無法進行有效的分段。
            return False

        # 提取視窗內的歷史訊息作為要壓縮的內容。
        segment = self._history[:window]

        # TODO: 建議將邏輯修改為壓縮與當前訊息相關的**相近內容**，而不是僅壓縮最舊的 N 個訊息。
        # 當前實作僅壓縮最舊的 'window' 條訊息。

        # 將分段的訊息轉換為字串列表，用於送入模型進行摘要。
        lines = [
            f"{message['role']}: {message['content']}" for message in segment]

        # 使用模型對這些訊息生成摘要。
        summary = complete(
            messages=[{"role": "user", "content": "\n".join(lines)}],
            model=self._model,
            system=_SUMMARY_SYSTEM,
            base_url=self._base_url,
            api_key=self._api_key,
        )

        # 創建一個包含摘要的新的訊息，作為壓縮的結果。
        compressed: Message = {
            "role": "assistant",
            "content": f"[摘要] {summary.strip()}",
        }

        # 更新歷史記錄：用新的摘要訊息替換了最舊的 segment，並保留剩餘的歷史記錄。
        self._history = [compressed, *self._history[window:]]

        return True
