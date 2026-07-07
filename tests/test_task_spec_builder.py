"""Tests for TaskSpecBuilder — 任务意图结构化解析器"""

from core.task_spec_builder import (
    AssetType,
    IntentType,
    RiskLevel,
    TaskSpecBuilder,
)

builder = TaskSpecBuilder()


class TestIntentClassification:
    def test_generate_intent(self):
        spec = builder.build("生成一张赛博朋克风格的图片")
        assert spec.intent_type == IntentType.GENERATE

    def test_analyze_intent(self):
        spec = builder.build("分析这个项目的代码质量")
        assert spec.intent_type == IntentType.ANALYZE

    def test_modify_intent(self):
        spec = builder.build("修改配置文件中的端口号")
        assert spec.intent_type == IntentType.MODIFY

    def test_search_intent(self):
        spec = builder.build("搜索代码中的SQL注入漏洞")
        assert spec.intent_type == IntentType.SEARCH

    def test_execute_intent(self):
        spec = builder.build("运行测试套件")
        assert spec.intent_type == IntentType.EXECUTE

    def test_review_intent(self):
        spec = builder.build("审计整个项目的安全性")
        assert spec.intent_type == IntentType.REVIEW

    def test_diagnose_intent(self):
        spec = builder.build("为什么启动报错？帮我诊断")
        assert spec.intent_type == IntentType.DIAGNOSE

    def test_deploy_intent(self):
        spec = builder.build("部署到生产环境")
        assert spec.intent_type == IntentType.DEPLOY

    def test_diagnose_takes_priority_over_analyze(self):
        """诊断类关键词应优先于分析"""
        spec = builder.build("为什么报错了，帮我分析一下")
        assert spec.intent_type == IntentType.DIAGNOSE

    def test_default_to_analyze(self):
        spec = builder.build("hello world")
        assert spec.intent_type == IntentType.ANALYZE


class TestRiskAssessment:
    def test_low_risk_by_default(self):
        spec = builder.build("帮我看看这段代码")
        assert spec.risk == RiskLevel.LOW

    def test_medium_risk_on_delete(self):
        spec = builder.build("删除临时文件")
        assert spec.risk == RiskLevel.MEDIUM

    def test_high_risk_on_destructive_combo(self):
        spec = builder.build("删除所有的临时文件并清空缓存")
        assert spec.risk == RiskLevel.HIGH

    def test_critical_risk_on_production(self):
        spec = builder.build("部署到生产环境")
        assert spec.risk == RiskLevel.CRITICAL

    def test_critical_risk_on_prod_keyword(self):
        spec = builder.build("上线到prod")
        assert spec.risk == RiskLevel.CRITICAL


class TestOutputInference:
    def test_image_output(self):
        spec = builder.build("生成一张图片")
        assert spec.output_type == "image"

    def test_video_output(self):
        spec = builder.build("创建一个视频动画")
        assert spec.output_type == "video"

    def test_code_output(self):
        spec = builder.build("生成代码实现")
        assert spec.output_type == "code"

    def test_report_output(self):
        spec = builder.build("写一份分析报告")
        assert spec.output_type == "report"

    def test_default_text_output(self):
        spec = builder.build("随便聊聊")
        assert spec.output_type == "text"


class TestCategorySuggestion:
    def test_generate_image_to_creative(self):
        spec = builder.build("生成一张图片")
        assert spec.suggested_category == "creative"

    def test_generate_video_to_creative(self):
        spec = builder.build("生成一段视频")
        assert spec.suggested_category == "creative"

    def test_modify_to_code(self):
        spec = builder.build("修改代码文件")
        assert spec.suggested_category == "code"

    def test_search_to_web(self):
        spec = builder.build("搜索Python代码")
        assert spec.suggested_category == "web"

    def test_execute_to_infra(self):
        spec = builder.build("运行编译")
        assert spec.suggested_category == "infra"

    def test_deploy_to_infra(self):
        spec = builder.build("部署上线")
        assert spec.suggested_category == "infra"


class TestComplexityEstimation:
    def test_simple_tasks_score_low(self):
        spec = builder.build("hello")
        assert spec.complexity <= 2

    def test_long_tasks_score_higher(self):
        long_prompt = "第一步分析代码结构，然后检查依赖关系，接着修改配置文件，同时更新测试用例，" * 10
        spec = builder.build(long_prompt)
        assert spec.complexity >= 3

    def test_chain_keywords_increase_complexity(self):
        spec = builder.build("先搜索代码，然后修改配置文件，接着运行测试并且部署")
        assert spec.complexity >= 3

    def test_context_failures_increase_complexity(self):
        spec = builder.build("改个变量名", {"recent_failures": 3, "files_touched": 4})
        assert spec.complexity >= 4


class TestAssetExtraction:
    def test_file_path_extraction(self):
        spec = builder.build("读取文件 config.json 的内容")
        assets = spec.input_assets
        assert len(assets) >= 1

    def test_image_file_detection(self):
        spec = builder.build("处理 image.png 文件")
        assets = [a for a in spec.input_assets if a.type == AssetType.IMAGE]
        assert len(assets) >= 1

    def test_no_assets_by_default(self):
        spec = builder.build("随便聊聊")
        assert len(spec.input_assets) == 0


class TestMultiAgentTrigger:
    def test_simple_tasks_not_multi_agent(self):
        spec = builder.build("hello world")
        assert spec.requires_multi_agent is False

    def test_complex_tasks_trigger_multi_agent(self):
        spec = builder.build("重构支付模块并跨文件迁移数据库架构")
        assert spec.requires_multi_agent is True


class TestApprovalRequirement:
    def test_deploy_requires_approval(self):
        spec = builder.build("部署到生产环境")
        assert spec.requires_approval is True

    def test_high_risk_requires_approval(self):
        spec = builder.build("删除所有的文件并清空缓存")
        assert spec.requires_approval is True

    def test_normal_tasks_no_approval(self):
        spec = builder.build("hello world")
        assert spec.requires_approval is False


class TestConstraints:
    def test_read_only_constraint(self):
        spec = builder.build("只读查看文件")
        assert "read_only" in spec.constraints

    def test_confirm_before_execute(self):
        spec = builder.build("修改文件，先确认")
        assert "confirm_before_execute" in spec.constraints

    def test_no_constraints_default(self):
        spec = builder.build("hello")
        assert spec.constraints == []


class TestTaskSpecProperties:
    def test_summary_format(self):
        spec = builder.build("生成图片", {})
        assert spec.intent in spec.summary

    def test_estimated_tools_calculation(self):
        spec = builder.build("简单任务")
        assert spec.estimated_tools >= 1
