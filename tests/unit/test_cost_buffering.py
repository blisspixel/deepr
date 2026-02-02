"""
Property-based tests for Cost Dashboard Write Batching.

Tests the cost buffer flush triggers and retention behavior:
- Property 7: Cost Buffer Flush Triggers
- Property 8: Cost Buffer Retention on Failure

Feature: code-quality-security-hardening
Properties: 7 (Flush Triggers), 8 (Retention on Failure)
**Validates: Requirements 7.2, 7.3, 7.6**
"""

import pytest
import tempfile
import threading
import time
from datetime import datetime, timedelta
from pathlib import Path
from unittest.mock import patch, MagicMock

from hypothesis import given, strategies as st, settings, assume, HealthCheck

from deepr.observability.costs import (
    BufferedCostDashboard,
    CostDashboard,
    CostEntry,
    COST_BUFFER_SIZE,
    COST_FLUSH_INTERVAL,
)


# =============================================================================
# Test Strategies
# =============================================================================

# Strategy for generating operation names
operation_names = st.sampled_from([
    "research", "chat", "synthesis", "fact_check", "summarize", "translate"
])

# Strategy for generating provider names
provider_names = st.sampled_from([
    "openai", "anthropic", "xai", "azure", "gemini", "cohere", "mistral"
])

# Strategy for generating model names
model_names = st.sampled_from([
    "gpt-4o", "gpt-4o-mini", "claude-3-5-sonnet", "grok-4-fast",
    "gemini-pro", "command-r", "mistral-large", ""
])

# Strategy for generating costs (non-negative)
costs = st.floats(min_value=0.0, max_value=10.0, allow_nan=False, allow_infinity=False)

# Strategy for generating token counts
token_counts = st.integers(min_value=0, max_value=100000)

# Strategy for generating buffer sizes
buffer_sizes = st.integers(min_value=1, max_value=50)

# Strategy for generating flush intervals (in seconds)
flush_intervals = st.integers(min_value=1, max_value=120)

# Strategy for generating number of entries to record
entry_counts = st.integers(min_value=1, max_value=100)


# =============================================================================
# Unit Tests for BufferedCostDashboard
# =============================================================================

@pytest.mark.unit
class TestBufferedCostDashboardBasics:
    """Basic unit tests for BufferedCostDashboard."""
    
    @pytest.fixture
    def temp_storage(self):
        """Create temporary storage path for tests."""
        with tempfile.TemporaryDirectory() as tmpdir:
            yield Path(tmpdir) / "costs.json"
    
    def test_initial_state(self, temp_storage):
        """New buffered dashboard should have empty buffer."""
        dashboard = BufferedCostDashboard(storage_path=temp_storage)
        
        assert dashboard.buffer_count == 0
        assert dashboard.buffer_size == COST_BUFFER_SIZE
        assert dashboard.flush_interval == COST_FLUSH_INTERVAL
        assert len(dashboard.entries) == 0
    
    def test_custom_buffer_settings(self, temp_storage):
        """Dashboard should accept custom buffer settings."""
        dashboard = BufferedCostDashboard(
            storage_path=temp_storage,
            buffer_size=20,
            flush_interval=60
        )
        
        assert dashboard.buffer_size == 20
        assert dashboard.flush_interval == 60
    
    def test_record_adds_to_buffer(self, temp_storage):
        """Recording should add entry to buffer."""
        dashboard = BufferedCostDashboard(
            storage_path=temp_storage,
            buffer_size=100  # Large buffer to prevent auto-flush
        )
        
        dashboard.record("research", "openai", 0.15)
        
        assert dashboard.buffer_count == 1
        assert len(dashboard.entries) == 1
    
    def test_record_returns_entry(self, temp_storage):
        """Recording should return the created entry."""
        dashboard = BufferedCostDashboard(
            storage_path=temp_storage,
            buffer_size=100
        )
        
        entry = dashboard.record(
            operation="research",
            provider="openai",
            cost=0.15,
            model="gpt-4o",
            tokens_input=500,
            tokens_output=1000
        )
        
        assert entry.operation == "research"
        assert entry.provider == "openai"
        assert entry.cost == 0.15
        assert entry.model == "gpt-4o"
    
    def test_negative_cost_clamped_to_zero(self, temp_storage):
        """Negative costs should be clamped to zero."""
        dashboard = BufferedCostDashboard(
            storage_path=temp_storage,
            buffer_size=100
        )
        
        entry = dashboard.record("research", "openai", -5.0)
        
        assert entry.cost == 0.0
    
    def test_explicit_flush(self, temp_storage):
        """Explicit flush should persist buffer and clear it."""
        dashboard = BufferedCostDashboard(
            storage_path=temp_storage,
            buffer_size=100  # Large buffer to prevent auto-flush
        )
        
        dashboard.record("research", "openai", 0.15)
        dashboard.record("chat", "anthropic", 0.10)
        
        assert dashboard.buffer_count == 2
        
        result = dashboard.flush()
        
        assert result is True
        assert dashboard.buffer_count == 0
        assert len(dashboard.entries) == 2  # Entries still in memory
    
    def test_flush_empty_buffer_succeeds(self, temp_storage):
        """Flushing empty buffer should succeed."""
        dashboard = BufferedCostDashboard(storage_path=temp_storage)
        
        result = dashboard.flush()
        
        assert result is True
    
    def test_time_until_flush(self, temp_storage):
        """time_until_flush should report remaining time."""
        dashboard = BufferedCostDashboard(
            storage_path=temp_storage,
            flush_interval=30
        )
        
        # Initially should be close to flush_interval
        remaining = dashboard.time_until_flush
        assert 0 <= remaining <= 30


# =============================================================================
# Property 7: Cost Buffer Flush Triggers
# =============================================================================

@pytest.mark.unit
class TestCostBufferFlushTriggersProperty:
    """Property 7: Cost Buffer Flush Triggers
    
    For any sequence of cost entries, the buffer SHALL be flushed when either:
    - Buffer size exceeds the configured threshold, OR
    - Time since last flush exceeds the configured interval
    
    Feature: code-quality-security-hardening, Property 7: Flush Triggers
    **Validates: Requirements 7.2, 7.3**
    """
    
    @pytest.fixture
    def temp_storage(self):
        """Create temporary storage path for tests."""
        with tempfile.TemporaryDirectory() as tmpdir:
            yield Path(tmpdir) / "costs.json"
    
    @given(
        buffer_size=buffer_sizes,
        num_entries=entry_counts
    )
    @settings(max_examples=30, deadline=None, suppress_health_check=[HealthCheck.too_slow])
    def test_buffer_flushes_at_size_threshold(self, buffer_size, num_entries):
        """Buffer should flush when size reaches threshold.
        
        **Validates: Requirements 7.2**
        """
        with tempfile.TemporaryDirectory() as tmpdir:
            storage_path = Path(tmpdir) / "costs.json"
            
            dashboard = BufferedCostDashboard(
                storage_path=storage_path,
                buffer_size=buffer_size,
                flush_interval=3600  # Long interval to test size trigger only
            )
            
            # Track flush calls
            flush_count = 0
            original_save = dashboard._save
            
            def counting_save():
                nonlocal flush_count
                flush_count += 1
                original_save()
            
            dashboard._save = counting_save
            
            # Record entries
            for i in range(num_entries):
                dashboard.record("research", "openai", 0.01)
            
            # Buffer should never exceed buffer_size
            # (it gets flushed when it reaches the threshold)
            assert dashboard.buffer_count < buffer_size or dashboard.buffer_count == 0
            
            # Number of flushes should be at least floor(num_entries / buffer_size)
            expected_min_flushes = num_entries // buffer_size
            assert flush_count >= expected_min_flushes, \
                f"Expected at least {expected_min_flushes} flushes, got {flush_count}"
    
    @given(
        buffer_size=buffer_sizes,
        operation=operation_names,
        provider=provider_names,
        cost=costs
    )
    @settings(max_examples=100, suppress_health_check=[HealthCheck.too_slow])
    def test_buffer_size_never_exceeds_threshold(self, buffer_size, operation, provider, cost):
        """Buffer size should never exceed the configured threshold.
        
        **Validates: Requirements 7.2**
        """
        with tempfile.TemporaryDirectory() as tmpdir:
            storage_path = Path(tmpdir) / "costs.json"
            
            dashboard = BufferedCostDashboard(
                storage_path=storage_path,
                buffer_size=buffer_size,
                flush_interval=3600  # Long interval
            )
            
            # Record exactly buffer_size entries
            for _ in range(buffer_size):
                dashboard.record(operation, provider, cost)
            
            # Buffer should have been flushed
            assert dashboard.buffer_count == 0, \
                f"Buffer should be empty after {buffer_size} entries, got {dashboard.buffer_count}"
    
    @given(
        flush_interval=st.integers(min_value=1, max_value=5)
    )
    @settings(max_examples=10, suppress_health_check=[HealthCheck.too_slow], deadline=None)
    def test_buffer_flushes_at_time_interval(self, flush_interval):
        """Buffer should flush when time interval is exceeded.
        
        **Validates: Requirements 7.3**
        """
        with tempfile.TemporaryDirectory() as tmpdir:
            storage_path = Path(tmpdir) / "costs.json"
            
            dashboard = BufferedCostDashboard(
                storage_path=storage_path,
                buffer_size=1000,  # Large buffer to test time trigger only
                flush_interval=flush_interval
            )
            
            # Record one entry
            dashboard.record("research", "openai", 0.01)
            initial_buffer_count = dashboard.buffer_count
            
            # Simulate time passing by manipulating _last_flush
            dashboard._last_flush = datetime.utcnow() - timedelta(seconds=flush_interval + 1)
            
            # Record another entry - should trigger time-based flush
            dashboard.record("chat", "anthropic", 0.02)
            
            # Buffer should have been flushed (only the new entry remains or buffer is empty)
            assert dashboard.buffer_count <= 1, \
                f"Buffer should have been flushed, got {dashboard.buffer_count} entries"
    
    @given(
        buffer_size=buffer_sizes,
        flush_interval=flush_intervals
    )
    @settings(max_examples=50, suppress_health_check=[HealthCheck.too_slow])
    def test_flush_updates_last_flush_timestamp(self, buffer_size, flush_interval):
        """Successful flush should update last flush timestamp.
        
        **Validates: Requirements 7.2, 7.3**
        """
        with tempfile.TemporaryDirectory() as tmpdir:
            storage_path = Path(tmpdir) / "costs.json"
            
            dashboard = BufferedCostDashboard(
                storage_path=storage_path,
                buffer_size=buffer_size,
                flush_interval=flush_interval
            )
            
            # Record entry and flush
            dashboard.record("research", "openai", 0.01)
            
            before_flush = dashboard._last_flush
            dashboard.flush()
            after_flush = dashboard._last_flush
            
            # Last flush should be updated
            assert after_flush >= before_flush
    
    @given(
        num_entries=st.integers(min_value=1, max_value=50)
    )
    @settings(max_examples=50, suppress_health_check=[HealthCheck.too_slow])
    def test_entries_preserved_in_memory_after_flush(self, num_entries):
        """Entries should remain in memory after flush for queries.
        
        **Validates: Requirements 7.2**
        """
        with tempfile.TemporaryDirectory() as tmpdir:
            storage_path = Path(tmpdir) / "costs.json"
            
            dashboard = BufferedCostDashboard(
                storage_path=storage_path,
                buffer_size=1,  # Flush after each entry
                flush_interval=3600
            )
            
            # Record entries (each will trigger a flush)
            for i in range(num_entries):
                dashboard.record("research", "openai", 0.01)
            
            # All entries should still be in memory
            assert len(dashboard.entries) == num_entries
            
            # Daily total should reflect all entries
            expected_total = num_entries * 0.01
            actual_total = dashboard.get_daily_total()
            assert abs(actual_total - expected_total) < 0.0001


# =============================================================================
# Property 8: Cost Buffer Retention on Failure
# =============================================================================

@pytest.mark.unit
class TestCostBufferRetentionOnFailureProperty:
    """Property 8: Cost Buffer Retention on Failure
    
    For any flush operation that fails, all buffered entries SHALL be 
    retained in the buffer for retry.
    
    Feature: code-quality-security-hardening, Property 8: Retention on Failure
    **Validates: Requirements 7.6**
    """
    
    @pytest.fixture
    def temp_storage(self):
        """Create temporary storage path for tests."""
        with tempfile.TemporaryDirectory() as tmpdir:
            yield Path(tmpdir) / "costs.json"
    
    @given(
        num_entries=st.integers(min_value=1, max_value=20),
        operation=operation_names,
        provider=provider_names
    )
    @settings(max_examples=100, suppress_health_check=[HealthCheck.too_slow])
    def test_buffer_retained_on_flush_failure(self, num_entries, operation, provider):
        """Buffer entries should be retained when flush fails.
        
        **Validates: Requirements 7.6**
        """
        with tempfile.TemporaryDirectory() as tmpdir:
            storage_path = Path(tmpdir) / "costs.json"
            
            dashboard = BufferedCostDashboard(
                storage_path=storage_path,
                buffer_size=1000,  # Large buffer to prevent auto-flush
                flush_interval=3600
            )
            
            # Record entries
            for i in range(num_entries):
                dashboard.record(operation, provider, 0.01 * (i + 1))
            
            initial_buffer_count = dashboard.buffer_count
            assert initial_buffer_count == num_entries
            
            # Mock _save to fail
            def failing_save():
                raise IOError("Simulated disk failure")
            
            dashboard._save = failing_save
            
            # Attempt flush - should fail
            result = dashboard.flush()
            
            assert result is False, "Flush should return False on failure"
            assert dashboard.buffer_count == num_entries, \
                f"Buffer should retain all {num_entries} entries, got {dashboard.buffer_count}"
    
    @given(
        num_entries=st.integers(min_value=1, max_value=20)
    )
    @settings(max_examples=50, suppress_health_check=[HealthCheck.too_slow])
    def test_entries_available_for_retry_after_failure(self, num_entries):
        """Retained entries should be available for retry.
        
        **Validates: Requirements 7.6**
        """
        with tempfile.TemporaryDirectory() as tmpdir:
            storage_path = Path(tmpdir) / "costs.json"
            
            dashboard = BufferedCostDashboard(
                storage_path=storage_path,
                buffer_size=1000,
                flush_interval=3600
            )
            
            # Record entries
            for i in range(num_entries):
                dashboard.record("research", "openai", 0.01)
            
            # Store original _save
            original_save = dashboard._save
            
            # First flush fails
            dashboard._save = lambda: (_ for _ in ()).throw(IOError("Disk full"))
            result1 = dashboard.flush()
            assert result1 is False
            assert dashboard.buffer_count == num_entries
            
            # Restore working _save
            dashboard._save = original_save
            
            # Second flush succeeds
            result2 = dashboard.flush()
            assert result2 is True
            assert dashboard.buffer_count == 0
    
    @given(
        num_entries=st.integers(min_value=1, max_value=10),
        num_failures=st.integers(min_value=1, max_value=5)
    )
    @settings(max_examples=50, suppress_health_check=[HealthCheck.too_slow])
    def test_multiple_failures_retain_all_entries(self, num_entries, num_failures):
        """Multiple consecutive failures should retain all entries.
        
        **Validates: Requirements 7.6**
        """
        with tempfile.TemporaryDirectory() as tmpdir:
            storage_path = Path(tmpdir) / "costs.json"
            
            dashboard = BufferedCostDashboard(
                storage_path=storage_path,
                buffer_size=1000,
                flush_interval=3600
            )
            
            # Record entries
            for i in range(num_entries):
                dashboard.record("research", "openai", 0.01)
            
            # Mock _save to fail
            dashboard._save = lambda: (_ for _ in ()).throw(IOError("Disk error"))
            
            # Multiple failed flush attempts
            for _ in range(num_failures):
                result = dashboard.flush()
                assert result is False
                assert dashboard.buffer_count == num_entries, \
                    "All entries should be retained after each failed flush"
    
    @given(
        num_entries=st.integers(min_value=1, max_value=20)
    )
    @settings(max_examples=50, suppress_health_check=[HealthCheck.too_slow])
    def test_entries_in_memory_preserved_on_failure(self, num_entries):
        """Entries in memory list should be preserved on flush failure.
        
        **Validates: Requirements 7.6**
        """
        with tempfile.TemporaryDirectory() as tmpdir:
            storage_path = Path(tmpdir) / "costs.json"
            
            dashboard = BufferedCostDashboard(
                storage_path=storage_path,
                buffer_size=1000,
                flush_interval=3600
            )
            
            # Record entries
            for i in range(num_entries):
                dashboard.record("research", "openai", 0.01)
            
            # Mock _save to fail
            dashboard._save = lambda: (_ for _ in ()).throw(IOError("Disk error"))
            
            # Attempt flush
            dashboard.flush()
            
            # Entries should still be in memory for queries
            assert len(dashboard.entries) == num_entries
            
            # Daily total should still work
            expected_total = num_entries * 0.01
            actual_total = dashboard.get_daily_total()
            assert abs(actual_total - expected_total) < 0.0001


# =============================================================================
# Thread Safety Tests
# =============================================================================

@pytest.mark.unit
class TestBufferedCostDashboardThreadSafety:
    """Tests for thread safety of BufferedCostDashboard."""
    
    @pytest.fixture
    def temp_storage(self):
        """Create temporary storage path for tests."""
        with tempfile.TemporaryDirectory() as tmpdir:
            yield Path(tmpdir) / "costs.json"
    
    def test_concurrent_records(self, temp_storage):
        """Concurrent record calls should be thread-safe."""
        dashboard = BufferedCostDashboard(
            storage_path=temp_storage,
            buffer_size=1000,  # Large buffer
            flush_interval=3600
        )
        
        num_threads = 10
        records_per_thread = 50
        errors = []
        
        def record_entries():
            try:
                for i in range(records_per_thread):
                    dashboard.record("research", "openai", 0.01)
            except Exception as e:
                errors.append(e)
        
        threads = [threading.Thread(target=record_entries) for _ in range(num_threads)]
        
        for t in threads:
            t.start()
        
        for t in threads:
            t.join()
        
        assert len(errors) == 0, f"Errors during concurrent recording: {errors}"
        
        expected_entries = num_threads * records_per_thread
        assert len(dashboard.entries) == expected_entries
    
    def test_concurrent_flush(self, temp_storage):
        """Concurrent flush calls should be thread-safe."""
        dashboard = BufferedCostDashboard(
            storage_path=temp_storage,
            buffer_size=1000,
            flush_interval=3600
        )
        
        # Add some entries
        for i in range(100):
            dashboard.record("research", "openai", 0.01)
        
        num_threads = 5
        errors = []
        
        def flush_buffer():
            try:
                dashboard.flush()
            except Exception as e:
                errors.append(e)
        
        threads = [threading.Thread(target=flush_buffer) for _ in range(num_threads)]
        
        for t in threads:
            t.start()
        
        for t in threads:
            t.join()
        
        assert len(errors) == 0, f"Errors during concurrent flushing: {errors}"
        assert dashboard.buffer_count == 0


# =============================================================================
# Integration Tests
# =============================================================================

@pytest.mark.unit
class TestBufferedCostDashboardIntegration:
    """Integration tests for BufferedCostDashboard."""
    
    @pytest.fixture
    def temp_storage(self):
        """Create temporary storage path for tests."""
        with tempfile.TemporaryDirectory() as tmpdir:
            yield Path(tmpdir) / "costs.json"
    
    def test_persistence_across_instances(self, temp_storage):
        """Data should persist across dashboard instances."""
        # First instance - record and flush
        dashboard1 = BufferedCostDashboard(
            storage_path=temp_storage,
            buffer_size=100
        )
        dashboard1.record("research", "openai", 0.15)
        dashboard1.record("chat", "anthropic", 0.10)
        dashboard1.flush()
        
        # Second instance - should load persisted data
        dashboard2 = BufferedCostDashboard(storage_path=temp_storage)
        
        assert len(dashboard2.entries) == 2
        total = dashboard2.get_daily_total()
        assert abs(total - 0.25) < 0.0001
    
    def test_alerts_work_with_buffering(self, temp_storage):
        """Alert system should work correctly with buffered dashboard."""
        dashboard = BufferedCostDashboard(
            storage_path=temp_storage,
            daily_limit=1.0,
            alert_thresholds=[0.5],
            buffer_size=100
        )
        
        # Record enough to trigger alert (55% of limit)
        dashboard.record("research", "openai", 0.55)
        
        # Alert should be triggered even without flush
        alerts = dashboard.get_active_alerts()
        assert len(alerts) >= 1
    
    def test_breakdowns_work_with_buffering(self, temp_storage):
        """Breakdown queries should work correctly with buffered dashboard."""
        dashboard = BufferedCostDashboard(
            storage_path=temp_storage,
            buffer_size=100
        )
        
        dashboard.record("research", "openai", 0.10)
        dashboard.record("chat", "openai", 0.15)
        dashboard.record("synthesis", "anthropic", 0.20)
        
        # Breakdowns should work even without flush
        by_provider = dashboard.get_breakdown_by_provider()
        assert abs(by_provider["openai"] - 0.25) < 0.0001
        assert abs(by_provider["anthropic"] - 0.20) < 0.0001
        
        by_operation = dashboard.get_breakdown_by_operation()
        assert abs(by_operation["research"] - 0.10) < 0.0001
        assert abs(by_operation["chat"] - 0.15) < 0.0001
        assert abs(by_operation["synthesis"] - 0.20) < 0.0001
