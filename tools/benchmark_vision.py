"""视觉模型 A/B 对比测试：智谱 GLM-4V-Flash vs Agnes-2.0-Flash。

测试维度：识别准确度、中文理解、UI 分析、代码阅读、速度、输出详细度。
"""

from __future__ import annotations

import base64
import json
import os
import time
from dataclasses import dataclass, field
from pathlib import Path

import httpx

# ── 配置 ──────────────────────────────────────

ROOT = Path(__file__).resolve().parent.parent
OUTPUT = ROOT / "output" / "vision_benchmark"
OUTPUT.mkdir(parents=True, exist_ok=True)

ZHIPU_API = "https://open.bigmodel.cn/api/paas/v4/chat/completions"
ZHIPU_MODEL = "glm-4v-flash"
ZHIPU_KEY = os.environ.get("ZHIPU_API_KEY", os.environ.get("GLM_API_KEY", ""))

AGNES_API = "https://apihub.agnes-ai.com/v1/chat/completions"
AGNES_MODEL = "agnes-2.0-flash"
AGNES_KEY = os.environ.get("AGNES_API_KEY", os.environ.get("CRUX_API_KEY", ""))

TEST_PROMPTS = {
    "text_extraction": "Read ALL text visible in this image. List every word you see, exactly as written. Be exhaustive.",
    "ui_analysis": "Describe this UI screenshot in detail: layout structure, colors, text content, visual hierarchy. What is good and what is bad about the design?",
    "code_reading": "If this image contains code, reproduce it EXACTLY. If not, describe what you see.",
    "chinese_ocr": "提取图片中的所有中文文字，保持原样输出。不要翻译，不要总结。",
    "detail_level": "Describe this image in maximum detail. Note colors, positions, sizes, text, fonts, spacing, every element. Be extremely thorough.",
}


@dataclass
class TestResult:
    model: str
    test: str
    latency_ms: float = 0
    output_len: int = 0
    output: str = ""
    error: str = ""
    tokens_per_sec: float = 0

    @property
    def ok(self) -> bool:
        return self.error == "" and self.output_len > 0


@dataclass
class Benchmark:
    results: list[TestResult] = field(default_factory=list)

    def call_vision(
        self, api_url: str, model: str, api_key: str, image_path: str, prompt: str, max_tokens: int = 1000
    ) -> TestResult:
        """调用视觉模型 API。"""
        t0 = time.monotonic()
        try:
            # 读取并编码图片
            with open(image_path, "rb") as f:
                img_data = base64.b64encode(f.read()).decode("utf-8")

            ext = Path(image_path).suffix.lower()
            mime_map = {
                ".png": "image/png",
                ".jpg": "image/jpeg",
                ".jpeg": "image/jpeg",
                ".webp": "image/webp",
                ".gif": "image/gif",
            }
            mime = mime_map.get(ext, "image/png")

            payload = {
                "model": model,
                "messages": [
                    {
                        "role": "user",
                        "content": [
                            {"type": "image_url", "image_url": {"url": f"data:{mime};base64,{img_data}"}},
                            {"type": "text", "text": prompt},
                        ],
                    }
                ],
                "max_tokens": max_tokens,
                "temperature": 0.1,
            }

            headers = {"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"}

            with httpx.Client(timeout=60) as client:
                resp = client.post(api_url, json=payload, headers=headers)
                resp.raise_for_status()
                data = resp.json()

            content = data["choices"][0]["message"].get("content", "")
            latency = (time.monotonic() - t0) * 1000
            tokens = data.get("usage", {}).get("completion_tokens", len(content))
            tps = tokens / (latency / 1000) if latency > 0 else 0

            return TestResult(
                model=model,
                test="",
                latency_ms=latency,
                output_len=len(content),
                output=content,
                tokens_per_sec=tps,
            )
        except Exception as e:
            return TestResult(
                model=model,
                test="",
                latency_ms=(time.monotonic() - t0) * 1000,
                error=f"{type(e).__name__}: {e}",
            )

    def run(self, image_path: str, tests: list[str] | None = None):
        """对一张图片跑所有测试维度。"""
        tests = tests or list(TEST_PROMPTS.keys())
        print(f"\n{'=' * 60}")
        print(f"Testing: {Path(image_path).name}")
        print(f"{'=' * 60}")

        for test_name in tests:
            prompt = TEST_PROMPTS[test_name]
            print(f"\n  [{test_name}]")

            # 智谱
            if ZHIPU_KEY:
                r = self.call_vision(ZHIPU_API, ZHIPU_MODEL, ZHIPU_KEY, image_path, prompt)
                r.test = test_name
                self.results.append(r)
                status = f"✓ {r.output_len}chars, {r.latency_ms:.0f}ms" if r.ok else f"✗ {r.error[:60]}"
                print(f"    Zhipu({ZHIPU_MODEL}): {status}")
            else:
                print("    Zhipu: SKIP (no ZHIPU_API_KEY)")

            # Agnes
            if AGNES_KEY:
                r = self.call_vision(AGNES_API, AGNES_MODEL, AGNES_KEY, image_path, prompt)
                r.test = test_name
                self.results.append(r)
                status = f"✓ {r.output_len}chars, {r.latency_ms:.0f}ms" if r.ok else f"✗ {r.error[:60]}"
                print(f"    Agnes({AGNES_MODEL}): {status}")
            else:
                print("    Agnes: SKIP (no AGNES_API_KEY)")

    def report(self) -> str:
        """生成对比报告。"""
        lines = []
        lines.append("\n" + "=" * 70)
        lines.append("视觉模型 A/B 对比报告")
        lines.append("=" * 70)

        # 按模型分组
        zhipu = [r for r in self.results if "glm" in r.model.lower()]
        agnes = [r for r in self.results if "agnes" in r.model.lower()]

        if not zhipu and not agnes:
            lines.append("\nNo results — both APIs unavailable.")
            return "\n".join(lines)

        # 汇总统计
        for name, results in [("智谱 GLM-4V-Flash", zhipu), ("Agnes-2.0-Flash", agnes)]:
            if not results:
                continue
            ok = [r for r in results if r.ok]
            ok_count = len(ok)
            total = len(results)
            avg_lat = sum(r.latency_ms for r in ok) / max(ok_count, 1)
            avg_len = sum(r.output_len for r in ok) / max(ok_count, 1)
            avg_tps = sum(r.tokens_per_sec for r in ok) / max(ok_count, 1)

            lines.append(f"\n## {name}")
            lines.append(f"  成功率: {ok_count}/{total}")
            lines.append(f"  平均延迟: {avg_lat:.0f}ms")
            lines.append(f"  平均输出: {avg_len} chars")
            lines.append(f"  平均速度: {avg_tps:.1f} tok/s")

        # 逐项对比
        lines.append("\n## 逐项对比")
        lines.append(f"{'测试':<20s} {'智谱':>8s} {'Agnes':>8s} {'胜出':>8s}")
        lines.append("-" * 48)
        for test_name in TEST_PROMPTS:
            zr = [r for r in zhipu if r.test == test_name and r.ok]
            ar = [r for r in agnes if r.test == test_name and r.ok]
            z_ok = len(zr) > 0
            a_ok = len(ar) > 0
            if not z_ok and not a_ok:
                winner = "—"
                z_str = "FAIL"
                a_str = "FAIL"
            elif not z_ok:
                winner = "Agnes"
                z_str = "FAIL"
                a_str = f"{ar[0].latency_ms:.0f}ms"
            elif not a_ok:
                winner = "Zhipu"
                z_str = f"{zr[0].latency_ms:.0f}ms"
                a_str = "FAIL"
            else:
                # 综合评分：输出详细度 60% + 速度 40%
                z_score = zr[0].output_len * 0.6 + (1 / max(zr[0].latency_ms, 1)) * 1000 * 0.4
                a_score = ar[0].output_len * 0.6 + (1 / max(ar[0].latency_ms, 1)) * 1000 * 0.4
                winner = "Zhipu" if z_score > a_score else "Agnes"
                z_str = f"{zr[0].latency_ms:.0f}ms"
                a_str = f"{ar[0].latency_ms:.0f}ms"
            lines.append(f"{test_name:<20s} {z_str:>8s} {a_str:>8s} {winner:>8s}")

        # 总体建议
        lines.append("\n## 建议")
        if zhipu and agnes:
            z_ok = sum(1 for r in zhipu if r.ok)
            a_ok = sum(1 for r in agnes if r.ok)
            if z_ok > a_ok:
                lines.append("  → 智谱稳定性更好，建议作为主力")
            elif a_ok > z_ok:
                lines.append("  → Agnes 稳定性更好，建议作为主力")
            else:
                z_avg = sum(r.latency_ms for r in zhipu if r.ok) / max(z_ok, 1)
                a_avg = sum(r.latency_ms for r in agnes if r.ok) / max(a_ok, 1)
                if z_avg < a_avg:
                    lines.append(f"  → 智谱更快 ({z_avg:.0f}ms vs {a_avg:.0f}ms)，建议主力智谱")
                else:
                    lines.append(f"  → Agnes 更快 ({a_avg:.0f}ms vs {z_avg:.0f}ms)，建议主力 Agnes")
            lines.append("  → 编排策略：先用主力，超时/失败时 fallback 到备用")
        elif zhipu:
            lines.append("  → 只有智谱可用，直接用它")
        elif agnes:
            lines.append("  → 只有 Agnes 可用，直接用它")
        else:
            lines.append("  → 两个都不可用，检查 API key")

        lines.append("=" * 70)
        return "\n".join(lines)

    def save(self):
        """保存完整结果到 JSON。"""
        data = {
            "results": [
                {
                    "model": r.model,
                    "test": r.test,
                    "latency_ms": r.latency_ms,
                    "output_len": r.output_len,
                    "output": r.output[:500],
                    "error": r.error,
                }
                for r in self.results
            ],
            "report": self.report(),
        }
        path = OUTPUT / f"benchmark_{time.strftime('%Y%m%d_%H%M%S')}.json"
        path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
        return path


def find_test_images() -> list[str]:
    """查找可用于测试的本地图片。"""
    candidates = []
    dirs = [
        ROOT / "output",
        ROOT / "tests" / "manual",
        Path.home() / "Desktop",
    ]
    for d in dirs:
        if d.exists():
            for ext in (".png", ".jpg", ".jpeg"):
                for p in sorted(d.glob(f"*{ext}"))[:3]:
                    if p.stat().st_size < 5 * 1024 * 1024:  # < 5MB
                        candidates.append(str(p))
    return candidates[:3]  # 最多 3 张


def main():
    print("视觉模型 A/B 对比测试")
    print(f"Zhipu key: {'set' if ZHIPU_KEY else 'MISSING — set ZHIPU_API_KEY'}")
    print(f"Agnes key: {'set' if AGNES_KEY else 'MISSING — set AGNES_API_KEY'}")

    images = find_test_images()
    if not images:
        print("\nNo test images found. Place .png/.jpg files in output/ or Desktop/")
        return

    print(f"\nTest images: {len(images)}")
    for img in images:
        print(f"  {Path(img).name}")

    benchmark = Benchmark()
    for img in images:
        benchmark.run(img)

    report = benchmark.report()
    print(report)

    path = benchmark.save()
    print(f"\nDetailed results saved to: {path}")


if __name__ == "__main__":
    main()
