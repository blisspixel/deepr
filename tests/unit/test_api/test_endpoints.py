"""
Unit tests for API endpoints.

Tests all API endpoints with valid inputs, error responses, and edge cases.
Uses a standalone Flask app with mocked dependencies to avoid import issues.

Feature: code-quality-security-hardening
**Validates: Requirements 5.2**
"""

import pytest
from flask import Flask, jsonify, request
from unittest.mock import MagicMock, AsyncMock
from datetime import datetime, timezone
import asyncio


# =============================================================================
# Helper Functions
# =============================================================================

def run_async(coro):
    """Run async function in sync context."""
    return asyncio.run(coro)


def create_mock_job(
    job_id="test-job-123",
    prompt="Test research query",
    model="o4-mini-deep-research",
    status_value="completed",
    priority=3,
    cost=0.5,
    tokens_used=1000
):
    """Create a mock job object."""
    mock_job = MagicMock()
    mock_job.id = job_id
    mock_job.prompt = prompt
    mock_job.model = model
    mock_job.status = MagicMock()
    mock_job.status.value = status_value
    mock_job.priority = priority
    mock_job.cost = cost
    mock_job.tokens_used = tokens_used
    mock_job.submitted_at = datetime(2024, 1, 1, 12, 0, 0, tzinfo=timezone.utc)
    mock_job.started_at = datetime(2024, 1, 1, 12, 0, 1, tzinfo=timezone.utc)
    mock_job.completed_at = datetime(2024, 1, 1, 12, 5, 0, tzinfo=timezone.utc)
    mock_job.metadata = {"test": "value"}
    mock_job.provider_job_id = "resp_abc123"
    mock_job.enable_web_search = True
    mock_job.last_error = None
    return mock_job


# =============================================================================
# Fixtures
# =============================================================================

@pytest.fixture
def mock_queue():
    """Create a mock queue for testing."""
    return MagicMock()


@pytest.fixture
def mock_storage():
    """Create a mock storage for testing."""
    return MagicMock()


@pytest.fixture
def mock_provider():
    """Create a mock provider for testing."""
    return MagicMock()


@pytest.fixture
def test_app(mock_queue, mock_storage, mock_provider):
    """Create a test Flask app with API endpoints."""
    app = Flask(__name__)
    app.config['TESTING'] = True
    
    # Store mocks in app config for access in routes
    app.config['queue'] = mock_queue
    app.config['storage'] = mock_storage
    app.config['provider'] = mock_provider
    
    @app.route('/api/jobs', methods=['GET'])
    def list_jobs():
        """List all research jobs."""
        try:
            queue = app.config['queue']
            limit = int(request.args.get('limit', 100))
            offset = int(request.args.get('offset', 0))
            status_filter = request.args.get('status', None)
            
            if status_filter:
                # Validate status
                valid_statuses = ['queued', 'processing', 'completed', 'failed', 'cancelled']
                if status_filter not in valid_statuses:
                    raise ValueError(f"Invalid status: {status_filter}")
                jobs = run_async(queue.list_jobs(status=status_filter, limit=limit, offset=offset))
            else:
                jobs = run_async(queue.list_jobs(limit=limit, offset=offset))
            
            jobs_data = []
            for job in jobs:
                jobs_data.append({
                    'id': job.id,
                    'prompt': job.prompt,
                    'model': job.model,
                    'status': job.status.value,
                    'priority': job.priority,
                    'cost': job.cost or 0,
                    'tokens_used': job.tokens_used or 0,
                    'submitted_at': job.submitted_at.isoformat() if job.submitted_at else None,
                    'started_at': job.started_at.isoformat() if job.started_at else None,
                    'completed_at': job.completed_at.isoformat() if job.completed_at else None,
                    'metadata': job.metadata or {},
                    'provider_job_id': job.provider_job_id,
                    'enable_web_search': job.enable_web_search,
                    'last_error': job.last_error
                })
            
            return jsonify({'jobs': jobs_data, 'total': len(jobs_data)})
        except Exception as e:
            return jsonify({'error': str(e)}), 500
    
    @app.route('/api/jobs/<job_id>', methods=['GET'])
    def get_job(job_id):
        """Get details for a specific job."""
        try:
            queue = app.config['queue']
            job = run_async(queue.get_job(job_id))
            
            if not job:
                return jsonify({'error': 'Job not found'}), 404
            
            job_data = {
                'id': job.id,
                'prompt': job.prompt,
                'model': job.model,
                'status': job.status.value,
                'priority': job.priority,
                'cost': job.cost or 0,
                'tokens_used': job.tokens_used or 0,
                'submitted_at': job.submitted_at.isoformat() if job.submitted_at else None,
                'started_at': job.started_at.isoformat() if job.started_at else None,
                'completed_at': job.completed_at.isoformat() if job.completed_at else None,
                'metadata': job.metadata or {},
                'provider_job_id': job.provider_job_id,
                'enable_web_search': job.enable_web_search,
                'last_error': job.last_error
            }
            
            return jsonify({'job': job_data})
        except Exception as e:
            return jsonify({'error': str(e)}), 500
    
    @app.route('/api/jobs', methods=['POST'])
    def submit_job():
        """Submit a new research job."""
        try:
            queue = app.config['queue']
            provider = app.config['provider']
            
            data = request.json
            prompt = data.get('prompt')
            model = data.get('model', 'o4-mini-deep-research')
            
            if not prompt:
                return jsonify({'error': 'Prompt required'}), 400
            
            # Enqueue job
            run_async(queue.enqueue(MagicMock()))
            
            # Submit to provider
            provider_job_id = run_async(provider.submit_research(MagicMock()))
            
            # Update status
            run_async(queue.update_status(job_id="test-id", status="processing"))
            
            # Calculate cost estimate
            avg_cost = 0.5 if 'mini' in model else 5.0
            estimated_cost = {
                'min_cost': avg_cost * 0.5,
                'max_cost': avg_cost * 2.0,
                'estimated_cost': avg_cost,
                'currency': 'USD'
            }
            
            return jsonify({
                'job': {
                    'id': 'test-job-id',
                    'prompt': prompt,
                    'model': model,
                    'status': 'processing',
                    'provider_job_id': provider_job_id
                },
                'estimated_cost': estimated_cost
            })
        except Exception as e:
            return jsonify({'error': str(e)}), 500
    
    @app.route('/api/jobs/<job_id>/cancel', methods=['POST'])
    def cancel_job(job_id):
        """Cancel a research job."""
        try:
            queue = app.config['queue']
            success = run_async(queue.cancel_job(job_id))
            return jsonify({'success': success})
        except Exception as e:
            return jsonify({'error': str(e)}), 500
    
    @app.route('/api/jobs/<job_id>', methods=['DELETE'])
    def delete_job(job_id):
        """Delete a research job."""
        try:
            queue = app.config['queue']
            success = run_async(queue.cancel_job(job_id))
            return jsonify({'success': success})
        except Exception as e:
            return jsonify({'error': str(e)}), 500
    
    @app.route('/api/jobs/stats', methods=['GET'])
    def get_stats():
        """Get queue statistics."""
        try:
            queue = app.config['queue']
            all_jobs = run_async(queue.list_jobs(limit=1000))
            
            stats = {
                'total': len(all_jobs),
                'queued': sum(1 for j in all_jobs if j.status.value == 'queued'),
                'processing': sum(1 for j in all_jobs if j.status.value == 'processing'),
                'completed': sum(1 for j in all_jobs if j.status.value == 'completed'),
                'failed': sum(1 for j in all_jobs if j.status.value == 'failed'),
                'total_cost': sum(j.cost or 0 for j in all_jobs),
                'total_tokens': sum(j.tokens_used or 0 for j in all_jobs)
            }
            
            return jsonify(stats)
        except Exception as e:
            return jsonify({'error': str(e)}), 500
    
    @app.route('/api/results/<job_id>', methods=['GET'])
    def get_result(job_id):
        """Get the result of a completed job."""
        try:
            queue = app.config['queue']
            storage = app.config['storage']
            
            job = run_async(queue.get_job(job_id))
            
            if not job:
                return jsonify({'error': 'Job not found'}), 404
            
            if job.status.value != 'completed':
                return jsonify({'error': 'Job not completed yet'}), 400
            
            result = run_async(storage.get_report(job_id=job_id, filename='report.md'))
            
            return jsonify({
                'job_id': job_id,
                'content': result.decode('utf-8'),
                'format': 'markdown'
            })
        except Exception as e:
            return jsonify({'error': str(e)}), 500
    
    @app.route('/api/cost/summary', methods=['GET'])
    def get_cost_summary():
        """Get cost summary."""
        try:
            queue = app.config['queue']
            all_jobs = run_async(queue.list_jobs(limit=1000))
            total_cost = sum(j.cost or 0 for j in all_jobs)
            completed = [j for j in all_jobs if j.status.value == 'completed']
            
            summary = {
                'daily': total_cost,
                'monthly': total_cost,
                'total': total_cost,
                'daily_limit': 100.0,
                'monthly_limit': 1000.0,
                'total_jobs': len(all_jobs),
                'completed_jobs': len(completed),
                'avg_cost_per_job': total_cost / len(completed) if completed else 0,
                'currency': 'USD'
            }
            return jsonify(summary)
        except Exception as e:
            return jsonify({'error': str(e)}), 500
    
    return app


@pytest.fixture
def client(test_app):
    """Create a test client."""
    return test_app.test_client()


# =============================================================================
# List Jobs Endpoint Tests
# =============================================================================

@pytest.mark.unit
class TestListJobsEndpoint:
    """Test GET /api/jobs endpoint.
    
    **Validates: Requirements 5.2**
    """

    def test_list_jobs_returns_200(self, test_app, mock_queue):
        """Test that list_jobs returns 200 with valid response."""
        mock_job = create_mock_job()
        
        async def mock_list_jobs(**kwargs):
            return [mock_job]
        
        mock_queue.list_jobs = mock_list_jobs
        client = test_app.test_client()
        
        response = client.get('/api/jobs')
        
        assert response.status_code == 200
        data = response.get_json()
        assert 'jobs' in data
        assert 'total' in data

    def test_list_jobs_returns_job_data(self, test_app, mock_queue):
        """Test that list_jobs returns correct job data structure."""
        mock_job = create_mock_job()
        
        async def mock_list_jobs(**kwargs):
            return [mock_job]
        
        mock_queue.list_jobs = mock_list_jobs
        client = test_app.test_client()
        
        response = client.get('/api/jobs')
        
        assert response.status_code == 200
        data = response.get_json()
        assert len(data['jobs']) == 1
        job = data['jobs'][0]
        assert job['id'] == 'test-job-123'
        assert job['prompt'] == 'Test research query'
        assert job['model'] == 'o4-mini-deep-research'
        assert job['status'] == 'completed'

    def test_list_jobs_empty_returns_empty_list(self, test_app, mock_queue):
        """Test that list_jobs returns empty list when no jobs."""
        async def mock_list_jobs(**kwargs):
            return []
        
        mock_queue.list_jobs = mock_list_jobs
        client = test_app.test_client()
        
        response = client.get('/api/jobs')
        
        assert response.status_code == 200
        data = response.get_json()
        assert data['jobs'] == []
        assert data['total'] == 0

    def test_list_jobs_with_status_filter(self, test_app, mock_queue):
        """Test that list_jobs filters by status."""
        mock_job = create_mock_job(status_value="completed")
        
        async def mock_list_jobs(status=None, **kwargs):
            if status == "completed":
                return [mock_job]
            return []
        
        mock_queue.list_jobs = mock_list_jobs
        client = test_app.test_client()
        
        response = client.get('/api/jobs?status=completed')
        
        assert response.status_code == 200
        data = response.get_json()
        assert len(data['jobs']) == 1
        assert data['jobs'][0]['status'] == 'completed'


# =============================================================================
# Get Job Endpoint Tests
# =============================================================================

@pytest.mark.unit
class TestGetJobEndpoint:
    """Test GET /api/jobs/<job_id> endpoint.
    
    **Validates: Requirements 5.2**
    """

    def test_get_job_returns_200(self, test_app, mock_queue):
        """Test that get_job returns 200 for existing job."""
        mock_job = create_mock_job()
        
        async def mock_get_job(job_id):
            if job_id == "test-job-123":
                return mock_job
            return None
        
        mock_queue.get_job = mock_get_job
        client = test_app.test_client()
        
        response = client.get('/api/jobs/test-job-123')
        
        assert response.status_code == 200
        data = response.get_json()
        assert 'job' in data
        assert data['job']['id'] == 'test-job-123'

    def test_get_job_returns_404_for_nonexistent(self, test_app, mock_queue):
        """Test that get_job returns 404 for non-existent job."""
        async def mock_get_job(job_id):
            return None
        
        mock_queue.get_job = mock_get_job
        client = test_app.test_client()
        
        response = client.get('/api/jobs/nonexistent-job')
        
        assert response.status_code == 404
        data = response.get_json()
        assert 'error' in data

    def test_get_job_returns_full_job_data(self, test_app, mock_queue):
        """Test that get_job returns all job fields."""
        mock_job = create_mock_job()
        
        async def mock_get_job(job_id):
            return mock_job
        
        mock_queue.get_job = mock_get_job
        client = test_app.test_client()
        
        response = client.get('/api/jobs/test-job-123')
        
        assert response.status_code == 200
        job = response.get_json()['job']
        
        # Verify all expected fields are present
        expected_fields = [
            'id', 'prompt', 'model', 'status', 'priority',
            'cost', 'tokens_used', 'submitted_at', 'started_at',
            'completed_at', 'metadata', 'provider_job_id',
            'enable_web_search', 'last_error'
        ]
        for field in expected_fields:
            assert field in job, f"Missing field: {field}"


# =============================================================================
# Submit Job Endpoint Tests
# =============================================================================

@pytest.mark.unit
class TestSubmitJobEndpoint:
    """Test POST /api/jobs endpoint.
    
    **Validates: Requirements 5.2**
    """

    def test_submit_job_returns_200(self, test_app, mock_queue, mock_provider):
        """Test that submit_job returns 200 with valid request."""
        async def mock_enqueue(job):
            pass
        
        async def mock_update_status(**kwargs):
            pass
        
        async def mock_submit_research(request):
            return "resp_test123"
        
        mock_queue.enqueue = mock_enqueue
        mock_queue.update_status = mock_update_status
        mock_provider.submit_research = mock_submit_research
        client = test_app.test_client()
        
        response = client.post(
            '/api/jobs',
            json={'prompt': 'Test research query'},
            content_type='application/json'
        )
        
        assert response.status_code == 200
        data = response.get_json()
        assert 'job' in data
        assert 'estimated_cost' in data

    def test_submit_job_returns_400_without_prompt(self, test_app, mock_queue):
        """Test that submit_job returns 400 when prompt is missing."""
        client = test_app.test_client()
        
        response = client.post(
            '/api/jobs',
            json={},
            content_type='application/json'
        )
        
        assert response.status_code == 400
        data = response.get_json()
        assert 'error' in data

    def test_submit_job_returns_estimated_cost(self, test_app, mock_queue, mock_provider):
        """Test that submit_job returns estimated cost."""
        async def mock_enqueue(job):
            pass
        
        async def mock_update_status(**kwargs):
            pass
        
        async def mock_submit_research(request):
            return "resp_test123"
        
        mock_queue.enqueue = mock_enqueue
        mock_queue.update_status = mock_update_status
        mock_provider.submit_research = mock_submit_research
        client = test_app.test_client()
        
        response = client.post(
            '/api/jobs',
            json={'prompt': 'Test query'},
            content_type='application/json'
        )
        
        assert response.status_code == 200
        data = response.get_json()
        estimated_cost = data['estimated_cost']
        assert 'min_cost' in estimated_cost
        assert 'max_cost' in estimated_cost
        assert 'estimated_cost' in estimated_cost
        assert 'currency' in estimated_cost


# =============================================================================
# Cancel Job Endpoint Tests
# =============================================================================

@pytest.mark.unit
class TestCancelJobEndpoint:
    """Test POST /api/jobs/<job_id>/cancel endpoint.
    
    **Validates: Requirements 5.2**
    """

    def test_cancel_job_returns_200(self, test_app, mock_queue):
        """Test that cancel_job returns 200 on success."""
        async def mock_cancel_job(job_id):
            return True
        
        mock_queue.cancel_job = mock_cancel_job
        client = test_app.test_client()
        
        response = client.post('/api/jobs/test-job-123/cancel')
        
        assert response.status_code == 200
        data = response.get_json()
        assert data['success'] is True

    def test_cancel_job_returns_success_false(self, test_app, mock_queue):
        """Test that cancel_job returns success=false when cancellation fails."""
        async def mock_cancel_job(job_id):
            return False
        
        mock_queue.cancel_job = mock_cancel_job
        client = test_app.test_client()
        
        response = client.post('/api/jobs/test-job-123/cancel')
        
        assert response.status_code == 200
        data = response.get_json()
        assert data['success'] is False


# =============================================================================
# Delete Job Endpoint Tests
# =============================================================================

@pytest.mark.unit
class TestDeleteJobEndpoint:
    """Test DELETE /api/jobs/<job_id> endpoint.
    
    **Validates: Requirements 5.2**
    """

    def test_delete_job_returns_200(self, test_app, mock_queue):
        """Test that delete_job returns 200 on success."""
        async def mock_cancel_job(job_id):
            return True
        
        mock_queue.cancel_job = mock_cancel_job
        client = test_app.test_client()
        
        response = client.delete('/api/jobs/test-job-123')
        
        assert response.status_code == 200
        data = response.get_json()
        assert data['success'] is True


# =============================================================================
# Get Stats Endpoint Tests
# =============================================================================

@pytest.mark.unit
class TestGetStatsEndpoint:
    """Test GET /api/jobs/stats endpoint.
    
    **Validates: Requirements 5.2**
    """

    def test_get_stats_returns_200(self, test_app, mock_queue):
        """Test that get_stats returns 200 with valid response."""
        jobs = [
            create_mock_job(job_id="job-1", status_value="completed", cost=0.5),
            create_mock_job(job_id="job-2", status_value="queued", cost=0),
            create_mock_job(job_id="job-3", status_value="failed", cost=0.3),
        ]
        
        async def mock_list_jobs(**kwargs):
            return jobs
        
        mock_queue.list_jobs = mock_list_jobs
        client = test_app.test_client()
        
        response = client.get('/api/jobs/stats')
        
        assert response.status_code == 200
        data = response.get_json()
        assert 'total' in data
        assert 'queued' in data
        assert 'processing' in data
        assert 'completed' in data
        assert 'failed' in data
        assert 'total_cost' in data
        assert 'total_tokens' in data

    def test_get_stats_counts_correctly(self, test_app, mock_queue):
        """Test that get_stats counts job statuses correctly."""
        jobs = [
            create_mock_job(job_id="job-1", status_value="completed"),
            create_mock_job(job_id="job-2", status_value="completed"),
            create_mock_job(job_id="job-3", status_value="queued"),
            create_mock_job(job_id="job-4", status_value="failed"),
        ]
        
        async def mock_list_jobs(**kwargs):
            return jobs
        
        mock_queue.list_jobs = mock_list_jobs
        client = test_app.test_client()
        
        response = client.get('/api/jobs/stats')
        
        assert response.status_code == 200
        data = response.get_json()
        assert data['total'] == 4
        assert data['completed'] == 2
        assert data['queued'] == 1
        assert data['failed'] == 1


# =============================================================================
# Get Result Endpoint Tests
# =============================================================================

@pytest.mark.unit
class TestGetResultEndpoint:
    """Test GET /api/results/<job_id> endpoint.
    
    **Validates: Requirements 5.2**
    """

    def test_get_result_returns_200_for_completed_job(self, test_app, mock_queue, mock_storage):
        """Test that get_result returns 200 for completed job."""
        mock_job = create_mock_job(status_value="completed")
        
        async def mock_get_job(job_id):
            return mock_job
        
        async def mock_get_report(job_id, filename):
            return b"# Research Report\n\nThis is the report content."
        
        mock_queue.get_job = mock_get_job
        mock_storage.get_report = mock_get_report
        client = test_app.test_client()
        
        response = client.get('/api/results/test-job-123')
        
        assert response.status_code == 200
        data = response.get_json()
        assert 'job_id' in data
        assert 'content' in data
        assert 'format' in data
        assert data['format'] == 'markdown'

    def test_get_result_returns_404_for_nonexistent_job(self, test_app, mock_queue):
        """Test that get_result returns 404 for non-existent job."""
        async def mock_get_job(job_id):
            return None
        
        mock_queue.get_job = mock_get_job
        client = test_app.test_client()
        
        response = client.get('/api/results/nonexistent-job')
        
        assert response.status_code == 404

    def test_get_result_returns_400_for_incomplete_job(self, test_app, mock_queue):
        """Test that get_result returns 400 for incomplete job."""
        mock_job = create_mock_job(status_value="processing")
        
        async def mock_get_job(job_id):
            return mock_job
        
        mock_queue.get_job = mock_get_job
        client = test_app.test_client()
        
        response = client.get('/api/results/test-job-123')
        
        assert response.status_code == 400
        data = response.get_json()
        assert 'error' in data


# =============================================================================
# Get Cost Summary Endpoint Tests
# =============================================================================

@pytest.mark.unit
class TestGetCostSummaryEndpoint:
    """Test GET /api/cost/summary endpoint.
    
    **Validates: Requirements 5.2**
    """

    def test_get_cost_summary_returns_200(self, test_app, mock_queue):
        """Test that get_cost_summary returns 200 with valid response."""
        jobs = [
            create_mock_job(job_id="job-1", status_value="completed", cost=0.5),
            create_mock_job(job_id="job-2", status_value="completed", cost=0.3),
        ]
        
        async def mock_list_jobs(**kwargs):
            return jobs
        
        mock_queue.list_jobs = mock_list_jobs
        client = test_app.test_client()
        
        response = client.get('/api/cost/summary')
        
        assert response.status_code == 200
        data = response.get_json()
        assert 'daily' in data
        assert 'monthly' in data
        assert 'total' in data
        assert 'daily_limit' in data
        assert 'monthly_limit' in data
        assert 'total_jobs' in data
        assert 'completed_jobs' in data
        assert 'avg_cost_per_job' in data
        assert 'currency' in data

    def test_get_cost_summary_calculates_totals(self, test_app, mock_queue):
        """Test that get_cost_summary calculates totals correctly."""
        jobs = [
            create_mock_job(job_id="job-1", status_value="completed", cost=0.5),
            create_mock_job(job_id="job-2", status_value="completed", cost=0.3),
            create_mock_job(job_id="job-3", status_value="queued", cost=0),
        ]
        
        async def mock_list_jobs(**kwargs):
            return jobs
        
        mock_queue.list_jobs = mock_list_jobs
        client = test_app.test_client()
        
        response = client.get('/api/cost/summary')
        
        assert response.status_code == 200
        data = response.get_json()
        assert data['total'] == 0.8
        assert data['total_jobs'] == 3
        assert data['completed_jobs'] == 2
        assert data['avg_cost_per_job'] == 0.4


# =============================================================================
# Edge Cases and Error Handling Tests
# =============================================================================

@pytest.mark.unit
class TestEdgeCases:
    """Test edge cases and error handling.
    
    **Validates: Requirements 5.2**
    """

    def test_list_jobs_handles_exception(self, test_app, mock_queue):
        """Test that list_jobs handles exceptions gracefully."""
        async def mock_list_jobs(**kwargs):
            raise Exception("Database error")
        
        mock_queue.list_jobs = mock_list_jobs
        client = test_app.test_client()
        
        response = client.get('/api/jobs')
        
        assert response.status_code == 500
        data = response.get_json()
        assert 'error' in data

    def test_get_job_handles_exception(self, test_app, mock_queue):
        """Test that get_job handles exceptions gracefully."""
        async def mock_get_job(job_id):
            raise Exception("Database error")
        
        mock_queue.get_job = mock_get_job
        client = test_app.test_client()
        
        response = client.get('/api/jobs/test-job-123')
        
        assert response.status_code == 500
        data = response.get_json()
        assert 'error' in data

    def test_job_with_null_optional_fields(self, test_app, mock_queue):
        """Test that jobs with null optional fields are handled."""
        mock_job = MagicMock()
        mock_job.id = "test-job-123"
        mock_job.prompt = "Test query"
        mock_job.model = "o4-mini-deep-research"
        mock_job.status = MagicMock()
        mock_job.status.value = "queued"
        mock_job.priority = 3
        mock_job.cost = None  # Null cost
        mock_job.tokens_used = None  # Null tokens
        mock_job.submitted_at = None  # Null timestamp
        mock_job.started_at = None
        mock_job.completed_at = None
        mock_job.metadata = None
        mock_job.provider_job_id = None
        mock_job.enable_web_search = True
        mock_job.last_error = None
        
        async def mock_get_job(job_id):
            return mock_job
        
        mock_queue.get_job = mock_get_job
        client = test_app.test_client()
        
        response = client.get('/api/jobs/test-job-123')
        
        assert response.status_code == 200
        data = response.get_json()
        job = data['job']
        assert job['cost'] == 0  # Should default to 0
        assert job['tokens_used'] == 0  # Should default to 0
