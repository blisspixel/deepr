"""Property-based tests for curriculum generation error handling.

This module tests the error exception hierarchy and ensures that all
error types properly capture and communicate failure information.
"""

from hypothesis import given
from hypothesis import strategies as st

from deepr.experts.errors import (
    APIKeyError,
    APIRateLimitError,
    APIServerError,
    APITimeoutError,
    BudgetExceededError,
    CurriculumGenerationError,
    DomainValidationError,
    InvalidCurriculumError,
    NetworkError,
)


class TestErrorExceptionHierarchy:
    """Test the error exception hierarchy and error capture."""

    def test_all_errors_inherit_from_base(self):
        """All curriculum errors should inherit from CurriculumGenerationError."""
        error_classes = [
            APITimeoutError,
            APIRateLimitError,
            APIServerError,
            InvalidCurriculumError,
            DomainValidationError,
            APIKeyError,
            BudgetExceededError,
            NetworkError,
        ]

        for error_class in error_classes:
            # Create instance with appropriate args
            if error_class == APITimeoutError:
                error = error_class(120)
            elif error_class == APIRateLimitError:
                error = error_class(60)
            elif error_class == APIServerError:
                error = error_class(500, "Internal Server Error")
            elif error_class == InvalidCurriculumError:
                error = error_class(["Missing field: title"])
            elif error_class == DomainValidationError:
                error = error_class("AI", "Too broad")
            elif error_class == APIKeyError:
                error = error_class("missing")
            elif error_class == BudgetExceededError:
                error = error_class(15.0, 10.0)
            else:  # NetworkError
                error = error_class()

            assert isinstance(error, CurriculumGenerationError)
            assert isinstance(error, Exception)

    @given(timeout=st.integers(min_value=1, max_value=600))
    def test_api_timeout_error_captures_timeout(self, timeout):
        """Property: APITimeoutError should capture timeout value."""
        error = APITimeoutError(timeout)

        assert error.timeout == timeout
        assert str(timeout) in str(error)
        assert "timed out" in str(error).lower()

    @given(retry_after=st.one_of(st.none(), st.integers(min_value=1, max_value=300)))
    def test_api_rate_limit_error_captures_retry_after(self, retry_after):
        """Property: APIRateLimitError should capture retry_after value."""
        error = APIRateLimitError(retry_after)

        assert error.retry_after == retry_after
        assert "rate limit" in str(error).lower()
        if retry_after:
            assert str(retry_after) in str(error)

    @given(status_code=st.integers(min_value=500, max_value=599), message=st.text(min_size=1, max_size=100))
    def test_api_server_error_captures_details(self, status_code, message):
        """Property: APIServerError should capture status code and message."""
        error = APIServerError(status_code, message)

        assert error.status_code == status_code
        assert str(status_code) in str(error)
        assert "server error" in str(error).lower()

    @given(issues=st.lists(st.text(min_size=1, max_size=50), min_size=1, max_size=10))
    def test_invalid_curriculum_error_captures_issues(self, issues):
        """Property: InvalidCurriculumError should capture all validation issues."""
        error = InvalidCurriculumError(issues)

        assert error.issues == issues
        assert "invalid curriculum" in str(error).lower()
        # All issues should be mentioned in error message
        for issue in issues:
            assert issue in str(error)

    @given(domain=st.text(min_size=1, max_size=100), reason=st.text(min_size=1, max_size=200))
    def test_domain_validation_error_captures_details(self, domain, reason):
        """Property: DomainValidationError should capture domain and reason."""
        error = DomainValidationError(domain, reason)

        assert error.domain == domain
        assert error.reason == reason
        assert domain in str(error)
        assert reason in str(error)
        assert "not suitable" in str(error).lower()

    @given(key_type=st.sampled_from(["missing", "invalid"]))
    def test_api_key_error_captures_key_type(self, key_type):
        """Property: APIKeyError should capture key type."""
        error = APIKeyError(key_type)

        assert error.key_type == key_type
        assert "api key" in str(error).lower()
        assert "OPENAI_API_KEY" in str(error)

    @given(
        estimated_cost=st.floats(min_value=0.1, max_value=100.0), budget_limit=st.floats(min_value=0.1, max_value=100.0)
    )
    def test_budget_exceeded_error_captures_amounts(self, estimated_cost, budget_limit):
        """Property: BudgetExceededError should capture cost and budget."""
        # Only test when cost exceeds budget
        if estimated_cost <= budget_limit:
            estimated_cost = budget_limit + 1.0

        error = BudgetExceededError(estimated_cost, budget_limit)

        assert error.estimated_cost == estimated_cost
        assert error.budget_limit == budget_limit
        assert "exceeds budget" in str(error).lower()

    def test_network_error_has_helpful_message(self):
        """NetworkError should have a helpful message."""
        error = NetworkError()

        assert "cannot reach" in str(error).lower()
        assert "internet connection" in str(error).lower()

    def test_errors_can_be_caught_by_base_class(self):
        """All errors should be catchable by base CurriculumGenerationError."""
        errors = [
            APITimeoutError(120),
            APIRateLimitError(60),
            APIServerError(500, "Error"),
            InvalidCurriculumError(["Issue"]),
            DomainValidationError("AI", "Too broad"),
            APIKeyError("missing"),
            BudgetExceededError(15.0, 10.0),
            NetworkError(),
        ]

        for error in errors:
            try:
                raise error
            except CurriculumGenerationError as e:
                assert isinstance(e, CurriculumGenerationError)
                assert str(e)  # Should have a message

    def test_errors_have_non_empty_messages(self):
        """All errors should have non-empty, informative messages."""
        errors = [
            APITimeoutError(120),
            APIRateLimitError(60),
            APIServerError(500, "Error"),
            InvalidCurriculumError(["Issue"]),
            DomainValidationError("AI", "Too broad"),
            APIKeyError("missing"),
            BudgetExceededError(15.0, 10.0),
            NetworkError(),
        ]

        for error in errors:
            message = str(error)
            assert message
            assert len(message) > 10  # Should be informative
            # Should not just be the class name
            assert message != error.__class__.__name__


class TestErrorMessageQuality:
    """Test that error messages are helpful and actionable."""

    def test_timeout_error_suggests_retry(self):
        """Timeout error should suggest retrying."""
        error = APITimeoutError(120)
        message = str(error).lower()

        assert "try again" in message or "retry" in message

    def test_rate_limit_error_suggests_waiting(self):
        """Rate limit error should suggest waiting."""
        error = APIRateLimitError(60)
        message = str(error).lower()

        assert "wait" in message

    def test_server_error_explains_not_user_fault(self):
        """Server error should explain it's not the user's fault."""
        error = APIServerError(500, "Internal Server Error")
        message = str(error).lower()

        assert "openai" in message or "api" in message

    def test_domain_validation_provides_examples(self):
        """Domain validation error should provide good/bad examples."""
        error = DomainValidationError("AI", "Too broad")
        message = str(error)

        assert "Examples of good domains" in message
        assert "Examples of bad domains" in message
        assert "AWS Solutions Architect" in message

    def test_api_key_error_provides_solution(self):
        """API key error should tell user how to fix it."""
        error = APIKeyError("missing")
        message = str(error)

        assert "OPENAI_API_KEY" in message
        assert ".env" in message

    def test_budget_error_suggests_solutions(self):
        """Budget error should suggest how to fix it."""
        error = BudgetExceededError(15.0, 10.0)
        message = str(error).lower()

        assert "--budget" in message or "increase budget" in message
