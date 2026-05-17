import pytest
from pydantic import BaseModel, Field, ValidationError

from aicentral.structured.validate import format_validation_errors, parse


class Ticket(BaseModel):
    title: str
    priority: int = Field(ge=1, le=5)


def test_parse_valid() -> None:
    ticket = parse({"title": "a", "priority": 2}, Ticket)
    assert ticket.title == "a"
    assert ticket.priority == 2


def test_parse_invalid_raises() -> None:
    with pytest.raises(ValidationError) as exc_info:
        parse({"title": "a", "priority": 9}, Ticket)
    summary = format_validation_errors(exc_info.value)
    assert "priority" in summary
