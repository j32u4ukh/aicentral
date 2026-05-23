"""
Chat 工作階段：有狀態 / 無狀態多輪對話、歷史修剪與串流（v1.2）。

職責分工：
  - 本模組：組裝請求、委派 ``complete()`` / ``complete_structured()``、模式切換。
  - ``History``（``aicentral.history``）：儲存、裁剪、向量分群與摘要壓縮。

串流與歷史寫入（有狀態）：
  ``complete(stream=True)`` 回傳迭代器，呼叫方每 consume 一個 delta 即收到一段文字。
  歷史寫入發生在迭代器**耗盡之後**；若中途例外或提前停止迭代，該輪不會進入 ``history``。
"""

from __future__ import annotations

import logging
from collections.abc import Iterable, Iterator
from enum import StrEnum
from typing import Any, TypeVar, overload

from pydantic import BaseModel

from aicentral.core.client import complete, complete_structured
from aicentral.core.types import Message
from aicentral.history import History, HistoryPolicy
from aicentral.routing.router import effective_embedding_model, effective_model

# 向後相容：歷史政策仍可由 ``from aicentral.chat import HistoryPolicy`` 匯入
__all__ = ["Chat", "ChatMode", "HistoryPolicy"]

_logger = logging.getLogger(__name__)


class ChatMode(StrEnum):
    """對話是否累積歷史。"""

    STATEFUL = "stateful"
    STATELESS = "stateless"


T = TypeVar("T", bound=BaseModel)


class Chat:
    """可切換有狀態 / 無狀態的聊天工作階段。

    有狀態時，多輪紀錄由 ``history`` 管理（預設僅 user/assistant，不含 system）。
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
        embedding_model: str | None = None,
    ) -> None:
        self._mode = mode
        self._system = system
        self._model = model
        self._base_url = base_url
        self._api_key = api_key
        self._mcp_servers = mcp_servers
        self._max_tool_rounds = max_tool_rounds
        # 記憶體管理解耦：向量用 embedding_model，摘要用對話 model（見 defaults.embedding_model）
        self.history = History(
            max_messages=max_messages,
            policy=history_policy,
            include_tool_messages=include_tool_messages_in_history,
            embedding_model=effective_embedding_model(embedding_model),
            summary_model=effective_model(model),
            base_url=base_url,
            api_key=api_key,
        )

    @classmethod
    def stateful(cls, **kwargs: Any) -> Chat:
        """建立有狀態工作階段（預設會累積 ``history``）。"""
        return cls(mode=ChatMode.STATEFUL, **kwargs)

    @classmethod
    def stateless(cls, **kwargs: Any) -> Chat:
        """建立無狀態工作階段（不寫入 ``history``，可搭配 ``context`` 傳入前情）。"""
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
        """返回當前歷史快照；無狀態模式一律回傳空列表。"""
        if self._mode == ChatMode.STATELESS:
            return []
        return self.history.messages

    def set_mode(self, mode: ChatMode, *, clear_on_stateless: bool = True) -> None:
        """切換模式；預設切到無狀態時會 ``clear()`` 歷史。"""
        self._mode = mode
        if mode == ChatMode.STATELESS and clear_on_stateless:
            self.clear()

    def clear(self) -> None:
        """清空 ``history`` 內所有訊息。"""
        self.history.clear()

    def delete(self, indices: Iterable[int]) -> None:
        """依索引刪除歷史訊息（僅有狀態有效）。"""
        if self._mode != ChatMode.STATEFUL:
            return
        self.history.delete(indices)

    def trim(self, *, keep_last: int) -> None:
        """保留最後 N 則原始訊息（依 ``turn_count`` 語意，見 ``History.trim``）。"""
        if self._mode != ChatMode.STATEFUL:
            return
        self.history.trim(keep_last)

    def _turn_count(self) -> int:
        """有效對話輪數（供測試與內部檢查；委派 ``history.turn_count``）。"""
        return self.history.turn_count()

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
        """完成一輪對話：組裝訊息、委派 ``complete()``，有狀態時寫入 ``history``。

        - **無狀態**：不累積歷史；串流回傳底層迭代器。
        - **有狀態 + 串流**：包裝迭代器，全文收齊後才 ``record_turn``（見 ``_complete_stateful_stream``）。
        - **有狀態 + 非串流**：取得回覆後寫入歷史；MCP 且 ``include_tool_messages_in_history``
          時可能收到 ``(reply, trail)`` 並一併寫入 tool 軌跡。
        - **SEGMENT_COMPRESS**：對話 API 與向量化 API 皆完成後才回傳（見 ``_record_stateful_turn``）。
        """
        # 組裝本輪 user 訊息，並與 history 或 stateless context 合併
        user_msg: Message = {"role": "user", "content": user_input}
        request_messages = self._build_request_messages(user_msg, context=context)
        mcp_kw = self._mcp_complete_kwargs()

        # MCP tool loop 不支援串流；在呼叫底層前檢查
        if self._mcp_servers is not None and stream:
            raise ValueError(
                "Chat.complete(stream=True) 不支援 mcp_servers；請使用 stream=False"
            )

        # 無狀態：不寫入 history，直接轉發底層 complete
        if self._mode == ChatMode.STATELESS:
            return complete(
                messages=request_messages,
                model=self._model,
                system=self._system,
                base_url=self._base_url,
                api_key=self._api_key,
                stream=stream,
                **mcp_kw,
                **kwargs,
            )

        # 有狀態 + 串流：回傳包裝迭代器，歷史在迭代結束後寫入
        if stream:
            return self._complete_stateful_stream(user_msg, request_messages, **kwargs)

        # 有狀態 + 非串流：呼叫底層取得全文（或 MCP trail）
        result = complete(
            messages=request_messages,
            model=self._model,
            system=self._system,
            base_url=self._base_url,
            api_key=self._api_key,
            **mcp_kw,
            **kwargs,
        )

        # 解析回傳：一般為 str；MCP + include_tool_messages 時為 (reply, trail)
        trail: list[Message] | None = None
        if isinstance(result, tuple):
            reply, trail = result
        else:
            reply = result

        self._record_stateful_turn(user_msg, reply, trail=trail)
        return reply

    def complete_structured(
        self,
        user_input: str,
        *,
        response_model: type[T],
        context: list[Message] | None = None,
        **kwargs: Any,
    ) -> T:
        """結構化完成一輪：由函式庫處理 schema / tools / 驗證。

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
            self._record_stateful_turn(user_msg, result.model_dump_json())
        return result

    # ==========================================
    # 對外便利方法（委派至 History 使用的同一組模型參數）
    # ==========================================
    def _record_stateful_turn(
        self,
        user_msg: Message,
        reply: str,
        *,
        trail: list[Message] | None = None,
    ) -> None:
        """寫入 history；``SEGMENT_COMPRESS`` 時先完成對話與向量化兩個 API 再寫入。"""
        turn_embedding: list[float] | None = None
        if self.history.policy == HistoryPolicy.SEGMENT_COMPRESS and not trail:
            try:
                turn_embedding = self.history.embed_turn(user_msg, reply)
            except Exception as exc:
                _logger.warning("本輪向量化失敗 (%s)，壓縮時將嘗試補齊或降級。", exc)
        self.history.record_turn(
            user_msg,
            reply,
            trail=trail,
            turn_embedding=turn_embedding,
        )

    def get_embedding(self, text: str) -> list[float]:
        """取向量（使用 ``history.embedding_model``，非對話 ``model``）。"""
        return self.history._get_embedding(text)

    def call_summary_api(self, text: str) -> str:
        """產生歷史摘要（使用 ``history.summary_model``）。"""
        return self.history._call_summary_api(text)

    def _mcp_complete_kwargs(self) -> dict[str, Any]:
        """組裝傳給底層 ``complete()`` 的 MCP 參數。"""
        if self._mcp_servers is None:
            return {}
        kw: dict[str, Any] = {
            "mcp_servers": self._mcp_servers,
            "max_tool_rounds": self._max_tool_rounds,
        }
        # 需在歷史保留 tool 軌跡時，要求 orchestrator 回傳 trail
        if self.history.include_tool_messages:
            kw["return_message_trail"] = True
        return kw

    def _build_request_messages(
        self,
        user_msg: Message,
        *,
        context: list[Message] | None,
    ) -> list[Message]:
        """合併本輪 user 與前情，產生送 API 的 messages 列表。"""
        if self._mode == ChatMode.STATELESS:
            prefix = list(context) if context else []
            return [*prefix, user_msg]
        return [*self.history.messages, user_msg]

    def _complete_stateful_stream(
        self,
        user_msg: Message,
        request_messages: list[Message],
        **kwargs: Any,
    ) -> Iterator[str]:
        """有狀態串流：邊收 SSE delta 邊 yield；全文收齊後才寫入 history。"""
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
            # 串流耗盡後：向量化 + 寫入 history；中途例外則不會執行到此
            self._record_stateful_turn(user_msg, "".join(chunks))

        return _iter()
