"""Minimal stdio JSON-RPC transport for the compact MCP tool."""

from __future__ import annotations

import argparse
import io
import json
import sys
from dataclasses import dataclass, field
from pathlib import Path
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

PARSE_ERROR: Final = -32700
INVALID_REQUEST: Final = -32600
METHOD_NOT_FOUND: Final = -32601
INVALID_PARAMS: Final = -32602
SERVER_NOT_INITIALIZED: Final = -32002


@dataclass
class McpStdioServer:
    """Tiny lifecycle wrapper around the single compact MCP dispatcher."""

    context: McpServerContext = field(default_factory=McpServerContext)
    initialized: bool = False
    ready: bool = False

    def handle_message(self, message: object) -> JsonObject | None:
        """Handle one JSON-RPC message."""

        if not isinstance(message, dict):
            return _error_response(None, INVALID_REQUEST, "Invalid Request")
        request_id = _response_id(message.get("id"))
        if message.get("jsonrpc") != JSON_RPC_VERSION:
            return _error_response(request_id, INVALID_REQUEST, "Invalid Request")
        method = message.get("method")
        if not isinstance(method, str) or not method:
            return _error_response(request_id, INVALID_REQUEST, "Invalid Request")
        if "id" not in message:
            self._handle_notification(method)
            return None
        if request_id is None:
            return _error_response(None, INVALID_REQUEST, "Invalid Request")
        return self._handle_request(method, message.get("params"), request_id)

    def _handle_notification(self, method: str) -> None:
        if method == "notifications/initialized" and self.initialized:
            self.ready = True

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
        if not self.ready:
            return _error_response(request_id, SERVER_NOT_INITIALIZED, "Server not initialized")
        if method == "tools/list":
            return self._handle_tools_list(params, request_id)
        if method == "tools/call":
            return self._handle_tools_call(params, request_id)
        return _error_response(request_id, METHOD_NOT_FOUND, "Method not found")

    def _handle_initialize(self, params: object | None, request_id: str | int) -> JsonObject:
        if params is not None and not isinstance(params, dict):
            return _invalid_params_response(request_id, "initialize params must be an object.")
        requested_version = params.get("protocolVersion") if isinstance(params, dict) else None
        protocol_version = (
            requested_version if requested_version == MCP_PROTOCOL_VERSION else MCP_PROTOCOL_VERSION
        )
        self.initialized = True
        self.ready = False
        return _result_response(
            request_id,
            {
                "protocolVersion": protocol_version,
                "capabilities": {"tools": {"listChanged": False}},
                "serverInfo": {
                    "name": SERVER_NAME,
                    "title": "Codex Supervisor",
                    "version": __version__,
                },
                "instructions": "Compact queue inspection over planning SQLite.",
            },
        )

    def _handle_tools_list(self, params: object | None, request_id: str | int) -> JsonObject:
        if params is not None and not isinstance(params, dict):
            return _invalid_params_response(request_id, "tools/list params must be an object.")
        return _result_response(request_id, {"tools": list(list_mcp_tools(context=self.context))})

    def _handle_tools_call(self, params: object | None, request_id: str | int) -> JsonObject:
        if not isinstance(params, dict):
            return _invalid_params_response(request_id, "tools/call params must be an object.")
        tool_name = params.get("name")
        if not isinstance(tool_name, str) or not tool_name.strip():
            return _invalid_params_response(request_id, "tools/call params.name must be a string.")
        arguments = params.get("arguments", {})
        if arguments is not None and not isinstance(arguments, dict):
            return _invalid_params_response(
                request_id,
                "tools/call params.arguments must be an object.",
            )
        result = dispatch_mcp_tool(tool_name, arguments, context=self.context)
        return _result_response(request_id, _tool_result_payload(result))


def serve_stdio(
    input_stream: TextIO,
    output_stream: TextIO,
    *,
    server: McpStdioServer | None = None,
    context: McpServerContext | None = None,
) -> int:
    """Serve newline-delimited JSON-RPC messages."""

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
    argv: list[str] | None = None,
) -> int:
    """Run the stdio MCP transport."""

    return serve_stdio(
        input_stream or _default_input_stream(),
        output_stream or _default_output_stream(),
        context=context or _context_from_args(argv),
    )


def _context_from_args(argv: list[str] | None) -> McpServerContext:
    parser = argparse.ArgumentParser(prog="codex-supervisor-mcp")
    parser.add_argument("--planning-path", type=Path, default=None)
    args = parser.parse_args(argv)
    return McpServerContext(planning_path=args.planning_path)


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
    except json.JSONDecodeError:
        return _error_response(None, PARSE_ERROR, "Parse error")
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
