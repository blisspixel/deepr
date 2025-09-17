"""
Deepr: Automated research pipeline using OpenAI's Deep Research API.

This script provides a command-line interface and webhook server for submitting, tracking, and saving structured research reports. It integrates with OpenAI's Deep Research API and supports automated report generation, formatting, and delivery.
"""

# --- Imports ---
from openai import OpenAI
from flask import Flask, request
from dotenv import load_dotenv
from threading import Thread
from colorama import Fore, Style, init
from docx import Document
from normalize import normalize_markdown
from datetime import datetime, timezone
from docx2pdf import convert
import os
import sys
import re
import json
import time
import uuid
import shlex
import select
import argparse
import requests
import subprocess
import style
import normalize

# --- Initialization ---
# Initialize colorama for colored CLI output (auto-reset after each print)
init(autoreset=True)


# Load environment variables from .env file (.env should contain OPENAI_API_KEY)
from pathlib import Path
env_loaded = load_dotenv()
if not env_loaded or not os.getenv("OPENAI_API_KEY"):
    # Try loading .env from the installed package directory
    package_dir = Path(__file__).parent.resolve()
    env_path = package_dir / ".env"
    if env_path.exists():
        load_dotenv(dotenv_path=env_path)

# Flask app handles webhook callbacks from OpenAI
app = Flask(__name__)

# Global flag to control polling loop for job status
polling_stopped = False
import time
import uuid
import shlex
import select
import argparse
import requests
import subprocess
import style
import normalize

# === CONFIG ===
LOG_DIR = "logs"                             # Directory for logs
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
if not OPENAI_API_KEY:
    raise RuntimeError(
        "\n[ERROR] Missing OpenAI API Key!\n"
        "You must create a .env file in the project directory with the following line:\n"
        "OPENAI_API_KEY=sk-...\n"
        "Refer to the README.md for setup instructions.\n"
        "Exiting."
    )
MODEL = "o3-deep-research-2025-06-26"        # Default model for research
PORT = 5000                                   # Webhook server port
REPORT_DIR = "reports"                       # Directory for output reports
MAX_WAIT = 1800                               # Max wait time for jobs (seconds)
NGROK_PATH = "ngrok"                         # Path to ngrok executable
CLI_ARGS = None                               # CLI arguments placeholder
LOG_FILE = os.path.join(LOG_DIR, "job_log.jsonl")
os.makedirs(LOG_DIR, exist_ok=True)

client = OpenAI(api_key=OPENAI_API_KEY)
os.makedirs(REPORT_DIR, exist_ok=True)

# === LOAD SYSTEM MESSAGE ===
def load_system_message():
    if CLI_ARGS.briefing:
        return CLI_ARGS.briefing
    try:
        with open("system_message.json", "r", encoding="utf-8") as f:
            return json.load(f)["message"]
    except Exception:
        return (
            "You are a professional researcher writing clear, structured, data-informed reports. "
            "Do not include inline links or references in the main body. If necessary, summarize sources in a short appendix. "
            "Use a mix of paragraphs and bullet points where appropriate. Avoid em-dashes and emojis. "
            "Be direct, detailed, and concise—no fluff or filler."
        )

# === START NGROK AND GET PUBLIC URL ===
# Start ngrok and get public URL
def start_ngrok():
    try:
        # Check if ngrok is running before attempting to kill it
        if os.name == 'nt':  # If on Windows
            result = subprocess.run("tasklist /FI \"IMAGENAME eq ngrok.exe\"", shell=True, capture_output=True, text=True)
            if "ngrok.exe" in result.stdout:
                subprocess.run("taskkill /F /IM ngrok.exe", shell=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)  # Suppress output
        else:
            # For Unix-like systems
            result = subprocess.run("pgrep ngrok", shell=True, capture_output=True, text=True)
            if result.stdout.strip():
                subprocess.run("pkill ngrok", shell=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)  # Suppress output

        # Wait to ensure the process is terminated before starting again
        time.sleep(2)

        # Start ngrok tunnel in the background
        ngrok_process = subprocess.Popen([NGROK_PATH, "http", str(PORT)], stdout=subprocess.PIPE, stderr=subprocess.PIPE)

        # Allow some time for ngrok to start and establish the tunnel
        time.sleep(3)

        # Query the ngrok API to retrieve the public URL
        for _ in range(10):  # Retry up to 10 times
            try:
                resp = requests.get("http://127.0.0.1:4040/api/tunnels")
                tunnels = resp.json().get("tunnels", [])
                for t in tunnels:
                    if t.get("public_url", "").startswith("https"):
                        return ngrok_process, f"{t['public_url']}/webhook"
            except Exception as e:
                print(f"{Fore.RED}Error fetching ngrok URL: {e}{Style.RESET_ALL}")
                time.sleep(1)

        raise RuntimeError("Failed to retrieve public URL from ngrok.")
    except Exception as e:
        raise RuntimeError(f"Ngrok startup failed: {e}")

def stop_ngrok(ngrok_process):
    try:
        print(f"{Fore.YELLOW}Stopping ngrok...{Style.RESET_ALL}")
        ngrok_process.terminate()  # Terminate the ngrok process
        ngrok_process.wait()  # Wait for ngrok to clean up and stop
        print(f"{Fore.GREEN}ngrok stopped successfully.{Style.RESET_ALL}")
    except Exception as e:
        print(f"{Fore.RED}Error stopping ngrok: {e}{Style.RESET_ALL}")

def clarify_prompt(prompt):
    """Returns clarification questions for the user to answer."""
    instructions = """
You are helping a user define a research prompt.

Your goal is to ask 2–3 concise, high-leverage clarifying questions that will help shape the scope of the research.

Ask only what is necessary. Do not generate the refined prompt yet.
""".strip()

    try:
        response = client.chat.completions.create(
            model="gpt-5",
            messages=[
                {"role": "system", "content": instructions},
                {"role": "user", "content": prompt}
            ]
        )
        return response.choices[0].message.content.strip()
    except Exception as e:
        print(f"{Fore.YELLOW}Warning: Failed to generate clarification questions. Skipping...{Style.RESET_ALL}")
        return None

def refine_prompt(prompt, user_clarification=None):
    """Rewrites a vague or underspecified research query into a detailed, actionable request for the Research Agent, including clarification and user answers."""

    instructions = """
You are refining a research prompt. Your task is to take the user's original query, incorporate any clarifying questions and answers, and transform them into a refined research request. This refined request will be given to the Research Agent to search online and build a detailed report.

Guidelines:
- Make sure the prompt is **specific** and **clear** without any ambiguity.
- Organize the research query logically, with **clear objectives**.
- **Include** any additional context or clarification provided by the user.
- Format the request in **Markdown** with clear sections and bullet points where helpful.
- The research request should focus on **what needs to be researched** without including any instructions for the Research Agent.
- The **final output** should be only the research request, ready to be used by the Research Agent to perform the task.

The Research Agent will use this prompt to search for data and build a detailed, data-driven report. Ensure the query is detailed enough for the agent to begin searching without needing additional clarification.
""".strip()

    # If the user has provided clarifications, include them in the refined request
    if user_clarification:
        # If clarification is empty, simply proceed without adding it
        if not user_clarification.strip():
            print(f"{Fore.YELLOW}Warning: No clarification provided. Proceeding with the original prompt.{Style.RESET_ALL}")
            detailed_prompt = f"Original prompt:\n{prompt}\n\nClarification: No additional details provided."
        else:
            detailed_prompt = f"Original prompt:\n{prompt}\n\nClarifying questions and answers:\n{user_clarification}"
    else:
        # If no clarification is provided, continue with the original prompt
        detailed_prompt = prompt

    try:
        # Combine instructions, original query, and clarification (if available)
        messages = [{"role": "system", "content": instructions}]
        messages.append({"role": "user", "content": detailed_prompt})

        # Send the combined information to OpenAI to get the refined prompt
        response = client.chat.completions.create(
            model="gpt-5",
            messages=messages
        )
        refined = response.choices[0].message.content.strip()

        # Output the refined research request for clarity
        print(f"{Fore.CYAN}Refined Research Request:{Style.RESET_ALL}\n{refined}\n")

        # Return the refined research request, which will be used by the Research Agent
        return refined
    except Exception as e:
        print(f"{Fore.YELLOW}Warning: Prompt refinement failed. Using original prompt.{Style.RESET_ALL}")
        return prompt

def convert_docx_to_pdf(docx_path):
    try:
        # Attempt to convert DOCX to PDF using docx2pdf
        convert(docx_path)
        print(f"PDF successfully created for {docx_path}")
    except Exception as e:
        # Handle any exceptions or errors that arise
        print(f"PDF conversion failed: {e}")
        return None
    return f"{docx_path.replace('.docx', '.pdf')}"

def generate_report_title(prompt):
    try:
        response = client.chat.completions.create(
            model="gpt-5",
            messages=[
                {
                    "role": "system",
                    "content": (
                        "You are a professional assistant. Generate a clear, topic-specific title for a structured research report, "
                        "and a separate filename that is safe for all operating systems.\n\n"
                        "- The display title should be human-readable and appropriate to the subject—avoid using generic labels like 'Business Report' unless the topic is explicitly business-related.\n"
                        "- The filename must contain no spaces, underscores, or punctuation other than alphanumerics.\n"
                        "- Capitalize each word in the filename and concatenate them without separators.\n"
                        "- Strip illegal characters from both fields (e.g., slashes, colons, quotes, parentheses, etc)."
                    )
                }
            ],
            function_call="auto"
        )

        args = json.loads(response.choices[0].message.function_call.arguments)

        # Sanitize title (safe for display and docx headers)
        raw_title = args.get("title", "Untitled Report").strip()
        clean_title = re.sub(r'[<>:"/\\|?*\n\r\t]', "", raw_title)

        # Sanitize filename (strict for filesystems)
        raw_filename = args.get("filename", "UntitledReport")
        clean_filename = re.sub(r"[^A-Za-z0-9]", "", raw_filename.strip())
        if not clean_filename:
            clean_filename = f"Report{str(uuid.uuid4())[:8]}"
        clean_filename = clean_filename[:100]  # Limit length to avoid Windows path limits

        return clean_title, clean_filename

    except Exception as e:
        print(f"{Fore.YELLOW}Warning: Failed to generate report title. Using fallback.{Style.RESET_ALL}")
        fallback_title = "Untitled Report"
        fallback_filename = f"Report{str(uuid.uuid4())[:8]}"
        return fallback_title, fallback_filename

def extract_links(text):
    """Extract all unique URLs from the text body."""
    url_pattern = r"https?://[^\s\)\]]+"
    return re.findall(url_pattern, text)

def get_output_paths(base):
    return {
        "txt": f"{base}.txt",
        "md": f"{base}.md",
        "json": f"{base}.json",
        "docx": f"{base}.docx"
    }

def save_output(run_id, data):
    metadata = data.get("metadata", {})
    report_title = metadata.get("report_title", "Untitled Report")
    filename_safe = metadata.get("filename_safe", f"Report{run_id}")
    filename_base = os.path.join(REPORT_DIR, filename_safe)

    # Extract raw text from OpenAI response structure
    text_parts = []
    for item in data.get("output", []):
        if item.get("type") == "message":
            for part in item.get("content", []):
                if part.get("type") == "output_text":
                    text_parts.append(part["text"])

    full_text = "\n\n".join(text_parts).strip()
    if not full_text:
        print(f"{Fore.YELLOW}No content to save.{Style.RESET_ALL}")
        return

    # === Step 1: Save RAW Text (No Normalization) ===
    with open(f"{filename_base}.txt", "w", encoding="utf-8") as f:
        f.write(full_text)

    # === Step 2: Normalize the Markdown for .md and .docx ===
    md_text = normalize_markdown(full_text)  # Normalize markdown content

    # === Step 3: Save Normalized Markdown to .md file ===
    with open(f"{filename_base}.md", "w", encoding="utf-8") as f:
        f.write(f"# {report_title}\n\n{md_text}")

    # === Step 4: Save Word Document (DOCX) ===
    doc = Document()
    para = doc.add_paragraph(report_title, style="Heading 1")
    style.format_paragraph(para, spacing_after=12)  # Use style.py's format_paragraph

    # Apply styles to the normalized markdown text using style.py
    style.apply_styles_to_doc(doc, md_text)  # Apply styles here using style.py

    # Save the .docx file
    docx_path = f"{filename_base}.docx"
    doc.save(docx_path)

    # === Step 5: Convert DOCX to PDF (if needed) ===
    pdf_path = None
    if not CLI_ARGS.no_pdf:  # Only convert to PDF if not skipped
        try:
            # Convert DOCX to PDF
            pdf_path = convert_docx_to_pdf(docx_path)
        except Exception as e:
            print(f"{Fore.YELLOW}PDF conversion failed: {e}{Style.RESET_ALL}")

    # Print all saved paths, ensuring DOCX comes before PDF in the logs
    print(f"{Fore.GREEN}Final report saved to:{Style.RESET_ALL}")
    print(f"{Fore.CYAN}- {filename_base}.txt")
    print(f"{Fore.CYAN}- {filename_base}.json")
    print(f"{Fore.CYAN}- {filename_base}.md")
    print(f"{Fore.CYAN}- {docx_path}")
    if pdf_path:
        print(f"{Fore.CYAN}- {pdf_path}")  # Only show PDF if successfully created
    print(f"{Fore.GREEN}Research complete.{Style.RESET_ALL}")

def log_job_submission(run_id, response_id, original_prompt, refined_prompt=None):
    log_entry = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "run_id": run_id,
        "response_id": response_id,
        "original_prompt": original_prompt,
        "status": "queued"  # Job is queued initially
    }

    # Include the refined prompt only if it differs
    if refined_prompt and refined_prompt.strip() != original_prompt.strip():
        log_entry["refined_prompt"] = refined_prompt.strip()

    try:
        with open(LOG_FILE, "a", encoding="utf-8") as f:
            f.write(json.dumps(log_entry) + "\n")
    except Exception as e:
        print(f"{Fore.RED}Failed to write job log: {e}{Style.RESET_ALL}")

def update_job_status(response_id, new_status):
    try:
        updated_lines = []
        with open(LOG_FILE, "r", encoding="utf-8") as f:
            for line in f:
                try:
                    entry = json.loads(line)
                    if entry.get("response_id") == response_id:
                        entry["status"] = new_status
                        line = json.dumps(entry)
                    updated_lines.append(line + "\n")
                except Exception:
                    updated_lines.append(line)
        with open(LOG_FILE, "w", encoding="utf-8") as f:
            f.writelines(updated_lines)
    except Exception as e:
        print(f"{Fore.RED}Failed to update job log status: {e}{Style.RESET_ALL}")

def build_tool_config(force_web_search=False):
    tools = []
    if force_web_search or not CLI_ARGS.no_web_search:
        tools.append({"type": "web_search_preview"})
    if not CLI_ARGS.cost_sensitive:
        tools.append({"type": "code_interpreter", "container": {"type": "auto"}})
    return tools

# === SUBMIT RESEARCH ===
def submit_research_query(prompt, webhook_url, force_web_search=False):
    run_id = str(uuid.uuid4())
    print(f"{Fore.CYAN}Submitting research to OpenAI...{Style.RESET_ALL}")

    try:
        # Determine whether to refine prompt
        if CLI_ARGS.research or CLI_ARGS.batch_file:
            final_prompt = prompt  # Skip refinement for scripted use
        else:
            final_prompt = prompt if CLI_ARGS.raw else refine_prompt(prompt)

        # Determine report title and filename
        if CLI_ARGS.output_title:
            report_title = CLI_ARGS.output_title.strip()
            words = re.findall(r"[A-Za-z0-9]+", report_title)
            filename_safe = ''.join(word.capitalize() for word in words)

        else:
            report_title, filename_safe = generate_report_title(final_prompt)
            # If filename_safe is missing or generic, use sanitized original prompt
            if not filename_safe or filename_safe.startswith("Report"):
                # Sanitize original prompt for filename: remove non-alphanumerics, capitalize words, limit length
                words = re.findall(r"[A-Za-z0-9]+", prompt)
                prompt_filename = ''.join(word.capitalize() for word in words)
                if prompt_filename:
                    filename_safe = prompt_filename[:100]
                else:
                    filename_safe = f"Report{str(uuid.uuid4())[:8]}"

        print(f"{Fore.GREEN}Report title: {report_title}{Style.RESET_ALL}")
        print(f"{Fore.GREEN}Filename base: {filename_safe}{Style.RESET_ALL}")

        # Configure tools
        tool_config = build_tool_config(force_web_search=force_web_search)
        model = "o4-mini-deep-research" if CLI_ARGS.cost_sensitive else MODEL
        max_tool_calls = 5 if CLI_ARGS.cost_sensitive else None

        # Build the request payload
        request_payload = {
            "model": model,
            "input": [
                {
                    "role": "developer",
                    "content": [{"type": "input_text", "text": load_system_message()}]
                },
                {
                    "role": "user",
                    "content": [{"type": "input_text", "text": final_prompt}]
                }
            ],
            "reasoning": {"summary": "auto"},
            "tools": tool_config,
            "tool_choice": "auto",
            "metadata": {
                "run_id": run_id,
                "report_title": report_title,
                "filename_safe": filename_safe
            },
            "extra_headers": {"OpenAI-Hook-URL": webhook_url},
            "store": True,
            "background": True
        }

        # Include max_tool_calls only if tools are present
        if tool_config and max_tool_calls is not None:
            request_payload["max_tool_calls"] = max_tool_calls

        # Submit the request
        response = client.responses.create(**request_payload)

        print(f"{Fore.GREEN}Submitted successfully. Response ID: {response.id}{Style.RESET_ALL}")

        # Log the job submission as queued
        log_job_submission(run_id, response.id, prompt, refined_prompt=final_prompt)

        return response.id

    except Exception as e:
        print(f"{Fore.RED}Submission failed: {e}{Style.RESET_ALL}")
        return None

def generate_time_estimate(prompt):
    """Uses LLM to estimate how long the research task will take based on complexity of the prompt."""
    try:
        instructions = """
        You are an assistant estimating the time required for a research task based on the prompt. The result will likely be 1-2 pages, 3-10 pages, or 10+ pages.

        Please analyze the research prompt and return an estimated time it will take to complete the research and generate a report. The time should correspond to:
        - 1-2 pages = 1-3 minutes
        - 3-10 pages = 3-5 minutes
        - 10+ pages = 5-30 minutes
        
        Example: 
        Research Prompt: 'What is the impact of AI on the future of healthcare?'
        Estimated Time: '3-5 minutes'

        Research Prompt: '{prompt}'
        Estimated Time:
        """.strip()

        response = client.chat.completions.create(
            model="gpt-4", 
            messages=[{"role": "user", "content": instructions.format(prompt=prompt)}]
        )
        
        # Get the estimated time output
        time_estimate = response.choices[0].message.content.strip()
        return time_estimate

    except Exception as e:
        print(f"{Fore.RED}Error generating time estimate: {e}{Style.RESET_ALL}")
        return "Unknown"  # Fallback in case of error

def clean_message(message):
    # Remove leading/trailing whitespace and quotes if present
    message = message.strip()  # Clean the leading and trailing whitespace
    if message.startswith('"') and message.endswith('"'):
        message = message[1:-1]  # Strip the leading and trailing quotes
    return message

def generate_waiting_message(research_request):
    """Generates a clever and casual one-liner with the time estimate from LLM."""
    time_estimate = generate_time_estimate(research_request)  # Get time estimate from LLM

    # Construct the prompt for the LLM to generate a clever waiting message
    prompt = f"Write a clever and fun one-liner telling the user that their research request: '{research_request}' will take approximately {time_estimate}. Keep it light-hearted and engaging, like: 'Hang tight, we’re working on it!'"

    try:
        response = client.chat.completions.create(
            model="gpt-4",  # Using GPT-4 to generate the waiting message
            messages=[{"role": "user", "content": prompt}]
        )
        waiting_message = response.choices[0].message.content.strip()

        # Clean up the message to remove unnecessary quotes
        waiting_message = clean_message(waiting_message)

        return waiting_message

    except Exception as e:
        print(f"{Fore.YELLOW}Warning: Failed to generate clever waiting message. Using fallback.{Style.RESET_ALL}")
        return f"Hold tight! We're working on it. This will take about {time_estimate}. Please be patient while we process your request."

def download_report(job_id, retries=5, delay=30):
    """
    Tries to download the report for a given job ID with retries if an error occurs.
    After downloading, it will automatically normalize, style, and save the report in multiple formats.
    """
    print(f"{Fore.CYAN}Fetching report for job ID: {job_id}{Style.RESET_ALL}")
    
    attempt = 0
    while attempt < retries:
        try:
            # Attempt to retrieve the report
            response = client.responses.retrieve(job_id)
            
            # Check if the job is completed
            if response.status != "completed":
                print(f"{Fore.YELLOW}Job status is {response.status}. Only completed jobs can be downloaded.{Style.RESET_ALL}")
                time.sleep(delay)  # Add a small delay before retrying
                attempt += 1
                continue  # Retry fetching the report if not completed

            blocks = response.output or []
            texts = [block.content[0].text for block in blocks if block.type == "message"]

            # If there is no content in the response
            if not texts:
                print(f"{Fore.YELLOW}No output found in this job.{Style.RESET_ALL}")
                return

            final_text = "\n\n".join(texts)

            # === STEP 1: Normalize the Text ===
            normalized_text = normalize.normalize_markdown(final_text)

            # === STEP 2: Use the existing save_output pipeline to save the report in multiple formats ===
            metadata = response.metadata  # Getting metadata (title, filename)
            
            # Pass it to the save_output function to apply styling, normalization, and save in multiple formats.
            save_output(job_id, {
                "metadata": metadata,
                "output": [{"type": "message", "content": [{"type": "output_text", "text": normalized_text}]}]
            })

            return  # Exit after successfully saving the report

        except Exception as e:
            # Print the error message for debugging
            print(f"{Fore.RED}Error occurred during download: {e}{Style.RESET_ALL}")
            
            # Retry logic if download fails
            attempt += 1
            if attempt < retries:
                print(f"{Fore.YELLOW}Retrying download... (Attempt {attempt}/{retries})")
                time.sleep(delay)  # Wait before retrying
            else:
                print(f"{Fore.RED}Max retries reached. Unable to download the report after {retries} attempts.{Style.RESET_ALL}")
                return

def poll_status(run_id, research_request, max_wait=1800):  # max wait 30 minutes
    global polling_stopped  # Use global flag to manage polling state

    start_time = time.time()
    print(f"Job in Queue, ID: {run_id}")

    # Initial waiting message based on the research request
    waiting_message = generate_waiting_message(research_request)
    print(f"{Fore.LIGHTCYAN_EX}{waiting_message}{Style.RESET_ALL}")

    last_status = "queued"  # Track the last known status to avoid repeated logging
    in_progress_displayed = False  # Flag to track if 'In progress' message was displayed

    while time.time() - start_time < max_wait:
        if polling_stopped:  # Stop polling if webhook completion was received
            print("\nPolling stopped due to webhook update.")
            return

        try:
            elapsed = int(time.time() - start_time)
            minutes = elapsed // 60
            seconds = elapsed % 60

            # Update elapsed time every second
            sys.stdout.write(f"\rElapsed time: {minutes:02}:{seconds:02}")
            sys.stdout.flush()  # Refresh the output every time

            # Only poll every 30 seconds to avoid spamming the API
            if elapsed % 30 == 0:
                # Retrieve job status from OpenAI API
                result = client.responses.retrieve(run_id)

                if result is None or not hasattr(result, 'status'):
                    print(f"\n{Fore.RED}Error: No valid response received. Please check the request.{Style.RESET_ALL}")
                    return

                status = result.status

                # Only update and print status if it has changed
                if status != last_status:
                    # Display "In progress" once
                    if status == "in_progress" and not in_progress_displayed:
                        print(f"\n{Fore.GREEN}Job is now in progress...{Style.RESET_ALL}")
                        in_progress_displayed = True
                    
                    sys.stdout.write(f"\rStatus: {status.capitalize()} | Elapsed time: {minutes:02}:{seconds:02}")
                    sys.stdout.flush()  # Refresh the output every time
                    last_status = status  # Update last status to current

                # Handle job completion and retrieve results
                if status == "completed":
                    print(f"\n{Fore.GREEN}Research complete. Waiting 5 seconds before fetching results.\n{Style.RESET_ALL}")
                    time.sleep(5)  # Delay before fetching results

                    try:
                        # Try downloading the report, with retries if needed
                        download_report(run_id)
                        update_job_status(run_id, "completed")
                    except Exception as e:
                        print(f"{Fore.RED}Error retrieving final output: {e}{Style.RESET_ALL}")
                    return

                elif status in {"failed", "cancelled", "expired"}:
                    print(f"\n{Fore.RED}Research {status}. Status: {status}{Style.RESET_ALL}")
                    update_job_status(run_id, status)
                    return

            # Wait 1 second before continuing the loop to update elapsed time
            time.sleep(1)

        except Exception as e:
            print(f"\n{Fore.RED}Polling error: {e}{Style.RESET_ALL}")
            time.sleep(30)  # Retry after a small delay if an error occurs

@app.route("/webhook", methods=["POST"])
def webhook():
    global polling_stopped  # Access global polling state

    data = request.json
    run_id = data.get("metadata", {}).get("run_id", "unknown")
    status = data.get("status", "unknown")

    print(f"\n{Fore.BLUE}[{datetime.now()}] Webhook update for run {run_id}:{Style.RESET_ALL}")

    if data.get("output"):
        # Save output only when status is truly completed
        save_output(run_id, data)
        update_job_status(run_id, "completed")
        polling_stopped = True  # Stop polling once the job is completed via webhook
    elif status in ["cancelled", "failed", "expired"]:
        print(f"{Fore.RED}Job {run_id} ended with status: {status}{Style.RESET_ALL}")
        update_job_status(run_id, status)
        polling_stopped = True  # Stop polling when the job is failed or cancelled
    else:
        print(f"{Fore.YELLOW}Webhook received but no output available yet. Status: {status}{Style.RESET_ALL}")

    return "", 200

# === WEBHOOK SERVER ===
def start_webhook_server():
    print(f"{Fore.YELLOW}Starting webhook server on port {PORT}...{Style.RESET_ALL}")
    app.run(host="0.0.0.0", port=PORT)

# === CLI ===
def main(CLI_ARGS):
    print(f"{Fore.GREEN}=== Deepr CLI OpenAI Deep Research ==={Style.RESET_ALL}")

    try:
        # Start ngrok and capture the process object
        ngrok_process = start_ngrok()

        # Fetch the public URL from ngrok process
        webhook_url = None
        for _ in range(10):  # Retry up to 10 times
            try:
                resp = requests.get("http://127.0.0.1:4040/api/tunnels")
                tunnels = resp.json().get("tunnels", [])
                for t in tunnels:
                    if t.get("public_url", "").startswith("https"):
                        webhook_url = f"{t['public_url']}/webhook"
                        break
                if webhook_url:
                    break
            except Exception as e:
                print(f"{Fore.RED}Error fetching ngrok URL: {e}{Style.RESET_ALL}")
                time.sleep(1)

        if not webhook_url:
            raise RuntimeError("Failed to retrieve public URL from ngrok.")

        print(f"{Fore.CYAN}Webhook URL: {webhook_url}{Style.RESET_ALL}")

    except Exception as e:
        print(f"{Fore.RED}{e}{Style.RESET_ALL}")
        return

    if CLI_ARGS.briefing:
        print(f"{Fore.YELLOW}Using custom system message override (--briefing):{Style.RESET_ALL}")
        print(f"{CLI_ARGS.briefing.strip()}\n")

    if CLI_ARGS.batch_file:
        if not os.path.isfile(CLI_ARGS.batch_file):
            print(f"{Fore.RED}Batch file not found: {CLI_ARGS.batch_file}{Style.RESET_ALL}")
            return
        try:
            with open(CLI_ARGS.batch_file, "r", encoding="utf-8") as f:
                prompts = [line.strip() for line in f if line.strip()]
            print(f"{Fore.CYAN}Running batch of {len(prompts)} prompts...{Style.RESET_ALL}")
            for i, prompt in enumerate(prompts, 1):
                print(f"\n{Fore.MAGENTA}[Batch {i}/{len(prompts)}]{Style.RESET_ALL}")
                response_id = submit_research_query(prompt, webhook_url)
                if response_id:
                    print(f"{Fore.YELLOW}Tracking job status for Response ID: {response_id}{Style.RESET_ALL}")
                    status = poll_status(response_id, prompt)
                    if status == "failed":
                        print(f"{Fore.YELLOW}Job failed. Pausing for 5 minutes before retrying...{Style.RESET_ALL}")
                        time.sleep(300)
                        print(f"{Fore.YELLOW}Retrying failed prompt...{Style.RESET_ALL}")
                        response_id_retry = submit_research_query(prompt, webhook_url)
                        if response_id_retry:
                            print(f"{Fore.YELLOW}Tracking job status for Response ID: {response_id_retry}{Style.RESET_ALL}")
                            poll_status(response_id_retry, prompt)
                        else:
                            print(f"{Fore.RED}Retry submission failed for prompt {i}.{Style.RESET_ALL}")
                else:
                    print(f"{Fore.RED}Submission failed for prompt {i}.{Style.RESET_ALL}")
                # Pause every 5 prompts for 3 minutes
                if i % 5 == 0 and i != len(prompts):
                    print(f"{Fore.YELLOW}Pausing for 3 minutes to avoid rate limits...{Style.RESET_ALL}")
                    time.sleep(180)
        except Exception as e:
            print(f"{Fore.RED}Failed to process batch file: {e}{Style.RESET_ALL}")
        return

    if CLI_ARGS.research:
        response_id = submit_research_query(CLI_ARGS.research, webhook_url)
        if response_id:
            print(f"{Fore.YELLOW}Tracking job status for Response ID: {response_id}{Style.RESET_ALL}")
            poll_status(response_id, CLI_ARGS.research)  # Pass CLI_ARGS.research as research_request
        else:
            print(f"{Fore.RED}Research task did not start successfully.{Style.RESET_ALL}")
        return

    print(f"{Fore.CYAN}Paste your research prompt (multi-line supported). Type 'DEEPR' on its own line to submit:{Style.RESET_ALL}")
    lines = []
    while True:
        try:
            line = input()
            if line.strip().upper() == "DEEPR":
                break
            lines.append(line)
        except EOFError:
            break

    if not lines:
        print(f"{Fore.RED}No input provided. Exiting.{Style.RESET_ALL}")
        return

    prompt = "\n".join(lines).strip()

    if not CLI_ARGS.cost_sensitive:
        cost = input("Use cost-sensitive mode (lower cost, fewer resources)? (y/N, Enter for No): ").strip().lower()
        if cost == "y" or cost == "":
            CLI_ARGS.cost_sensitive = True

    if not CLI_ARGS.raw:
        clarify = input("Would you like to clarify and refine this prompt with GPT-5? (Yes or Enter for Yes, n for No): ").strip().lower()
        if clarify in ("y", "yes", ""):
            questions = clarify_prompt(prompt)
            if questions:
                print(f"\n{Fore.CYAN}GPT-5 asks for clarification:{Style.RESET_ALL}\n{questions}\n")
                print(f"{Fore.CYAN}Enter your clarification below (press DEEPR when done):{Style.RESET_ALL}")
                clarification_lines = []
                while True:
                    line = input()
                    if line.strip().upper() == "DEEPR":
                        break
                    clarification_lines.append(line)
                user_clarification = "\n".join(clarification_lines).strip()
                if user_clarification:
                    print(f"{Fore.YELLOW}Processing your clarification...{Style.RESET_ALL}")
                    prompt = refine_prompt(prompt, user_clarification=user_clarification)
                else:
                    print(f"{Fore.RED}No clarification entered. Proceeding with original prompt.{Style.RESET_ALL}")
            else:
                print(f"{Fore.YELLOW}Clarification not needed. Proceeding with refining prompt...{Style.RESET_ALL}")
                prompt = refine_prompt(prompt)

    if not CLI_ARGS.append_references:
        refs = input("Append extracted URLs as references at the end? (y/N, Enter for No): ").strip().lower()
        if refs == "y" or refs == "":
            CLI_ARGS.append_references = True

    print(f"\n{Fore.CYAN}=== Review the Research Request ==={Style.RESET_ALL}")
    print(f"Research Request: {prompt}")
    print(f"\n{Fore.CYAN}=== Selected Options ==={Style.RESET_ALL}")
    print(f"Cost-sensitive mode: {'Yes' if CLI_ARGS.cost_sensitive else 'No'}")
    print(f"Clarification applied: {'Yes' if clarify != 'n' and clarify != '' else 'No'}")
    print(f"Append references: {'Yes' if CLI_ARGS.append_references else 'No'}")

    confirm = input(f"\nGo ahead with the research? Press Enter to confirm or 'n' to revise: ").strip().lower()
    if confirm == "n":
        print(f"{Fore.YELLOW}Prompt revision canceled. You can make edits to the prompt before submitting.{Style.RESET_ALL}")
        return

    response_id = submit_research_query(prompt, webhook_url, force_web_search=True)
    if response_id:
        print(f"{Fore.YELLOW}Tracking job status for Response ID: {response_id}{Style.RESET_ALL}")
        poll_status(response_id, prompt)  # Pass prompt as research_request

        flattened_prompt = prompt.replace('\n', ' ').strip()
        escaped_prompt = flattened_prompt.replace('"', '\\"')
        suggested_cmd = f'python {os.path.basename(__file__)} --research "{escaped_prompt}"'

        if CLI_ARGS.raw:
            suggested_cmd += " --raw"
        if CLI_ARGS.cost_sensitive:
            suggested_cmd += " --cost-sensitive"
        if CLI_ARGS.append_references:
            suggested_cmd += " --append-references"
        if CLI_ARGS.output_title:
            safe_output_title = CLI_ARGS.output_title.strip().replace('"', '\\"')
            suggested_cmd += f' --output-title "{safe_output_title}"'
        if CLI_ARGS.briefing:
            safe_briefing = CLI_ARGS.briefing.strip().replace('"', '\\"')
            suggested_cmd += f' --briefing "{safe_briefing}"'
        if CLI_ARGS.no_web_search:
            suggested_cmd += " --no-web-search"

        print(f"\n{Fore.GREEN}To run this same task directly next time, use:{Style.RESET_ALL}")
        print(f"{Fore.CYAN}{suggested_cmd}{Style.RESET_ALL}\n")
    else:
        print(f"{Fore.RED}Research task did not start successfully.{Style.RESET_ALL}")

    # Stop ngrok after all tasks are done
    ngrok_process, webhook_url = start_ngrok()  # Ensure ngrok is stopped after all tasks complete


# === CLI ENTRY POINT FOR CONSOLE_SCRIPTS ===
def cli_entry():
    parser = argparse.ArgumentParser(
        prog="deepr",
        description="Deepr: Automated research pipeline using OpenAI's Deep Research API.\n\n"
                    "Usage: deepr [options]\n\n"
                    "Examples:\n"
                    "  deepr --research 'What are the top AI trends for 2025?'\n"
                    "  deepr --batch-file prompts.txt --cost-sensitive\n\n"
                    "For full documentation, see the README.md."
    )
    parser.add_argument("--research", type=str, metavar="PROMPT", help="Submit a single research topic (non-interactive)")
    parser.add_argument("--raw", action="store_true", help="Skip prompt refinement and submit original input")
    parser.add_argument("--briefing", type=str, metavar="TEXT", help="Override system_message.json at runtime")
    parser.add_argument("--batch-file", type=str, metavar="FILE", help="Path to a .txt or .csv file containing prompts (one per line)")
    parser.add_argument("--cost-sensitive", action="store_true", help="Limit tool usage and model to reduce cost")
    parser.add_argument("--no-web-search", action="store_true", help="Disable web search tool for this run")
    parser.add_argument("--output-title", type=str, metavar="TITLE", help="Optional custom title for output report files")
    parser.add_argument("--append-references", action="store_true", help="Append extracted links at the end under a References section")
    parser.add_argument("--no-pdf", action="store_true", help="Skip PDF generation from the Word document")
    CLI_ARGS = parser.parse_args()
    try:
        main(CLI_ARGS)
    except KeyboardInterrupt:
        print(f"\n{Fore.RED}Interrupted by user. Exiting...{Style.RESET_ALL}")
        sys.exit(1)

# === ENTRY ===
if __name__ == "__main__":
    cli_entry()

