"""Property-based tests for curriculum generation progress feedback.

This module tests the progress feedback system to ensure it properly
tracks and communicates progress during curriculum generation.
"""

import pytest
from hypothesis import given, strategies as st
from datetime import datetime
import time
from deepr.experts.curriculum import CurriculumGenerationProgress


class TestProgressFeedback:
    """Test progress feedback functionality."""
    
    @given(step_name=st.text(min_size=1, max_size=100))
    def test_start_captures_step_name(self, step_name):
        """Property: start() should capture and display step name."""
        messages = []
        progress = CurriculumGenerationProgress(callback=messages.append)
        
        progress.start(step_name)
        
        assert progress.current_step == step_name
        assert progress.start_time is not None
        assert len(messages) == 1
        assert step_name in messages[0]
    
    @given(update_message=st.text(min_size=1, max_size=100))
    def test_update_displays_message(self, update_message):
        """Property: update() should display progress messages."""
        messages = []
        progress = CurriculumGenerationProgress(callback=messages.append)
        
        progress.start("Test Step")
        messages.clear()  # Clear start message
        progress.update(update_message)
        
        assert len(messages) == 1
        assert update_message in messages[0]
    
    @given(completion_message=st.text(min_size=1, max_size=100))
    def test_complete_shows_elapsed_time(self, completion_message):
        """Property: complete() should show elapsed time."""
        messages = []
        progress = CurriculumGenerationProgress(callback=messages.append)
        
        progress.start("Test Step")
        time.sleep(0.1)  # Small delay to ensure measurable time
        messages.clear()
        progress.complete(completion_message)
        
        assert len(messages) == 1
        assert completion_message in messages[0]
        # Should contain time in format like "(0.1s)"
        assert "(" in messages[0] and "s)" in messages[0]
    
    @given(error_message=st.text(min_size=1, max_size=100))
    def test_error_displays_error_marker(self, error_message):
        """Property: error() should display error with error symbol (✗ or [X])."""
        from deepr.cli.colors import get_symbol
        messages = []
        progress = CurriculumGenerationProgress(callback=messages.append)
        
        progress.error(error_message)
        
        assert len(messages) == 1
        # Modern CLI uses symbols: ✗ (Unicode) or [X] (ASCII fallback)
        error_symbol = get_symbol("error")
        assert error_symbol in messages[0]
        assert error_message in messages[0]
    
    def test_timestamp_format_is_valid(self):
        """Timestamp should be in HH:MM:SS format."""
        progress = CurriculumGenerationProgress()
        timestamp = progress._timestamp()
        
        # Should be in format HH:MM:SS
        parts = timestamp.split(":")
        assert len(parts) == 3
        assert all(part.isdigit() for part in parts)
        assert 0 <= int(parts[0]) <= 23  # Hours
        assert 0 <= int(parts[1]) <= 59  # Minutes
        assert 0 <= int(parts[2]) <= 59  # Seconds
    
    def test_callback_receives_all_messages(self):
        """All progress messages should be sent to callback."""
        messages = []
        progress = CurriculumGenerationProgress(callback=messages.append)
        
        progress.start("Step 1")
        progress.update("Update 1")
        progress.update("Update 2")
        progress.complete("Done")
        progress.error("Error occurred")
        
        assert len(messages) == 5
        assert "Step 1" in messages[0]
        assert "Update 1" in messages[1]
        assert "Update 2" in messages[2]
        assert "Done" in messages[3]
        assert "Error occurred" in messages[4]
    
    def test_no_callback_uses_click_echo(self):
        """Without callback, should use click.echo (no errors)."""
        progress = CurriculumGenerationProgress()
        
        # Should not raise any errors
        progress.start("Test")
        progress.update("Update")
        progress.complete()
        progress.error("Error")
    
    def test_multiple_steps_track_separately(self):
        """Each step should track its own timing."""
        messages = []
        progress = CurriculumGenerationProgress(callback=messages.append)
        
        progress.start("Step 1")
        time.sleep(0.05)
        progress.complete()
        
        messages.clear()
        progress.start("Step 2")
        time.sleep(0.05)
        progress.complete()
        
        # Should have start and complete for Step 2
        assert len(messages) == 2
        assert "Step 2" in messages[0]
    
    def test_complete_without_start_still_works(self):
        """complete() should work even if start() wasn't called."""
        messages = []
        progress = CurriculumGenerationProgress(callback=messages.append)
        
        progress.complete("Done")
        
        assert len(messages) == 1
        assert "Done" in messages[0]
        # Should not have timing info since no start
        assert "(" not in messages[0] or "s)" not in messages[0]
    
    @given(
        steps=st.lists(
            st.text(min_size=1, max_size=50),
            min_size=1,
            max_size=10
        )
    )
    def test_multiple_steps_sequence(self, steps):
        """Property: Should handle arbitrary sequence of steps."""
        messages = []
        progress = CurriculumGenerationProgress(callback=messages.append)
        
        for step in steps:
            progress.start(step)
            progress.update(f"Processing {step}")
            progress.complete()
        
        # Should have 3 messages per step (start, update, complete)
        assert len(messages) == len(steps) * 3
        
        # Each step should appear in messages
        for step in steps:
            assert any(step in msg for msg in messages)
    
    def test_elapsed_time_is_reasonable(self):
        """Elapsed time should be accurate within reasonable bounds."""
        messages = []
        progress = CurriculumGenerationProgress(callback=messages.append)
        
        progress.start("Test")
        time.sleep(0.2)  # Sleep for 200ms
        messages.clear()
        progress.complete()
        
        # Extract time from message like "(0.2s)"
        message = messages[0]
        time_str = message[message.find("(")+1:message.find("s)")]
        elapsed = float(time_str)
        
        # Should be close to 0.2 seconds (allow 0.1s tolerance)
        assert 0.15 <= elapsed <= 0.35


class TestProgressMessageFormatting:
    """Test that progress messages are properly formatted."""
    
    def test_start_message_has_timestamp(self):
        """Start message should include the step name."""
        messages = []
        progress = CurriculumGenerationProgress(callback=messages.append)
        
        progress.start("Test Step")
        
        # Modern CLI: clean step name without timestamp prefix
        assert "Test Step" in messages[0]
    
    def test_update_message_is_indented(self):
        """Update messages should be indented."""
        messages = []
        progress = CurriculumGenerationProgress(callback=messages.append)
        
        progress.update("Update")
        
        # Should start with spaces for indentation
        assert messages[0].startswith("  ")
    
    def test_complete_message_is_indented(self):
        """Complete messages should be indented."""
        messages = []
        progress = CurriculumGenerationProgress(callback=messages.append)
        
        progress.start("Test")
        messages.clear()
        progress.complete()
        
        # Should start with spaces for indentation
        assert messages[0].startswith("  ")
    
    def test_error_message_is_indented(self):
        """Error messages should be indented."""
        messages = []
        progress = CurriculumGenerationProgress(callback=messages.append)
        
        progress.error("Error")
        
        # Should start with spaces for indentation
        assert messages[0].startswith("  ")
    
    def test_complete_message_has_success_symbol(self):
        """Complete message should have success symbol (✓ or [OK])."""
        from deepr.cli.colors import get_symbol
        messages = []
        progress = CurriculumGenerationProgress(callback=messages.append)
        
        progress.start("Test")
        messages.clear()
        progress.complete("Done")
        
        # Modern CLI uses symbols: ✓ (Unicode) or [OK] (ASCII fallback)
        success_symbol = get_symbol("success")
        assert success_symbol in messages[0]
        assert "Done" in messages[0]
    
    def test_error_message_has_error_marker(self):
        """Error message should have error symbol (✗ or [X])."""
        from deepr.cli.colors import get_symbol
        messages = []
        progress = CurriculumGenerationProgress(callback=messages.append)
        
        progress.error("Something failed")
        
        # Modern CLI uses symbols: ✗ (Unicode) or [X] (ASCII fallback)
        error_symbol = get_symbol("error")
        assert error_symbol in messages[0]



class TestSpecificProgressMessages:
    """Test specific progress messages used in curriculum generation."""
    
    def test_calling_gpt5_message(self):
        """Should display 'Calling GPT-5 Responses API...' message."""
        messages = []
        progress = CurriculumGenerationProgress(callback=messages.append)
        
        progress.start("Calling GPT-5 Responses API...")
        
        assert len(messages) == 1
        assert "Calling GPT-5 Responses API" in messages[0]
    
    def test_parsing_response_message(self):
        """Should display 'Parsing curriculum response...' message."""
        messages = []
        progress = CurriculumGenerationProgress(callback=messages.append)
        
        progress.start("Parsing curriculum response...")
        
        assert len(messages) == 1
        assert "Parsing curriculum response" in messages[0]
    
    def test_validating_structure_message(self):
        """Should display 'Validating curriculum structure...' message."""
        messages = []
        progress = CurriculumGenerationProgress(callback=messages.append)
        
        progress.start("Validating curriculum structure...")
        
        assert len(messages) == 1
        assert "Validating curriculum structure" in messages[0]
    
    def test_curriculum_generated_successfully_message(self):
        """Should display 'Curriculum generated successfully' with topic count."""
        messages = []
        progress = CurriculumGenerationProgress(callback=messages.append)
        
        topic_count = 10
        progress.start("Test")
        messages.clear()
        progress.complete(f"Curriculum generated successfully ({topic_count} topics)")
        
        assert len(messages) == 1
        assert "Curriculum generated successfully" in messages[0]
        assert str(topic_count) in messages[0]
        assert "topics" in messages[0]
    
    def test_typical_workflow_messages(self):
        """Test a typical curriculum generation workflow."""
        messages = []
        progress = CurriculumGenerationProgress(callback=messages.append)
        
        # Typical workflow
        progress.start("Calling GPT-5 Responses API...")
        progress.update("Waiting for response...")
        progress.complete("API call successful")
        
        progress.start("Parsing curriculum response...")
        progress.complete("Parsed successfully")
        
        progress.start("Validating curriculum structure...")
        progress.complete("Validation passed")
        
        progress.complete("Curriculum generated successfully (10 topics)")
        
        # Should have all expected messages
        all_messages = "\n".join(messages)
        assert "Calling GPT-5 Responses API" in all_messages
        assert "Parsing curriculum response" in all_messages
        assert "Validating curriculum structure" in all_messages
        assert "Curriculum generated successfully" in all_messages
