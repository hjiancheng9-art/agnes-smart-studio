"""Structured patch engine -- reliable code modification with context matching.

Replaces fragile exact-text-match in edit_file. Uses unified-diff-style hunks
with context markers. Handles any encoding, auto-backups, syntax-verifies.

Format (v1 compatibility):
    *** Update File: path/to/file
    @@ context line that must match
    -old line to remove
    +new line to add
      unchanged context line

Format (v2 precision):
    *** Update File: path/to/file
    @@ [<line_number>] [<context_line>]
      [additional_context_lines...]
    -remove_this_line
    +add_this_line
      keep_this_line

    - @@ 42 -- jump to 1-indexed line 42, verify context below
    - @@ def foo(): -- single-line exact match (indentation preserved)
    - @@ 42 def foo(): -- line anchor + context verification
    - Additional lines starting with space after @@ extend the context block
    - A hunk matches when ALL context lines align at a location
    - strip() is NEVER used for matching -- indentation is part of the context

Operations: add_file, delete_file, update_file (with one or more hunks)
"""

import contextlib
from pathlib import Path

__all__ = ["PatchEngine", "PatchError", "ROOT", "apply", "rollback_last"]

ROOT = Path(__file__).resolve().parent.parent

# 模块级快照：最近一次成功 apply 的备份，供 rollback_last() 撤销使用。
# _LAST_BACKUPS = {path: 改前内容}（恢复写回）
# _LAST_ADDED   = {path}（撤销时删除，因为应用前不存在）
_LAST_BACKUPS: dict[str, str] = {}
_LAST_ADDED: set[str] = set()


class PatchError(Exception):
    def __init__(self, message: str, file: str = "", line: int = 0) -> None:
        super().__init__(message)
        self.file = file
        self.line = line


class PatchEngine:
    """Applies structured patches with backup, verification, and rollback."""

    def __init__(self, root: Path | None = None) -> None:
        self.root = root or ROOT
        self._backups: dict[str, str] = {}
        self._modified: set[str] = set()

    def apply(self, patch_text: str, verify: bool = True) -> dict:
        """Parse and apply a multi-operation patch. Returns summary.

        v2: Core-file protection — applies a global pre-patch snapshot so
        that rollback restores ALL files to pre-patch state, not per-hunk.
        """
        global _LAST_BACKUPS, _LAST_ADDED
        self._backups = {}
        self._modified = set()
        ops = self._parse(patch_text)

        # Global snapshot: backup every target BEFORE any modification.
        # If ANY hunk/syntax check fails, ALL files are rolled back atomically.
        for op in ops:
            if op.get("type") in ("update_file", "delete_file"):
                p = self._resolve_path(op["path"])
                if p.exists():
                    self._backups[str(p)] = p.read_text(encoding="utf-8")

        results = []
        added_paths: set[str] = set()
        try:
            for op in ops:
                op_type = op["type"]
                if op_type == "add_file":
                    target = self._resolve_path(op["path"])
                    # 应用前不存在 → 视为新增，撤销时要删
                    if not target.exists():
                        added_paths.add(str(target))
                    results.append(self._add_file(op["path"], op["content"], verify))
                elif op_type == "delete_file":
                    results.append(self._delete_file(op["path"]))
                elif op_type == "update_file":
                    results.append(self._update_file(op["path"], op["hunks"], verify))
        except PatchError as e:
            self._rollback()
            return {"success": False, "error": str(e), "file": e.file, "results": results}
        except (OSError, ValueError, RuntimeError) as e:
            self._rollback()
            return {"success": False, "error": str(e), "results": results}
        # 成功：把本次备份提升为模块级"最近一次"快照，供 rollback_last() 使用
        _LAST_BACKUPS = dict(self._backups)
        _LAST_ADDED = added_paths
        return {"success": True, "files_modified": len(self._modified), "results": results}

    def _parse(self, text: str) -> list[dict]:
        """Parse patch text into operations.

        v2 enhancements:
        - `@@ N` -- line-number anchor (1-indexed)
        - `@@ N context` -- line anchor + context verification
        - `@@ context` -- single-line exact context (indentation preserved)
        - Multi-line context: consecutive ` ` lines after `@@` form
          an extended context block (collected before any `-`/`+` lines).
        """
        ops = []
        raw_lines = text.split(chr(10))
        i = 0
        while i < len(raw_lines):
            stripped = raw_lines[i].strip()
            if stripped.startswith("*** Add File:"):
                path = stripped[len("*** Add File:"):].strip()
                content_lines = []
                i += 1
                while i < len(raw_lines) and not raw_lines[i].strip().startswith("***"):
                    if raw_lines[i].startswith("+"):
                        content_lines.append(raw_lines[i][1:])
                    else:
                        content_lines.append(raw_lines[i])
                    i += 1
                ops.append({"type": "add_file", "path": path, "content": chr(10).join(content_lines)})
            elif stripped.startswith("*** Delete File:"):
                path = stripped[len("*** Delete File:"):].strip()
                ops.append({"type": "delete_file", "path": path})
                i += 1
            elif stripped.startswith("*** Update File:"):
                path = stripped[len("*** Update File:"):].strip()
                i += 1
                hunks = []
                current_hunk = None
                in_context_block = False
                while i < len(raw_lines) and not raw_lines[i].strip().startswith("***"):
                    raw_line = raw_lines[i]
                    if raw_line.startswith("@@"):
                        if current_hunk:
                            hunks.append(current_hunk)
                        # Parse header: optional line number, optional context
                        header = raw_line[2:]  # after "@@"
                        line_num = 0
                        context_text = ""
                        if header.strip():
                            parts = header.strip().split(None, 1)
                            if parts and parts[0].isdigit():
                                line_num = int(parts[0])
                                context_text = parts[1] if len(parts) > 1 else ""
                            else:
                                context_text = header  # preserve indentation for exact match
                        current_hunk = {
                            "line_num": line_num,
                            "context": context_text,
                            "context_lines": [],
                            "changes": [],
                        }
                        in_context_block = True
                    elif current_hunk is not None:
                        if in_context_block and raw_line.startswith(" "):
                            current_hunk["context_lines"].append(raw_line[1:])
                        else:
                            in_context_block = False
                            current_hunk["changes"].append(raw_line)
                    i += 1
                if current_hunk:
                    hunks.append(current_hunk)
                if hunks:
                    ops.append({"type": "update_file", "path": path, "hunks": hunks})
            else:
                i += 1
        return ops

    def _resolve_path(self, rel_path: str) -> Path:
        p = Path(rel_path)
        if p.is_absolute():
            # 绝对路径拒绝：所有路径必须在项目根目录内
            resolved = p.resolve()
            if self.root.resolve() not in resolved.parents and resolved != self.root.resolve():
                raise PatchError(f"路径超出项目根目录: {rel_path}", file=rel_path)
            return resolved
        resolved = (self.root / p).resolve()
        if self.root.resolve() not in resolved.parents and resolved != self.root.resolve():
            raise PatchError(f"路径超出项目根目录: {rel_path}", file=rel_path)
        return resolved

    def _backup(self, path: Path):
        if str(path) not in self._backups and path.exists():
            self._backups[str(path)] = path.read_text(encoding="utf-8")

    def _rollback(self):
        for path_str, content in self._backups.items():
            with contextlib.suppress(OSError, UnicodeDecodeError):
                Path(path_str).write_text(content, encoding="utf-8")

    def _verify_syntax(self, path: Path) -> bool:
        if path.suffix != ".py":
            return True
        try:
            import ast

            ast.parse(path.read_text(encoding="utf-8"))
            return True
        except SyntaxError:
            return False

    def _add_file(self, rel_path: str, content: str, verify: bool) -> dict:
        path = self._resolve_path(rel_path)
        path.parent.mkdir(parents=True, exist_ok=True)
        if path.exists():
            self._backup(path)
        path.write_text(content, encoding="utf-8")
        if verify and not self._verify_syntax(path):
            raise PatchError(f"Syntax error after add: {rel_path}", file=rel_path)
        self._modified.add(str(path))
        return {"op": "add", "file": rel_path, "status": "ok"}

    def _delete_file(self, rel_path: str) -> dict:
        path = self._resolve_path(rel_path)
        if path.exists():
            self._backup(path)
            path.unlink()
        self._modified.add(str(path))
        return {"op": "delete", "file": rel_path, "status": "ok"}

    def _update_file(self, rel_path: str, hunks: list[dict], verify: bool) -> dict:
        """Apply hunks to a file with exact context matching.

        v2: Exact match (no strip), line-number anchoring, multi-line context.
        """
        path = self._resolve_path(rel_path)
        if not path.exists():
            raise PatchError(f"File not found: {rel_path}", file=rel_path)
        self._backup(path)
        content = path.read_text(encoding="utf-8")
        file_lines = content.split(chr(10))
        applied = 0
        for hunk in hunks:
            ctx_text = hunk.get("context", "")
            ctx_lines = hunk.get("context_lines", [])
            line_num = hunk.get("line_num", 0)
            changes = hunk.get("changes", [])

            # Build the full context block for matching
            if ctx_text and not ctx_lines:
                # Single-line context (v1 compat + v2 single)
                context_block = [ctx_text]
            elif ctx_text and ctx_lines:
                # Line-number header included text, prepend to context block
                context_block = [ctx_text] + ctx_lines
            elif ctx_lines:
                # Multi-line context only (no header text)
                context_block = ctx_lines
            else:
                # No context provided
                context_block = []

            # ── Exact context matching ──
            match_idx = -1
            if context_block:
                # Determine search range
                start_search = max(0, line_num - 1) if line_num > 0 else 0
                if line_num > 0 and line_num > len(file_lines):
                    raise PatchError(
                        f"Line number {line_num} exceeds file length ({len(file_lines)}) in {rel_path}",
                        file=rel_path,
                    )
                # Exact multi-line context search
                for idx in range(start_search, len(file_lines) - len(context_block) + 1):
                    match_all = True
                    for j, ctx_line in enumerate(context_block):
                        if file_lines[idx + j] != ctx_line:
                            match_all = False
                            break
                    if match_all:
                        match_idx = idx
                        break

                if match_idx < 0 and len(context_block) == 1 and not ctx_lines:
                    # v1 backward compat: try strip-match for single-line context
                    stripped_ctx = context_block[0].strip()
                    for idx in range(start_search, len(file_lines)):
                        if file_lines[idx].strip() == stripped_ctx:
                            match_idx = idx
                            break

                if match_idx < 0:
                    ctx_preview = context_block[0][:60] if context_block else "(empty)"
                    hint = ""
                    if line_num > 0:
                        hint = f" near line {line_num}"
                    raise PatchError(
                        f"Context not found in {rel_path}{hint}: {chr(39)}{ctx_preview}{chr(39)}",
                        file=rel_path,
                    )
            else:
                # No context: anchor on line number only
                if line_num > 0:
                    match_idx = line_num - 1
                else:
                    match_idx = 0  # top of file

            # ── Apply hunk changes ──
            insert_lines = []
            for ch in changes:
                if ch.startswith("-"):
                    continue  # remove line
                elif ch.startswith("+") or ch.startswith(" "):
                    insert_lines.append(ch[1:])
                else:
                    insert_lines.append(ch)

            # Calculate original lines to remove
            remove_count = len(context_block)  # context lines
            for ch in changes:
                if ch.startswith("-") or ch.startswith(" "):
                    remove_count += 1

            # Apply the replacement
            file_lines[match_idx : match_idx + remove_count] = insert_lines
            applied += 1

        path.write_text(chr(10).join(file_lines), encoding="utf-8")
        if verify and not self._verify_syntax(path):
            raise PatchError(f"Syntax error after update: {rel_path}", file=rel_path)
        self._modified.add(str(path))
        return {"op": "update", "file": rel_path, "hunks_applied": applied, "status": "ok"}
def apply(patch_text: str, verify: bool = True) -> dict:
    """Apply a structured patch and return result."""
    return PatchEngine().apply(patch_text, verify=verify)


def rollback_last() -> dict:
    """撤销最近一次成功 apply 的 patch。

    - 对被修改的文件：从 _LAST_BACKUPS 写回改前内容。
    - 对被新增的文件：删除（恢复到应用前不存在的状态）。
    - 对被删除的文件：备份在 _LAST_BACKUPS 里，一并恢复。

    幂等：再次调用时无快照可撤销，返回 nothing_to_undo。
    """
    global _LAST_BACKUPS, _LAST_ADDED
    import contextlib

    if not _LAST_BACKUPS and not _LAST_ADDED:
        return {"success": False, "reason": "nothing_to_undo", "message": "没有可撤销的 patch（快照为空）"}

    restored, deleted = [], []
    for path_str, content in _LAST_BACKUPS.items():
        try:
            Path(path_str).write_text(content, encoding="utf-8")
            restored.append(path_str)
        except (OSError, UnicodeDecodeError):
            pass
    for path_str in _LAST_ADDED:
        if path_str in _LAST_BACKUPS:
            continue  # 已在备份恢复路径里处理
        with contextlib.suppress(OSError):
            Path(path_str).unlink()
            deleted.append(path_str)

    summary = {
        "success": True,
        "restored": len(restored),
        "deleted_new_files": len(deleted),
        "paths": {"restored": restored, "deleted": deleted},
    }

    # 清空快照，避免重复撤销
    _LAST_BACKUPS = {}
    _LAST_ADDED = set()
    return summary
