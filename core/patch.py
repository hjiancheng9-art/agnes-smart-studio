"""Structured patch engine -- reliable code modification with context matching.

Replaces fragile exact-text-match in edit_file. Uses unified-diff-style hunks
with @@ context markers. Handles any encoding, auto-backups, syntax-verifies.

Format:
    *** Update File: path/to/file
    @@ context line that must match
    -old line to remove
    +new line to add
      unchanged context line

Operations: add_file, delete_file, update_file (with one or more hunks)
"""

import contextlib
from pathlib import Path

__all__ = ['PatchEngine', 'PatchError', 'ROOT', 'apply', 'rollback_last']

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
        """Parse and apply a multi-operation patch. Returns summary."""
        global _LAST_BACKUPS, _LAST_ADDED
        self._backups = {}
        self._modified = set()
        ops = self._parse(patch_text)
        results = []
        # 记录本次 patch 新建的文件（应用前不存在），用于撤销时删除
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
            return {"success": False, "error": str(e), "file": e.file,
                    "results": results}
        except (OSError, ValueError, RuntimeError) as e:
            self._rollback()
            return {"success": False, "error": str(e), "results": results}
        # 成功：把本次备份提升为模块级"最近一次"快照，供 rollback_last() 使用
        _LAST_BACKUPS = dict(self._backups)
        _LAST_ADDED = added_paths
        return {"success": True, "files_modified": len(self._modified),
                "results": results}

    def _parse(self, text: str) -> list[dict]:
        ops = []
        lines = text.split("\n")
        i = 0
        while i < len(lines):
            line = lines[i].strip()
            if line.startswith("*** Add File:"):
                path = line[len("*** Add File:"):].strip()
                content_lines = []
                i += 1
                while i < len(lines) and not lines[i].strip().startswith("***"):
                    if lines[i].startswith("+"):
                        content_lines.append(lines[i][1:])
                    else:
                        content_lines.append(lines[i])
                    i += 1
                ops.append({"type": "add_file", "path": path,
                            "content": "\n".join(content_lines)})
            elif line.startswith("*** Delete File:"):
                path = line[len("*** Delete File:"):].strip()
                ops.append({"type": "delete_file", "path": path})
                i += 1
            elif line.startswith("*** Update File:"):
                path = line[len("*** Update File:"):].strip()
                i += 1
                hunks = []
                current_hunk = None
                while i < len(lines) and not lines[i].strip().startswith("***"):
                    line = lines[i]
                    if line.startswith("@@"):
                        if current_hunk:
                            hunks.append(current_hunk)
                        current_hunk = {"context": line[2:].strip(), "changes": []}
                    elif current_hunk is not None:
                        current_hunk["changes"].append(line)
                    i += 1
                if current_hunk:
                    hunks.append(current_hunk)
                if hunks:
                    ops.append({"type": "update_file", "path": path, "hunks": hunks})
                else:
                    i += 1
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
        path = self._resolve_path(rel_path)
        if not path.exists():
            raise PatchError(f"File not found: {rel_path}", file=rel_path)
        self._backup(path)
        content = path.read_text(encoding="utf-8")
        lines = content.split("\n")
        applied = 0
        for hunk in hunks:
            ctx = hunk["context"]
            changes = hunk["changes"]
            # Find context match
            ctx_idx = -1
            for i in range(len(lines)):
                if lines[i].strip() == ctx.strip():
                    ctx_idx = i
                    break
            if ctx_idx < 0:
                raise PatchError(
                    f"Context not found in {rel_path}: '{ctx[:60]}'",
                    file=rel_path)
            # Determine hunk boundaries: context line + following lines until next @@ or EOF
            # Build new lines: start from ctx line, replace with changes
            insert_lines = []
            for ch in changes:
                if ch.startswith("-"):
                    continue  # skip old line
                elif ch.startswith("+") or ch.startswith(" "):
                    insert_lines.append(ch[1:])
                else:
                    insert_lines.append(ch)
            # Replace: remove from ctx_idx to end of changes section
            # Calculate how many original lines to remove (count all - lines + context + unchanged)
            remove_count = 1  # context line itself
            for ch in changes:
                if ch.startswith("-") or ch.startswith(" "):
                    remove_count += 1
            lines[ctx_idx:ctx_idx + remove_count] = insert_lines
            applied += 1
        path.write_text("\n".join(lines), encoding="utf-8")
        if verify and not self._verify_syntax(path):
            raise PatchError(f"Syntax error after update: {rel_path}", file=rel_path)
        self._modified.add(str(path))
        return {"op": "update", "file": rel_path, "hunks_applied": applied, "status": "ok"}


# Convenience function
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
        return {"success": False, "reason": "nothing_to_undo",
                "message": "没有可撤销的 patch（快照为空）"}

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

    summary = {"success": True, "restored": len(restored),
               "deleted_new_files": len(deleted),
               "paths": {"restored": restored, "deleted": deleted}}

    # 清空快照，避免重复撤销
    _LAST_BACKUPS = {}
    _LAST_ADDED = set()
    return summary
