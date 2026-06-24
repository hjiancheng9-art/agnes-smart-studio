"""Export engine -- conversation to Markdown, asset lists, config packaging."""

import json
from datetime import datetime
from pathlib import Path

__all__ = ["EXPORT_DIR", "ExportEngine", "ROOT", "export_assets", "export_chat"]
ROOT = Path(__file__).resolve().parent.parent
EXPORT_DIR = ROOT / "output" / "exports"


class ExportEngine:
    def __init__(self, root: Path | None = None) -> None:
        self.root = root or ROOT
        self.dir = self.root / "output" / "exports"
        self.dir.mkdir(parents=True, exist_ok=True)

    def conversation_to_md(self, messages: list[dict], title: str = "Conversation") -> str:
        ts = datetime.now().strftime("%Y%m%d_%H%M%S")
        fname = f"chat_{ts}.md"
        path = self.dir / fname
        lines = [f"# {title}", f"_Exported: {datetime.now().isoformat()}_", ""]
        for msg in messages:
            role = msg.get("role", "?").upper()
            content = msg.get("content", "")
            if isinstance(content, list):
                parts = []
                for item in content:
                    if isinstance(item, dict) and item.get("type") == "text":
                        parts.append(item.get("text", ""))
                content = " ".join(parts)
            if not isinstance(content, str):
                content = str(content)
            lines.append(f"### {role}")
            lines.append(content[:5000])
            lines.append("")
        path.write_text("\n".join(lines), encoding="utf-8")
        return str(path)

    def asset_list(self) -> dict:
        assets = {"images": [], "videos": [], "exports": []}
        for cat, subdir in [("images", "images"), ("videos", "videos"), ("exports", "exports")]:
            d = self.root / "output" / subdir
            if d.exists():
                for f in sorted(d.iterdir(), key=lambda p: p.stat().st_mtime, reverse=True)[:20]:
                    assets[cat].append(
                        {
                            "name": f.name,
                            "size": f.stat().st_size,
                            "modified": f.stat().st_mtime,
                        }
                    )
        return assets

    def config_snapshot(self) -> str:
        ts = datetime.now().strftime("%Y%m%d_%H%M%S")
        path = self.dir / f"config_{ts}.json"
        snapshot = {}
        for cfg_file in ["models.json", "tools.json"]:
            p = self.root / cfg_file
            if p.exists():
                snapshot[cfg_file] = json.loads(p.read_text(encoding="utf-8"))
        path.write_text(json.dumps(snapshot, ensure_ascii=False, indent=2), encoding="utf-8")
        return str(path)


def export_chat(messages: list[dict], title: str = "") -> str:
    return ExportEngine().conversation_to_md(messages, title)


def export_assets() -> dict:
    return ExportEngine().asset_list()
