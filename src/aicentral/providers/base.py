"""Provider 模組協定（v2.0）。"""

from __future__ import annotations

from collections.abc import Iterator
from typing import Any, Protocol

from aicentral.core.types import Message


class ProviderModule(Protocol):
    """具 chat_completions / chat_completions_stream 的 provider 模組。"""

    def chat_completions(
        self,
        *,
        messages: list[Message],
        model: str,
        base_url: str | None = None,
        api_key: str | None = None,
        **kwargs: Any,
    ) -> str: ...

    def chat_completions_stream(
        self,
        *,
        messages: list[Message],
        model: str,
        base_url: str | None = None,
        api_key: str | None = None,
        **kwargs: Any,
    ) -> Iterator[str]: ...
