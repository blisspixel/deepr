"""
AWS Fargate worker for Deepr research jobs.

Polls SQS for jobs, executes research, stores results in S3.
"""

import asyncio
import json
import logging
import os
import sys
from datetime import datetime, timezone

import boto3

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger('deepr.worker')

# AWS clients
sqs = boto3.client('sqs')
s3 = boto3.client('s3')
secrets_client = boto3.client('secretsmanager')

QUEUE_URL = os.environ.get('QUEUE_URL')
RESULTS_BUCKET = os.environ.get('RESULTS_BUCKET')
SECRETS_ARN = os.environ.get('SECRETS_ARN')


def load_secrets():
    """Load API keys from Secrets Manager into environment."""
    try:
        response = secrets_client.get_secret_value(SecretId=SECRETS_ARN)
        secrets = json.loads(response['SecretString'])

        for key, value in secrets.items():
            if value:
                os.environ[key] = value

        logger.info("Loaded secrets from Secrets Manager")
    except Exception as e:
        logger.error(f"Failed to load secrets: {e}")
        sys.exit(1)


def update_job_status(job_id: str, status: str, **kwargs):
    """Update job status in S3."""
    try:
        # Get current metadata
        response = s3.get_object(
            Bucket=RESULTS_BUCKET,
            Key=f'jobs/{job_id}/metadata.json'
        )
        job = json.loads(response['Body'].read())

        # Update status and additional fields
        job['status'] = status
        job['updated_at'] = datetime.now(timezone.utc).isoformat()
        job.update(kwargs)

        # Save back to S3
        s3.put_object(
            Bucket=RESULTS_BUCKET,
            Key=f'jobs/{job_id}/metadata.json',
            Body=json.dumps(job),
            ContentType='application/json'
        )
        logger.info(f"Updated job {job_id} status to {status}")
    except Exception as e:
        logger.error(f"Failed to update job status: {e}")


def save_result(job_id: str, content: str):
    """Save research result to S3."""
    s3.put_object(
        Bucket=RESULTS_BUCKET,
        Key=f'jobs/{job_id}/report.md',
        Body=content.encode('utf-8'),
        ContentType='text/markdown'
    )
    logger.info(f"Saved result for job {job_id}")


async def execute_research(job: dict) -> tuple[str, float, int]:
    """Execute research job using Deepr providers."""
    # Import here after secrets are loaded
    from deepr.providers.base import ResearchRequest, ToolConfig
    from deepr.providers.openai_provider import OpenAIProvider

    job_id = job['id']
    prompt = job['prompt']
    enable_web_search = job.get('enable_web_search', True)

    # Check for auto-routed jobs with routing decision
    if job.get('auto_routed') and job.get('routing_decision'):
        routing = job['routing_decision']
        provider_name = routing.get('provider', 'openai')
        model = routing.get('model', 'o4-mini-deep-research')
        logger.info(f"Auto-routed job {job_id}: {provider_name}/{model} (complexity: {routing.get('complexity')})")
    else:
        model = job.get('model', 'o4-mini-deep-research')
        provider_name = job.get('provider', 'openai')

    logger.info(f"Executing research job {job_id} with {provider_name}/{model}")

    # Initialize provider based on routing decision
    if provider_name == 'xai':
        from deepr.providers.xai_provider import XAIProvider
        provider = XAIProvider()
    elif provider_name == 'gemini':
        from deepr.providers.gemini_provider import GeminiProvider
        provider = GeminiProvider()
    else:
        # Default to OpenAI for openai/azure
        provider = OpenAIProvider()

    # Create request
    request = ResearchRequest(
        prompt=prompt,
        model=model,
        system_message='You are a research assistant. Provide comprehensive, citation-backed analysis.',
        tools=[ToolConfig(type='web_search_preview')] if enable_web_search else [],
        background=False,  # Run synchronously in worker
    )

    # Submit and wait for completion
    provider_job_id = await provider.submit_research(request)

    # Poll for completion
    while True:
        status = await provider.get_status(provider_job_id)

        if status.status == 'completed':
            return status.content, status.usage.total_cost if status.usage else 0, status.usage.total_tokens if status.usage else 0
        elif status.status == 'failed':
            raise Exception(f"Research failed: {status.error}")

        await asyncio.sleep(30)  # Poll every 30 seconds


async def process_message(message):
    """Process a single SQS message."""
    try:
        job = json.loads(message['Body'])
        job_id = job['id']

        logger.info(f"Processing job {job_id}")

        # Check if job was cancelled
        try:
            response = s3.get_object(
                Bucket=RESULTS_BUCKET,
                Key=f'jobs/{job_id}/metadata.json'
            )
            current_job = json.loads(response['Body'].read())
            if current_job.get('status') == 'cancelled':
                logger.info(f"Job {job_id} was cancelled, skipping")
                return True
        except Exception:
            pass

        # Update status to processing
        update_job_status(job_id, 'processing', started_at=datetime.now(timezone.utc).isoformat())

        # Execute research
        content, cost, tokens = await execute_research(job)

        # Save result
        save_result(job_id, content)

        # Update status to completed
        update_job_status(
            job_id,
            'completed',
            completed_at=datetime.now(timezone.utc).isoformat(),
            cost=cost,
            tokens_used=tokens
        )

        logger.info(f"Completed job {job_id} (cost: ${cost:.2f}, tokens: {tokens})")
        return True

    except Exception as e:
        logger.error(f"Failed to process job: {e}")
        job_id = json.loads(message['Body']).get('id')
        if job_id:
            update_job_status(job_id, 'failed', error=str(e))
        return False


async def poll_queue():
    """Poll SQS for messages and process them."""
    logger.info(f"Starting worker, polling {QUEUE_URL}")

    while True:
        try:
            # Receive messages (long polling)
            response = sqs.receive_message(
                QueueUrl=QUEUE_URL,
                MaxNumberOfMessages=1,
                WaitTimeSeconds=20,
                VisibilityTimeout=5400,  # 90 minutes
                MessageAttributeNames=['All']
            )

            messages = response.get('Messages', [])

            if not messages:
                continue

            for message in messages:
                success = await process_message(message)

                # Delete message from queue if processed successfully
                if success:
                    sqs.delete_message(
                        QueueUrl=QUEUE_URL,
                        ReceiptHandle=message['ReceiptHandle']
                    )

        except Exception as e:
            logger.error(f"Error polling queue: {e}")
            await asyncio.sleep(5)


def main():
    """Main entry point."""
    if not QUEUE_URL or not RESULTS_BUCKET or not SECRETS_ARN:
        logger.error("Missing required environment variables")
        sys.exit(1)

    # Load secrets into environment
    load_secrets()

    # Run worker
    asyncio.run(poll_queue())


if __name__ == '__main__':
    main()
