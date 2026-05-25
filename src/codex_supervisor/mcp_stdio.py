"""Stdio JSON-RPC transport for the read-only MCP supervisor tools."""

from __future__ import annotations

import io
import json
import sys
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Final, TextIO

from codex_supervisor import __version__
from codex_supervisor.mcp_server import (
    JsonObject,
    McpServerContext,
    dispatch_mcp_tool,
    list_mcp_tools,
)

JSON_RPC_VERSION: Final = "2.0"
MCP_PROTOCOL_VERSION: Final = "2025-11-25"
SERVER_NAME: Final = "codex-supervisor"

PARSE_ERROR = -32700
INVALID_REQUEST = -32600
METHOD_NOT_FOUND = -32601
INVALID_PARAMS = -32602
INTERNAL_ERROR = -32603
SERVER_NOT_INITIALIZED = -32002

ToolDispatcher = Callable[[str, object | None, McpServerContext], JsonObject]
ToolLister = Callable[[McpServerContext], tuple[JsonObject, ...]]


def _default_tool_dispatcher(
    tool_name: str,
    arguments: object | None,
    context: McpServerContext,
) -> JsonObject:
    return dispatch_mcp_tool(tool_name, arguments, context=context)


def _default_tool_lister(context: McpServerContext) -> tuple[JsonObject, ...]:
    return list_mcp_tools(context=context)


@dataclass
class McpStdioServer:
    """Stateful MCP stdio session around the read-only tool dispatcher."""

    context: McpServerContext = field(default_factory=McpServerContext)
    tool_dispatcher: ToolDispatcher = _default_tool_dispatcher
    tool_lister: ToolLister = _default_tool_lister
    initialized: bool = False
    lifecycle_ready: bool = False

    def handle_message(self, message: object) -> JsonObject | None:
        """Handle one decoded JSON-RPC message and return an optional response."""

        if not isinstance(message, dict):
            return _error_response(
                None,
                INVALID_REQUEST,
                "Invalid Request",
                data={"code": "invalid_request", "message": "JSON-RPC message must be an object."},
            )
        request_id = _response_id(message.get("id"))
        if message.get("jsonrpc") != JSON_RPC_VERSION:
            return _error_response(
                request_id,
                INVALID_REQUEST,
                "Invalid Request",
                data={"code": "invalid_request", "message": "jsonrpc must be '2.0'."},
            )
        method = message.get("method")
        if not isinstance(method, str) or not method:
            return _error_response(
                request_id,
                INVALID_REQUEST,
                "Invalid Request",
                data={"code": "invalid_request", "message": "method must be a nonblank string."},
            )
        has_id = "id" in message
        if has_id and not _is_valid_request_id(message.get("id")):
            return _error_response(
                None,
                INVALID_REQUEST,
                "Invalid Request",
                data={
                    "code": "invalid_request",
                    "message": "request id must be a string or integer.",
                },
            )
        if not has_id:
            self._handle_notification(method)
            return None
        return self._handle_request(method, message.get("params"), message["id"])

    def _handle_notification(self, method: str) -> None:
        if method == "notifications/initialized" and self.initialized:
            self.lifecycle_ready = True

    def _handle_request(
        self,
        method: str,
        params: object | None,
        request_id: str | int,
    ) -> JsonObject:
        if method == "initialize":
            return self._handle_initialize(params, request_id)
        if method == "ping":
            return _result_response(request_id, {})
        if not self.lifecycle_ready:
            return _error_response(
                request_id,
                SERVER_NOT_INITIALIZED,
                "Server not initialized",
                data={
                    "code": "server_not_initialized",
                    "message": "Call initialize and send notifications/initialized first.",
                },
            )
        if method == "tools/list":
            return self._handle_tools_list(params, request_id)
        if method == "tools/call":
            return self._handle_tools_call(params, request_id)
        return _error_response(
            request_id,
            METHOD_NOT_FOUND,
            "Method not found",
            data={"code": "method_not_found", "method": method},
        )

    def _handle_initialize(self, params: object | None, request_id: str | int) -> JsonObject:
        if params is not None and not isinstance(params, dict):
            return _invalid_params_response(request_id, "initialize params must be an object.")
        requested_version = params.get("protocolVersion") if isinstance(params, dict) else None
        protocol_version = (
            requested_version if requested_version == MCP_PROTOCOL_VERSION else MCP_PROTOCOL_VERSION
        )
        self.initialized = True
        self.lifecycle_ready = False
        return _result_response(
            request_id,
            {
                "protocolVersion": protocol_version,
                "capabilities": _capabilities(self.context),
                "serverInfo": {
                    "name": SERVER_NAME,
                    "title": "Codex Supervisor",
                    "version": __version__,
                },
                "instructions": "Read-only codex-supervisor inspection tools.",
            },
        )

    def _handle_tools_list(self, params: object | None, request_id: str | int) -> JsonObject:
        if params is not None and not isinstance(params, dict):
            return _invalid_params_response(request_id, "tools/list params must be an object.")
        return _result_response(request_id, {"tools": list(self.tool_lister(self.context))})

    def _handle_tools_call(self, params: object | None, request_id: str | int) -> JsonObject:
        if not isinstance(params, dict):
            return _invalid_params_response(request_id, "tools/call params must be an object.")
        tool_name = params.get("name")
        if not isinstance(tool_name, str) or not tool_name.strip():
            return _invalid_params_response(request_id, "tools/call params.name must be a string.")
        arguments = params.get("arguments", {})
        if not isinstance(arguments, dict):
            return _invalid_params_response(
                request_id,
                "tools/call params.arguments must be an object.",
            )
        try:
            result = self.tool_dispatcher(tool_name, arguments, self.context)
        except Exception as exc:
            result = {
                "ok": False,
                "tool": tool_name,
                "error": {
                    "code": "dispatcher_failed",
                    "message": str(exc) or exc.__class__.__name__,
                },
            }
        return _result_response(request_id, _tool_result_payload(result))


def serve_stdio(
    input_stream: TextIO,
    output_stream: TextIO,
    *,
    server: McpStdioServer | None = None,
    context: McpServerContext | None = None,
) -> int:
    """Serve newline-delimited JSON-RPC messages from stdin-like text streams."""

    active_server = server or McpStdioServer(context=context or McpServerContext())
    for line in input_stream:
        payload = line.rstrip("\r\n")
        if not payload:
            continue
        response = _decode_and_handle(active_server, payload)
        if response is not None:
            _write_json_line(output_stream, response)
    return 0


def main(
    input_stream: TextIO | None = None,
    output_stream: TextIO | None = None,
    *,
    context: McpServerContext | None = None,
) -> int:
    """Run the MCP stdio server with injectable streams for tests."""

    return serve_stdio(
        input_stream or _default_input_stream(),
        output_stream or _default_output_stream(),
        context=context,
    )


def _default_input_stream() -> TextIO:
    if isinstance(sys.stdin, io.TextIOWrapper):
        sys.stdin.reconfigure(encoding="utf-8")
    return sys.stdin


def _default_output_stream() -> TextIO:
    if isinstance(sys.stdout, io.TextIOWrapper):
        sys.stdout.reconfigure(encoding="utf-8", newline="\n")
    return sys.stdout


def _decode_and_handle(server: McpStdioServer, payload: str) -> JsonObject | None:
    try:
        message = json.loads(payload)
    except json.JSONDecodeError as exc:
        return _error_response(
            None,
            PARSE_ERROR,
            "Parse error",
            data={"code": "parse_error", "message": exc.msg},
        )
    return server.handle_message(message)


def _tool_result_payload(dispatch_result: JsonObject) -> JsonObject:
    payload: JsonObject = {
        "content": [
            {
                "type": "text",
                "text": json.dumps(dispatch_result, sort_keys=True, separators=(",", ":")),
            }
        ],
        "structuredContent": dispatch_result,
    }
    if dispatch_result.get("ok") is False:
        payload["isError"] = True
    return payload


def _capabilities(context: McpServerContext) -> JsonObject:
    if not context.enabled:
        return {}
    return {"tools": {"listChanged": False}}


def _is_valid_request_id(value: object) -> bool:
    return isinstance(value, str) or (isinstance(value, int) and not isinstance(value, bool))


def _response_id(value: object) -> str | int | None:
    if isinstance(value, str):
        return value
    if isinstance(value, int) and not isinstance(value, bool):
        return value
    return None


def _invalid_params_response(request_id: str | int, message: str) -> JsonObject:
    return _error_response(
        request_id,
        INVALID_PARAMS,
        "Invalid params",
        data={"code": "validation_error", "message": message},
    )


def _result_response(request_id: str | int, result: JsonObject) -> JsonObject:
    return {"jsonrpc": JSON_RPC_VERSION, "id": request_id, "result": result}


def _error_response(
    request_id: str | int | None,
    code: int,
    message: str,
    *,
    data: object | None = None,
) -> JsonObject:
    error: JsonObject = {"code": code, "message": message}
    if data is not None:
        error["data"] = data
    return {"jsonrpc": JSON_RPC_VERSION, "id": request_id, "error": error}


def _write_json_line(output_stream: TextIO, message: JsonObject) -> None:
    output_stream.write(json.dumps(message, sort_keys=True, separators=(",", ":")))
    output_stream.write("\n")
    output_stream.flush()


if __name__ == "__main__":
    raise SystemExit(main())
