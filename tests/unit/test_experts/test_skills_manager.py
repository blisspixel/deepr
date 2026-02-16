"""Unit tests for SkillManager discovery, indexing, and activation."""

from __future__ import annotations

import logging
from pathlib import Path

import pytest
import yaml

import deepr.experts.skills.manager as manager_mod
from deepr.experts.skills.manager import SkillManager


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _create_skill_dir(
    base: Path,
    name: str,
    *,
    domains: list[str] | None = None,
    keywords: list[str] | None = None,
    patterns: list[str] | None = None,
) -> Path:
    """Write a minimal skill.yaml into *base/name* and return the directory."""
    d = base / name
    d.mkdir(parents=True, exist_ok=True)
    yaml_content = {
        "name": name,
        "version": "1.0.0",
        "description": f"Test skill {name}",
        "domains": domains or [],
        "triggers": {
            "keywords": keywords or [],
            "patterns": patterns or [],
        },
        "tools": [],
    }
    (d / "skill.yaml").write_text(yaml.dump(yaml_content))
    return d


# ---------------------------------------------------------------------------
# Initialization
# ---------------------------------------------------------------------------

class TestSkillManagerInit:
    """SkillManager.__init__ scans built-in and global dirs."""

    def test_scans_builtin_and_global(self, tmp_path, monkeypatch):
        builtin = tmp_path / "builtin"
        global_ = tmp_path / "global"
        builtin.mkdir()
        global_.mkdir()

        _create_skill_dir(builtin, "alpha")
        _create_skill_dir(global_, "beta")

        monkeypatch.setattr(manager_mod, "_BUILTIN_DIR", builtin)
        monkeypatch.setattr(manager_mod, "_USER_GLOBAL_DIR", global_)

        mgr = SkillManager()
        names = {s.name for s in mgr.list_all()}
        assert names == {"alpha", "beta"}

    def test_skips_nonexistent_dirs(self, tmp_path, monkeypatch):
        monkeypatch.setattr(manager_mod, "_BUILTIN_DIR", tmp_path / "no_such_dir")
        monkeypatch.setattr(manager_mod, "_USER_GLOBAL_DIR", tmp_path / "also_missing")

        mgr = SkillManager()
        assert mgr.list_all() == []

    def test_expert_local_tier_scanned_when_name_provided(self, tmp_path, monkeypatch):
        builtin = tmp_path / "builtin"
        global_ = tmp_path / "global"
        builtin.mkdir()
        global_.mkdir()

        monkeypatch.setattr(manager_mod, "_BUILTIN_DIR", builtin)
        monkeypatch.setattr(manager_mod, "_USER_GLOBAL_DIR", global_)

        expert_skills = tmp_path / "data" / "experts" / "mybot" / "skills"
        _create_skill_dir(expert_skills, "local-skill")

        monkeypatch.chdir(tmp_path)
        mgr = SkillManager(expert_name="mybot")
        assert mgr.get_skill("local-skill") is not None
        assert mgr.get_skill("local-skill").tier == "expert-local"

    def test_expert_name_none_skips_expert_local(self, tmp_path, monkeypatch):
        builtin = tmp_path / "builtin"
        global_ = tmp_path / "global"
        builtin.mkdir()
        global_.mkdir()

        monkeypatch.setattr(manager_mod, "_BUILTIN_DIR", builtin)
        monkeypatch.setattr(manager_mod, "_USER_GLOBAL_DIR", global_)

        mgr = SkillManager(expert_name=None)
        assert mgr.list_all() == []


# ---------------------------------------------------------------------------
# _scan_tier
# ---------------------------------------------------------------------------

class TestScanTier:
    """_scan_tier picks up valid skills and handles edge cases."""

    def test_picks_up_valid_skill(self, tmp_path, monkeypatch):
        builtin = tmp_path / "builtin"
        builtin.mkdir()
        _create_skill_dir(builtin, "valid-skill")

        monkeypatch.setattr(manager_mod, "_BUILTIN_DIR", builtin)
        monkeypatch.setattr(manager_mod, "_USER_GLOBAL_DIR", tmp_path / "empty")

        mgr = SkillManager()
        skill = mgr.get_skill("valid-skill")
        assert skill is not None
        assert skill.name == "valid-skill"
        assert skill.tier == "built-in"

    def test_skips_dirs_without_skill_yaml(self, tmp_path, monkeypatch):
        builtin = tmp_path / "builtin"
        builtin.mkdir()

        # Create a directory with no skill.yaml
        (builtin / "no-manifest").mkdir()

        # Also create a directory with a valid skill for comparison
        _create_skill_dir(builtin, "has-manifest")

        monkeypatch.setattr(manager_mod, "_BUILTIN_DIR", builtin)
        monkeypatch.setattr(manager_mod, "_USER_GLOBAL_DIR", tmp_path / "empty")

        mgr = SkillManager()
        assert mgr.get_skill("no-manifest") is None
        assert mgr.get_skill("has-manifest") is not None

    def test_skips_files_in_tier_dir(self, tmp_path, monkeypatch):
        builtin = tmp_path / "builtin"
        builtin.mkdir()
        (builtin / "README.md").write_text("not a skill dir")
        _create_skill_dir(builtin, "real-skill")

        monkeypatch.setattr(manager_mod, "_BUILTIN_DIR", builtin)
        monkeypatch.setattr(manager_mod, "_USER_GLOBAL_DIR", tmp_path / "empty")

        mgr = SkillManager()
        assert len(mgr.list_all()) == 1
        assert mgr.list_all()[0].name == "real-skill"

    def test_handles_malformed_yaml_gracefully(self, tmp_path, monkeypatch, caplog):
        builtin = tmp_path / "builtin"
        builtin.mkdir()

        bad_dir = builtin / "bad-skill"
        bad_dir.mkdir()
        (bad_dir / "skill.yaml").write_text(":::not valid yaml: [")

        monkeypatch.setattr(manager_mod, "_BUILTIN_DIR", builtin)
        monkeypatch.setattr(manager_mod, "_USER_GLOBAL_DIR", tmp_path / "empty")

        with caplog.at_level(logging.WARNING):
            mgr = SkillManager()

        assert mgr.get_skill("bad-skill") is None
        assert any("Skipping malformed skill" in msg for msg in caplog.messages)

    def test_handles_invalid_yaml_content(self, tmp_path, monkeypatch, caplog):
        """skill.yaml that is valid YAML but not a mapping should be skipped."""
        builtin = tmp_path / "builtin"
        builtin.mkdir()

        bad_dir = builtin / "list-skill"
        bad_dir.mkdir()
        (bad_dir / "skill.yaml").write_text("- item1\n- item2\n")

        monkeypatch.setattr(manager_mod, "_BUILTIN_DIR", builtin)
        monkeypatch.setattr(manager_mod, "_USER_GLOBAL_DIR", tmp_path / "empty")

        with caplog.at_level(logging.WARNING):
            mgr = SkillManager()

        assert mgr.get_skill("list-skill") is None

    def test_nonexistent_base_dir_is_noop(self, tmp_path, monkeypatch):
        monkeypatch.setattr(manager_mod, "_BUILTIN_DIR", tmp_path / "gone")
        monkeypatch.setattr(manager_mod, "_USER_GLOBAL_DIR", tmp_path / "also_gone")

        mgr = SkillManager()
        assert mgr.list_all() == []


# ---------------------------------------------------------------------------
# get_skill
# ---------------------------------------------------------------------------

class TestGetSkill:
    """get_skill returns a SkillDefinition or None."""

    def test_returns_skill_by_name(self, tmp_path, monkeypatch):
        builtin = tmp_path / "builtin"
        builtin.mkdir()
        _create_skill_dir(builtin, "my-skill", domains=["python"])

        monkeypatch.setattr(manager_mod, "_BUILTIN_DIR", builtin)
        monkeypatch.setattr(manager_mod, "_USER_GLOBAL_DIR", tmp_path / "empty")

        mgr = SkillManager()
        skill = mgr.get_skill("my-skill")
        assert skill is not None
        assert skill.name == "my-skill"
        assert skill.domains == ["python"]

    def test_returns_none_for_unknown_name(self, tmp_path, monkeypatch):
        monkeypatch.setattr(manager_mod, "_BUILTIN_DIR", tmp_path / "empty1")
        monkeypatch.setattr(manager_mod, "_USER_GLOBAL_DIR", tmp_path / "empty2")

        mgr = SkillManager()
        assert mgr.get_skill("nonexistent") is None


# ---------------------------------------------------------------------------
# list_all
# ---------------------------------------------------------------------------

class TestListAll:
    """list_all returns all discovered skills."""

    def test_returns_all_skills(self, tmp_path, monkeypatch):
        builtin = tmp_path / "builtin"
        global_ = tmp_path / "global"
        builtin.mkdir()
        global_.mkdir()

        _create_skill_dir(builtin, "skill-a")
        _create_skill_dir(builtin, "skill-b")
        _create_skill_dir(global_, "skill-c")

        monkeypatch.setattr(manager_mod, "_BUILTIN_DIR", builtin)
        monkeypatch.setattr(manager_mod, "_USER_GLOBAL_DIR", global_)

        mgr = SkillManager()
        names = {s.name for s in mgr.list_all()}
        assert names == {"skill-a", "skill-b", "skill-c"}

    def test_empty_when_no_skills(self, tmp_path, monkeypatch):
        monkeypatch.setattr(manager_mod, "_BUILTIN_DIR", tmp_path / "none1")
        monkeypatch.setattr(manager_mod, "_USER_GLOBAL_DIR", tmp_path / "none2")

        mgr = SkillManager()
        assert mgr.list_all() == []

    def test_returns_list_not_dict_values(self, tmp_path, monkeypatch):
        builtin = tmp_path / "builtin"
        builtin.mkdir()
        _create_skill_dir(builtin, "only")

        monkeypatch.setattr(manager_mod, "_BUILTIN_DIR", builtin)
        monkeypatch.setattr(manager_mod, "_USER_GLOBAL_DIR", tmp_path / "empty")

        mgr = SkillManager()
        result = mgr.list_all()
        assert isinstance(result, list)


# ---------------------------------------------------------------------------
# get_installed_skills
# ---------------------------------------------------------------------------

class TestGetInstalledSkills:
    """get_installed_skills returns matching skills, skips unknowns."""

    def test_returns_matching_skills(self, tmp_path, monkeypatch):
        builtin = tmp_path / "builtin"
        builtin.mkdir()
        _create_skill_dir(builtin, "alpha")
        _create_skill_dir(builtin, "beta")
        _create_skill_dir(builtin, "gamma")

        monkeypatch.setattr(manager_mod, "_BUILTIN_DIR", builtin)
        monkeypatch.setattr(manager_mod, "_USER_GLOBAL_DIR", tmp_path / "empty")

        mgr = SkillManager()
        result = mgr.get_installed_skills(["alpha", "gamma"])
        names = [s.name for s in result]
        assert names == ["alpha", "gamma"]

    def test_skips_unknown_names(self, tmp_path, monkeypatch):
        builtin = tmp_path / "builtin"
        builtin.mkdir()
        _create_skill_dir(builtin, "exists")

        monkeypatch.setattr(manager_mod, "_BUILTIN_DIR", builtin)
        monkeypatch.setattr(manager_mod, "_USER_GLOBAL_DIR", tmp_path / "empty")

        mgr = SkillManager()
        result = mgr.get_installed_skills(["exists", "does-not-exist"])
        assert len(result) == 1
        assert result[0].name == "exists"

    def test_empty_names_returns_empty(self, tmp_path, monkeypatch):
        builtin = tmp_path / "builtin"
        builtin.mkdir()
        _create_skill_dir(builtin, "skill")

        monkeypatch.setattr(manager_mod, "_BUILTIN_DIR", builtin)
        monkeypatch.setattr(manager_mod, "_USER_GLOBAL_DIR", tmp_path / "empty")

        mgr = SkillManager()
        assert mgr.get_installed_skills([]) == []

    def test_all_unknown_returns_empty(self, tmp_path, monkeypatch):
        monkeypatch.setattr(manager_mod, "_BUILTIN_DIR", tmp_path / "e1")
        monkeypatch.setattr(manager_mod, "_USER_GLOBAL_DIR", tmp_path / "e2")

        mgr = SkillManager()
        assert mgr.get_installed_skills(["x", "y", "z"]) == []

    def test_preserves_request_order(self, tmp_path, monkeypatch):
        builtin = tmp_path / "builtin"
        builtin.mkdir()
        _create_skill_dir(builtin, "z-skill")
        _create_skill_dir(builtin, "a-skill")
        _create_skill_dir(builtin, "m-skill")

        monkeypatch.setattr(manager_mod, "_BUILTIN_DIR", builtin)
        monkeypatch.setattr(manager_mod, "_USER_GLOBAL_DIR", tmp_path / "empty")

        mgr = SkillManager()
        result = mgr.get_installed_skills(["m-skill", "z-skill", "a-skill"])
        names = [s.name for s in result]
        assert names == ["m-skill", "z-skill", "a-skill"]


# ---------------------------------------------------------------------------
# detect_skills_for_query
# ---------------------------------------------------------------------------

class TestDetectSkillsForQuery:
    """detect_skills_for_query matches keywords from installed skills."""

    def test_matches_keyword_in_query(self, tmp_path, monkeypatch):
        builtin = tmp_path / "builtin"
        builtin.mkdir()
        _create_skill_dir(builtin, "market-data", keywords=["stock", "earnings"])
        _create_skill_dir(builtin, "weather", keywords=["forecast", "temperature"])

        monkeypatch.setattr(manager_mod, "_BUILTIN_DIR", builtin)
        monkeypatch.setattr(manager_mod, "_USER_GLOBAL_DIR", tmp_path / "empty")

        mgr = SkillManager()
        matches = mgr.detect_skills_for_query(
            "What are the latest stock earnings?",
            ["market-data", "weather"],
        )
        names = [s.name for s in matches]
        assert "market-data" in names
        assert "weather" not in names

    def test_no_match_returns_empty(self, tmp_path, monkeypatch):
        builtin = tmp_path / "builtin"
        builtin.mkdir()
        _create_skill_dir(builtin, "niche", keywords=["quantum"])

        monkeypatch.setattr(manager_mod, "_BUILTIN_DIR", builtin)
        monkeypatch.setattr(manager_mod, "_USER_GLOBAL_DIR", tmp_path / "empty")

        mgr = SkillManager()
        matches = mgr.detect_skills_for_query(
            "Tell me about cooking recipes",
            ["niche"],
        )
        assert matches == []

    def test_only_checks_installed_names(self, tmp_path, monkeypatch):
        builtin = tmp_path / "builtin"
        builtin.mkdir()
        _create_skill_dir(builtin, "installed", keywords=["hello"])
        _create_skill_dir(builtin, "not-installed", keywords=["hello"])

        monkeypatch.setattr(manager_mod, "_BUILTIN_DIR", builtin)
        monkeypatch.setattr(manager_mod, "_USER_GLOBAL_DIR", tmp_path / "empty")

        mgr = SkillManager()
        matches = mgr.detect_skills_for_query("hello world", ["installed"])
        names = [s.name for s in matches]
        assert names == ["installed"]

    def test_unknown_installed_name_is_skipped(self, tmp_path, monkeypatch):
        builtin = tmp_path / "builtin"
        builtin.mkdir()
        _create_skill_dir(builtin, "real", keywords=["test"])

        monkeypatch.setattr(manager_mod, "_BUILTIN_DIR", builtin)
        monkeypatch.setattr(manager_mod, "_USER_GLOBAL_DIR", tmp_path / "empty")

        mgr = SkillManager()
        matches = mgr.detect_skills_for_query("test query", ["real", "fake"])
        assert len(matches) == 1
        assert matches[0].name == "real"

    def test_case_insensitive_keyword_match(self, tmp_path, monkeypatch):
        builtin = tmp_path / "builtin"
        builtin.mkdir()
        _create_skill_dir(builtin, "ci-skill", keywords=["Python"])

        monkeypatch.setattr(manager_mod, "_BUILTIN_DIR", builtin)
        monkeypatch.setattr(manager_mod, "_USER_GLOBAL_DIR", tmp_path / "empty")

        mgr = SkillManager()
        matches = mgr.detect_skills_for_query("I love python", ["ci-skill"])
        assert len(matches) == 1

    def test_pattern_based_trigger(self, tmp_path, monkeypatch):
        builtin = tmp_path / "builtin"
        builtin.mkdir()
        _create_skill_dir(
            builtin, "regex-skill", keywords=[], patterns=[r"\bP/E\b"]
        )

        monkeypatch.setattr(manager_mod, "_BUILTIN_DIR", builtin)
        monkeypatch.setattr(manager_mod, "_USER_GLOBAL_DIR", tmp_path / "empty")

        mgr = SkillManager()
        matches = mgr.detect_skills_for_query(
            "What is the P/E ratio?", ["regex-skill"]
        )
        assert len(matches) == 1

    def test_empty_installed_names(self, tmp_path, monkeypatch):
        builtin = tmp_path / "builtin"
        builtin.mkdir()
        _create_skill_dir(builtin, "some-skill", keywords=["match"])

        monkeypatch.setattr(manager_mod, "_BUILTIN_DIR", builtin)
        monkeypatch.setattr(manager_mod, "_USER_GLOBAL_DIR", tmp_path / "empty")

        mgr = SkillManager()
        matches = mgr.detect_skills_for_query("match this", [])
        assert matches == []

    def test_multiple_matches(self, tmp_path, monkeypatch):
        builtin = tmp_path / "builtin"
        builtin.mkdir()
        _create_skill_dir(builtin, "skill-a", keywords=["data"])
        _create_skill_dir(builtin, "skill-b", keywords=["data"])

        monkeypatch.setattr(manager_mod, "_BUILTIN_DIR", builtin)
        monkeypatch.setattr(manager_mod, "_USER_GLOBAL_DIR", tmp_path / "empty")

        mgr = SkillManager()
        matches = mgr.detect_skills_for_query("show me data", ["skill-a", "skill-b"])
        names = {s.name for s in matches}
        assert names == {"skill-a", "skill-b"}


# ---------------------------------------------------------------------------
# suggest_skills_for_domain
# ---------------------------------------------------------------------------

class TestSuggestSkillsForDomain:
    """suggest_skills_for_domain matches domain tags bidirectionally."""

    def test_tag_in_domain(self, tmp_path, monkeypatch):
        """Skill tag 'finance' should match domain 'personal finance'."""
        builtin = tmp_path / "builtin"
        builtin.mkdir()
        _create_skill_dir(builtin, "fin-skill", domains=["finance"])

        monkeypatch.setattr(manager_mod, "_BUILTIN_DIR", builtin)
        monkeypatch.setattr(manager_mod, "_USER_GLOBAL_DIR", tmp_path / "empty")

        mgr = SkillManager()
        suggestions = mgr.suggest_skills_for_domain("personal finance")
        assert len(suggestions) == 1
        assert suggestions[0].name == "fin-skill"

    def test_domain_in_tag(self, tmp_path, monkeypatch):
        """Domain 'ml' should match skill tag 'machine learning and ml'."""
        builtin = tmp_path / "builtin"
        builtin.mkdir()
        _create_skill_dir(builtin, "ml-skill", domains=["machine learning and ml"])

        monkeypatch.setattr(manager_mod, "_BUILTIN_DIR", builtin)
        monkeypatch.setattr(manager_mod, "_USER_GLOBAL_DIR", tmp_path / "empty")

        mgr = SkillManager()
        suggestions = mgr.suggest_skills_for_domain("ml")
        assert len(suggestions) == 1
        assert suggestions[0].name == "ml-skill"

    def test_case_insensitive_match(self, tmp_path, monkeypatch):
        builtin = tmp_path / "builtin"
        builtin.mkdir()
        _create_skill_dir(builtin, "py-skill", domains=["Python"])

        monkeypatch.setattr(manager_mod, "_BUILTIN_DIR", builtin)
        monkeypatch.setattr(manager_mod, "_USER_GLOBAL_DIR", tmp_path / "empty")

        mgr = SkillManager()
        suggestions = mgr.suggest_skills_for_domain("PYTHON")
        assert len(suggestions) == 1

    def test_no_match_returns_empty(self, tmp_path, monkeypatch):
        builtin = tmp_path / "builtin"
        builtin.mkdir()
        _create_skill_dir(builtin, "unrelated", domains=["biology"])

        monkeypatch.setattr(manager_mod, "_BUILTIN_DIR", builtin)
        monkeypatch.setattr(manager_mod, "_USER_GLOBAL_DIR", tmp_path / "empty")

        mgr = SkillManager()
        suggestions = mgr.suggest_skills_for_domain("quantum computing")
        assert suggestions == []

    def test_multiple_tags_first_hit_wins(self, tmp_path, monkeypatch):
        """Skill with multiple domain tags should appear only once."""
        builtin = tmp_path / "builtin"
        builtin.mkdir()
        _create_skill_dir(builtin, "multi", domains=["data", "data science"])

        monkeypatch.setattr(manager_mod, "_BUILTIN_DIR", builtin)
        monkeypatch.setattr(manager_mod, "_USER_GLOBAL_DIR", tmp_path / "empty")

        mgr = SkillManager()
        suggestions = mgr.suggest_skills_for_domain("data science research")
        # Should contain the skill exactly once (break after first tag match)
        assert len(suggestions) == 1
        assert suggestions[0].name == "multi"

    def test_empty_domains_no_match(self, tmp_path, monkeypatch):
        builtin = tmp_path / "builtin"
        builtin.mkdir()
        _create_skill_dir(builtin, "no-domain", domains=[])

        monkeypatch.setattr(manager_mod, "_BUILTIN_DIR", builtin)
        monkeypatch.setattr(manager_mod, "_USER_GLOBAL_DIR", tmp_path / "empty")

        mgr = SkillManager()
        suggestions = mgr.suggest_skills_for_domain("anything")
        assert suggestions == []

    def test_multiple_skills_suggested(self, tmp_path, monkeypatch):
        builtin = tmp_path / "builtin"
        builtin.mkdir()
        _create_skill_dir(builtin, "skill-x", domains=["web"])
        _create_skill_dir(builtin, "skill-y", domains=["web development"])

        monkeypatch.setattr(manager_mod, "_BUILTIN_DIR", builtin)
        monkeypatch.setattr(manager_mod, "_USER_GLOBAL_DIR", tmp_path / "empty")

        mgr = SkillManager()
        suggestions = mgr.suggest_skills_for_domain("web")
        names = {s.name for s in suggestions}
        assert names == {"skill-x", "skill-y"}


# ---------------------------------------------------------------------------
# Tier override behaviour
# ---------------------------------------------------------------------------

class TestTierOverride:
    """Later tiers override earlier tiers for same-name skills."""

    def test_global_overrides_builtin(self, tmp_path, monkeypatch):
        builtin = tmp_path / "builtin"
        global_ = tmp_path / "global"
        builtin.mkdir()
        global_.mkdir()

        _create_skill_dir(builtin, "shared-name", domains=["builtin-domain"])
        _create_skill_dir(global_, "shared-name", domains=["global-domain"])

        monkeypatch.setattr(manager_mod, "_BUILTIN_DIR", builtin)
        monkeypatch.setattr(manager_mod, "_USER_GLOBAL_DIR", global_)

        mgr = SkillManager()
        skill = mgr.get_skill("shared-name")
        assert skill is not None
        assert skill.tier == "global"
        assert skill.domains == ["global-domain"]

    def test_expert_local_overrides_global(self, tmp_path, monkeypatch):
        builtin = tmp_path / "builtin"
        global_ = tmp_path / "global"
        builtin.mkdir()
        global_.mkdir()

        _create_skill_dir(global_, "shared-name", domains=["global-ver"])

        expert_skills = tmp_path / "data" / "experts" / "bot" / "skills"
        _create_skill_dir(expert_skills, "shared-name", domains=["local-ver"])

        monkeypatch.setattr(manager_mod, "_BUILTIN_DIR", builtin)
        monkeypatch.setattr(manager_mod, "_USER_GLOBAL_DIR", global_)
        monkeypatch.chdir(tmp_path)

        mgr = SkillManager(expert_name="bot")
        skill = mgr.get_skill("shared-name")
        assert skill is not None
        assert skill.tier == "expert-local"
        assert skill.domains == ["local-ver"]

    def test_override_does_not_increase_count(self, tmp_path, monkeypatch):
        """Overriding a skill keeps the total count the same."""
        builtin = tmp_path / "builtin"
        global_ = tmp_path / "global"
        builtin.mkdir()
        global_.mkdir()

        _create_skill_dir(builtin, "dup")
        _create_skill_dir(global_, "dup")

        monkeypatch.setattr(manager_mod, "_BUILTIN_DIR", builtin)
        monkeypatch.setattr(manager_mod, "_USER_GLOBAL_DIR", global_)

        mgr = SkillManager()
        assert len(mgr.list_all()) == 1

    def test_three_tier_cascade(self, tmp_path, monkeypatch):
        """Expert-local overrides global which overrides built-in."""
        builtin = tmp_path / "builtin"
        global_ = tmp_path / "global"
        builtin.mkdir()
        global_.mkdir()

        _create_skill_dir(builtin, "cascade", domains=["tier1"])
        _create_skill_dir(global_, "cascade", domains=["tier2"])

        expert_skills = tmp_path / "data" / "experts" / "e1" / "skills"
        _create_skill_dir(expert_skills, "cascade", domains=["tier3"])

        monkeypatch.setattr(manager_mod, "_BUILTIN_DIR", builtin)
        monkeypatch.setattr(manager_mod, "_USER_GLOBAL_DIR", global_)
        monkeypatch.chdir(tmp_path)

        mgr = SkillManager(expert_name="e1")
        skill = mgr.get_skill("cascade")
        assert skill.domains == ["tier3"]
        assert skill.tier == "expert-local"
        assert len(mgr.list_all()) == 1
