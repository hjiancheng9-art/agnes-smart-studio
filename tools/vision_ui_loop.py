"""视觉-语言闭环：截图 → 视觉分析 → JSON 代码改动 → 自动应用 → 截图验证。

让视觉模型直接输出可执行的代码修改，语言模型只负责执行。
消除"视觉→说话→理解→改代码"的翻译损失。
"""

from __future__ import annotations

import base64
import json
import os
import time
from pathlib import Path

import httpx

ROOT = Path(__file__).resolve().parent.parent
ZHIPU_KEY = os.environ.get("ZHIPU_API_KEY", "")
ZHIPU_URL = "https://open.bigmodel.cn/api/paas/v4/chat/completions"

DESIGN_PROMPT = """你是 UI 设计专家，也是 Python 工程师。

这是一张 CRUX 终端应用的截图。分析它的视觉问题，输出一个 JSON 对象，包含最多 3 条具体的代码修改建议。

JSON 格式：
```json
{
  "changes": [
    {
      "file": "ui/terminal_chat.py",
      "method": "_header_text",
      "issue": "当前问题的描述",
      "old_text": "需要替换的精确文本（一行或多行）",
      "new_text": "替换后的新文本"
    }
  ]
}
```

规则：
- old_text 必须和源文件中的文本完全一致（含缩进、空格）
- new_text 必须是可以直接替代的有效 Python 代码
- 每处改动独立，互不依赖
- 如果界面已经很好，返回 {"changes": []}
- 只关注终端内部的 TUI 元素，不要提窗口大小、桌面布局等
- 给出精确的颜色值 (#rrggbb) 和精确的文本内容
- 如果某个元素不存在于截图中，不要提它的改动

输出纯 JSON，不要包含 markdown 代码块标记。"""


def screenshot(output_path: str) -> str:
    """截图桌面并返回文件路径。"""
    from PIL import ImageGrab

    img = ImageGrab.grab()
    img.save(output_path)
    return output_path


def analyze(image_path: str) -> dict:
    """发送截图给视觉模型，获取 JSON 改动建议。"""
    if not ZHIPU_KEY:
        raise RuntimeError("ZHIPU_API_KEY not set")

    with open(image_path, "rb") as f:
        img64 = base64.b64encode(f.read()).decode()

    resp = httpx.post(
        ZHIPU_URL,
        json={
            "model": "GLM-4V-Flash",
            "max_tokens": 2048,
            "temperature": 0.3,
            "messages": [
                {
                    "role": "user",
                    "content": [
                        {"type": "image_url", "image_url": {"url": f"data:image/png;base64,{img64}"}},
                        {"type": "text", "text": DESIGN_PROMPT},
                    ],
                }
            ],
        },
        headers={
            "Authorization": f"Bearer {ZHIPU_KEY}",
            "Content-Type": "application/json",
        },
        timeout=60,
    )
    resp.raise_for_status()
    content = resp.json()["choices"][0]["message"]["content"]

    # 从回复中提取 JSON（可能被 think/markdown 包裹）
    # 找第一个 { 和最后一个 }
    start = content.find("{")
    end = content.rfind("}") + 1
    if start >= 0 and end > start:
        try:
            return json.loads(content[start:end])
        except json.JSONDecodeError:
            pass
    return {"changes": [], "raw": content[:500]}


def apply_changes(changes: list[dict]) -> list[str]:
    """应用改动到源文件。返回日志列表。"""
    log = []
    for _i, c in enumerate(changes):
        fpath = ROOT / c["file"]
        if not fpath.exists():
            log.append(f"  ✗ {fpath}: file not found")
            continue

        source = fpath.read_text("utf-8")
        old = c["old_text"]
        if old not in source:
            log.append(f"  ✗ {c['method']}: old_text not found in file")
            continue

        # 备份
        fpath.with_suffix(".py.bak").write_text(source, "utf-8")

        new_source = source.replace(old, c["new_text"], 1)
        fpath.write_text(new_source, "utf-8")
        log.append(f"  ✓ {c['method']}: {c['issue'][:60]}")

    return log


def main():
    # 检查 API key
    if not ZHIPU_KEY:
        # 尝试从 models.json 加载
        cfg_path = ROOT / "models.json"
        if cfg_path.exists():
            with open(cfg_path) as f:
                cfg = json.load(f)
            zp = cfg.get("providers", {}).get("zhipu", {})
            os.environ["ZHIPU_API_KEY"] = zp.get("api_key", "")
        if not os.environ.get("ZHIPU_API_KEY"):
            print("ZHIPU_API_KEY not found")
            return 1

    # 确保输出目录
    out_dir = ROOT / "output" / "ui_loop"
    out_dir.mkdir(parents=True, exist_ok=True)

    iteration = 0
    max_iterations = 3
    while iteration < max_iterations:
        iteration += 1
        print(f"\n{'=' * 60}")
        print(f"ITERATION {iteration}/{max_iterations}")
        print(f"{'=' * 60}")

        # 1. 截图
        img_path = str(out_dir / f"screenshot_{iteration:02d}.png")
        print(f"Screenshot → {img_path}")
        screenshot(img_path)

        # 2. 分析
        print("Analyzing with vision model...")
        t0 = time.monotonic()
        result = analyze(img_path)
        elapsed = time.monotonic() - t0
        print(f"  done in {elapsed:.1f}s")

        changes = result.get("changes", [])
        if not changes:
            print("No changes suggested. UI looks good!")
            if "raw" in result:
                print(f"Raw response preview: {result['raw'][:200]}")
            break

        print(f"  {len(changes)} changes suggested:")
        for c in changes:
            print(f"    - {c.get('method')}: {c.get('issue', '?')[:80]}")

        # 3. 确认
        if iteration > 1:
            resp = input("\nApply changes? [Y/n] ").strip().lower()
            if resp == "n":
                break

        # 4. 应用
        print("\nApplying changes...")
        log = apply_changes(changes)
        for line in log:
            print(line)

        # 5. 语法验证
        for c in changes:
            fpath = ROOT / c["file"]
            try:
                import py_compile

                py_compile.compile(str(fpath), doraise=True)
                print(f"  ✓ {c['file']}: syntax OK")
            except py_compile.PyCompileError as e:
                print(f"  ✗ {c['file']}: SYNTAX ERROR — {e}")
                # 回滚
                bak = fpath.with_suffix(".py.bak")
                if bak.exists():
                    fpath.write_text(bak.read_text("utf-8"), "utf-8")
                    print("  → rolled back from backup")

        print(f"\nIteration {iteration} complete. Restart CRUX to see changes.")
        if iteration < max_iterations:
            input("Press Enter for next iteration...")

    print(f"\nUI loop finished after {iteration} iterations.")


if __name__ == "__main__":
    main()
