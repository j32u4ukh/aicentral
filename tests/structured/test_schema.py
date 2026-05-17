from pydantic import BaseModel, Field

from aicentral.structured.schema import build_tool


class Ticket(BaseModel):
    title: str = Field(description="工單標題")
    priority: int = Field(ge=1, le=5)


def test_build_tool_name_and_parameters() -> None:
    spec = build_tool(Ticket)
    assert spec.tool_name == "ticket"
    assert spec.tool_choice == {"type": "function", "function": {"name": "ticket"}}
    assert len(spec.tools) == 1
    function = spec.tools[0]["function"]
    assert function["name"] == "ticket"
    params = function["parameters"]
    assert "properties" in params
    assert "title" in params["properties"]
    assert "priority" in params["properties"]
