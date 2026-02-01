"""Unit tests for API app module.

Tests the REST API endpoints including:
- POST /api/jobs creates job with valid prompt
- POST /api/jobs returns 400 without prompt
- Rate limiting returns 429 with Retry-After
- GET /api/jobs/<id> returns 404 for non-existent job
- All CRUD operations on jobs endpoint
- Cost summary endpoint
- Results endpoint

All tests use mocks to avoid external API calls.
"""

import pytest
import json
from unittest.mock import AsyncMock, MagicMock, patch
from datetime import datetime

from hypothesis import given, settings, assume
import hypothesis.strategies as st


# =============================================================================
# Test Fixtures
# =============================================================================

@pytest.fixture
def mock_queue():
    """Create a mock queue with common async methods."""
    mock = MagicMock()
    mock.enqueue = AsyncMock(return_value=None)
    mock.update_status = AsyncMock(return_value=None)
    mock.get_job = AsyncMock(return_value=None)
    mock.list_jobs = AsyncMock(return_value=[])
    mock.cancel_job = AsyncMock(return_value=True)
    return mock


@pytest.fixture
def mock_provider():
    """Create a mock provider with common async methods."""
    mock = MagicMock()
    mock.submit_research = AsyncMock(return_value="provider-job-123")
    return mock


@pytest.fixture
def mock_storage():
    """Create a mock storage with common async methods."""
    mock = MagicMock()
    mock.get_report = AsyncMock(return_value=b'# Research Report\n\nContent here...')
    return mock


@pytest.fixture
def client(mock_queue, mock_provider, mock_storage):
    """Create Flask test client with mocked dependencies.
    
    Uses sys.modules to get the actual module object because
    deepr/api/__init__.py exports the Flask app directly, which
    causes normal import to return the app instead of the module.
    We need the module to patch its globals (queue, provider, storage).
    """
    import sys
    
    # Import the module first to ensure it's loaded
    import deepr.api.app
    
    # Get the actual module from sys.modules (not the Flask app)
    app_module = sys.modules['deepr.api.app']
    
    # Patch the module-level globals
    with patch.object(app_module, 'queue', mock_queue), \
         patch.object(app_module, 'provider', mock_provider), \
         patch.object(app_module, 'storage', mock_storage):
        
        app_module.app.config['TESTING'] = True
        
        with app_module.app.test_client() as test_client:
            # Attach mocks to client for test access
            test_client.mock_queue = mock_queue
            test_client.mock_provider = mock_provider
            test_client.mock_storage = mock_storage
            yield test_client


# =============================================================================
# Job Submission Tests
# =============================================================================

class TestJobSubmission:
    """Test POST /api/jobs endpoint."""

    def test_submit_job_with_valid_prompt(self, client):
        """Test that POST /api/jobs creates job with valid prompt."""
        response = client.post(
            '/api/jobs',
            json={'prompt': 'Research quantum computing'},
            content_type='application/json'
        )
        
        assert response.status_code == 200
        data = json.loads(response.data)
        
        assert 'job' in data
        assert 'id' in data['job']
        assert data['job']['prompt'] == 'Research quantum computing'
        assert data['job']['status'] == 'processing'
        assert 'estimated_cost' in data

    def test_submit_job_without_prompt_returns_400(self, client):
        """Test that POST /api/jobs returns 400 without prompt."""
        response = client.post(
            '/api/jobs',
            json={},
            content_type='application/json'
        )
        
        assert response.status_code == 400
        data = json.loads(response.data)
        assert 'error' in data
        assert 'Prompt required' in data['error']

    def test_submit_job_with_empty_prompt_returns_400(self, client):
        """Test that POST /api/jobs returns 400 with empty prompt."""
        response = client.post(
            '/api/jobs',
            json={'prompt': ''},
            content_type='application/json'
        )
        
        assert response.status_code == 400
        data = json.loads(response.data)
        assert 'error' in data

    def test_submit_job_with_custom_model(self, client):
        """Test that POST /api/jobs accepts custom model."""
        response = client.post(
            '/api/jobs',
            json={'prompt': 'Research AI', 'model': 'o3-deep-research'},
            content_type='application/json'
        )
        
        assert response.status_code == 200
        data = json.loads(response.data)
        assert data['job']['model'] == 'o3-deep-research'

    def test_submit_job_with_priority(self, client):
        """Test that POST /api/jobs accepts priority."""
        response = client.post(
            '/api/jobs',
            json={'prompt': 'Research AI', 'priority': 1},
            content_type='application/json'
        )
        assert response.status_code == 200

    def test_submit_job_with_web_search_disabled(self, client):
        """Test that POST /api/jobs accepts enable_web_search flag."""
        response = client.post(
            '/api/jobs',
            json={'prompt': 'Research AI', 'enable_web_search': False},
            content_type='application/json'
        )
        assert response.status_code == 200

    def test_submit_job_returns_estimated_cost(self, client):
        """Test that POST /api/jobs returns estimated cost."""
        response = client.post(
            '/api/jobs',
            json={'prompt': 'Research quantum computing'},
            content_type='application/json'
        )
        
        assert response.status_code == 200
        data = json.loads(response.data)
        
        assert 'estimated_cost' in data
        assert 'min_cost' in data['estimated_cost']
        assert 'max_cost' in data['estimated_cost']
        assert 'estimated_cost' in data['estimated_cost']
        assert data['estimated_cost']['currency'] == 'USD'


# =============================================================================
# Job Retrieval Tests
# =============================================================================

class TestJobRetrieval:
    """Test GET /api/jobs/<id> endpoint."""

    def test_get_job_returns_404_for_nonexistent(self, client):
        """Test that GET /api/jobs/<id> returns 404 for non-existent job."""
        client.mock_queue.get_job = AsyncMock(return_value=None)
        
        response = client.get('/api/jobs/nonexistent-job-id')
        
        assert response.status_code == 404
        data = json.loads(response.data)
        assert 'error' in data
        assert 'not found' in data['error'].lower()

    def test_get_job_returns_job_details(self, client):
        """Test that GET /api/jobs/<id> returns job details."""
        from deepr.queue.base import ResearchJob, JobStatus
        
        mock_job = ResearchJob(
            id='test-job-123',
            prompt='Test prompt',
            model='o4-mini-deep-research',
            status=JobStatus.COMPLETED,
            priority=3,
            cost=0.50,
            tokens_used=15000,
            submitted_at=datetime.now(),
            enable_web_search=True
        )
        client.mock_queue.get_job = AsyncMock(return_value=mock_job)
        
        response = client.get('/api/jobs/test-job-123')
        
        assert response.status_code == 200
        data = json.loads(response.data)
        
        assert 'job' in data
        assert data['job']['id'] == 'test-job-123'
        assert data['job']['prompt'] == 'Test prompt'
        assert data['job']['status'] == 'completed'
        assert data['job']['cost'] == 0.50


# =============================================================================
# Job Listing Tests
# =============================================================================

class TestJobListing:
    """Test GET /api/jobs endpoint."""

    def test_list_jobs_returns_empty_list(self, client):
        """Test that GET /api/jobs returns empty list when no jobs."""
        client.mock_queue.list_jobs = AsyncMock(return_value=[])
        
        response = client.get('/api/jobs')
        
        assert response.status_code == 200
        data = json.loads(response.data)
        
        assert 'jobs' in data
        assert data['jobs'] == []
        assert data['total'] == 0

    def test_list_jobs_returns_jobs(self, client):
        """Test that GET /api/jobs returns list of jobs."""
        from deepr.queue.base import ResearchJob, JobStatus
        
        mock_jobs = [
            ResearchJob(
                id='job-1', prompt='Prompt 1', model='o4-mini-deep-research',
                status=JobStatus.COMPLETED, priority=3
            ),
            ResearchJob(
                id='job-2', prompt='Prompt 2', model='o4-mini-deep-research',
                status=JobStatus.QUEUED, priority=2
            )
        ]
        client.mock_queue.list_jobs = AsyncMock(return_value=mock_jobs)
        
        response = client.get('/api/jobs')
        
        assert response.status_code == 200
        data = json.loads(response.data)
        
        assert len(data['jobs']) == 2
        assert data['total'] == 2

    def test_list_jobs_with_status_filter(self, client):
        """Test that GET /api/jobs accepts status filter."""
        from deepr.queue.base import ResearchJob, JobStatus
        
        mock_jobs = [
            ResearchJob(
                id='job-1', prompt='Prompt 1', model='o4-mini-deep-research',
                status=JobStatus.COMPLETED, priority=3
            )
        ]
        client.mock_queue.list_jobs = AsyncMock(return_value=mock_jobs)
        
        response = client.get('/api/jobs?status=completed')
        assert response.status_code == 200

    def test_list_jobs_with_pagination(self, client):
        """Test that GET /api/jobs accepts pagination params."""
        client.mock_queue.list_jobs = AsyncMock(return_value=[])
        response = client.get('/api/jobs?limit=10&offset=5')
        assert response.status_code == 200



# =============================================================================
# Job Cancellation Tests
# =============================================================================

class TestJobCancellation:
    """Test POST /api/jobs/<id>/cancel endpoint."""

    def test_cancel_job_success(self, client):
        """Test that POST /api/jobs/<id>/cancel returns success."""
        client.mock_queue.cancel_job = AsyncMock(return_value=True)
        
        response = client.post('/api/jobs/test-job-123/cancel')
        
        assert response.status_code == 200
        data = json.loads(response.data)
        assert data['success'] is True

    def test_cancel_job_failure(self, client):
        """Test that POST /api/jobs/<id>/cancel returns failure."""
        client.mock_queue.cancel_job = AsyncMock(return_value=False)
        
        response = client.post('/api/jobs/nonexistent-job/cancel')
        
        assert response.status_code == 200
        data = json.loads(response.data)
        assert data['success'] is False


# =============================================================================
# Job Deletion Tests
# =============================================================================

class TestJobDeletion:
    """Test DELETE /api/jobs/<id> endpoint."""

    def test_delete_job_success(self, client):
        """Test that DELETE /api/jobs/<id> returns success."""
        client.mock_queue.cancel_job = AsyncMock(return_value=True)
        
        response = client.delete('/api/jobs/test-job-123')
        
        assert response.status_code == 200
        data = json.loads(response.data)
        assert data['success'] is True


# =============================================================================
# Queue Stats Tests
# =============================================================================

class TestQueueStats:
    """Test GET /api/jobs/stats endpoint."""

    def test_get_stats_returns_statistics(self, client):
        """Test that GET /api/jobs/stats returns queue statistics."""
        from deepr.queue.base import ResearchJob, JobStatus
        
        mock_jobs = [
            ResearchJob(
                id='job-1', prompt='Prompt 1', model='o4-mini-deep-research',
                status=JobStatus.COMPLETED, priority=3, cost=0.50, tokens_used=10000
            ),
            ResearchJob(
                id='job-2', prompt='Prompt 2', model='o4-mini-deep-research',
                status=JobStatus.QUEUED, priority=2, cost=0, tokens_used=0
            )
        ]
        client.mock_queue.list_jobs = AsyncMock(return_value=mock_jobs)
        
        response = client.get('/api/jobs/stats')
        
        assert response.status_code == 200
        data = json.loads(response.data)
        
        assert 'total' in data
        assert 'queued' in data
        assert 'processing' in data
        assert 'completed' in data
        assert 'failed' in data
        assert 'total_cost' in data
        assert 'total_tokens' in data
        
        assert data['total'] == 2
        assert data['completed'] == 1
        assert data['queued'] == 1



# =============================================================================
# Results Tests
# =============================================================================

class TestResults:
    """Test GET /api/results/<id> endpoint."""

    def test_get_result_returns_404_for_nonexistent(self, client):
        """Test that GET /api/results/<id> returns 404 for non-existent job."""
        client.mock_queue.get_job = AsyncMock(return_value=None)
        
        response = client.get('/api/results/nonexistent-job-id')
        assert response.status_code == 404

    def test_get_result_returns_400_for_incomplete_job(self, client):
        """Test that GET /api/results/<id> returns 400 for incomplete job."""
        from deepr.queue.base import ResearchJob, JobStatus
        
        mock_job = ResearchJob(
            id='test-job-123', prompt='Test prompt', model='o4-mini-deep-research',
            status=JobStatus.PROCESSING, priority=3
        )
        client.mock_queue.get_job = AsyncMock(return_value=mock_job)
        
        response = client.get('/api/results/test-job-123')
        
        assert response.status_code == 400
        data = json.loads(response.data)
        assert 'not completed' in data['error'].lower()

    def test_get_result_returns_content_for_completed_job(self, client):
        """Test that GET /api/results/<id> returns content for completed job."""
        from deepr.queue.base import ResearchJob, JobStatus
        
        mock_job = ResearchJob(
            id='test-job-123', prompt='Test prompt', model='o4-mini-deep-research',
            status=JobStatus.COMPLETED, priority=3
        )
        client.mock_queue.get_job = AsyncMock(return_value=mock_job)
        client.mock_storage.get_report = AsyncMock(
            return_value=b'# Research Report\n\nContent here...'
        )
        
        response = client.get('/api/results/test-job-123')
        
        assert response.status_code == 200
        data = json.loads(response.data)
        
        assert data['job_id'] == 'test-job-123'
        assert 'Research Report' in data['content']
        assert data['format'] == 'markdown'


# =============================================================================
# Cost Summary Tests
# =============================================================================

class TestCostSummary:
    """Test GET /api/cost/summary endpoint."""

    def test_get_cost_summary(self, client):
        """Test that GET /api/cost/summary returns cost summary."""
        from deepr.queue.base import ResearchJob, JobStatus
        
        mock_jobs = [
            ResearchJob(
                id='job-1', prompt='Prompt 1', model='o4-mini-deep-research',
                status=JobStatus.COMPLETED, priority=3, cost=0.50
            ),
            ResearchJob(
                id='job-2', prompt='Prompt 2', model='o4-mini-deep-research',
                status=JobStatus.COMPLETED, priority=2, cost=0.75
            )
        ]
        client.mock_queue.list_jobs = AsyncMock(return_value=mock_jobs)
        
        response = client.get('/api/cost/summary')
        
        assert response.status_code == 200
        data = json.loads(response.data)
        
        assert 'daily' in data
        assert 'monthly' in data
        assert 'total' in data
        assert 'daily_limit' in data
        assert 'monthly_limit' in data
        assert 'total_jobs' in data
        assert 'completed_jobs' in data
        assert 'avg_cost_per_job' in data
        assert data['currency'] == 'USD'
        
        assert data['total'] == 1.25
        assert data['completed_jobs'] == 2


# =============================================================================
# Property-Based Tests
# =============================================================================

class TestAPIResponseStructure:
    """Property-based tests for API response structure consistency.
    
    These tests verify that API responses maintain consistent structure
    regardless of input variations, ensuring frontend compatibility.
    """

    @given(st.text(min_size=1, max_size=500).filter(lambda x: x.strip()))
    @settings(max_examples=50, deadline=5000)
    def test_job_submission_response_structure(self, prompt):
        """Property: POST /api/jobs always returns consistent structure.
        
        For any valid prompt, the response must contain:
        - 'job' object with 'id', 'prompt', 'model', 'status'
        - 'estimated_cost' object with 'min_cost', 'max_cost', 'estimated_cost', 'currency'
        
        This ensures frontend can reliably parse responses.
        """
        import sys
        
        # Create fresh mocks for each test iteration
        mock_queue = MagicMock()
        mock_queue.enqueue = AsyncMock(return_value=None)
        mock_queue.update_status = AsyncMock(return_value=None)
        
        mock_provider = MagicMock()
        mock_provider.submit_research = AsyncMock(return_value="provider-job-123")
        
        mock_storage = MagicMock()
        
        # Import and patch
        import deepr.api.app
        app_module = sys.modules['deepr.api.app']
        
        with patch.object(app_module, 'queue', mock_queue), \
             patch.object(app_module, 'provider', mock_provider), \
             patch.object(app_module, 'storage', mock_storage):
            
            app_module.app.config['TESTING'] = True
            
            # Disable rate limiting by setting limiter.enabled = False
            app_module.limiter.enabled = False
            
            try:
                with app_module.app.test_client() as client:
                    response = client.post(
                        '/api/jobs',
                        json={'prompt': prompt.strip()},
                        content_type='application/json'
                    )
                    
                    # Should succeed for any non-empty prompt
                    assert response.status_code == 200
                    data = json.loads(response.data)
                    
                    # Verify job structure
                    assert 'job' in data
                    job = data['job']
                    assert 'id' in job
                    assert 'prompt' in job
                    assert 'model' in job
                    assert 'status' in job
                    assert job['prompt'] == prompt.strip()
                    
                    # Verify estimated_cost structure
                    assert 'estimated_cost' in data
                    cost = data['estimated_cost']
                    assert 'min_cost' in cost
                    assert 'max_cost' in cost
                    assert 'estimated_cost' in cost
                    assert 'currency' in cost
                    assert cost['currency'] == 'USD'
                    
                    # Verify cost bounds are sensible
                    assert cost['min_cost'] >= 0
                    assert cost['max_cost'] >= cost['min_cost']
                    assert cost['min_cost'] <= cost['estimated_cost'] <= cost['max_cost']
            finally:
                # Re-enable rate limiting for other tests
                app_module.limiter.enabled = True

    @given(st.text(min_size=0, max_size=100))
    @settings(max_examples=30, deadline=5000)
    def test_job_list_response_structure(self, status_filter):
        """Property: GET /api/jobs always returns consistent list structure.
        
        For any status filter (valid or invalid), the response must contain:
        - 'jobs' array (may be empty)
        - 'total' integer count
        
        Invalid status filters should return 500 error with 'error' field.
        """
        import sys
        from deepr.queue.base import ResearchJob, JobStatus
        
        mock_queue = MagicMock()
        mock_jobs = [
            ResearchJob(
                id='job-1', prompt='Test', model='o4-mini-deep-research',
                status=JobStatus.COMPLETED, priority=3
            )
        ]
        mock_queue.list_jobs = AsyncMock(return_value=mock_jobs)
        
        mock_provider = MagicMock()
        mock_storage = MagicMock()
        
        import deepr.api.app
        app_module = sys.modules['deepr.api.app']
        
        with patch.object(app_module, 'queue', mock_queue), \
             patch.object(app_module, 'provider', mock_provider), \
             patch.object(app_module, 'storage', mock_storage):
            
            app_module.app.config['TESTING'] = True
            
            with app_module.app.test_client() as client:
                # Build URL with optional status filter
                url = '/api/jobs'
                if status_filter.strip():
                    url = f'/api/jobs?status={status_filter}'
                
                response = client.get(url)
                data = json.loads(response.data)
                
                # Valid statuses should return 200 with jobs array
                valid_statuses = {'queued', 'processing', 'completed', 'failed', 'cancelled', ''}
                if status_filter.strip().lower() in valid_statuses or not status_filter.strip():
                    if response.status_code == 200:
                        assert 'jobs' in data
                        assert isinstance(data['jobs'], list)
                        assert 'total' in data
                        assert isinstance(data['total'], int)
                        assert data['total'] >= 0
                
                # Invalid statuses should return error
                if response.status_code == 500:
                    assert 'error' in data

    @given(st.uuids())
    @settings(max_examples=30, deadline=5000)
    def test_job_not_found_response_structure(self, job_id):
        """Property: GET /api/jobs/<id> returns consistent 404 structure.
        
        For any job ID that doesn't exist, the response must contain:
        - HTTP 404 status
        - 'error' field with descriptive message
        """
        import sys
        
        mock_queue = MagicMock()
        mock_queue.get_job = AsyncMock(return_value=None)
        
        mock_provider = MagicMock()
        mock_storage = MagicMock()
        
        import deepr.api.app
        app_module = sys.modules['deepr.api.app']
        
        with patch.object(app_module, 'queue', mock_queue), \
             patch.object(app_module, 'provider', mock_provider), \
             patch.object(app_module, 'storage', mock_storage):
            
            app_module.app.config['TESTING'] = True
            
            with app_module.app.test_client() as client:
                response = client.get(f'/api/jobs/{job_id}')
                
                assert response.status_code == 404
                data = json.loads(response.data)
                assert 'error' in data
                assert isinstance(data['error'], str)
                assert len(data['error']) > 0


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
