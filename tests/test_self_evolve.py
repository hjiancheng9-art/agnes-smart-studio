"""Tests for core/self_evolve.py — autonomous improvement engine."""

from core.self_evolve import SelfEvolver, Weakness, EvolutionReport, evolve


class TestWeakness:
    def test_creation(self):
        w = Weakness(
            severity="high",
            category="agent",
            location="agents/test.agent.md",
            description="test weakness",
            suggestion="fix it",
            auto_fixable=True,
            fix_template="test_template",
        )
        assert w.severity == "high"
        assert w.category == "agent"
        assert w.auto_fixable
        assert w.fix_template == "test_template"

    def test_severity_levels(self):
        for sev in ("critical", "high", "medium", "low"):
            w = Weakness(sev, "test", "loc", "desc", "sugg")
            assert w.severity == sev


class TestEvolutionReport:
    def test_empty_report(self):
        r = EvolutionReport()
        assert len(r.weaknesses) == 0
        assert r.fixes_applied == 0
        assert r.fixes_failed == 0
        assert len(r.needs_human) == 0


class TestSelfEvolverScanners:
    def setup_method(self):
        self.evo = SelfEvolver()

    def test_scan_agent_thin_prompts(self):
        weaknesses = self.evo.scan_agent_thin_prompts()
        assert isinstance(weaknesses, list)
        for w in weaknesses:
            assert w.category == "agent"
            assert "thin" in w.description.lower() or "500" in w.description

    def test_scan_skill_stubs(self):
        weaknesses = self.evo.scan_skill_stubs()
        assert isinstance(weaknesses, list)
        for w in weaknesses:
            assert w.category == "skill"

    def test_scan_auto_trigger_gaps(self):
        weaknesses = self.evo.scan_auto_trigger_gaps()
        assert isinstance(weaknesses, list)
        for w in weaknesses:
            assert w.category == "skill"

    def test_scan_disallowed_tools(self):
        weaknesses = self.evo.scan_disallowed_tools_gaps()
        assert isinstance(weaknesses, list)
        for w in weaknesses:
            assert w.category == "agent"
            assert "disallowedTools" in w.description.lower()

    def test_scan_monolingual(self):
        weaknesses = self.evo.scan_monolingual_descriptions()
        assert isinstance(weaknesses, list)

    def test_scan_missing_tests(self):
        weaknesses = self.evo.scan_missing_tests()
        assert isinstance(weaknesses, list)

    def test_scan_all_returns_list(self):
        all_w = self.evo.scan_all()
        assert isinstance(all_w, list)
        # Report should be populated
        assert len(self.evo.report.weaknesses) == len(all_w)

    def test_generate_report(self):
        self.evo.scan_all()
        report = self.evo.generate_report()
        assert "Self-Evolution Report" in report
        assert "Weaknesses" in report
        assert "Summary" in report

    def test_devops_and_git_workflow_skipped_in_disallowed(self):
        """DevOps-Deployer and Git-Workflow legitimately need full access."""
        weaknesses = self.evo.scan_disallowed_tools_gaps()
        names = [w.location for w in weaknesses]
        for name in names:
            assert "DevOps-Deployer" not in name
            assert "Git-Workflow" not in name


class TestEvolveAPI:
    def test_evolve_returns_dict(self):
        result = evolve(fix=False)
        assert isinstance(result, dict)
        assert "weaknesses" in result
        assert "by_severity" in result
        assert "auto_fixable" in result
        assert "report" in result
        assert "needs_human" in result

    def test_evolve_report_is_string(self):
        result = evolve(fix=False)
        assert isinstance(result["report"], str)
        assert len(result["report"]) > 0

    def test_evolve_severity_counts(self):
        result = evolve(fix=False)
        sev = result["by_severity"]
        total = sev["critical"] + sev["high"] + sev["medium"] + sev["low"]
        assert total == result["weaknesses"]


class TestSelfEvolverEdgeCases:
    def test_empty_scan_all_does_not_crash(self):
        evo = SelfEvolver()
        all_w = evo.scan_all()
        assert isinstance(all_w, list)

    def test_apply_fixes_no_crash(self):
        evo = SelfEvolver()
        evo.scan_all()
        report = evo.apply_fixes()
        assert isinstance(report, EvolutionReport)
