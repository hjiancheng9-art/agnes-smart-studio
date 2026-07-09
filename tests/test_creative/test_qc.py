"""Tests for core.creative.qc — 质量检查（离线场景）"""
from core.creative.qc import FrameQC, QCResult, VideoQC


class TestQCResult:
    def test_default_passed_false(self):
        r = QCResult()
        assert not r.passed
        assert r.score == 0
        assert r.issues == []

    def test_set_attributes(self):
        r = QCResult(passed=True, score=85, issues=["构图不佳"])
        assert r.passed
        assert r.score == 85
        assert "构图不佳" in r.issues


class TestFrameQC:
    def test_init(self):
        qc = FrameQC(threshold=60)
        assert qc.threshold == 60

    def test_default_threshold(self):
        qc = FrameQC()
        assert qc.threshold == 60

    def test_extract_score(self):
        qc = FrameQC()
        assert qc._extract_score("总分: 85") == 85
        assert qc._extract_score("总分：72") == 72
        assert qc._extract_score("no score here") == 50
        assert qc._extract_score("总分: 999") == 100  # capped

    def test_extract_issues(self):
        qc = FrameQC()
        issues = qc._extract_issues("问题: 构图有问题, 光线不足, 风格不符")
        assert len(issues) == 3
        assert "构图有问题" in issues

    def test_extract_issues_stops_at_suggestions(self):
        qc = FrameQC()
        issues = qc._extract_issues("问题: 构图, 风格 建议: 改构图")
        assert len(issues) == 2
        assert "建议: 改构图" not in issues

    def test_extract_suggestions(self):
        qc = FrameQC()
        sug = qc._extract_suggestions("建议: 优化构图, 增加光线")
        assert len(sug) == 2

    def test_scoring_threshold_pass(self, monkeypatch):
        qc = FrameQC(threshold=60)
        # Mock _analyze_frame to avoid HTTP
        monkeypatch.setattr(qc, "_analyze_frame",
                           lambda url, desc: "总分: 75\n问题: \n建议: 可以进入视频")
        r = qc.check("http://fake.url/img.png", "a cat")
        assert r.score == 75
        assert r.passed


class TestVideoQC:
    def test_check_basic(self):
        from core.creative.shot_contract import ShotContract
        vqc = VideoQC()
        c = ShotContract(num_frames=81, frame_rate=24)
        r = vqc.check("http://fake.url/vid.mp4", c)
        assert r.passed
