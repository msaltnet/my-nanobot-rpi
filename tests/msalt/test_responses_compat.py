import pytest
from nanobot.providers.openai_responses import parsing, state
from openai.types.responses.response_function_tool_call import ResponseFunctionToolCall

from msalt.responses_compat import install_responses_compat


@pytest.fixture(autouse=True)
def install_compat():
    install_responses_compat()


def test_function_tool_call_serializes_wire_aliases():
    call = ResponseFunctionToolCall(
        type="function_call", name="read_file", arguments="{}", call_id="call_1",
    )
    dumped = parsing._response_object(call)
    assert "async_" not in dumped
    assert "async" not in dumped  # Absent optional SDK fields must remain absent.


def test_legacy_replayed_call_repairs_async_alias_without_changing_arguments():
    call = {
        "type": "function_call", "name": "read_file", "arguments": '{"async_":true}',
        "call_id": "call_1", "async_": None,
    }
    replayed = state._prepare_replayed_items([call])
    assert "async_" not in replayed[0]
    assert "async" not in replayed[0]
    assert replayed[0]["arguments"] == call["arguments"]
    assert "async_" in call
