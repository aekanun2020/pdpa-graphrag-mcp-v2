#!/usr/bin/env python3
"""Generic contract-driven LLM/MCP harness runtime."""

from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
import os
import re
import shutil
import subprocess
import sys
import time
import urllib.error
import urllib.request
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from types import ModuleType
from typing import Any


# Models the owner has authorized, one per profile. Adding a model here is a policy decision,
# recorded in AGENTS.md, not a configuration edit: qwen3.5 (root default) and deepseek-v4.1-flash
# (102/117 over three BPS-39 rounds, codex-queue jobs 014 and 016, 2026-10-01).
AUTHORIZED_MODELS = ("qwen/qwen3.5-35b-a3b", "deepseek/deepseek-v4.1-flash")


class HarnessError(RuntimeError):
    pass


class IncompleteGeneration(HarnessError):
    """A saved provider response ended before a complete assistant turn."""

    def __init__(self, reason: str, content: str = '') -> None:
        super().__init__('Incomplete model generation: ' + reason)
        self.content = content


def response_message(value: dict[str, Any], model: str) -> dict[str, Any]:
    """Validate the real provider envelope before accepting any model text."""
    require(isinstance(value, dict), 'Model response is not an object')
    require(not value.get('error'), 'Model API error: ' + str(value.get('error')))
    require(value.get('model') == model, 'Unexpected model: ' + str(value.get('model')))
    choices = value.get('choices')
    require(isinstance(choices, list) and choices, 'Model returned no choices')
    choice = choices[0]
    message = choice.get('message')
    require(isinstance(message, dict), 'Model returned no assistant message')
    reason = choice.get('finish_reason')
    if reason == 'length':
        raise IncompleteGeneration('length', str(message.get('content') or ''))
    require(reason in {'stop', 'tool_calls'}, 'Model finish failed: ' + str(reason))
    require(not message.get('refusal'), 'Model refused the request')
    require(not choice.get('error'), 'Model choice failed: ' + str(choice.get('error')))
    if not (message.get('content') or '').strip() and not message.get('tool_calls'):
        raise IncompleteGeneration('empty content')
    return message


def require(condition: bool, message: str) -> None:
    if not condition:
        raise HarnessError(message)


def canonical(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def digest(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def repair_release(calls: int, base_limit: int, released: int, repair_calls: int, wanted_tools: list[str]) -> tuple[int, list[str]]:
    """Budget after a rejected draft: how many held-back calls to release, and which tools to open.

    A rejection that can be fixed by rewriting the draft needs one more call; one that the hook
    says needs a query (wanted_tools) needs two, the query and the redraft. Held-back calls are
    released only when the remaining budget cannot cover that, so a clean run never pays. Tools
    are opened only when both calls fit; otherwise a query would be spent with no call left to
    draft from it.
    """
    needed = calls + (2 if wanted_tools else 1) - (base_limit + released)
    if needed > 0:
        released += min(needed, max(0, repair_calls - released))
    fits = calls + 2 <= base_limit + released
    return released, (list(wanted_tools) if wanted_tools and fits else [])


def write_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def load_json(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    require(isinstance(value, dict), f"{path} must contain a JSON object")
    return value


def schema_errors(value: Any, schema: dict[str, Any], path: str = "$") -> list[str]:
    if "anyOf" in schema:
        branches = [schema_errors(value, branch, path) for branch in schema["anyOf"]]
        return [] if any(not errors for errors in branches) else [f"{path}: no anyOf branch matched"]
    if "oneOf" in schema:
        matches = sum(not schema_errors(value, branch, path) for branch in schema["oneOf"])
        return [] if matches == 1 else [f"{path}: expected exactly one oneOf match"]
    expected = schema.get("type")
    checks = {
        "object": lambda item: isinstance(item, dict),
        "array": lambda item: isinstance(item, list),
        "string": lambda item: isinstance(item, str),
        "integer": lambda item: isinstance(item, int) and not isinstance(item, bool),
        "number": lambda item: isinstance(item, (int, float)) and not isinstance(item, bool),
        "boolean": lambda item: isinstance(item, bool),
        "null": lambda item: item is None,
    }
    if expected in checks and not checks[expected](value):
        return [f"{path}: expected {expected}, got {type(value).__name__}"]
    errors: list[str] = []
    if "enum" in schema and value not in schema["enum"]:
        errors.append(f"{path}: value is outside enum")
    if isinstance(value, dict):
        properties = schema.get("properties", {})
        for key in schema.get("required", []):
            if key not in value:
                errors.append(f"{path}.{key}: required")
        if schema.get("additionalProperties") is False:
            errors.extend(f"{path}.{key}: additional property forbidden" for key in value if key not in properties)
        for key, item in value.items():
            if key in properties:
                errors.extend(schema_errors(item, properties[key], f"{path}.{key}"))
    if isinstance(value, list) and isinstance(schema.get("items"), dict):
        for index, item in enumerate(value):
            errors.extend(schema_errors(item, schema["items"], f"{path}[{index}]"))
    return errors


def json_from_text(text: str) -> dict[str, Any]:
    start, end = text.find("{"), text.rfind("}")
    require(start >= 0 and end > start, "Model output has no JSON object")
    try:
        value = json.loads(text[start:end + 1])
    except json.JSONDecodeError as exc:
        raise HarnessError(f"Invalid model JSON: {exc}") from exc
    require(isinstance(value, dict), "Model JSON is not an object")
    return value


class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req: Any, fp: Any, code: int, msg: str, headers: Any, newurl: str) -> None:
        raise HarnessError(f"Redirect refused: {code} {newurl}")


class MCPClient:
    def __init__(self, config: dict[str, Any], timeout: float) -> None:
        self.config = config
        self.endpoint = config["endpoint"]
        self.timeout = timeout
        self.request_id = 0
        self.session_id: str | None = None
        self.protocol_version: str | None = None
        self.opener = urllib.request.build_opener(NoRedirect())

    @staticmethod
    def decode(body: bytes, content_type: str) -> dict[str, Any]:
        if not body:
            return {}
        if "text/event-stream" not in content_type:
            value = json.loads(body.decode("utf-8"))
            require(isinstance(value, dict), "MCP response is not an object")
            return value
        events: list[dict[str, Any]] = []
        data_lines: list[str] = []
        for line in body.decode("utf-8").splitlines() + [""]:
            if line == "":
                if data_lines:
                    events.append(json.loads("\n".join(data_lines)))
                    data_lines = []
            elif line.startswith("data:"):
                data_lines.append(line[5:].lstrip())
        require(bool(events), "MCP returned empty SSE")
        return events[-1]

    def request(self, method: str, params: dict[str, Any] | None = None, notification: bool = False) -> dict[str, Any]:
        payload: dict[str, Any] = {"jsonrpc": "2.0", "method": method}
        if params is not None:
            payload["params"] = params
        if not notification:
            self.request_id += 1
            payload["id"] = self.request_id
        headers = {"Content-Type": "application/json", "Accept": "application/json, text/event-stream"}
        if self.session_id:
            headers["Mcp-Session-Id"] = self.session_id
        if self.protocol_version:
            headers["MCP-Protocol-Version"] = self.protocol_version
        request = urllib.request.Request(
            self.endpoint,
            data=canonical(payload).encode(),
            headers=headers,
            method="POST",
        )
        maximum = self.config["max_response_bytes"]
        try:
            with self.opener.open(request, timeout=self.timeout) as response:
                body = response.read(maximum + 1)
                require(len(body) <= maximum, "MCP response budget exceeded")
                if response.headers.get("Mcp-Session-Id"):
                    self.session_id = response.headers["Mcp-Session-Id"]
                envelope = self.decode(body, response.headers.get("Content-Type", ""))
        except urllib.error.HTTPError as exc:
            raise HarnessError(f"MCP HTTP {exc.code}: {exc.read(4096).decode(errors='replace')}") from exc
        except urllib.error.URLError as exc:
            raise HarnessError(f"MCP connection failed: {exc.reason}") from exc
        if notification:
            return {}
        require("error" not in envelope, f"MCP JSON-RPC error: {envelope.get('error')}")
        require(envelope.get("id") == self.request_id, "MCP response id mismatch")
        result = envelope.get("result")
        require(isinstance(result, dict), "MCP result is not an object")
        return result

    def initialize(self) -> dict[str, Any]:
        protocol = self.config["protocol_version"]
        result = self.request(
            "initialize",
            {
                "protocolVersion": protocol,
                "capabilities": {},
                "clientInfo": self.config["client_info"],
            },
        )
        require(result.get("protocolVersion") == protocol, "MCP protocol negotiation mismatch")
        self.protocol_version = protocol
        self.request("notifications/initialized", notification=True)
        return result

    def list_tools(self) -> list[dict[str, Any]]:
        tools = []
        cursor = None
        seen = set()
        while True:
            page = self.request("tools/list", {"cursor": cursor} if cursor else {})
            require(isinstance(page.get("tools"), list), "MCP tools/list returned no list")
            tools.extend(page["tools"])
            cursor = page.get("nextCursor")
            if not cursor:
                return tools
            require(cursor not in seen, "MCP repeated pagination cursor")
            seen.add(cursor)

    def call(self, name: str, arguments: dict[str, Any]) -> dict[str, Any]:
        return self.request("tools/call", {"name": name, "arguments": arguments})

    def close(self) -> None:
        if not self.session_id:
            return
        request = urllib.request.Request(
            self.endpoint,
            headers={"Mcp-Session-Id": self.session_id, "MCP-Protocol-Version": self.protocol_version or self.config["protocol_version"]},
            method="DELETE",
        )
        try:
            self.opener.open(request, timeout=self.timeout).close()
        except Exception:
            pass


class ModelClient:
    def __init__(self, config: dict[str, Any], api_key: str, run_dir: Path, timeout: float) -> None:
        self.config = config
        self.api_key = api_key
        self.run_dir = run_dir
        self.timeout = timeout
        self.calls = 0
        self.usage: list[dict[str, Any]] = []

    def complete(
        self,
        role: str,
        messages: list[dict[str, Any]],
        max_tokens: int,
        tools: list[dict[str, Any]] | None = None,
        response_format: dict[str, Any] | None = None,
        request_options: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        require(self.calls < self.config["max_calls"], "Model-call budget exhausted")
        model = self.config["roles"][role]
        self.calls += 1
        payload: dict[str, Any] = {
            "model": model,
            "messages": messages,
            "temperature": self.config["temperature"],
            "max_completion_tokens": max_tokens,
        }
        if tools:
            payload.update({
                "tools": tools,
                "tool_choice": self.config["tool_choice"],
                "parallel_tool_calls": self.config["parallel_tool_calls"],
            })
        if response_format:
            payload["response_format"] = response_format
        if request_options:
            require(not ({"model", "messages", "tools", "max_completion_tokens"} & request_options.keys()), "Reserved model request option overridden")
            payload.update(request_options)
        allowed = self.config["validated_allowlist"]
        print("Resolved models before request:", canonical(self.config["roles"]), flush=True)
        require(bool(self.config["roles"]) and all(v in allowed for v in self.config["roles"].values()), "Unauthorized model role")
        for variable in self.config["guard_environment_variables"]:
            require(os.environ.get(variable, model) == model, f"{variable} differs from authorized model")
        require(payload["model"] in allowed, "Unauthorized request model")
        require(self.config["endpoint"] == "https://openrouter.ai/api/v1/chat/completions", "Unauthorized model endpoint")
        write_json(self.run_dir / "model-requests" / f"call-{self.calls:02d}-{role}.json", payload)
        request = urllib.request.Request(
            self.config["endpoint"],
            data=canonical(payload).encode(),
            headers={
                "Authorization": f"Bearer {self.api_key}",
                "Content-Type": "application/json",
                **self.config.get("headers", {}),
            },
            method="POST",
        )
        # A 429/5xx from the provider is a transport condition, not a model decision: retry the same
        # call (same call number, same payload) a few times before failing the case.
        retry_delays = self.config.get("transient_retry_delays", [3, 8, 20])
        for retry, delay in enumerate([0, *retry_delays]):
            if delay:
                print(f"Model HTTP transient error; retry {retry}/{len(retry_delays)} after {delay}s", flush=True)
                time.sleep(delay)
            try:
                with urllib.request.build_opener(NoRedirect()).open(request, timeout=self.timeout) as response:
                    body = response.read(self.config["max_response_bytes"] + 1)
                    require(len(body) <= self.config["max_response_bytes"], "Model response budget exceeded")
                break
            except urllib.error.HTTPError as exc:
                detail = exc.read(4096).decode(errors='replace')
                if exc.code in (429, 502, 503, 504) and retry < len(retry_delays):
                    continue
                raise HarnessError(f"Model HTTP {exc.code}: {detail}") from exc
            except urllib.error.URLError as exc:
                raise HarnessError(f"Model connection failed: {exc.reason}") from exc
        value = json.loads(body.decode())
        write_json(self.run_dir / "model-responses" / f"call-{self.calls:02d}-{role}.json", value)
        self.usage.append(value.get("usage", {}) if isinstance(value, dict) else {})
        return response_message(value, model)


class Harness:
    def __init__(
        self,
        config_path: Path,
        case_path: Path | None,
        output_dir: Path | None,
        timeout_override: float | None,
        policy_overrides: dict[str, Path] | None = None,
    ) -> None:
        self.config_path = config_path.resolve()
        self.base = self.config_path.parent
        self.config = load_json(self.config_path)
        policy_files = self.config.pop("policy_files", {})
        require(isinstance(policy_files, dict), "policy_files must be an object")
        # A model profile swaps whole policy files (models, phases) for another authorized model;
        # it never edits a policy in place and never reaches prompts, hooks, schema or knowledge.
        for section, path in (policy_overrides or {}).items():
            require(section in policy_files, f"Policy override for unknown section: {section}")
            override = Path(path).resolve()
            require(override.is_relative_to(self.base) and override.is_file(), f"Policy override outside harness: {section}")
            policy_files[section] = str(override.relative_to(self.base))
        for section, relative_path in policy_files.items():
            require(section not in self.config, f"Duplicate inline and external policy section: {section}")
            require(isinstance(relative_path, str), f"Policy path for {section} must be a string")
            self.config[section] = load_json((self.base / relative_path).resolve())

        self.project_root = (self.base / self.config["project_root"]).resolve()
        root = self.project_root
        def reference_boundary(event: str, args: tuple) -> None:
            if event == "open" and args and isinstance(args[0], (str, bytes, os.PathLike)):
                path = Path(os.fsdecode(args[0])).resolve()
                if path.is_relative_to(root.parent) and not path.is_relative_to(root):
                    raise HarnessError("Reference isolation: sibling project artifacts forbidden")
                if path.is_relative_to(root / "evaluation"):
                    raise HarnessError("Evaluation files forbidden in runtime")
        sys.addaudithook(reference_boundary)
        selected_case = case_path.resolve() if case_path else self.resolve(self.config["default_case"])
        self.case_metadata = load_json(selected_case)
        self.case_base = selected_case.parent
        inputs = self.case_metadata.get("inputs")
        require(isinstance(inputs, dict), "Case inputs must be an object")
        self.config["inputs"] = inputs
        evidence_contract = self.case_metadata.get("evidence_contract")
        require(isinstance(evidence_contract, str), "Case evidence_contract must be a string")
        self.evidence_contract_path = (self.case_base / evidence_contract).resolve()

        stamp = datetime.now(timezone.utc).strftime(self.config["run"]["timestamp_format"])
        run_root = self.resolve(self.config["run"]["root"])
        self.run_dir = output_dir.resolve() if output_dir else run_root / stamp
        self.run_dir.mkdir(parents=True, exist_ok=False)
        self.timeout_override = timeout_override
        self.phase = "initialization"
        self.question_path = (self.case_base / self.config["inputs"]["question"]).resolve()
        self.manifest_path = (self.case_base / self.config["inputs"]["manifest"]).resolve()
        self.question = self.question_path.read_text(encoding="utf-8")
        self.manifest = load_json(self.manifest_path)
        self.state: dict[str, Any] = {}
        self.events: list[dict[str, Any]] = []
        self.rejections = 0
        self.transcript: list[dict[str, Any]] = []
        self.hooks = self.load_hooks()
        mcp_config = dict(self.config["mcp"])
        mcp_config["endpoint"] = self.config["mcp"]["endpoint"]
        self.mcp = MCPClient(
            mcp_config,
            timeout_override if timeout_override is not None else mcp_config["timeout_seconds"],
        )
        self.tool_schemas: dict[str, dict[str, Any]] = {}
        self.model: ModelClient | None = None
        self.compiled_contract: dict[str, Any] = {}
        # Every tool is served by exactly one source. The SQL source is the original client; a
        # document source (run.py --documents mcp) is added by enable_documents and reached
        # through call_tool, so hooks and the loop never pick a client themselves.
        self.sources: dict[str, MCPClient] = {"sql": self.mcp}
        self.tool_sources: dict[str, str] = {}
        self.documents: list[Any] = []
        self.document_context: list[dict[str, Any]] = []

    def enable_documents(self, as_of: str) -> None:
        """Turn the `documents` policy into live sources. Off by default: without this call the
        run has one source, the original tool set and byte-identical prompts."""
        from dfai_harness.documents import load_sources
        require("documents" in self.config, "No documents policy section in the harness")
        require(bool(re.fullmatch(r"\d{4}-\d{2}-\d{2}", as_of)), "as_of must be an ISO date")
        self.documents = load_sources(self.config["documents"])
        self.config["documents_mode"] = "mcp"
        self.config["documents_as_of"] = as_of
        # The external verifier runs as a separate process from the harness JSON alone; it must
        # replay against the same document sources this run used (a per-run policy swap included),
        # so the resolved policy is written beside the evidence (job 039: the verifier reloaded the
        # default file and silently skipped every rule from the swapped source).
        write_json(self.run_dir / "documents-policy.json", self.config["documents"])

    def call_tool(self, name: str, arguments: dict[str, Any]) -> dict[str, Any]:
        source = self.tool_sources.get(name, "sql")
        return self.sources[source].call(name, arguments)

    def resolve(self, path: str) -> Path:
        return (self.base / path).resolve()

    def read_asset(self, key: str) -> str:
        text = self.resolve(self.config["assets"][key]).read_text(encoding="utf-8")
        if key in {'skill', 'synthesizer_prompt'}:
            from dfai_harness.knowledge import load_knowledge
            context, receipt = load_knowledge(self.project_root, self.config.get('knowledge_mode', 'off'))
            write_json(self.run_dir / 'knowledge-context.json', receipt)
            if context:
                text += '\n\nSource-verified knowledge (not benchmark answers; observations are not organization-approved policy):\n' + context
        if self.config.get('semantic_mode','off') == 'catalog' and key in {'skill','synthesizer_prompt'}:
            from dfai_harness.semantic import load_catalog
            context, receipt = load_catalog(self.project_root)
            write_json(self.run_dir / 'semantic-context.json', receipt)
            text += '\n\nSource-backed semantic catalog; unknown business meaning stays unknown:\n' + context
        if self.config.get('documents_mode', 'off') == 'mcp' and key in {'contract_compiler_prompt', 'investigator_prompt', 'synthesizer_prompt'}:
            text += '\n\n' + self.resolve(self.config['assets']['document_rules_prompt']).read_text(encoding='utf-8')
        if self.config.get('finalization_mode','legacy') == 'bound-report' and key == 'investigator_prompt':
            text = text.replace('When done, output ONLY a JSON object with exactly:', 'When done, call FinalizeReport with these arguments:').replace('Do not wrap the JSON in Markdown fences.', 'Do not send free-text JSON instead of the tool call.')
            text += '\nFinalization override: call FinalizeReport instead of sending a free-text JSON draft. Supply a concise Thai answer and exact bindings. The runtime inserts bound MCP result tables verbatim and performs real replay before publishing; there is no second model writer. Do not recopy all table rows into the narrative. Explain requested comparisons, units and unknowns. Query all requested values with readable aliases. If numeric text is rounded scientific notation, query the original database again with an explicit text projection preserving source precision; do not reconstruct missing digits.'
        return text

    def load_hooks(self) -> ModuleType:
        path = self.resolve(self.config["hooks"]["module"])
        spec = importlib.util.spec_from_file_location(self.config["hooks"]["module_name"], path)
        require(spec is not None and spec.loader is not None, f"Cannot load hook module {path}")
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        return module

    def preflight_models(self) -> str:
        allowlist = load_json(self.resolve(self.config["models"]["allowlist_file"]))["allowed"]
        roles = self.config["models"]["roles"]
        self.config["models"]["validated_allowlist"] = allowlist
        require(len(allowlist) == 1 and allowlist[0] in AUTHORIZED_MODELS, "Only a user-authorized model profile is permitted: " + ", ".join(AUTHORIZED_MODELS))
        require(set(roles) == {"contract_compiler", "agent", "synthesizer"}, "Missing or unexpected model role")
        require(all(model in allowlist for model in roles.values()), "A resolved model is outside allowlist policy")
        for variable in self.config["models"]["guard_environment_variables"]:
            value = os.environ.get(variable)
            require(value is None or value in allowlist, f"{variable} is outside model allowlist")
        key = os.environ.get(self.config["models"]["api_key_environment_variable"], "")
        require(bool(key), "Configured model API key environment variable is not set")
        print("Resolved models:", flush=True)
        for role, model in roles.items():
            print(f"  {role}: {model}", flush=True)
        print("Model preflight: PASS", flush=True)
        return key

    def initialize_mcp(self) -> list[dict[str, Any]]:
        initialized = self.mcp.initialize()
        expected = self.config["mcp"]
        require(initialized.get("protocolVersion") == expected["protocol_version"], "MCP protocol changed")
        server = initialized.get("serverInfo", {})
        require(server.get("name") == expected["server_name"], "MCP server name changed")
        require(server.get("version") == expected["server_version"], "MCP server version changed")
        allowed = set(expected["allowed_tools"])
        selected = [tool for tool in self.mcp.list_tools() if tool.get("name") in allowed]
        require({tool["name"] for tool in selected} == allowed, "Required MCP tool set is unavailable")
        self.tool_schemas = {
            tool["name"]: tool.get("inputSchema") or {"type": "object", "properties": {}}
            for tool in selected
        }
        self.tool_sources = {tool["name"]: "sql" for tool in selected}
        for source in self.documents:
            client = MCPClient(source.mcp_config, self.timeout_override if self.timeout_override is not None else source.mcp_config["timeout_seconds"])
            info = client.initialize()
            require(info.get("protocolVersion") == source.mcp_config["protocol_version"], f"{source.name}: MCP protocol changed")
            server = info.get("serverInfo", {})
            for key in ("name", "version"):
                pinned = source.mcp_config.get(f"server_{key}")
                require(pinned is None or server.get(key) == pinned, f"{source.name}: MCP server {key} changed")
            source.live_server = {"name": server.get("name"), "version": server.get("version")}
            allowed = set(source.allowed_tools)
            found = [tool for tool in client.list_tools() if tool.get("name") in allowed]
            require({tool["name"] for tool in found} == allowed, f"{source.name}: required document tool set is unavailable")
            for tool in found:
                require(tool["name"] not in self.tool_schemas, f"Tool name {tool['name']} is served by two sources")
                self.tool_schemas[tool["name"]] = tool.get("inputSchema") or {"type": "object", "properties": {}}
                self.tool_sources[tool["name"]] = source.name
            self.sources[source.name] = client
            selected = [*selected, *found]
        return selected

    def lookup_documents(self) -> list[dict[str, Any]]:
        """Pre-compile document lookup through the hook-tool path: every call is schema-checked,
        admitted by the source's integrity rules and recorded as evidence. No model call."""
        contexts = []
        for source in self.documents:
            def call(tool: str, arguments: dict[str, Any]) -> tuple[dict[str, Any], str]:
                result = self.invoke_hook_tool(tool, arguments)
                return result, self.events[-1]["evidence_id"]
            context = source.lookup(call, self.question, self.config["documents_as_of"])
            context["server"] = getattr(source, "live_server", None)
            budget = source.policy["budgets"].get("max_context_bytes")
            size = len(canonical(context).encode())
            require(budget is None or size <= budget, f"{source.name}: document context {size} bytes exceeds budget {budget}")
            contexts.append(context)
        self.document_context = contexts
        write_json(self.run_dir / "document-lookup.json", [
            {**context, "records": [source.metadata_only(r) for r in context["records"]]}
            for source, context in zip(self.documents, contexts)
        ])
        return contexts

    def record_tool(
        self,
        origin: str,
        name: str,
        arguments: dict[str, Any],
        result: dict[str, Any],
        call_id: str,
        admitted: bool,
    ) -> str:
        evidence_id = f"E{len(self.events) + 1:04d}"
        event = {
            "evidence_id": evidence_id,
            "origin": origin,
            "source": self.tool_sources.get(name, "sql"),
            "tool_call_id": call_id,
            "tool": name,
            "arguments": arguments,
            "result": result,
            "admitted": admitted,
            "result_sha256": digest(canonical(result).encode()),
        }
        self.events.append(event)
        write_json(self.run_dir / "evidence" / f"{evidence_id}-{name}.json", event)
        return evidence_id

    def invoke_hook_tool(self, name: str, arguments: dict[str, Any]) -> dict[str, Any]:
        require(len(self.events) < self.config["run"]["max_tool_calls"], "Tool-call budget exhausted")
        require(name in self.tool_schemas, f"Hook requested unavailable tool {name}")
        errors = schema_errors(arguments, self.tool_schemas[name])
        errors.extend(self.hooks.pre_tool_use(self, name, arguments))
        require(not errors, "Hook tool schema violation: " + "; ".join(errors))
        result = self.call_tool(name, arguments)
        admitted, post_errors = self.hooks.post_tool_use(self, name, arguments, result)
        self.record_tool("hook", name, arguments, result, "hook", admitted)
        require(admitted and not post_errors, "Hook tool result rejected: " + "; ".join(post_errors))
        return result

    def model_tools(self, tools: list[dict[str, Any]]) -> list[dict[str, Any]]:
        return [
            {
                "type": "function",
                "function": {
                    "name": tool["name"],
                    "description": tool.get("description", ""),
                    "parameters": tool.get("inputSchema") or {"type": "object", "properties": {}},
                    **self.config["models"].get("tool_function_options", {}),
                },
            }
            for tool in tools
        ]

    def compile_contract(self, tools: list[dict[str, Any]]) -> None:
        context = self.hooks.prepare_contract_context(self)
        phase = self.config["phases"]["contract_compiler"]
        structured = phase["structured_output"]
        contract_schema = load_json(self.resolve(self.config["assets"][structured["schema_asset"]]))
        if hasattr(self.hooks, "prepare_contract_schema"):
            contract_schema = self.hooks.prepare_contract_schema(self, contract_schema)
        document_records: list[dict[str, Any]] = []
        if self.documents:
            # Document lookup is harness input like the schema: it runs before the model, and
            # the rule enums below are drawn from what it admitted, so no section can be cited
            # that was not read with its checksum verified.
            contexts = self.lookup_documents()
            document_records = [record for context in contexts for record in context["records"]]
            context["document_evidence"] = [
                {**{k: v for k, v in c.items() if k not in {"records", "catalogue"}},
                 "catalogue": source.catalogue_documents(c["catalogue"]),
                 "records": c["records"]}
                for source, c in zip(self.documents, contexts)
            ]
            max_rules = self.config["documents"].get("max_rules", 24)
            for source in self.documents:
                contract_schema = source.extend_contract_schema(contract_schema, document_records, max_rules)
        write_json(self.run_dir / "task-contract-schema.json", contract_schema)
        response_format = {
            "type": "json_schema",
            "json_schema": {"name": structured["name"], "strict": structured["strict"], "schema": contract_schema},
        }
        messages = [
            {"role": "system", "content": self.read_asset("skill") + "\n\n" + self.read_asset("contract_compiler_prompt")},
            {"role": "user", "content": canonical({
                "case_id": self.case_metadata["case_id"], "question": self.question,
                "manifest": self.manifest, "mcp_tools": tools, "hook_context": context,
                "task_contract_schema": contract_schema,
            })},
        ]
        attempts = phase.get("max_attempts", 1)
        require(isinstance(attempts, int) and 1 <= attempts <= 2, "Compiler attempts outside limit")
        for attempt in range(attempts):
            content = ''
            try:
                message = self.model.complete(
                    phase["role"], messages, phase["max_tokens"], response_format=response_format,
                    request_options=phase.get("request_options"),
                )
            except IncompleteGeneration as exc:
                content = exc.content
                errors = [str(exc)]
            else:
                content = str(message.get("content") or "")
                try:
                    contract = json_from_text(content)
                    if isinstance(contract, dict) and contract.get("question") != self.question:
                        # The question is harness input, not model output: a paraphrase here is not a contract defect.
                        contract["question"] = self.question
                    if hasattr(self.hooks, "normalise_compiled_contract") and isinstance(contract, dict):
                        contract, dropped = self.hooks.normalise_compiled_contract(self, contract)
                        if dropped:
                            write_json(self.run_dir / "compiler-normalisations" / f"attempt-{attempt+1}.json", {"dropped": dropped})
                    span_enum = set(contract_schema.get("properties", {}).get("requirements", {}).get("items", {}).get("properties", {}).get("question_span_id", {}).get("enum", []))
                    for requirement in (contract.get("requirements") or []) if isinstance(contract, dict) else []:
                        span_id = requirement.get("question_span_id") if isinstance(requirement, dict) else None
                        match = re.fullmatch(r"S(\d+)", str(span_id or ""))
                        padded = f"S{int(match.group(1)):03d}" if match else None
                        if span_id not in span_enum and padded in span_enum:
                            # Same span, unpadded id (S24 for S024): a formatting slip, not a different source span.
                            requirement["question_span_id"] = padded
                    errors = schema_errors(contract, contract_schema)
                    if not errors:
                        errors.extend(self.hooks.validate_compiled_contract(self, contract))
                    for source in self.documents if not errors else []:
                        errors.extend(source.contract_errors(contract, document_records))
                except HarnessError as exc:
                    errors = [str(exc)]
            if not errors:
                break
            write_json(self.run_dir / "compiler-rejections" / f"attempt-{attempt+1}.json", {"errors": errors, "output": content})
            require(attempt + 1 < attempts, "Compiled contract rejected: " + "; ".join(errors))
            messages.append({"role": "assistant", "content": content})
            messages.append({"role": "user", "content": canonical({"validation_errors": errors, "instruction": "Correct only the rejected contract. Copy the exact question, select question_span_id from the provided source map, and select table names from schema enum. Do not change the user's task."})})
        for source in self.documents:
            contract = source.bind_rules(contract, document_records)
        self.compiled_contract = contract
        write_json(self.run_dir / "compiled-task-contract.json", contract)
        (self.run_dir / "compiled-task-contract.sha256").write_text(
            digest(canonical(contract).encode()) + "\n",
            encoding="ascii",
        )

    def reject_tool_call(self, call: dict[str, Any], name: str, arguments: dict[str, Any], errors: list[str]) -> None:
        self.rejections += 1
        require(self.rejections <= self.config["run"]["max_rejected_tool_calls"], "Tool rejection budget exhausted")
        payload = {
            "error": "pre_tool_use_rejected",
            "details": errors,
            "repair_instruction": self.config["hooks"]["repair_instruction"],
        }
        write_json(
            self.run_dir / "hook-rejections" / f"rejection-{self.rejections:02d}.json",
            {"tool": name, "arguments": arguments, **payload},
        )
        self.transcript.append({
            "role": "tool",
            "tool_call_id": call.get("id"),
            "name": name,
            "content": canonical(payload),
        })

    def run_tool_loop(self, tools: list[dict[str, Any]]) -> str:
        phase = self.config["phases"]["investigator"]
        self.transcript = [
            {
                "role": "system",
                "content": self.read_asset("skill") + "\n\n" + self.read_asset("investigator_prompt"),
            },
            {
                "role": "user",
                "content": canonical({
                    "question": self.question,
                    "compiled_task_contract": self.compiled_contract,
                    "discovery_evidence": [event for event in self.events if event["admitted"]],
                }),
            },
        ]
        draft = ""
        force_compose = False
        # A rejection on the last budgeted call used to end the case with no answer, although the
        # hook had just said exactly what to correct. One repair call is held back for that case
        # and released only after a rejected draft, so a clean run keeps the same budget as before.
        repair_calls = self.config['run'].get('repair_calls', 0)
        require(isinstance(repair_calls, int) and 0 <= repair_calls <= 2, 'Invalid repair budget')
        repair_released = 0
        # A rejection can also say that no admitted evidence returns a required alias. Then the only
        # repair is a query, but the compose window has already closed the tools, and the model's
        # attempt to follow the hook ends the case (HQ-05 x3 and HQ-02, 2026-09-28). For that case
        # the hook names the tools the repair needs; they are opened for exactly one call, with a
        # second held-back call released for the redraft, and no router call is spent on a choice
        # the hook has already made.
        repair_tools: list[str] = []
        repair_instruction = ''
        # The call after an opened repair call must be the draft whatever the counter says: opened
        # at call 13, before the window, the model queried again at 14 (HQ-02 #2 on d9a24e5).
        force_redraft = False
        base_limit = self.config['models']['max_calls'] - self.config['run']['reserved_model_calls'] - repair_calls

        def open_repair(errors: list[str]) -> None:
            nonlocal repair_released, repair_tools, repair_instruction
            needs = getattr(self.hooks, 'repair_needs_tools', None)
            wanted = list(needs(self, errors) or []) if needs is not None else []
            repair_released, repair_tools = repair_release(self.model.calls, base_limit, repair_released, repair_calls, wanted)
            describe = getattr(self.hooks, 'repair_tool_instruction', None)
            repair_instruction = str(describe(self, errors) or '') if repair_tools and describe is not None else ''

        while self.model.calls < base_limit + repair_released:
            limit = base_limit + repair_released
            compose_calls = self.config['run'].get('compose_calls', 0)
            require(isinstance(compose_calls, int) and 0 <= compose_calls <= 2, 'Invalid compose budget')
            must_compose = (self.model.calls >= limit - compose_calls or force_redraft) and not self.hooks.evidence_errors(self) and not repair_tools
            if repair_tools:
                self.transcript.append({'role': 'user', 'content': 'Tools are open for this one call only, to obtain the evidence the rejection named, with the exact required_outputs aliases as returned column names. The call after it must return the complete draft; do not run any other query. ' + repair_instruction})
            elif must_compose:
                self.transcript.append({'role': 'user', 'content': ('Call FinalizeReport. ' if self.config.get('finalization_mode','legacy') == 'bound-report' else '') + 'The remaining investigator calls are for composition/repair. Use only admitted evidence already obtained. Return the complete required draft JSON and bindings now. Do not invent missing results; unsupported requirements must remain a reported failure.'})
            available_tools = None if must_compose or (force_compose and self.config["hooks"]["disable_tools_after_evidence_complete"]) else self.model_tools(tools)
            if repair_tools:
                available_tools = [t for t in self.model_tools(tools) if t['function']['name'] in repair_tools] or None
            bound_report = self.config.get('finalization_mode','legacy') == 'bound-report'
            options = dict(phase.get('request_options') or {})
            if bound_report and not self.hooks.evidence_errors(self) and not repair_tools:
                final_tool = self.hooks.finalization_tool(self)
                available_tools = [*(available_tools or []), final_tool]
                if must_compose or force_compose:
                    available_tools = [final_tool]
                    options['tool_choice'] = 'auto'  # Qwen thinking supports auto/none only; local gates still require FinalizeReport
            selection = None
            model_messages = self.transcript
            if self.config.get('tool_routing', 'native') in ('direct-score', 'jev'):
                from .tool_router import select_tool
                selection = select_tool(self, available_tools,
                                        allow_compose=not bound_report and not repair_tools and (not available_tools or not self.hooks.evidence_errors(self)),
                                        limit=limit)
                if selection is not None:
                    available_tools = [t for t in (available_tools or [])
                                       if t['function']['name'] == selection] or None
                    options['parallel_tool_calls'] = False
                    options['tool_choice'] = 'none' if selection == 'compose' else 'auto'
                    model_messages = [*self.transcript, {'role': 'user', 'content':
                        ('Compose the complete required draft now without calling tools.' if selection == 'compose'
                         else f'The tool router selected {selection}. Generate exactly one call to that tool with valid arguments.')}]
            try:
                message = self.model.complete(
                    phase["role"], model_messages, phase["max_tokens"], available_tools,
                    request_options=options,
                )
            except IncompleteGeneration as exc:
                write_json(self.run_dir / 'agent-rejections' / f'call-{self.model.calls:02d}.json', {'error': str(exc), 'partial_content': exc.content})
                self.transcript.append({'role': 'user', 'content': 'The last generation was incomplete. Produce a concise complete response; partial output was not accepted.'})
                continue
            calls = message.get("tool_calls") or []
            assistant = {"role": "assistant", "content": message.get("content") or ""}
            for field in self.config["models"].get("preserve_message_fields", []):
                if message.get(field) is not None:
                    assistant[field] = message[field]
            if calls:
                assistant["tool_calls"] = calls
            self.transcript.append(assistant)
            if repair_tools:  # the one open call has been spent, whatever the model did with it
                repair_tools, force_redraft = [], True
            if selection is not None:
                from .tool_router import enforce_selection
                routing_errors = enforce_selection(message, selection)
                if routing_errors:
                    write_json(self.run_dir / 'tool-routing' / f'rejected-call-{self.model.calls:02d}.json',
                               {'selection': selection, 'errors': routing_errors, 'message': message})
                    for call in calls:
                        self.transcript.append({'role': 'tool', 'tool_call_id': call.get('id'),
                                                'name': (call.get('function') or {}).get('name'),
                                                'content': canonical({'errors': routing_errors})})
                    if not calls:
                        self.transcript.append({'role': 'user', 'content': '; '.join(routing_errors)})
                    continue
            if must_compose and calls and not bound_report:
                for call in calls:
                    self.transcript.append({
                        'role': 'tool',
                        'tool_call_id': call.get('id'),
                        'name': (call.get('function') or {}).get('name'),
                        'content': canonical({
                            'error': 'no tools are available now',
                            'instruction': 'Return the complete required draft JSON directly as your message content now. Do not call any tool.',
                        }),
                    })
                continue
            final_calls = [c for c in calls if (c.get('function') or {}).get('name') == 'FinalizeReport'] if bound_report else []
            if final_calls:
                force_redraft = False
                errors = ['FinalizeReport must be the only tool call in its turn'] if len(calls) != 1 else []
                candidate = ''
                if not errors:
                    try:
                        arguments = json.loads(final_calls[0]['function'].get('arguments') or '{}')
                        candidate = self.hooks.finalization_draft(self, arguments)
                        errors = self.hooks.completion_errors(self, candidate)
                    except (ValueError, TypeError, KeyError) as exc:
                        # A hook may raise the item list itself so the model sees one entry per error.
                        errors = [str(e) for e in exc.args[0]] if exc.args and isinstance(exc.args[0], list) else [str(exc)]
                instruction = ('Correct the stated error using admitted evidence; no result was published yet.' if len(errors) <= 1 else
                               f'{len(errors)} errors are listed; the next FinalizeReport call must correct all of them at once, '
                               'using admitted evidence. No result was published yet.')
                for call in calls:
                    self.transcript.append({'role':'tool','tool_call_id':call.get('id'),'name':(call.get('function') or {}).get('name'), 'content':canonical({'accepted':not errors,'errors':errors,'instruction':instruction})})
                write_json(self.run_dir/'finalization-events'/f'call-{self.model.calls:02d}.json',{'accepted':not errors,'errors':errors,'draft':candidate})
                if not errors:
                    draft = candidate
                    break
                open_repair(errors)
                continue
            if must_compose and bound_report and calls:
                for call in calls:
                    self.transcript.append({
                        'role': 'tool',
                        'tool_call_id': call.get('id'),
                        'name': (call.get('function') or {}).get('name'),
                        'content': canonical({
                            'error': 'only FinalizeReport is allowed now',
                            'instruction': 'Call FinalizeReport with the complete draft and bindings using only evidence already obtained. Do not request additional queries.',
                        }),
                    })
                continue
            if calls:
                for call in calls:
                    require(len(self.events) < self.config["run"]["max_tool_calls"], "Tool-call budget exhausted")
                    function = call.get("function") or {}
                    name = str(function.get("name", ""))
                    try:
                        arguments = json.loads(function.get("arguments") or "{}")
                    except json.JSONDecodeError:
                        arguments = {}
                        self.reject_tool_call(call, name, arguments, ["tool arguments are not valid JSON"])
                        continue
                    errors = []
                    if name not in self.tool_schemas:
                        errors.append("tool is not in the live allowed schema set")
                    elif isinstance(arguments, dict):
                        errors.extend(schema_errors(arguments, self.tool_schemas[name]))
                        errors.extend(self.hooks.pre_tool_use(self, name, arguments))
                    else:
                        errors.append("tool arguments must be an object")
                    if errors:
                        self.reject_tool_call(call, name, arguments if isinstance(arguments, dict) else {}, errors)
                        finalize = getattr(self.hooks, 'finalize_after_rejection', None)
                        if finalize is not None and finalize(self, name, arguments, errors):
                            force_redraft = True
                        continue
                    result = self.call_tool(name, arguments)
                    admitted, post_errors = self.hooks.post_tool_use(self, name, arguments, result)
                    evidence_id = self.record_tool("agent", name, arguments, result, str(call.get("id", "")), admitted)
                    self.transcript.append({
                        "role": "tool",
                        "tool_call_id": call.get("id"),
                        "name": name,
                        "content": canonical({
                            "evidence_id": evidence_id,
                            "admitted": admitted,
                            "post_tool_errors": post_errors,
                            "mcp_result": result,
                        }),
                    })
                if self.config["hooks"]["force_compose_when_evidence_complete"]:
                    evidence_errors = self.hooks.evidence_errors(self)
                    if not evidence_errors:
                        force_compose = True
                        self.transcript.append({
                            "role": "user",
                            "content": self.config["hooks"]["evidence_complete_instruction"],
                        })
                continue
            if bound_report:
                self.transcript.append({'role':'user','content':'Finish through FinalizeReport with exact requirement bindings, not free-text JSON. Obtain missing evidence before finalizing.'})
                continue
            draft = str(message.get("content") or "").strip()
            force_redraft = False
            missing = self.hooks.completion_errors(self, draft)
            if draft and not missing:
                break
            if draft:
                open_repair(missing)
            # Numbered, with the count up front: given "A; B" the model has fixed A and resubmitted
            # with B untouched, spending the one repair call on a rejection it had already been told about.
            items = missing if len(missing) == 1 else [f"{len(missing)} items, all of which the next draft must fix together:",
                                                         *(f"{i}. {m}" for i, m in enumerate(missing, 1))]
            self.transcript.append({
                "role": "user",
                "content": self.config["hooks"]["completion_repair_prefix"] + "\n".join(items),
            })
        require(bool(draft), "Agent produced no draft")
        missing = self.hooks.completion_errors(self, draft)
        require(not missing, "Completion hook rejected stop: " + "; ".join(missing))
        write_json(self.run_dir / "agent-transcript.json", self.transcript)
        return draft

    def run_external_hook(self, hook: dict[str, Any]) -> dict[str, Path]:
        values = {
            "python": sys.executable,
            "endpoint": self.mcp.endpoint,
            "project_root": str(self.project_root),
            "config_root": str(self.base),
            "evidence_contract": str(self.evidence_contract_path),
            "question": str(self.question_path),
            "manifest": str(self.manifest_path),
            "run_dir": str(self.run_dir),
        }
        command = [part.format(**values) for part in hook["command"]]
        env = os.environ.copy()
        for variable in hook.get("strip_environment", []):
            env.pop(variable, None)
        completed = subprocess.run(
            command,
            cwd=self.project_root,
            env=env,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            timeout=hook["timeout_seconds"],
            check=False,
        )
        output_path = self.run_dir / hook["stdout_artifact"]
        output_path.write_text(completed.stdout, encoding="utf-8")
        require(completed.returncode in hook["success_exit_codes"], f"External hook failed: {completed.returncode}")
        artifacts: dict[str, Path] = {}
        for name, pattern in hook["artifact_patterns"].items():
            match = re.search(pattern, completed.stdout, re.MULTILINE)
            require(bool(match), f"External hook omitted artifact {name}")
            path = Path(match.group(1).strip()).resolve()
            require(path.is_file(), f"External hook artifact is missing: {path}")
            artifacts[name] = path
        return artifacts

    def synthesize(self, draft: str, verified_report: str) -> str:
        if self.config.get('finalization_mode','legacy') == 'bound-report':
            value = self.hooks.parse_draft(draft)
            errors = self.hooks.completion_errors(self, draft)
            require(not errors, 'Bound report failed validation: ' + '; '.join(errors))
            write_json(self.run_dir/'render-receipt.json',{'source':'validated FinalizeReport plus bound original MCP tables; replay already passed','model_writer_calls':0,'semantic_assessment':'not_assessed'})
            return value['answer']
        phase = self.config["phases"]["synthesizer"]
        payload: dict[str, Any] = {
            "compiled_task_contract": self.compiled_contract,
            "agent_draft": draft,
            "verified_report": verified_report,
        }
        if self.documents:
            # What the document gate will check, stated as data rather than left to the prompt
            # (job 041: answers dropped a section id or a status word on rewrite and were refused).
            payload["required_document_citations"] = [
                item for source in self.documents
                for item in source.citation_requirements(self.compiled_contract, self.config.get("documents_as_of"))
            ]
            # Admission is independent of compiled rules: an investigator can read policy
            # after compilation. Forward that text with its original provenance, not the draft.
            payload["admitted_documents"] = []
            for source in self.documents:
                records = []
                for event in self.events:
                    if (not event.get("admitted") or event.get("source") != source.name
                            or event.get("tool") not in source.layouts):
                        continue
                    for record in source.normalise(event["tool"], event["result"]):
                        if not any(isinstance(record.get(k), str) for k in ("content", "excerpt")):
                            continue
                        records.append({**record, "evidence_id": event["evidence_id"]})
                budget = source.policy["budgets"].get("max_context_bytes")
                if budget is not None and len(canonical(records).encode()) > budget:
                    # Reserve all metadata first; shorten only text, at UTF-8 boundaries.
                    texts = [(record, key, record[key]) for record in records
                             for key in ("content", "excerpt") if isinstance(record.get(key), str)]
                    for record, key, text in texts:
                        record[key] = ""
                        record[key + "_truncated"] = bool(text)
                    for record, key, text in texts:
                        room = max(0, budget - len(canonical(records).encode()))
                        record[key] = text.encode()[:room].decode("utf-8", errors="ignore")
                        # JSON quoting can add bytes beyond the raw UTF-8 text size.
                        while record[key] and len(canonical(records).encode()) > budget:
                            excess = len(canonical(records).encode()) - budget
                            record[key] = record[key].encode()[:-excess].decode("utf-8", errors="ignore")
                        record[key + "_truncated"] = record[key] != text
                payload["admitted_documents"].extend(records)
        messages = [
                {"role": "system", "content": self.read_asset("synthesizer_prompt")},
                {"role": "user", "content": canonical(payload)},
            ]
        attempts = phase.get('max_attempts', 1)
        require(isinstance(attempts, int) and 1 <= attempts <= self.config['run']['reserved_model_calls'], 'Synthesis attempts exceed reserved calls')
        for attempt in range(attempts):
            text = ''
            try:
                message = self.model.complete(phase['role'], messages, phase['max_tokens'], request_options=phase.get('request_options'))
                text = str(message.get('content') or '').strip()
                errors = self.hooks.synthesis_errors(self, text, draft, verified_report)
            except IncompleteGeneration as exc:
                text = exc.content
                errors = [str(exc)]
            if not errors:
                return text
            write_json(self.run_dir / 'synthesis-rejections' / f'attempt-{attempt+1}.json', {'errors': errors, 'output': text})
            require(attempt + 1 < attempts, 'Synthesis rejected: ' + '; '.join(errors))
            messages.append({'role': 'user', 'content': canonical({'validation_errors': errors, 'instruction': 'Regenerate the entire answer concisely from the same evidence. Put all requested table rows first. Omit optional explanations. Never substitute, concatenate or present partial text as complete.'})})
        raise HarnessError('Synthesis produced no complete answer')

    def run(self) -> tuple[Path, Path]:
        if self.config.get('tool_routing') == 'direct-score':
            self.phase = 'score-preflight'
            from .tool_router import ScoreClient
            self.score_client = ScoreClient.from_environment()
            self.score_client.check_model()
        if self.config.get('tool_routing') in ('jev','jev-functions'):
            self.phase = 'jev-preflight'
            from .jev_router import JevClient
            self.jev_client = JevClient.from_environment()
        self.phase = "model-preflight"
        key = self.preflight_models()
        self.phase = "mcp-initialization"
        tools = self.initialize_mcp()
        model_config = dict(self.config["models"])
        model_config["max_calls"] = self.config["models"]["max_calls"]
        self.model = ModelClient(
            model_config,
            key,
            self.run_dir,
            self.timeout_override if self.timeout_override is not None else model_config["timeout_seconds"],
        )
        self.phase = "contract-compilation"
        if self.config.get('tool_routing') == 'jev-functions':
            self.phase = 'function-dispatch'
            from .function_dispatch import run_functions
            result = run_functions(self)
            if result is not None:
                return result
            self.phase = 'contract-compilation'
        self.compile_contract(tools)
        self.phase = "agent-tool-loop"
        draft = self.run_tool_loop(tools)
        draft_path = self.run_dir / self.config["run"]["draft_artifact"]
        draft_path.write_text(draft + "\n", encoding="utf-8")

        self.phase = "post-tool-verifier"
        external = self.run_external_hook(self.config["hooks"]["post_tool_verifier"])
        verified_report = external["answer"].read_text(encoding="utf-8")
        self.phase = "answer-synthesis"
        synthesis = self.synthesize(draft, verified_report)
        self.phase = "publication"
        template = self.read_asset("answer_template")
        answer = template.replace("{{SYNTHESIS}}", synthesis).replace("{{VERIFIED_REPORT}}", verified_report)
        answer_path = self.run_dir / self.config["run"]["answer_artifact"]
        answer_path.write_text(answer, encoding="utf-8")
        verifier_receipt = self.run_dir / self.config["run"]["verifier_receipt_artifact"]
        shutil.copyfile(external["receipt"], verifier_receipt)

        receipt = {
            "schema": self.config["run"]["receipt_schema"],
            "status": "satisfied",
            "finished_at": datetime.now(timezone.utc).isoformat(),
            "case_id": self.case_metadata.get("case_id"),
            "resolved_models": dict(self.config["models"]["roles"]),
            "tool_routing": self.config.get('tool_routing', 'native'),
            "model_profile": self.config.get('model_profile', 'qwen3.5'),
            "router_model": getattr(getattr(self, 'jev_client', None), 'model', None),
            "function_dispatch_fallback": self.state.get('function_dispatch_fallback', False),
            "model_calls": self.model.calls,
            "model_usage": self.model.usage,
            "compiled_contract_sha256": digest(canonical(self.compiled_contract).encode()),
            "mcp_endpoint": self.mcp.endpoint,
            "documents_mode": self.config.get("documents_mode", "off"),
            "documents_as_of": self.config.get("documents_as_of"),
            "documents_policy": self.config.get("documents_policy"),
            "document_sources": {source.name: {"endpoint": source.mcp_config["endpoint"], "server": getattr(source, "live_server", None)} for source in self.documents},
            "document_lookup_calls": sum(c.get("lookup_calls", 0) for c in self.document_context),
            "document_rules": len(self.compiled_contract.get("rules") or []),
            "tool_calls": len(self.events),
            "tool_counts": dict(sorted(Counter(event["tool"] for event in self.events).items())),
            "hook_rejections": self.rejections,
            "answer_sha256": digest(answer_path.read_bytes()),
            "verifier_receipt_sha256": digest(verifier_receipt.read_bytes()),
            "oracle_answer_used": False,
            "semantic_assessment": "not_assessed; runtime gates are structural only",
            "config_sha256": digest(canonical(self.config).encode()),
            "question_sha256": digest(self.question.encode()),
        }
        receipt_path = self.run_dir / self.config["run"]["receipt_artifact"]
        write_json(receipt_path, receipt)
        return answer_path, receipt_path

    def close(self) -> None:
        if getattr(self, 'jev_client', None) is not None:
            self.jev_client.close()
        for client in self.sources.values():
            client.close()


def parse_args() -> argparse.Namespace:
    script = Path(__file__).resolve()
    parser = argparse.ArgumentParser(description="Generic configurable LLM/MCP harness")
    parser.add_argument(
        "--harness",
        type=Path,
        default=script.parents[2] / "harnesses/bps39/harness.json",
    )
    parser.add_argument("--case", type=Path, help="Optional case file overriding the harness default_case")
    parser.add_argument("--output-dir", type=Path)
    parser.add_argument("--timeout", type=float, help="Optional override for model and MCP transport timeouts")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    harness: Harness | None = None
    try:
        harness = Harness(args.harness, args.case, args.output_dir, args.timeout)
        answer, receipt = harness.run()
        print(f"Answer: {answer}")
        print(f"Receipt: {receipt}")
        return 0
    except BaseException as exc:
        if harness is not None:
            write_json(
                harness.run_dir / harness.config["run"]["failure_artifact"],
                {
                    "status": "failed",
                    "error_type": type(exc).__name__,
                    "error": str(exc),
                    "phase": harness.phase,
                    "finished_at": datetime.now(timezone.utc).isoformat(),
                },
            )
            print(f"Failure: {harness.run_dir / harness.config['run']['failure_artifact']}", file=sys.stderr)
        print(f"ERROR: {type(exc).__name__}: {exc}", file=sys.stderr)
        return 2
    finally:
        if harness is not None:
            write_json(harness.run_dir / "agent-transcript.json", harness.transcript)
            if harness.model is not None:
                write_json(harness.run_dir / "usage.json", {"attempted_model_calls": harness.model.calls, "usage": harness.model.usage})
            harness.close()


if __name__ == "__main__":
    raise SystemExit(main())
