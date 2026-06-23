"""Tests for the per-(expert, verb) overlap guard and startup jitter."""

from __future__ import annotations

import pytest

from deepr.experts.loop_lock import (
    apply_startup_jitter,
    expert_verb_lock,
    startup_jitter_seconds,
)


class TestExpertVerbLock:
    def test_acquires_when_free(self, tmp_path):
        with expert_verb_lock("Expert A", "sync", lock_dir=tmp_path) as acquired:
            assert acquired is True

    def test_second_holder_is_told_to_skip(self, tmp_path):
        with expert_verb_lock("Expert A", "sync", lock_dir=tmp_path) as first:
            assert first is True
            with expert_verb_lock("Expert A", "sync", lock_dir=tmp_path) as second:
                assert second is False  # never blocks, never raises

    def test_lock_is_released_after_the_block(self, tmp_path):
        with expert_verb_lock("Expert A", "sync", lock_dir=tmp_path) as acquired:
            assert acquired is True
        # The next run can take it again.
        with expert_verb_lock("Expert A", "sync", lock_dir=tmp_path) as again:
            assert again is True

    def test_lock_is_released_even_on_exception(self, tmp_path):
        with pytest.raises(RuntimeError):
            with expert_verb_lock("Expert A", "sync", lock_dir=tmp_path) as acquired:
                assert acquired is True
                raise RuntimeError("verb blew up")
        with expert_verb_lock("Expert A", "sync", lock_dir=tmp_path) as again:
            assert again is True  # a crash frees the lock for the next run

    def test_different_verbs_do_not_contend(self, tmp_path):
        with expert_verb_lock("Expert A", "sync", lock_dir=tmp_path) as sync_lock:
            assert sync_lock is True
            with expert_verb_lock("Expert A", "health-check", lock_dir=tmp_path) as health_lock:
                assert health_lock is True

    def test_different_experts_do_not_contend(self, tmp_path):
        with expert_verb_lock("Expert A", "sync", lock_dir=tmp_path) as a_lock:
            assert a_lock is True
            with expert_verb_lock("Expert B", "sync", lock_dir=tmp_path) as b_lock:
                assert b_lock is True

    def test_verb_name_is_slugged_into_one_lock_file(self, tmp_path):
        # "health-check" and "health check" normalize to the same lock, so a
        # spelling variant can't bypass the guard.
        with expert_verb_lock("Expert A", "health check", lock_dir=tmp_path):
            assert (tmp_path / "expert-a__health-check.lock").exists()
            with expert_verb_lock("Expert A", "health-check", lock_dir=tmp_path) as second:
                assert second is False


class TestStartupJitter:
    def test_is_deterministic_per_expert(self):
        assert startup_jitter_seconds("Expert A", 60) == startup_jitter_seconds("Expert A", 60)

    def test_is_bounded(self):
        for name in ("Expert A", "Expert B", "AI Policy Expert", "z" * 200):
            delay = startup_jitter_seconds(name, 60)
            assert 0.0 <= delay < 60.0

    def test_zero_or_negative_max_means_no_jitter(self):
        assert startup_jitter_seconds("Expert A", 0) == 0.0
        assert startup_jitter_seconds("Expert A", -5) == 0.0

    def test_different_experts_generally_get_different_slots(self):
        slots = {startup_jitter_seconds(f"Expert {i}", 600) for i in range(50)}
        # No hard guarantee, but SHA-256 over distinct names should not collide
        # across 50 experts into a tiny set.
        assert len(slots) >= 45

    def test_apply_sleeps_for_the_delay_and_returns_it(self):
        slept: list[float] = []
        delay = apply_startup_jitter("Expert A", 60, sleep=slept.append)
        assert delay == startup_jitter_seconds("Expert A", 60)
        assert slept == [delay]

    def test_apply_does_not_sleep_when_disabled(self):
        slept: list[float] = []
        delay = apply_startup_jitter("Expert A", 0, sleep=slept.append)
        assert delay == 0.0
        assert slept == []
