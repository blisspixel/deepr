#!/usr/bin/env python
"""
Start the Deepr research agent in the foreground.

This script runs the job polling research agent that:
- Polls the OpenAI API for job status
- Updates the queue when jobs complete
- Saves results to storage
- Tracks costs

Usage:
    python bin/start-research agent.py
    python bin/start-research agent.py --interval 15  # Poll every 15 seconds
"""

import sys
import asyncio
import logging
from pathlib import Path

# Add parent directory to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from deepr.research_agent.poller import run_poller


def main():
    """Start the research agent."""
    import argparse

    parser = argparse.ArgumentParser(description="Start Deepr job research agent")
    parser.add_argument(
        "--interval", "-i",
        type=int,
        default=30,
        help="Poll interval in seconds (default: 30)"
    )
    parser.add_argument(
        "--verbose", "-v",
        action="store_true",
        help="Enable verbose logging"
    )

    args = parser.parse_args()

    # Configure logging
    log_level = logging.DEBUG if args.verbose else logging.INFO
    logging.basicConfig(
        level=log_level,
        format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
    )

    logger = logging.getLogger(__name__)

    logger.info(f"Starting Deepr research agent (poll interval: {args.interval}s)")
    logger.info("Press Ctrl+C to stop")

    try:
        asyncio.run(run_poller(poll_interval=args.interval))
    except KeyboardInterrupt:
        logger.info("\nResearch Agent stopped by user")
        sys.exit(0)
    except Exception as e:
        logger.error(f"Research Agent error: {e}", exc_info=True)
        sys.exit(1)


if __name__ == "__main__":
    main()
