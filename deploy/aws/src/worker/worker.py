"""
AWS Fargate worker for Deepr research jobs.

Polls SQS for jobs, executes research, stores results in S3.
"""

import asyncio
import json
import logging
import os
import sys
from datetime import UTC, datetime

import boto3

logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(name)s - %(levelname)s - %(message)s")
logger = logging.getLogger("deepr.worker")

# AWS clients
sqs = boto3.client("sqs")
s3 = boto3.client("s3")
secrets_client = boto3.client("secretsmanager")
dynamodb = boto3.resource("dynamodb")

QUEUE_URL = os.environ.get("QUEUE_URL")
RESULTS_BUCKET = os.environ.get("RESULTS_BUCKET")
SECRETS_ARN = os.environ.get("SECRETS_ARN")
JOBS_TABLE = os.environ.get("JOBS_TABLE")

# DynamoDB is the API's source of truth for job lifecycle (status,
# cancellation, completion). The worker must read/write DynamoDB rather than
# a parallel S3 metadata.json that the API never creates — otherwise
# cancelled jobs still execute and completed reports never become visible
# to the result endpoint.
jobs_table = dynamodb.Table(JOBS_TABLE) if JOBS_TABLE else None


def load_secrets():
    """Load API keys from Secrets Manager into environment."""
    try:
        response = secrets_client.get_secret_value(SecretId=SECRETS_ARN)
        secrets = json.loads(response["SecretString"])

        for key, value in secrets.items():
            if value:
                os.environ[key] = value

        logger.info("Loaded secrets from Secrets Manager")
    except Exception as e:
        logger.error(f"Failed to load secrets: {e}")
        sys.exit(1)


def update_job_status(job_id: str, status: str, **kwargs):
    """Update job status in DynamoDB (the API's source of truth).

    Previously this wrote to an S3 jobs/{id}/metadata.json object that the
    API never creates, so completed/failed/cancelled state never reached
    the result endpoint. Use DynamoDB UpdateItem instead so the API
    observes cancellations and can serve completed reports.
    """
    if jobs_table is None:
        logger.error("JOBS_TABLE not configured; cannot update job %s", job_id)
        return
    try:
        names = {"#status": "status", "#updated_at": "updated_at"}
        values = {
            ":status": status,
            ":updated_at": datetime.now(UTC).isoformat(),
        }
        sets = ["#status = :status", "#updated_at = :updated_at"]
        for i, (k, v) in enumerate(kwargs.items()):
            placeholder = f"#k{i}"
            value_key = f":v{i}"
            names[placeholder] = k
            values[value_key] = v
            sets.append(f"{placeholder} = {value_key}")

        # Guard against the cancel/complete race: once a user has
        # marked the job cancelled, a late "completed"/"failed" update
        # from this worker must not overwrite that. The worker checks
        # cancellation once at the start of execution, but the multi-hour
        # research window leaves plenty of time for a cancel to land
        # while the call is in flight.
        update_kwargs = dict(
            Key={"job_id": job_id},
            UpdateExpression="SET " + ", ".join(sets),
            ExpressionAttributeNames=names,
            ExpressionAttributeValues=values,
        )
        if status != "cancelled":
            update_kwargs["ConditionExpression"] = "attribute_not_exists(#status) OR #status <> :cancelled_state"
            update_kwargs["ExpressionAttributeValues"] = {
                **values,
                ":cancelled_state": "cancelled",
            }
        try:
            jobs_table.update_item(**update_kwargs)
        except Exception as inner_e:
            # ConditionalCheckFailedException is normal when a cancel
            # raced ahead of completion; log at info level so it's
            # observable without spamming error metrics.
            err_name = getattr(inner_e, "response", {}).get("Error", {}).get("Code", "")
            if err_name == "ConditionalCheckFailedException":
                logger.info(
                    "Skipping %s update for job %s: already cancelled",
                    status,
                    job_id,
                )
                return
            raise
        logger.info("Updated job %s status to %s", job_id, status)
    except Exception as e:
        logger.error("Failed to update job %s status in DynamoDB: %s", job_id, e)


def is_job_cancelled(job_id: str) -> bool:
    """Read the authoritative DynamoDB status to detect cancellation.

    Returns False on lookup failure rather than swallowing the error
    silently — the previous behavior caused cancelled jobs to still call
    paid providers when S3 metadata was unreadable.
    """
    if jobs_table is None:
        return False
    try:
        result = jobs_table.get_item(Key={"job_id": job_id})
        item = result.get("Item")
        if not item:
            return False
        return item.get("status") == "cancelled"
    except Exception as e:
        logger.warning("Could not read DynamoDB status for job %s: %s", job_id, e)
        return False


def save_result(job_id: str, content: str):
    """Save research result to S3 under the prefix the API reads from."""
    s3.put_object(
        Bucket=RESULTS_BUCKET,
        Key=f"results/{job_id}/report.md",
        Body=content.encode("utf-8"),
        ContentType="text/markdown",
    )
    logger.info("Saved result for job %s", job_id)


async def execute_research(job: dict) -> tuple[str, float, int]:
    """Execute research job using Deepr providers."""
    # Import here after secrets are loaded
    from deepr.providers.base import ResearchRequest, ToolConfig
    from deepr.providers.openai_provider import OpenAIProvider

    job_id = job["id"]
    prompt = job["prompt"]
    enable_web_search = job.get("enable_web_search", True)

    # Check for auto-routed jobs with routing decision
    if job.get("auto_routed") and job.get("routing_decision"):
        routing = job["routing_decision"]
        provider_name = routing.get("provider", "openai")
        model = routing.get("model", "o4-mini-deep-research")
        logger.info(f"Auto-routed job {job_id}: {provider_name}/{model} (complexity: {routing.get('complexity')})")
    else:
        model = job.get("model", "o4-mini-deep-research")
        provider_name = job.get("provider", "openai")

    logger.info(f"Executing research job {job_id} with {provider_name}/{model}")

    # Initialize provider based on routing decision
    if provider_name == "xai":
        from deepr.providers.xai_provider import XAIProvider

        provider = XAIProvider()
    elif provider_name == "gemini":
        from deepr.providers.gemini_provider import GeminiProvider

        provider = GeminiProvider()
    else:
        # Default to OpenAI for openai/azure
        provider = OpenAIProvider()

    # Create request
    request = ResearchRequest(
        prompt=prompt,
        model=model,
        system_message="You are a research assistant. Provide comprehensive, citation-backed analysis.",
        tools=[ToolConfig(type="web_search_preview")] if enable_web_search else [],
        background=False,  # Run synchronously in worker
    )

    # Submit and wait for completion
    provider_job_id = await provider.submit_research(request)

    # Poll for completion
    while True:
        status = await provider.get_status(provider_job_id)

        if status.status == "completed":
            return (
                status.content,
                status.usage.total_cost if status.usage else 0,
                status.usage.total_tokens if status.usage else 0,
            )
        elif status.status == "failed":
            raise Exception(f"Research failed: {status.error}")

        await asyncio.sleep(30)  # Poll every 30 seconds


async def process_message(message):
    """Process a single SQS message."""
    try:
        job = json.loads(message["Body"])
        job_id = job["id"]

        logger.info(f"Processing job {job_id}")

        # Check cancellation in DynamoDB before spending any provider call.
        if is_job_cancelled(job_id):
            logger.info("Job %s was cancelled in DynamoDB, skipping provider call", job_id)
            return True

        # Update status to processing
        update_job_status(job_id, "processing", started_at=datetime.now(UTC).isoformat())

        # Execute research
        content, cost, tokens = await execute_research(job)

        # Save result
        save_result(job_id, content)

        # Update status to completed
        update_job_status(
            job_id, "completed", completed_at=datetime.now(UTC).isoformat(), cost=cost, tokens_used=tokens
        )

        logger.info(f"Completed job {job_id} (cost: ${cost:.2f}, tokens: {tokens})")
        return True

    except Exception as e:
        logger.error(f"Failed to process job: {e}")
        job_id = json.loads(message["Body"]).get("id")
        if job_id:
            update_job_status(job_id, "failed", error=str(e))
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
                MessageAttributeNames=["All"],
            )

            messages = response.get("Messages", [])

            if not messages:
                continue

            for message in messages:
                success = await process_message(message)

                # Delete message from queue if processed successfully
                if success:
                    sqs.delete_message(QueueUrl=QUEUE_URL, ReceiptHandle=message["ReceiptHandle"])

        except Exception as e:
            logger.error(f"Error polling queue: {e}")
            await asyncio.sleep(5)


def main():
    """Main entry point."""
    # JOBS_TABLE was previously omitted from this check. Without it the
    # worker would still poll SQS, run paid research jobs, then silently
    # discard the completion update — the API row stayed "queued" forever
    # while the user paid the provider. Fail fast instead.
    missing = [
        name
        for name, value in (
            ("QUEUE_URL", QUEUE_URL),
            ("RESULTS_BUCKET", RESULTS_BUCKET),
            ("SECRETS_ARN", SECRETS_ARN),
            ("JOBS_TABLE", JOBS_TABLE),
        )
        if not value
    ]
    if missing:
        logger.error("Missing required environment variables: %s", ", ".join(missing))
        sys.exit(1)

    # Load secrets into environment
    load_secrets()

    # Run worker
    asyncio.run(poll_queue())


if __name__ == "__main__":
    main()
