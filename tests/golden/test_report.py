"""Blueprint Coverage Report 测试"""
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "../.."))

from comfyflow_compiler.blueprint.report import scan_blueprints, print_report, TARGET_COVERAGE
import io


def test_report_basic():
    r = scan_blueprints()
    assert "error" not in r, str(r.get("error"))
    assert r["total_blueprints"] >= 18, f"蓝图数量不足: {r['total_blueprints']}"
    assert r["valid"] == r["total_blueprints"], f"有无效蓝图: {r['invalid']}"
    print(f"  [PASS] total={r['total_blueprints']}, valid={r['valid']}")


def test_report_by_task():
    r = scan_blueprints()
    by_task = r["by_task"]
    assert by_task.get("txt2img", 0) >= 5, f"txt2img 不足: {by_task.get('txt2img', 0)}"
    assert by_task.get("img2img", 0) >= 3, f"img2img 不足: {by_task.get('img2img', 0)}"
    assert by_task.get("i2v", 0) >= 2, f"i2v 不足: {by_task.get('i2v', 0)}"
    print(f"  [PASS] txt2img={by_task.get('txt2img')} >=5, img2img={by_task.get('img2img')} >=3, i2v={by_task.get('i2v')} >=2")


def test_report_by_origin():
    r = scan_blueprints()
    by_origin = r["by_origin"]
    total = sum(by_origin.values())
    assert total == r["total_blueprints"]
    print(f"  [PASS] origins: {by_origin}")


def test_report_printable():
    r = scan_blueprints()
    buf = io.StringIO()
    old_stdout = sys.stdout
    sys.stdout = buf
    try:
        print_report(r)
    finally:
        sys.stdout = old_stdout
    output = buf.getvalue()
    assert "Coverage Report" in output
    assert "total" in output.lower()
    print(f"  [PASS] print_report output: {len(output)} chars")


def test_no_validation_errors():
    r = scan_blueprints()
    assert len(r.get("validation_issues", [])) == 0, f"校验问题: {r.get('validation_issues')}"
    print(f"  [PASS] no validation errors")


def test_coverage_gaps_known():
    r = scan_blueprints()
    # t2v 是已知缺失，不应算作意外失败
    missing = r["coverage"]["missing_tasks"]
    if "t2v" in missing:
        from comfyflow_compiler.blueprint.report import KNOWN_GAPS
        assert "t2v" in KNOWN_GAPS, "t2v 缺失但未在 KNOWN_GAPS 中声明"
    print(f"  [PASS] known gaps documented")


if __name__ == "__main__":
    print(f"\n{'='*50}")
    print("  Coverage Report Tests")
    print(f"{'='*50}\n")

    tests = [test_report_basic, test_report_by_task, test_report_by_origin,
             test_report_printable, test_no_validation_errors, test_coverage_gaps_known]

    passed = 0
    for t in tests:
        try:
            t()
            passed += 1
            print(f"  ✅ {t.__name__}")
        except Exception as e:
            import traceback
            print(f"  ❌ {t.__name__}: {e}")
            traceback.print_exc()

    print(f"\n{'='*50}")
    print(f"  {passed}/{len(tests)} passed")
    print(f"{'='*50}")
