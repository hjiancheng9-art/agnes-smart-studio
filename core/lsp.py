"""LSP (Language Server Protocol) client.

Provides tools for code intelligence via LSP:
- Go-to-definition (jump to symbol definition)
- Hover (type info and documentation)
- Diagnostics (errors and warnings)
- Completion (autocomplete suggestions)
- Find references (all usages of a symbol)
- Rename (safe symbol renaming)

Supports Python, JavaScript, TypeScript, Go, and Rust.
Communicates with language servers over JSON-RPC 2.0 using stdio transport.
"""

import contextlib
import json
import os
import subprocess
import sys
import threading
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path

from core.config import OUTPUT_DIR

__all__ = [
    "LSPClient",
    "LSPServerConfig",
    "LSP_EXECUTOR_MAP",
    "LSP_TOOL_DEFS",
    "Language",
    "detect_language",
    "execute_lsp_diagnostics",
    "execute_lsp_find_references",
    "execute_lsp_goto_definition",
    "execute_lsp_hover",
    "get_lsp_client",
]

# ======================================================================
# Language enum
# ======================================================================


class Language(Enum):
    """Supported programming languages for LSP."""

    PYTHON = "python"
    JAVASCRIPT = "javascript"
    TYPESCRIPT = "typescript"
    GO = "go"
    RUST = "rust"


# ======================================================================
# Server configuration
# ======================================================================


@dataclass
class LSPServerConfig:
    """Configuration for a single LSP server process."""

    language: Language
    command: str
    args: list[str] = field(default_factory=list)
    enabled: bool = True


# Default server commands for each language.
# These must be installed separately; the client handles missing servers gracefully.
DEFAULT_SERVERS: dict[Language, dict] = {
    Language.PYTHON: {"command": "python", "args": ["-m", "pylsp"]},
    Language.JAVASCRIPT: {"command": "npx", "args": ["typescript-language-server", "--stdio"]},
    Language.TYPESCRIPT: {"command": "npx", "args": ["typescript-language-server", "--stdio"]},
    Language.GO: {"command": "gopls", "args": []},
    Language.RUST: {"command": "rust-analyzer", "args": []},
}

# Install hints shown when a server is not installed.
INSTALL_HINTS: dict[Language, str] = {
    Language.PYTHON: "pip install python-lsp-server",
    Language.JAVASCRIPT: "npm install -g typescript-language-server",
    Language.TYPESCRIPT: "npm install -g typescript-language-server",
    Language.GO: "go install golang.org/x/tools/gopls@latest",
    Language.RUST: "rustup component add rust-analyzer",
}

# File extension to Language mapping.
_EXTENSION_MAP: dict[str, Language] = {
    ".py": Language.PYTHON,
    ".js": Language.JAVASCRIPT,
    ".jsx": Language.JAVASCRIPT,
    ".mjs": Language.JAVASCRIPT,
    ".ts": Language.TYPESCRIPT,
    ".tsx": Language.TYPESCRIPT,
    ".go": Language.GO,
    ".rs": Language.RUST,
}


def detect_language(file_path: str) -> Language:
    """Detect the programming language from a file path extension.

    Returns the Language enum member, or raises ValueError for unknown extensions.
    """
    suffix = Path(file_path).suffix.lower()
    if suffix not in _EXTENSION_MAP:
        raise ValueError(
            f"Cannot detect language for extension '{suffix}'. Supported: {', '.join(sorted(_EXTENSION_MAP.keys()))}"
        )
    return _EXTENSION_MAP[suffix]


def _to_file_uri(file_path: str) -> str:
    """Convert an absolute filesystem path to a file:// URI."""
    abs_path = os.path.abspath(file_path)
    # Use pathlib to normalize separators, then build URI.
    # On Windows, Path.as_uri() produces file:///C:/...
    return Path(abs_path).as_uri()


# ======================================================================
# LSP Client
# ======================================================================


class LSPClient:
    """Lightweight LSP client managing one server process per language.

    Communication uses JSON-RPC 2.0 over stdio with Content-Length framing:
        Content-Length: N\r\n\r\n{json_payload}

    Each language gets its own server process, started lazily on first use
    and reused for subsequent requests. All process management is thread-safe.
    """

    def __init__(self) -> None:
        self._processes: dict[Language, subprocess.Popen] = {}
        self._lock = threading.Lock()
        self._request_id = 0
        self._configs: dict[Language, LSPServerConfig] = {}
        self._load_config()

    def _load_config(self):
        """Load server configuration from OUTPUT_DIR/lsp_servers.json.

        Falls back to DEFAULT_SERVERS if the config file is missing or
        cannot be parsed. User config overrides defaults per language.
        """
        config_path = OUTPUT_DIR / "lsp_servers.json"
        for lang, spec in DEFAULT_SERVERS.items():
            self._configs[lang] = LSPServerConfig(
                language=lang,
                command=spec["command"],
                args=list(spec.get("args", [])),
                enabled=True,
            )

        if not config_path.exists():
            return

        try:
            with open(config_path, encoding="utf-8") as f:
                user_config = json.load(f)
        except (json.JSONDecodeError, OSError):
            return

        for lang in Language:
            key = lang.value
            if key in user_config and isinstance(user_config[key], dict):
                spec = user_config[key]
                self._configs[lang] = LSPServerConfig(
                    language=lang,
                    command=spec.get("command", DEFAULT_SERVERS[lang]["command"]),
                    args=list(spec.get("args", DEFAULT_SERVERS[lang].get("args", []))),
                    enabled=spec.get("enabled", True),
                )

    # ------------------------------------------------------------------
    # Server lifecycle
    # ------------------------------------------------------------------

    def start_server(self, language: Language) -> dict:
        """Start the LSP server for a language and send initialize request.

        Returns the initialize response on success, or an error dict if the
        server binary is not installed or fails to start.
        """
        with self._lock:
            if language in self._processes:
                proc = self._processes[language]
                if proc.poll() is None:
                    return {"status": "already_running", "language": language.value}

            config = self._configs.get(language)
            if config is None or not config.enabled:
                return {"error": f"LSP server for {language.value} is disabled. Enable it in lsp_servers.json."}

            # Check if the server binary is available.
            if not self._is_command_available(config.command):
                return {
                    "error": f"LSP server for {language.value} not available. "
                    f"Install: {INSTALL_HINTS.get(language, '')}"
                }

            try:
                proc = subprocess.Popen(
                    [config.command] + config.args,
                    stdin=subprocess.PIPE,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE,
                    bufsize=0,
                    creationflags=subprocess.CREATE_NEW_PROCESS_GROUP if sys.platform == "win32" else 0,
                )
            except FileNotFoundError:
                return {
                    "error": f"LSP server for {language.value} not available. "
                    f"Install: {INSTALL_HINTS.get(language, '')}"
                }
            except (subprocess.SubprocessError, OSError) as e:
                return {"error": f"Failed to start {language.value} server: {e}"}

            self._processes[language] = proc

        # Send initialize request (outside lock to avoid blocking other languages).
        init_response = self._send_request(
            proc,
            "initialize",
            {
                "processId": os.getpid(),
                "rootUri": Path.cwd().as_uri(),
                "capabilities": {
                    "textDocument": {
                        "synchronization": {
                            "didOpen": True,
                            "didChange": True,
                            "didClose": True,
                        },
                        "definition": {"linkSupport": False},
                        "hover": {"contentFormat": ["markdown", "plaintext"]},
                        "references": {},
                        "rename": {"prepareSupport": False},
                        "completion": {
                            "completionItem": {
                                "snippetSupport": False,
                                "documentationFormat": ["markdown", "plaintext"],
                            },
                        },
                    },
                },
                "workspace": {
                    "workspaceFolders": [{"uri": Path.cwd().as_uri(), "name": Path.cwd().name}],
                },
            },
        )

        if "error" in init_response:
            return init_response

        # Send initialized notification.
        self._send_notification(proc, "initialized", {})

        return {"status": "started", "language": language.value, "response": init_response}

    def stop_server(self, language: Language) -> dict:
        """Stop the LSP server for a language.

        Sends shutdown + exit requests, then terminates the process.
        Returns a status dict.
        """
        with self._lock:
            proc = self._processes.pop(language, None)

        if proc is None or proc.poll() is not None:
            return {"status": "not_running", "language": language.value}

        with contextlib.suppress(OSError, ValueError):
            self._send_request(proc, "shutdown", {})

        with contextlib.suppress(OSError, ValueError):
            self._send_notification(proc, "exit", {})

        try:
            proc.terminate()
            proc.wait(timeout=5)
        except subprocess.TimeoutExpired:
            proc.kill()
        except (subprocess.SubprocessError, OSError):
            pass

        return {"status": "stopped", "language": language.value}

    def stop_all(self):
        """Stop all running LSP servers."""
        for lang in list(self._processes.keys()):
            self.stop_server(lang)

    # ------------------------------------------------------------------
    # LSP feature methods
    # ------------------------------------------------------------------

    def goto_definition(self, file_path: str, line: int, character: int) -> list[dict]:
        """LSP textDocument/definition -- jump to symbol definition.

        Args:
            file_path: absolute path to the source file
            line: 0-based line number
            character: 0-based character offset

        Returns a list of location dicts: {uri, range: {start, end}}.
        """
        language = detect_language(file_path)
        proc = self._ensure_server(language)
        if proc is None:
            return [
                {"error": f"LSP server for {language.value} not available. Install: {INSTALL_HINTS.get(language, '')}"}
            ]

        self._did_open(proc, file_path, language)

        result = self._send_request(
            proc,
            "textDocument/definition",
            {
                "textDocument": {"uri": _to_file_uri(file_path)},
                "position": {"line": line, "character": character},
            },
        )

        if "error" in result:
            return [result]

        locations = result.get("result", [])
        if isinstance(locations, dict):
            # Single Location object.
            return [locations]
        if isinstance(locations, list):
            return locations
        return []

    def hover(self, file_path: str, line: int, character: int) -> dict:
        """LSP textDocument/hover -- get type info and documentation.

        Returns a Hover dict with 'contents' (markdown or plaintext).
        """
        language = detect_language(file_path)
        proc = self._ensure_server(language)
        if proc is None:
            return {
                "error": f"LSP server for {language.value} not available. Install: {INSTALL_HINTS.get(language, '')}"
            }

        self._did_open(proc, file_path, language)

        result = self._send_request(
            proc,
            "textDocument/hover",
            {
                "textDocument": {"uri": _to_file_uri(file_path)},
                "position": {"line": line, "character": character},
            },
        )

        if "error" in result:
            return result

        hover = result.get("result")
        if hover is None:
            return {"contents": ""}
        return hover

    def get_diagnostics(self, file_path: str) -> list[dict]:
        """LSP textDocument/publishDiagnostics -- get errors and warnings.

        Opens the document (triggering diagnostic publication) and collects
        diagnostics. Returns a list of diagnostic dicts.
        """
        language = detect_language(file_path)
        proc = self._ensure_server(language)
        if proc is None:
            return [
                {"error": f"LSP server for {language.value} not available. Install: {INSTALL_HINTS.get(language, '')}"}
            ]

        self._did_open(proc, file_path, language)

        # Diagnostics are pushed via notification, not a request response.
        # Read any pending notifications from the server stdout.
        return self._collect_diagnostics(proc, file_path)

    def get_completion(self, file_path: str, line: int, character: int) -> list[dict]:
        """LSP textDocument/completion -- get autocomplete suggestions.

        Returns a list of completion item dicts.
        """
        language = detect_language(file_path)
        proc = self._ensure_server(language)
        if proc is None:
            return [
                {"error": f"LSP server for {language.value} not available. Install: {INSTALL_HINTS.get(language, '')}"}
            ]

        self._did_open(proc, file_path, language)

        result = self._send_request(
            proc,
            "textDocument/completion",
            {
                "textDocument": {"uri": _to_file_uri(file_path)},
                "position": {"line": line, "character": character},
            },
        )

        if "error" in result:
            return [result]

        completion = result.get("result")
        if completion is None:
            return []
        if isinstance(completion, list):
            return completion
        # CompletionList object with 'items' key.
        if isinstance(completion, dict) and "items" in completion:
            return completion["items"]
        return []

    def find_references(self, file_path: str, line: int, character: int) -> list[dict]:
        """LSP textDocument/references -- find all usages of a symbol.

        Returns a list of location dicts.
        """
        language = detect_language(file_path)
        proc = self._ensure_server(language)
        if proc is None:
            return [
                {"error": f"LSP server for {language.value} not available. Install: {INSTALL_HINTS.get(language, '')}"}
            ]

        self._did_open(proc, file_path, language)

        result = self._send_request(
            proc,
            "textDocument/references",
            {
                "textDocument": {"uri": _to_file_uri(file_path)},
                "position": {"line": line, "character": character},
                "context": {"includeDeclaration": True},
            },
        )

        if "error" in result:
            return [result]

        locations = result.get("result", [])
        if isinstance(locations, list):
            return locations
        return []

    def rename(self, file_path: str, line: int, character: int, new_name: str) -> dict:
        """LSP textDocument/rename -- safe symbol renaming.

        Returns a WorkspaceEdit dict with 'changes' mapping URIs to TextEdit lists.
        """
        language = detect_language(file_path)
        proc = self._ensure_server(language)
        if proc is None:
            return {
                "error": f"LSP server for {language.value} not available. Install: {INSTALL_HINTS.get(language, '')}"
            }

        self._did_open(proc, file_path, language)

        result = self._send_request(
            proc,
            "textDocument/rename",
            {
                "textDocument": {"uri": _to_file_uri(file_path)},
                "position": {"line": line, "character": character},
                "newName": new_name,
            },
        )

        if "error" in result:
            return result

        return result.get("result", {})

    # ------------------------------------------------------------------
    # Low-level JSON-RPC transport
    # ------------------------------------------------------------------

    def _format_message(self, content: str) -> bytes:
        """Format an LSP message with Content-Length header.

        Returns the full message bytes ready to write to stdin.
        """
        content_bytes = content.encode("utf-8")
        header = f"Content-Length: {len(content_bytes)}\r\n\r\n"
        return header.encode("ascii") + content_bytes

    def _send_request(
        self, process: subprocess.Popen, method: str, params: dict | None = None, timeout: float = 10.0
    ) -> dict:
        """Send a JSON-RPC 2.0 request and wait for the response.

        Reads from stdout until a matching response (by id) is found,
        skipping any notifications in between. Returns the response dict.

        Thread-safety: the whole request→response cycle is serialized via
        ``self._lock`` because a single LSP process has one stdin/stdout
        pair — concurrent requests would interleave writes and misroute
        responses.
        """
        with self._lock:
            self._request_id += 1
            req_id = self._request_id

            message = {
                "jsonrpc": "2.0",
                "id": req_id,
                "method": method,
            }
            if params is not None:
                message["params"] = params

            payload = json.dumps(message, ensure_ascii=False)
            data = self._format_message(payload)

            stdin = process.stdin
            if stdin is None:
                return {"error": f"Failed to send request '{method}': process stdin is closed"}
            try:
                stdin.write(data)
                stdin.flush()
            except (BrokenPipeError, OSError, ValueError) as e:
                return {"error": f"Failed to send request '{method}': {e}"}

            # Read responses until we find the one matching our request id.
            import time

            deadline = time.time() + timeout
            while time.time() < deadline:
                remaining = deadline - time.time()
                response = self._read_response(process, timeout=remaining)
                if response is None:
                    return {"error": f"Timeout waiting for response to '{method}'"}

                # If it's a notification (no id), skip it and keep reading.
                if "id" not in response:
                    continue

                if response["id"] == req_id:
                    return response
                # Response for a different request (shouldn't happen in serial mode).
                continue

            return {"error": f"Timeout waiting for response to '{method}'"}

    def _send_notification(self, process: subprocess.Popen, method: str, params: dict | None = None):
        """Send a JSON-RPC 2.0 notification (no response expected)."""
        message: dict[str, str | dict] = {
            "jsonrpc": "2.0",
            "method": method,
        }
        if params is not None:
            message["params"] = params

        payload = json.dumps(message, ensure_ascii=False)
        data = self._format_message(payload)

        stdin = process.stdin
        if stdin is None:
            return
        try:
            stdin.write(data)
            stdin.flush()
        except (BrokenPipeError, OSError, ValueError):
            pass

    def _read_response(self, process: subprocess.Popen, timeout: float = 10.0) -> dict | None:
        """Read a single LSP message from the server stdout.

        Parses the Content-Length header, reads the JSON body, and returns
        the parsed dict. Returns None on timeout or EOF.

        Uses thread-based reads with deadline to avoid blocking forever
        (the original process.stdout.read(1) ignores the deadline check
        while blocked on I/O, which can hang the main thread indefinitely).
        """
        import queue
        import threading
        import time

        def _read_with_timeout(read_fn, remaining):
            """Run read_fn in a daemon thread; return result or _TIMEOUT sentinel."""
            q = queue.Queue()

            def _worker():
                try:
                    q.put(read_fn())
                except (subprocess.SubprocessError, OSError):
                    q.put(None)

            t = threading.Thread(target=_worker, daemon=True)
            t.start()
            try:
                return q.get(timeout=max(remaining, 0.01))
            except queue.Empty:
                return None  # timeout → treat as no data

        deadline = time.time() + timeout

        stdout = process.stdout
        if stdout is None:
            return None

        # Read headers until we hit the blank line separator.
        headers = {}
        header_line = b""

        while time.time() < deadline:
            byte = _read_with_timeout(
                lambda: stdout.read(1),
                deadline - time.time(),
            )
            if not byte:
                return None

            if byte == b"\n":
                line = header_line.strip()
                header_line = b""
                if line == b"":
                    # End of headers.
                    break
                # Parse "Key: Value".
                if b":" in line:
                    key, _, val = line.partition(b":")
                    headers[key.strip().lower().decode("ascii", errors="replace")] = val.strip().decode(
                        "ascii", errors="replace"
                    )
            elif byte == b"\r":
                continue
            else:
                header_line += byte

        content_length_str = headers.get("content-length")
        if content_length_str is None:
            return None

        try:
            content_length = int(content_length_str)
        except ValueError:
            return None

        # Read the JSON body.
        body = b""
        while len(body) < content_length and time.time() < deadline:
            remaining = deadline - time.time()
            chunk = _read_with_timeout(
                lambda n=content_length - len(body): stdout.read(n),  # noqa: B008
                remaining,
            )
            if not chunk:
                break
            body += chunk

        if len(body) < content_length:
            return None

        try:
            return json.loads(body.decode("utf-8"))
        except (json.JSONDecodeError, UnicodeDecodeError) as e:
            return {"error": f"Failed to parse LSP response: {e}"}

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _ensure_server(self, language: Language) -> subprocess.Popen | None:
        """Ensure the server for a language is running. Start it if needed.

        Returns the process, or None if the server could not be started.
        """
        with self._lock:
            proc = self._processes.get(language)
            if proc is not None and proc.poll() is None:
                return proc

        result = self.start_server(language)
        if "error" in result:
            return None

        with self._lock:
            return self._processes.get(language)

    def _did_open(self, process: subprocess.Popen, file_path: str, language: Language):
        """Send textDocument/didOpen notification for a file."""
        try:
            content = Path(file_path).read_text(encoding="utf-8", errors="replace")
        except (subprocess.SubprocessError, OSError):
            content = ""

        # Map Language to LSP languageId.
        lang_id = {
            Language.PYTHON: "python",
            Language.JAVASCRIPT: "javascript",
            Language.TYPESCRIPT: "typescript",
            Language.GO: "go",
            Language.RUST: "rust",
        }.get(language, "plaintext")

        self._send_notification(
            process,
            "textDocument/didOpen",
            {
                "textDocument": {
                    "uri": _to_file_uri(file_path),
                    "languageId": lang_id,
                    "version": 1,
                    "text": content,
                },
            },
        )

    def _collect_diagnostics(self, process: subprocess.Popen, file_path: str) -> list[dict]:
        """Collect diagnostics for a file from server notifications.

        After didOpen, the server pushes a publishDiagnostics notification.
        This reads messages until a diagnostics notification for the target
        file is found (or timeout).
        """
        import time

        target_uri = _to_file_uri(file_path)
        deadline = time.time() + 5.0

        while time.time() < deadline:
            remaining = deadline - time.time()
            msg = self._read_response(process, timeout=remaining)
            if msg is None:
                break

            method = msg.get("method")
            if method == "textDocument/publishDiagnostics":
                params = msg.get("params", {})
                if params.get("uri") == target_uri:
                    return params.get("diagnostics", [])

        return []

    @staticmethod
    def _is_command_available(command: str) -> bool:
        """Check if a command is available on the system PATH."""
        import shutil

        return shutil.which(command) is not None


# ======================================================================
# Singleton accessor
# ======================================================================

_lsp_client: LSPClient | None = None
_client_lock = threading.Lock()


def get_lsp_client() -> LSPClient:
    """Get the global LSPClient singleton instance."""
    global _lsp_client
    if _lsp_client is None:
        with _client_lock:
            if _lsp_client is None:
                _lsp_client = LSPClient()
    return _lsp_client


def reset_lsp_client() -> None:
    """Stop all LSP servers and drop the global singleton.

    Used for test isolation and hot reload. A subsequent get_lsp_client()
    call will spin up a fresh LSPClient.
    """
    global _lsp_client
    with _client_lock:
        if _lsp_client is not None:
            with contextlib.suppress(Exception):
                _lsp_client.stop_all()
            _lsp_client = None


# ======================================================================
# Tool executors for integration with ToolRegistry
# ======================================================================


def execute_lsp_goto_definition(file_path: str = "", line: int = 0, character: int = 0) -> str:
    """Tool executor: jump to symbol definition via LSP."""
    if not file_path:
        return json.dumps({"error": "file_path required"}, ensure_ascii=False)

    client = get_lsp_client()
    try:
        result = client.goto_definition(file_path, line, character)
        return json.dumps(
            {"file": file_path, "line": line, "character": character, "definitions": result},
            ensure_ascii=False,
            indent=2,
        )
    except ValueError as e:
        return json.dumps({"error": str(e)}, ensure_ascii=False)
    except (json.JSONDecodeError, TypeError, KeyError) as e:
        return json.dumps({"error": f"LSP request failed: {e}"}, ensure_ascii=False)


def execute_lsp_hover(file_path: str = "", line: int = 0, character: int = 0) -> str:
    """Tool executor: get hover info (type, docs) via LSP."""
    if not file_path:
        return json.dumps({"error": "file_path required"}, ensure_ascii=False)

    client = get_lsp_client()
    try:
        result = client.hover(file_path, line, character)
        return json.dumps(
            {"file": file_path, "line": line, "character": character, "hover": result}, ensure_ascii=False, indent=2
        )
    except ValueError as e:
        return json.dumps({"error": str(e)}, ensure_ascii=False)
    except (json.JSONDecodeError, TypeError, KeyError) as e:
        return json.dumps({"error": f"LSP request failed: {e}"}, ensure_ascii=False)


def execute_lsp_diagnostics(file_path: str = "") -> str:
    """Tool executor: get diagnostics (errors, warnings) via LSP."""
    if not file_path:
        return json.dumps({"error": "file_path required"}, ensure_ascii=False)

    client = get_lsp_client()
    try:
        result = client.get_diagnostics(file_path)
        return json.dumps(
            {"file": file_path, "diagnostics": result, "count": len(result)}, ensure_ascii=False, indent=2
        )
    except ValueError as e:
        return json.dumps({"error": str(e)}, ensure_ascii=False)
    except (json.JSONDecodeError, TypeError, KeyError) as e:
        return json.dumps({"error": f"LSP request failed: {e}"}, ensure_ascii=False)


def execute_lsp_find_references(file_path: str = "", line: int = 0, character: int = 0) -> str:
    """Tool executor: find all references to a symbol via LSP."""
    if not file_path:
        return json.dumps({"error": "file_path required"}, ensure_ascii=False)

    client = get_lsp_client()
    try:
        result = client.find_references(file_path, line, character)
        return json.dumps(
            {"file": file_path, "line": line, "character": character, "references": result, "count": len(result)},
            ensure_ascii=False,
            indent=2,
        )
    except ValueError as e:
        return json.dumps({"error": str(e)}, ensure_ascii=False)
    except (json.JSONDecodeError, TypeError, KeyError) as e:
        return json.dumps({"error": f"LSP request failed: {e}"}, ensure_ascii=False)


def execute_lsp_completion(file_path: str = "", line: int = 0, character: int = 0) -> str:
    """Tool executor: get autocomplete suggestions via LSP."""
    if not file_path:
        return json.dumps({"error": "file_path required"}, ensure_ascii=False)
    client = get_lsp_client()
    try:
        result = client.get_completion(file_path, line, character)
        return json.dumps(
            {"file": file_path, "line": line, "character": character, "completions": result},
            ensure_ascii=False,
            indent=2,
        )
    except ValueError as e:
        return json.dumps({"error": str(e)}, ensure_ascii=False)
    except (json.JSONDecodeError, TypeError, KeyError) as e:
        return json.dumps({"error": f"LSP request failed: {e}"}, ensure_ascii=False)


def execute_lsp_rename(file_path: str = "", line: int = 0, character: int = 0, new_name: str = "") -> str:
    """Tool executor: rename symbol across project via LSP."""
    if not file_path or not new_name:
        return json.dumps({"error": "file_path and new_name required"}, ensure_ascii=False)
    client = get_lsp_client()
    try:
        result = client.rename(file_path, line, character, new_name)
        return json.dumps(
            {"file": file_path, "line": line, "character": character, "new_name": new_name, "changes": result},
            ensure_ascii=False,
            indent=2,
        )
    except ValueError as e:
        return json.dumps({"error": str(e)}, ensure_ascii=False)
    except (json.JSONDecodeError, TypeError, KeyError) as e:
        return json.dumps({"error": f"LSP request failed: {e}"}, ensure_ascii=False)


# Tool definitions for ToolRegistry.
LSP_TOOL_DEFS = [
    {
        "type": "function",
        "function": {
            "name": "lsp_goto_definition",
            "description": "Jump to the definition of a symbol at a given position in a file using the Language Server Protocol. Returns the file URI and range of the definition. Use this to navigate code.",
            "parameters": {
                "type": "object",
                "properties": {
                    "file_path": {
                        "type": "string",
                        "description": "Absolute path to the source file",
                    },
                    "line": {
                        "type": "integer",
                        "description": "0-based line number (first line is 0)",
                    },
                    "character": {
                        "type": "integer",
                        "description": "0-based character offset in the line (first character is 0)",
                    },
                },
                "required": ["file_path", "line", "character"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "lsp_hover",
            "description": "Get hover information (type signature, documentation) for a symbol at a given position in a file using LSP. Returns markdown or plaintext content with type info and docs.",
            "parameters": {
                "type": "object",
                "properties": {
                    "file_path": {
                        "type": "string",
                        "description": "Absolute path to the source file",
                    },
                    "line": {
                        "type": "integer",
                        "description": "0-based line number",
                    },
                    "character": {
                        "type": "integer",
                        "description": "0-based character offset",
                    },
                },
                "required": ["file_path", "line", "character"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "lsp_diagnostics",
            "description": "Get diagnostics (errors, warnings, hints) for a file using LSP. The file is opened in the language server and any issues are returned. Use this to check for compilation or lint errors.",
            "parameters": {
                "type": "object",
                "properties": {
                    "file_path": {
                        "type": "string",
                        "description": "Absolute path to the source file",
                    },
                },
                "required": ["file_path"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "lsp_find_references",
            "description": "Find all references to the symbol at a given position in a file using LSP. Returns a list of locations where the symbol is used. Use this to understand impact before refactoring.",
            "parameters": {
                "type": "object",
                "properties": {
                    "file_path": {
                        "type": "string",
                        "description": "Absolute path to the source file",
                    },
                    "line": {
                        "type": "integer",
                        "description": "0-based line number",
                    },
                    "character": {
                        "type": "integer",
                        "description": "0-based character offset",
                    },
                },
                "required": ["file_path", "line", "character"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "lsp_completion",
            "description": "Get autocomplete suggestions at a given position in a file using LSP. Returns a list of completion items with labels, detail, and documentation. Use this to get code suggestions.",
            "parameters": {
                "type": "object",
                "properties": {
                    "file_path": {
                        "type": "string",
                        "description": "Absolute path to the source file",
                    },
                    "line": {
                        "type": "integer",
                        "description": "0-based line number",
                    },
                    "character": {
                        "type": "integer",
                        "description": "0-based character offset",
                    },
                },
                "required": ["file_path", "line", "character"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "lsp_rename",
            "description": "Rename a symbol across the entire project using LSP. Returns a list of workspace edits showing all files and positions that will be changed. Use this for safe, project-wide refactoring.",
            "parameters": {
                "type": "object",
                "properties": {
                    "file_path": {
                        "type": "string",
                        "description": "Absolute path to the source file containing the symbol",
                    },
                    "line": {
                        "type": "integer",
                        "description": "0-based line number of the symbol",
                    },
                    "character": {
                        "type": "integer",
                        "description": "0-based character offset of the symbol",
                    },
                    "new_name": {
                        "type": "string",
                        "description": "The new name for the symbol",
                    },
                },
                "required": ["file_path", "line", "character", "new_name"],
            },
        },
    },
]

# Executor map: tool name -> callable returning JSON string.
LSP_EXECUTOR_MAP = {
    "lsp_goto_definition": lambda **kw: execute_lsp_goto_definition(
        file_path=kw.get("file_path", ""),
        line=kw.get("line", 0),
        character=kw.get("character", 0),
    ),
    "lsp_hover": lambda **kw: execute_lsp_hover(
        file_path=kw.get("file_path", ""),
        line=kw.get("line", 0),
        character=kw.get("character", 0),
    ),
    "lsp_diagnostics": lambda **kw: execute_lsp_diagnostics(
        file_path=kw.get("file_path", ""),
    ),
    "lsp_find_references": lambda **kw: execute_lsp_find_references(
        file_path=kw.get("file_path", ""),
        line=kw.get("line", 0),
        character=kw.get("character", 0),
    ),
    "lsp_completion": lambda **kw: execute_lsp_completion(
        file_path=kw.get("file_path", ""),
        line=kw.get("line", 0),
        character=kw.get("character", 0),
    ),
    "lsp_rename": lambda **kw: execute_lsp_rename(
        file_path=kw.get("file_path", ""),
        line=kw.get("line", 0),
        character=kw.get("character", 0),
        new_name=kw.get("new_name", ""),
    ),
}
