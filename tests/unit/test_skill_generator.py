"""Tests for skill auto-generation and efficacy scoring."""

from deepr.experts.skills.generator import (
    SkillEfficacy,
    _extract_domains,
    _extract_keywords,
    _slugify,
    generate_skill_from_report,
)


class TestSkillEfficacy:
    def test_defaults(self):
        e = SkillEfficacy(skill_name="test")
        assert e.citations_added == 0
        assert e.impact_score == 0.0
        assert e.cost_per_activation == 0.0

    def test_impact_score(self):
        e = SkillEfficacy(skill_name="test", citations_added=10, gaps_closed=2, total_cost=1.0)
        # impact = (10 + 2*5) / 1.0 = 20.0
        assert e.impact_score == 20.0

    def test_impact_score_zero_cost(self):
        e = SkillEfficacy(skill_name="test", citations_added=5, gaps_closed=1)
        assert e.impact_score == 10.0  # 5 + 1*5 = 10

    def test_cost_per_activation(self):
        e = SkillEfficacy(skill_name="test", times_activated=4, total_cost=2.0)
        assert e.cost_per_activation == 0.5

    def test_to_dict(self):
        e = SkillEfficacy(skill_name="my-skill", citations_added=3, gaps_closed=1)
        d = e.to_dict()
        assert d["skill_name"] == "my-skill"
        assert d["citations_added"] == 3
        assert d["impact_score"] == 8.0

    def test_roundtrip(self):
        original = SkillEfficacy(skill_name="rt", citations_added=5, total_cost=0.50)
        restored = SkillEfficacy.from_dict(original.to_dict())
        assert restored.skill_name == "rt"
        assert restored.citations_added == 5
        assert restored.total_cost == 0.50


class TestSlugify:
    def test_basic(self):
        assert _slugify("Azure Fabric") == "azure-fabric"

    def test_special_chars(self):
        assert _slugify("AI/ML Research!") == "aiml-research"

    def test_long_name_truncated(self):
        result = _slugify("a" * 100)
        assert len(result) <= 50


class TestExtractKeywords:
    def test_finds_frequent_words(self):
        content = "The kubernetes cluster uses kubernetes pods in kubernetes namespace"
        keywords = _extract_keywords(content)
        assert "kubernetes" in keywords

    def test_excludes_stop_words(self):
        content = "This is about that which have been will would could"
        keywords = _extract_keywords(content)
        assert "this" not in keywords
        assert "about" not in keywords


class TestExtractDomains:
    def test_from_topic(self):
        domains = _extract_domains("some content", "Cloud Security")
        assert "cloud" in domains
        assert "security" in domains

    def test_from_content_indicators(self):
        content = "Using Azure Kubernetes for machine learning model deployment"
        domains = _extract_domains(content, "ML Ops")
        assert "cloud" in domains
        assert "ai" in domains


class TestGenerateSkillFromReport:
    def test_basic_generation(self, tmp_path):
        report = tmp_path / "report.md"
        report.write_text(
            "# AI Safety Report\n\n"
            "Machine learning models require alignment techniques.\n"
            "Neural network training involves optimization.\n",
            encoding="utf-8",
        )

        skill = generate_skill_from_report("AI Safety", report)

        assert skill.name == "ai-safety"
        assert skill.version == "0.1.0"
        assert "ai" in skill.domains or "safety" in skill.domains
        assert len(skill.keywords) > 0
        assert "AI Safety" in skill.prompt_content
        assert skill.source_artifact == str(report)

    def test_skill_yaml_structure(self, tmp_path):
        report = tmp_path / "report.md"
        report.write_text("# Test\n\nContent here.", encoding="utf-8")

        skill = generate_skill_from_report("Test Topic", report)

        assert skill.skill_yaml["name"] == "test-topic"
        assert skill.skill_yaml["version"] == "0.1.0"
        assert "triggers" in skill.skill_yaml
        assert "keywords" in skill.skill_yaml["triggers"]

    def test_write_to_disk(self, tmp_path):
        report = tmp_path / "report.md"
        report.write_text("# Cloud\n\nAzure services overview.", encoding="utf-8")

        skill = generate_skill_from_report("Cloud Azure", report)
        skill_dir = skill.write_to(tmp_path / "skills")

        assert skill_dir.exists()
        assert (skill_dir / "skill.yaml").exists()
        assert (skill_dir / "prompt.md").exists()

        # Verify YAML is parseable
        import yaml

        with open(skill_dir / "skill.yaml") as f:
            data = yaml.safe_load(f)
        assert data["name"] == "cloud-azure"

    def test_prompt_truncation(self, tmp_path):
        report = tmp_path / "big.md"
        report.write_text("# Big\n\n" + "x" * 20000, encoding="utf-8")

        skill = generate_skill_from_report("Big Report", report)
        assert len(skill.prompt_content) < 15000
        assert "truncated" in skill.prompt_content
