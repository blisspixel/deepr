import os
import json
import time
import argparse
import logging
import pytz
from datetime import datetime
from dotenv import load_dotenv
from colorama import Fore, Style, init
from openai import OpenAI


# --- Initialization and Configuration ---
# Set up colorama for colored CLI output
init(autoreset=True)

# Load environment variables from .env file
load_dotenv()

# Retrieve OpenAI API key from environment
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
if not OPENAI_API_KEY:
    raise RuntimeError("Set OPENAI_API_KEY in your .env file.")

# Initialize OpenAI client
client = OpenAI(api_key=OPENAI_API_KEY)

# Job retention and logging configuration
RETENTION_DAYS = 7  # Number of days to retain completed jobs in log
LOG_DIR = "logs"    # Directory for job logs
LOG_FILE = os.path.join(LOG_DIR, "job_log.jsonl")
os.makedirs(LOG_DIR, exist_ok=True)

# Configure logging to suppress verbose API logs
logging.basicConfig(level=logging.WARNING, format='%(asctime)s - %(levelname)s - %(message)s')

def parse_timestamp(ts_str):
    """
    Parse a timestamp string (ISO 8601 or Unix) and return seconds since epoch (EST).
    Returns 0 if parsing fails.
    """
    try:
        if isinstance(ts_str, str) and 'T' in ts_str:
            dt = datetime.fromisoformat(ts_str)
            est = pytz.timezone('US/Eastern')
            dt = dt.astimezone(est)
            return dt.timestamp()
        if ts_str:
            return float(ts_str)
        return 0
    except Exception as e:
        logging.error(f"Failed to parse timestamp {ts_str}: {e}")
        return 0

def format_local_time(ts):
    """
    Format a Unix timestamp as a human-readable EST datetime string.
    """
    dt = datetime.fromtimestamp(ts, pytz.timezone('US/Eastern'))
    return dt.strftime("%b %d, %I:%M %p").lstrip("0").replace(" 0", " ")

def human_elapsed(created_ts):
    """
    Return elapsed time since created_ts as a human-readable string (e.g., '2h 15m').
    """
    delta = int(time.time() - created_ts)
    hours, remainder = divmod(delta, 3600)
    minutes, _ = divmod(remainder, 60)
    return f"{hours}h {minutes}m" if hours else f"{minutes}m"

def clean_old_completed_jobs():
    """
    Remove completed jobs older than RETENTION_DAYS from the log file.
    Returns the number of jobs cleaned.
    """
    if not os.path.exists(LOG_FILE):
        return 0
    now = time.time()
    cleaned = 0
    retained = []
    with open(LOG_FILE, "r", encoding="utf-8") as f:
        for line in f:
            try:
                entry = json.loads(line)
                ts = parse_timestamp(entry.get("timestamp", ""))
                if entry.get("status") == "completed" and ts < now - RETENTION_DAYS * 86400:
                    cleaned += 1
                    continue
            except Exception:
                pass
            retained.append(line)
    if cleaned:
        with open(LOG_FILE, "w", encoding="utf-8") as f:
            f.writelines(retained)
    return cleaned

def get_prompt_from_log(job_id):
    """
    Retrieve the prompt (original or refined) for a given job ID from the job log.
    Returns 'Prompt Not Available' if not found.
    """
        """
        Search the job log for a given job ID and return the associated prompt.
        Returns the refined prompt if available, otherwise the original prompt.
        Returns 'Prompt Not Available' if the job is not found or log is missing/corrupt.
        """
    log_file = "logs/job_log.jsonl"
    if not os.path.exists(log_file):
        return "Prompt Not Available"
    with open(log_file, "r", encoding="utf-8") as f:
        for line in f:
            try:
                entry = json.loads(line)
                if entry.get("response_id") == job_id:
                    if "refined_prompt" in entry:
                        return entry["refined_prompt"]
                    elif "original_prompt" in entry:
                        return entry["original_prompt"]
            except json.JSONDecodeError:
                continue
    return "Prompt Not Available"

def refresh_job_statuses():
    """
    Update statuses of all jobs in the log by querying the OpenAI API.
    Returns the number of jobs updated.
    """
        """
        Poll the OpenAI API to update the status of all jobs in the log that are not yet completed or cancelled.
        Ensures local job status is consistent with remote state. Returns the number of jobs updated.
        """
    if not os.path.exists(LOG_FILE):
        return
    updated_lines = []
    changed = 0
    with open(LOG_FILE, "r", encoding="utf-8") as f:
        for line in f:
            try:
                entry = json.loads(line)
                if entry.get("status") in ("submitted", "queued", "in_progress", "requires_action"):
                    job_id = entry["response_id"]
                    remote = client.responses.retrieve(job_id)
                    entry["status"] = remote.status
                    changed += 1
                updated_lines.append(json.dumps(entry) + "\n")
            except Exception as e:
                updated_lines.append(line)
    with open(LOG_FILE, "w", encoding="utf-8") as f:
        f.writelines(updated_lines)
    return changed

# Calculate rough cost based on tokens (input + output) and model
def calculate_cost(input_tokens, output_tokens, model):
    input_cost_per_1M = 0
    output_cost_per_1M = 0

    if "o3-deep-research" in model:
        input_cost_per_1M = 2.00  # Input cost for o3-deep-research
        output_cost_per_1M = 8.00  # Output cost for o3-deep-research
    elif "o4-mini-deep-research" in model:
        input_cost_per_1M = 1.10  # Input cost for o4-mini-deep-research
        output_cost_per_1M = 4.40  # Output cost for o4-mini-deep-research

    # Calculate input and output cost
    input_cost = (input_tokens / 1_000_000) * input_cost_per_1M
    output_cost = (output_tokens / 1_000_000) * output_cost_per_1M

    total_cost = round(input_cost + output_cost, 4)  # Total cost rounded to 4 decimal places
    return total_cost
        """
        Estimate the dollar cost of a job based on token usage and model pricing.
        Pricing is hardcoded for supported models. Returns total cost as a float.
        """

def list_jobs(show_all=False, limit=100):
    if not os.path.exists(LOG_FILE):
        print(f"{Fore.YELLOW}No job log found.{Style.RESET_ALL}")
        return []

    jobs = []
    with open(LOG_FILE, "r", encoding="utf-8") as f:
        for line in f:
            try:
                entry = json.loads(line)
                if "response_id" not in entry:
                    continue
                jobs.append(entry)
            except Exception:
                continue

    # Sort jobs by timestamp descending (newest first)
    jobs.sort(key=lambda j: parse_timestamp(j.get("timestamp", "")), reverse=True)

    now = time.time()
    active, completed = [], []

    for job in jobs[:limit]:
        status = job.get("status", "")
        ts = parse_timestamp(job.get("timestamp", ""))
        summary = job.get("prompt", "N/A").strip().replace("\n", " ")[:100]
        info = {
            "id": job["response_id"],
            "status": status,
            "created_ts": ts,
            "created": format_local_time(ts),
            "elapsed": human_elapsed(ts),
            "summary": summary
        }
        if status in ("submitted", "queued", "in_progress", "requires_action"):
            active.append(info)
        elif status == "completed" and job.get("status") != "cancelled":
            completed.append(info)

    if not show_all:
        print(f"\n{Fore.GREEN}Completed Jobs (Last 5):{Style.RESET_ALL}")
        for i, job in enumerate(completed[:5], 1):  # already sorted, so just take first 5
            print(f"{i}. {job['created']}  |  {job['summary']}  [{job['status']}] ({job['elapsed']})")
            print(f"    ID: {Fore.WHITE}{job['id']}{Style.RESET_ALL}")
        print(f"{Fore.WHITE}Job Summary: {len(active)} active, {len(completed)} completed, {len(jobs)} total.{Style.RESET_ALL}")
        return active

    def print_group(label, color, group):
        if not group:
            return
        print(f"\n{color}{label}:{Style.RESET_ALL}")
        for i, job in enumerate(group, 1):
            print(f"{i}. ID       : {job['id']}")
            print(f"   Status   : {job['status']}")
            print(f"   Created  : {job['created']}")
            print(f"   Elapsed  : {job['elapsed']}")
            print(f"   Summary  : {job['summary']}")
            print("-" * 60)

    print_group("Active Jobs", Fore.CYAN, active)
    print_group("Completed Jobs", Fore.GREEN, completed)
    print(f"{Fore.WHITE}Job Summary: {len(active)} active, {len(completed)} completed, {len(jobs)} total.{Style.RESET_ALL}")
    return active + completed
        """
        List jobs from the log file, sorted by creation time (newest first).
        Returns a list of job info dicts. If show_all is False, prints a summary and returns active jobs only.
        Each job dict includes id, status, created time, elapsed time, and summary.
        """

def cancel_job(job_id):
    print(f"{Fore.YELLOW}Attempting to cancel job {job_id}...{Style.RESET_ALL}")
    try:
        client.responses.cancel(job_id)
        print(f"{Fore.RED}Job {job_id} cancelled via API.{Style.RESET_ALL}")
    except Exception as e:
        print(f"{Fore.RED}Failed to cancel job {job_id}: {e}{Style.RESET_ALL}")
        return

    updated = []
    if os.path.exists(LOG_FILE):
        with open(LOG_FILE, "r", encoding="utf-8") as f:
            for line in f:
                try:
                    entry = json.loads(line)
                    if entry.get("response_id") == job_id:
                        entry["status"] = "cancelled"
                        line = json.dumps(entry)
                    updated.append(line + "\n")
                except Exception:
                    updated.append(line)
        with open(LOG_FILE, "w", encoding="utf-8") as f:
            f.writelines(updated)

def download_report(job_id, save=True):
    print(f"{Fore.CYAN}Fetching report for job ID: {job_id}{Style.RESET_ALL}")
    try:
        response = client.responses.retrieve(job_id)
    except Exception as e:
        print(f"{Fore.RED}Failed to retrieve job: {e}{Style.RESET_ALL}")
        return

    if response.status != "completed":
        print(f"{Fore.YELLOW}Job status is {response.status}. Only completed jobs can be downloaded.{Style.RESET_ALL}")
        return

    blocks = response.output or []
    texts = [block.content[0].text for block in blocks if block.type == "message"]

    if not texts:
        print(f"{Fore.YELLOW}No output found in this job.{Style.RESET_ALL}")
        return

    final_text = "\n\n".join(texts)
    print(f"\n{Fore.GREEN}--- Report Output ---{Style.RESET_ALL}\n{final_text[:1000]}")

    if save:
        os.makedirs("reports", exist_ok=True)
        filename = os.path.join("reports", f"report_{job_id}.txt")
        with open(filename, "w", encoding="utf-8") as f:
            f.write(final_text)
        print(f"{Fore.GREEN}Saved report to {filename}{Style.RESET_ALL}")

def view_job_details():
    jobs = list_jobs()  # List jobs and select one
    if not jobs:
        print(f"{Fore.RED}No jobs found.{Style.RESET_ALL}")
        return

    # Asking the user to select a job to view
    print("\nSelect a job to view details:")
    for i, job in enumerate(jobs, 1):
        print(f"{i}. {job['created']} | {job['summary']} | ID: {job['id']}")

    # Get user choice
    choice = input("Enter the job number: ").strip()

    try:
        choice = int(choice)
        if 0 < choice <= len(jobs):
            job = jobs[choice - 1]
            job_id = job['id']  # Get job ID

            # Fetch job details from the API
            try:
                job_details = client.responses.retrieve(job_id)

                # Print job details without showing the output
                print(f"\n{Fore.GREEN}--- Job Details ---{Style.RESET_ALL}")
                print(f"ID         : {job_details.id}")
                print(f"Status     : {job_details.status}")

                # Handle 'created' timestamp (use timestamp from API or fallback to log timestamp)
                created_ts = parse_timestamp(job.get("timestamp", ""))  # Fallback to log timestamp
                if hasattr(job_details, 'created') and job_details.created:
                    created_ts = parse_timestamp(job_details.created)
                print(f"Created    : {format_local_time(created_ts)} ({human_elapsed(created_ts)} ago)")

                # Fetch the prompt from the local log
                prompt = get_prompt_from_log(job_id)
                print(f"Prompt     : {prompt}")

                # Handle the 'usage' object for tokens used
                tokens_used_input = 0
                tokens_used_output = 0
                if hasattr(job_details, 'usage'):
                    tokens_used_input = job_details.usage.input_tokens if hasattr(job_details.usage, 'input_tokens') else 0
                    tokens_used_output = job_details.usage.output_tokens if hasattr(job_details.usage, 'output_tokens') else 0

                cost = calculate_cost(tokens_used_input, tokens_used_output, job_details.model)
                print(f"Tokens Used: {tokens_used_input + tokens_used_output}")
                print(f"Estimated Cost: ${cost}")

            except Exception as e:
                print(f"{Fore.RED}Error fetching job details from the API: {e}{Style.RESET_ALL}")

        else:
            print(f"{Fore.RED}Invalid selection.{Style.RESET_ALL}")
    except ValueError:
        print(f"{Fore.RED}Invalid input.{Style.RESET_ALL}")

def interactive_mode():
    print(f"{Fore.GREEN}Welcome to the Deep Research Job Manager.{Style.RESET_ALL}")
    
    cleaned = clean_old_completed_jobs()
    refreshed = refresh_job_statuses()
    
    if cleaned:
        print(f"{Fore.MAGENTA}Cleaned {cleaned} old completed jobs from the log.{Style.RESET_ALL}")
    if refreshed:
        print(f"{Fore.MAGENTA}Updated {refreshed} job statuses from API.{Style.RESET_ALL}")

    list_jobs()  # Initial summary view

    while True:
        print(f"\n{Fore.CYAN}Choose an action:{Style.RESET_ALL}")
        print("1. View job details")
        print("2. View all jobs")
        print("3. Download report by ID")
        print("4. Cancel a job")
        print("5. Cancel all active jobs")
        print("6. Clear log file")
        print("7. Exit")
        choice = input("Select [1–7]: ").strip()

        if choice == "1":
            view_job_details()

        elif choice == "2":
            list_jobs(show_all=True)

        elif choice == "3":
            job_id = input("Enter job ID to download: ").strip()
            download_report(job_id)

        elif choice == "4":
            jobs = list_jobs()
            if not jobs:
                print(f"{Fore.YELLOW}No jobs available to cancel.{Style.RESET_ALL}")
                continue
            cancel_choice = input("Enter job number or ID: ").strip()
            if cancel_choice.isdigit():
                index = int(cancel_choice) - 1
                if 0 <= index < len(jobs):
                    cancel_job(jobs[index]["id"])
                else:
                    print(f"{Fore.RED}Invalid job number.{Style.RESET_ALL}")
            else:
                cancel_job(cancel_choice)
            list_jobs()

        elif choice == "5":
            jobs = list_jobs()
            for job in jobs:
                cancel_job(job["id"])
            list_jobs()

        elif choice == "6":
            confirm = input("Are you sure you want to clear the job log? [y/N]: ").strip().lower()
            if confirm == "y" and os.path.exists(LOG_FILE):
                os.remove(LOG_FILE)
                print(f"{Fore.RED}Job log cleared.{Style.RESET_ALL}")

        elif choice == "7":
            print(f"{Fore.CYAN}Goodbye.{Style.RESET_ALL}")
            break

        else:
            print(f"{Fore.RED}Invalid selection.{Style.RESET_ALL}")

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Manage Deep Research jobs")
    parser.add_argument("--details", type=str, help="Show full details for a job by ID")
    parser.add_argument("--list", action="store_true", help="List jobs")
    parser.add_argument("--cancel", type=str, help="Cancel job by ID")
    parser.add_argument("--cancel-all", action="store_true", help="Cancel all active jobs")
    parser.add_argument("--download", type=str, help="Download report by ID")
    parser.add_argument("--clear", action="store_true", help="Clear log file")
    parser.add_argument("--all", action="store_true", help="Show all jobs")
    parser.add_argument("--interactive", action="store_true", help="Run interactively")

    args = parser.parse_args()

    if args.clear:
        if os.path.exists(LOG_FILE):
            os.remove(LOG_FILE)
            print(f"{Fore.RED}Job log cleared.{Style.RESET_ALL}")

    elif args.details:
        job_id = args.details
        jobs = []
        if os.path.exists(LOG_FILE):
            with open(LOG_FILE, "r", encoding="utf-8") as f:
                for line in f:
                    try:
                        entry = json.loads(line)
                        if entry.get("response_id") == job_id:
                            jobs.append(entry)
                            break
                    except Exception:
                        continue
        if not jobs:
            print(f"{Fore.RED}Job ID '{job_id}' not found in log.{Style.RESET_ALL}")
        else:
            job = jobs[0]
            print(f"\n{Fore.GREEN}--- Job Details ---{Style.RESET_ALL}")
            print(f"ID         : {job.get('response_id')}")
            print(f"Status     : {job.get('status')}")
            ts = parse_timestamp(job.get("timestamp", ""))
            print(f"Created    : {format_local_time(ts)} ({human_elapsed(ts)} ago)")
            print(f"Model      : {job.get('model', 'N/A')}")
            print(f"Tokens Used: {job.get('usage', {}).get('total_tokens', 'N/A')}")
            print(f"Temperature: {job.get('temperature', 'N/A')}")
            print("\nPrompt:")
            print(job.get("prompt", "N/A")[:1000])
            print("-" * 60)

    elif args.download:
        download_report(args.download)

    elif args.list:
        list_jobs(show_all=args.all)

    elif args.cancel:
        cancel_job(args.cancel)

    elif args.cancel_all:
        jobs = list_jobs()
        for job in jobs:
            cancel_job(job["id"])

    else:
        interactive_mode()
