"""
DEPRECATED - LEGACY VERSION 1.x

This file is preserved for backward compatibility only.
It will be removed in version 3.0.

For NEW CODE, use the modular API:
    from deepr import AppConfig
    from deepr.providers import create_provider
    from deepr.storage import create_storage
    from deepr.core import ResearchOrchestrator

See: docs/migration-guide.md and QUICKSTART_V2.md

---

Deepr: Automated research pipeline using OpenAI's Deep Research API.

This script provides a command-line interface and webhook server for submitting, tracking,
and saving structured research reports. It integrates with OpenAI's Deep Research API and
supports automated report generation, formatting, and delivery.

Preferences honored:
- NO inline citations in the body text.
- Optional "References" section appended at the end (controlled by --append-references).
- Verbose, step-by-step logging for vector store lifecycle (create → attach → ingest → cleanup).
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
from pathlib import Path

import os
import sys
import re
import json
import time
import uuid
import argparse
import requests
import subprocess
import logging
import style
import normalize

# --- Initialization ---
init(autoreset=True)
logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")

# Load environment variables from .env file (.env should contain OPENAI_API_KEY)
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

# === CONFIG ===
LOG_DIR = "logs"                               # Directory for logs
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
if not OPENAI_API_KEY:
    raise RuntimeError(
        "\n[ERROR] Missing OpenAI API Key!\n"
        "You must create a .env file with: OPENAI_API_KEY=sk-...\n"
        "Refer to the README.md for setup instructions.\n"
        "Exiting."
    )
MODEL = "o3-deep-research-2025-06-26"          # Default DR model (use an enabled DR model for your account)
PORT = 5000                                    # Webhook server port
REPORT_DIR = "reports"                         # Directory for output reports
MAX_WAIT = 1800                                # Max wait time for jobs (seconds)
NGROK_PATH = os.getenv("NGROK_PATH", "ngrok")  # Path to ngrok executable
CLI_ARGS = None                                # CLI arguments placeholder
LOG_FILE = os.path.join(LOG_DIR, "job_log.jsonl")
os.makedirs(LOG_DIR, exist_ok=True)

client = OpenAI(api_key=OPENAI_API_KEY)
os.makedirs(REPORT_DIR, exist_ok=True)

# Track live vector stores by run_id for cleanup AFTER completion
ACTIVE_VECTOR_STORES = {}  # run_id -> vector_store_id


# === LOAD SYSTEM MESSAGE ===
def load_system_message():
    """
    System message explicitly enforces NO inline citations.
    """
    if CLI_ARGS and CLI_ARGS.briefing:
        return CLI_ARGS.briefing
    try:
        package_dir = Path(__file__).parent.resolve()
        msg_path = package_dir / "system_message.json"
        if msg_path.exists():
            with open(msg_path, "r", encoding="utf-8") as f:
                return json.load(f)["message"]
        # fallback: try current working directory
        if Path("system_message.json").exists():
            with open("system_message.json", "r", encoding="utf-8") as f:
                return json.load(f)["message"]
    except Exception:
        pass
    return (
        "You are a professional researcher writing clear, structured, data-informed reports. "
        "Do not include inline links, parenthetical citations, numeric bracket citations, or footnote markers in the main body. "
        "If references are needed, provide them as a short 'References' section at the end only. "
        "Use a mix of paragraphs and bullet points where appropriate. Avoid em dashes and emojis. "
        "Be direct, detailed, and concise."
    )


# === UTIL: strip inline citations from body text ===
_CIT_NUMERIC = re.compile(r"\s?\[\d{1,3}\]")
_CIT_URL_PAREN = re.compile(r"\s?\((https?://[^\s)]+)\)")
_CIT_MISC_FOOTNOTE = re.compile(r"\s?\^\d{1,3}")
def remove_inline_citations(text: str) -> str:
    # Remove [1], [23], etc.
    text = _CIT_NUMERIC.sub("", text)
    # Remove (http://...) parenthetical urls
    text = _CIT_URL_PAREN.sub("", text)
    # Remove ^1 ^12 style
    text = _CIT_MISC_FOOTNOTE.sub("", text)
    return text


# === START NGROK AND GET PUBLIC URL ===
def start_ngrok():
    try:
        # Kill any prior ngrok
        if os.name == 'nt':
            subprocess.run("taskkill /F /IM ngrok.exe", shell=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        else:
            subprocess.run("pkill ngrok", shell=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        time.sleep(1)

        # Start ngrok tunnel in the background
        logging.info("Starting ngrok tunnel...")
        ngrok_process = subprocess.Popen([NGROK_PATH, "http", str(PORT)], stdout=subprocess.PIPE, stderr=subprocess.PIPE)

        # Poll the local ngrok API for the public URL
        public_url = None
        for _ in range(60):
            try:
                resp = requests.get("http://127.0.0.1:4040/api/tunnels", timeout=2)
                tunnels = resp.json().get("tunnels", [])
                for t in tunnels:
                    if t.get("public_url", "").startswith("https"):
                        public_url = t["public_url"]
                        break
                if public_url:
                    break
                time.sleep(1)
            except Exception:
                time.sleep(1)

        if not public_url:
            try:
                ngrok_process.terminate()
                ngrok_process.wait(timeout=5)
            except Exception:
                pass
            raise RuntimeError("Failed to retrieve public URL from ngrok.")

        return ngrok_process, f"{public_url}/webhook"

    except Exception as e:
        raise RuntimeError(f"Ngrok startup failed: {e}")


def stop_ngrok(ngrok_process):
    try:
        print(f"{Fore.YELLOW}Stopping ngrok...{Style.RESET_ALL}")
        ngrok_process.terminate()
        ngrok_process.wait(timeout=5)
        print(f"{Fore.GREEN}ngrok stopped successfully.{Style.RESET_ALL}")
    except Exception as e:
        print(f"{Fore.RED}Error stopping ngrok: {e}{Style.RESET_ALL}")


def clarify_prompt(prompt):
    """Returns 2–3 clarifying questions for the user to answer."""
    instructions = """
You are helping a user define a research prompt.

Ask 2–3 concise, high-leverage clarifying questions that will shape the scope of the research.

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
    except Exception:
        print(f"{Fore.YELLOW}Warning: Failed to generate clarification questions. Skipping...{Style.RESET_ALL}")
        return None


def refine_prompt(prompt, user_clarification=None):
    """Rewrites a vague query into a detailed, actionable research request."""
    instructions = """
You are refining a research prompt. Take the user's original query, incorporate any clarifications,
and transform them into a refined research request with clear objectives. Return only the final request in Markdown.
""".strip()

    detailed_prompt = prompt
    if user_clarification:
        if not user_clarification.strip():
            print(f"{Fore.YELLOW}Warning: No clarification provided. Proceeding with the original prompt.{Style.RESET_ALL}")
            detailed_prompt = f"Original prompt:\n{prompt}\n\nClarification: No additional details provided."
        else:
            detailed_prompt = f"Original prompt:\n{prompt}\n\nClarifying questions and answers:\n{user_clarification}"

    try:
        messages = [{"role": "system", "content": instructions},
                    {"role": "user", "content": detailed_prompt}]

        response = client.chat.completions.create(
            model="gpt-5",
            messages=messages
        )
        refined = response.choices[0].message.content.strip()
        print(f"{Fore.CYAN}Refined Research Request:{Style.RESET_ALL}\n{refined}\n")
        return refined
    except Exception:
        print(f"{Fore.YELLOW}Warning: Prompt refinement failed. Using original prompt.{Style.RESET_ALL}")
        return prompt


def convert_docx_to_pdf(docx_path):
    try:
        convert(docx_path)
        print(f"PDF successfully created for {docx_path}")
    except Exception as e:
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
                        "- The display title should be human-readable and appropriate to the subject.\n"
                        "- The filename must contain only alphanumerics, no spaces or punctuation, CamelCase.\n"
                        "- Strip illegal characters from both fields."
                    )
                },
                {"role": "user", "content": prompt}
            ],
            function_call="auto"
        )

        args = json.loads(response.choices[0].message.function_call.arguments)

        raw_title = args.get("title", "Untitled Report").strip()
        clean_title = re.sub(r'[<>:"/\\|?*\n\r\t]', "", raw_title)

        raw_filename = args.get("filename", "UntitledReport")
        clean_filename = re.sub(r"[^A-Za-z0-9]", "", raw_filename.strip())
        if not clean_filename:
            clean_filename = f"Report{str(uuid.uuid4())[:8]}"
        clean_filename = clean_filename[:100]

        return clean_title, clean_filename

    except Exception:
        print(f"{Fore.YELLOW}Warning: Failed to generate report title. Using fallback.{Style.RESET_ALL}")
        fallback_title = "Untitled Report"
        fallback_filename = f"Report{str(uuid.uuid4())[:8]}"
        return fallback_title, fallback_filename


def extract_links(text):
    """Extract all unique URLs from the text body."""
    url_pattern = r"https?://[^\s\)\]]+"
    return sorted(set(re.findall(url_pattern, text)))


def get_output_paths(base):
    return {
        "txt": f"{base}.txt",
        "md": f"{base}.md",
        "json": f"{base}.json",
        "docx": f"{base}.docx"
    }


def save_output(run_id, data):
    """
    Post-process to ensure NO inline citations. Optionally append references
    (only if --append-references was requested).
    """
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

    # Remove inline citations forcibly (defense-in-depth)
    body_text = remove_inline_citations(full_text)

    # Prepare optional References
    references_block = ""
    if CLI_ARGS.append_references:
        links = extract_links(full_text)
        if links:
            references_block = "\n\n## References\n" + "\n".join(f"- {u}" for u in links)

    # Full export text for Markdown/docx (clean body + optional refs)
    export_text = body_text + references_block

    # Step 1: Raw text (body only, no refs)
    with open(f"{filename_base}.txt", "w", encoding="utf-8") as f:
        f.write(body_text)

    # Step 1b: Save raw JSON payload too
    try:
        with open(f"{filename_base}.json", "w", encoding="utf-8") as jf:
            json.dump(data, jf, indent=2)
    except Exception as e:
        print(f"{Fore.YELLOW}Warning: Could not save JSON payload: {e}{Style.RESET_ALL}")

    # Step 2: Normalize Markdown for .md and .docx
    md_text = normalize_markdown(export_text)

    # Step 3: Save normalized Markdown
    with open(f"{filename_base}.md", "w", encoding="utf-8") as f:
        f.write(f"# {report_title}\n\n{md_text}")

    # Step 4: Word document
    doc = Document()
    para = doc.add_paragraph(report_title, style="Heading 1")
    style.format_paragraph(para, spacing_after=12)
    style.apply_styles_to_doc(doc, md_text)
    docx_path = f"{filename_base}.docx"
    doc.save(docx_path)

    # Step 5: Optional PDF
    pdf_path = None
    if not CLI_ARGS.no_pdf:
        try:
            pdf_path = convert_docx_to_pdf(docx_path)
        except Exception as e:
            print(f"{Fore.YELLOW}PDF conversion failed: {e}{Style.RESET_ALL}")

    # Print saved paths
    print(f"{Fore.GREEN}Final report saved to:{Style.RESET_ALL}")
    print(f"{Fore.CYAN}- {filename_base}.txt")
    print(f"{Fore.CYAN}- {filename_base}.json")
    print(f"{Fore.CYAN}- {filename_base}.md")
    print(f"{Fore.CYAN}- {docx_path}")
    if pdf_path:
        print(f"{Fore.CYAN}- {pdf_path}")
    print(f"{Fore.GREEN}Research complete.{Style.RESET_ALL}")


def log_job_submission(run_id, response_id, original_prompt, refined_prompt=None):
    log_entry = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "run_id": run_id,
        "response_id": response_id,
        "original_prompt": original_prompt,
        "status": "queued"
    }
    if refined_prompt and refined_prompt.strip() != original_prompt.strip():
        log_entry["refined_prompt"] = refined_prompt.strip()

    try:
        with open(LOG_FILE, "a", encoding="utf-8") as f:
            f.write(json.dumps(log_entry) + "\n")
    except Exception as e:
        print(f"{Fore.RED}Failed to write job log: {e}{Style.RESET_ALL}")


def update_job_status(run_or_response_id, new_status):
    try:
        if not os.path.exists(LOG_FILE):
            return
        updated_lines = []
        with open(LOG_FILE, "r", encoding="utf-8") as f:
            for line in f:
                try:
                    entry = json.loads(line)
                    if entry.get("response_id") == run_or_response_id or entry.get("run_id") == run_or_response_id:
                        entry["status"] = new_status
                        line = json.dumps(entry)
                    updated_lines.append(line + ("\n" if not line.endswith("\n") else ""))  # ensure newline
                except Exception:
                    updated_lines.append(line if line.endswith("\n") else line + "\n")
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


# ========== File upload helper ==========
def collect_document_refs(openai_client, paths):
    refs = []
    if not paths:
        return refs
    print(f"{Fore.YELLOW}Uploading documents to OpenAI file storage...{Style.RESET_ALL}")
    for p in paths:
        if not os.path.exists(p):
            print(f"{Fore.RED}Document not found: {p}{Style.RESET_ALL}")
            continue
        try:
            with open(p, "rb") as f:
                # assistants purpose is compatible with vector stores
                file_obj = openai_client.files.create(file=f, purpose="assistants")
            refs.append(file_obj.id)
            print(f"{Fore.GREEN}Uploaded: {p} as {file_obj.id}{Style.RESET_ALL}")
        except Exception as e:
            print(f"{Fore.RED}Failed to upload {p}: {e}{Style.RESET_ALL}")
    if refs:
        print(f"{Fore.GREEN}Documents uploaded and ready: {refs}{Style.RESET_ALL}")
    else:
        print(f"{Fore.RED}No valid documents uploaded.{Style.RESET_ALL}")
    return refs


# ===== Vector Store lifecycle (with delayed cleanup) =====
def _cleanup_vector_store_for(run_id: str):
    vs_id = ACTIVE_VECTOR_STORES.pop(run_id, None)
    if vs_id:
        try:
            client.vector_stores.delete(vs_id)
            print(f"{Fore.CYAN}Deleted vector store id={vs_id}{Style.RESET_ALL}")
        except Exception as e:
            print(f"{Fore.YELLOW}Warning: Failed to delete vector store {vs_id}: {e}{Style.RESET_ALL}")


class EphemeralStore:
    def __init__(self, name_prefix: str = "deepr"):
        self.name = f"{name_prefix}-{int(time.time())}"
        self.id = None
        self.file_ids = []

    def __enter__(self):
        vs = client.vector_stores.create(name=self.name)
        self.id = vs.id
        print(f"{Fore.CYAN}Created vector store: {self.name} (id={self.id}){Style.RESET_ALL}")
        return self

    def add_files(self, file_ids):
        print(f"{Fore.CYAN}Attaching files to vector store {self.id}...{Style.RESET_ALL}")
        for fid in file_ids:
            client.vector_stores.files.create(vector_store_id=self.id, file_id=fid)
            self.file_ids.append(fid)
            print(f"{Fore.GREEN}Attached file_id={fid}{Style.RESET_ALL}")

    def wait_ingestion(self, timeout_s=900, poll_s=2.0):
        print(f"{Fore.CYAN}Waiting for ingestion to complete...{Style.RESET_ALL}")
        t0 = time.time()
        while True:
            listing = client.vector_stores.files.list(vector_store_id=self.id)
            states = [(it.id, getattr(it, "status", "completed")) for it in listing.data]
            pending = [s for s in states if s[1] != "completed"]
            if not pending:
                print(f"{Fore.GREEN}Ingestion completed for {len(states)} files{Style.RESET_ALL}")
                return
            if time.time() - t0 > timeout_s:
                raise TimeoutError(f"Ingestion timeout. Pending: {pending[:3]}...")
            time.sleep(poll_s)

    def __exit__(self, exc_type, exc, tb):
        # IMPORTANT: Do NOT delete here; background run still needs the store.
        pass


def _ensure_model_and_tools(selected_model: str, tools: list) -> str:
    """
    DR models require at least one of web_search_preview, mcp, or file_search.
    If none present and user disallowed web, downgrade to a non-DR model.
    """
    is_deep_research = "deep-research" in (selected_model or "")
    has_required_tool = any(t.get("type") in {"web_search_preview", "file_search", "mcp"} for t in (tools or []))

    if is_deep_research and not has_required_tool:
        if CLI_ARGS.no_web_search:
            # User forbids web and there is no file_search; pick a non-DR model
            fallback = "o4-mini"
            print(f"{Fore.YELLOW}No allowed DR tools; falling back to {fallback}.{Style.RESET_ALL}")
            return fallback
        else:
            # Add web search automatically
            tools.append({"type": "web_search_preview"})
            print(f"{Fore.YELLOW}Added web_search_preview to satisfy DR tool requirement.{Style.RESET_ALL}")
            return selected_model
    return selected_model


def submit_research_query(prompt, webhook_url, force_web_search=False, document_refs=None):
    run_id = str(uuid.uuid4())
    print(f"{Fore.CYAN}Submitting research to OpenAI...{Style.RESET_ALL}")
    try:
        if CLI_ARGS.research or CLI_ARGS.batch_file:
            final_prompt = prompt
        else:
            final_prompt = prompt if CLI_ARGS.raw else refine_prompt(prompt)

        if CLI_ARGS.output_title:
            report_title = CLI_ARGS.output_title.strip()
            words = re.findall(r"[A-Za-z0-9]+", report_title)
            filename_safe = ''.join(word.capitalize() for word in words)
        else:
            report_title, filename_safe = generate_report_title(final_prompt)
            if not filename_safe or filename_safe.startswith("Report"):
                words = re.findall(r"[A-Za-z0-9]+", prompt)
                prompt_filename = ''.join(word.capitalize() for word in words)
                if prompt_filename:
                    filename_safe = prompt_filename[:100]
                else:
                    filename_safe = f"Report{str(uuid.uuid4())[:8]}"

        print(f"{Fore.GREEN}Report title: {report_title}{Style.RESET_ALL}")
        print(f"{Fore.GREEN}Filename base: {filename_safe}{Style.RESET_ALL}")

        # --------------- DOC-ONLY path ---------------
        if document_refs:
            with EphemeralStore() as es:
                # Attach uploaded file IDs and wait for ingestion
                es.add_files(document_refs)
                es.wait_ingestion()

                # Tools: file_search required; optionally add web/code if user allowed
                tools = [{"type": "file_search", "vector_store_ids": [es.id]}]
                if force_web_search and not CLI_ARGS.no_web_search:
                    tools.append({"type": "web_search_preview"})
                if not CLI_ARGS.cost_sensitive:
                    tools.append({"type": "code_interpreter", "container": {"type": "auto"}})

                tool_choice = "required"  # ensure it consults file_search

                # Strong instruction set: Use docs, no inline citations; append refs optional (handled in save_output)
                updated_prompt = (
                    "Use ONLY the attached document(s) as source material. Fulfill the user's request EXACTLY. "
                    "Do NOT include inline citations, links, footnotes, bracketed numbers, or parenthetical sources in the body text. "
                    "Preserve headings and basic formatting when relevant to the user's request. "
                    "If the attached files do not contain the necessary content, state that explicitly.\n\n"
                    f"User request:\n{final_prompt}"
                )

                model = "o4-mini-deep-research" if CLI_ARGS.cost_sensitive else MODEL

                # Keep vector store alive for this run (CLEAN UP AFTER completion)
                ACTIVE_VECTOR_STORES[run_id] = es.id

                request_payload = {
                    "model": model,
                    "input": [
                        {"role": "developer", "content": [{"type": "input_text", "text": load_system_message()}]},
                        {"role": "user", "content": [{"type": "input_text", "text": updated_prompt}]}
                    ],
                    "reasoning": {"summary": "auto"},
                    "tools": tools,
                    "tool_choice": tool_choice,
                    "metadata": {
                        "run_id": run_id,
                        "report_title": report_title,
                        "filename_safe": filename_safe
                    },
                    "extra_headers": {"OpenAI-Hook-URL": webhook_url},
                    "store": True,
                    "background": True
                }

                response = client.responses.create(**request_payload)
                print(f"{Fore.GREEN}Submitted successfully. Response ID: {response.id}{Style.RESET_ALL}")

                # Save initial payload (best-effort)
                try:
                    payload = response.model_dump() if hasattr(response, "model_dump") else json.loads(response.json())
                    with open("last_response.json", "w", encoding="utf-8") as f:
                        json.dump(payload, f, indent=2)
                except Exception as e:
                    print(f"{Fore.YELLOW}Warning: Could not save full response payload: {e}{Style.RESET_ALL}")

                log_job_submission(run_id, response.id, prompt, refined_prompt=updated_prompt)
                return response.id

        # --------------- NO-DOC path ---------------
        tools = []
        if force_web_search or not CLI_ARGS.no_web_search:
            tools.append({"type": "web_search_preview"})
        if not CLI_ARGS.cost_sensitive:
            tools.append({"type": "code_interpreter", "container": {"type": "auto"}})

        tool_choice = "auto"
        updated_prompt = (
            "Do NOT include inline citations in the body text. If references are needed, the writer will append them at the end. "
            + final_prompt
        )
        model = "o4-mini-deep-research" if CLI_ARGS.cost_sensitive else MODEL

        # Ensure DR tool requirement or fallback
        model = _ensure_model_and_tools(model, tools)

        request_payload = {
            "model": model,
            "input": [
                {"role": "developer", "content": [{"type": "input_text", "text": load_system_message()}]},
                {"role": "user", "content": [{"type": "input_text", "text": updated_prompt}]}
            ],
            "reasoning": {"summary": "auto"},
            "tools": tools,
            "tool_choice": tool_choice,
            "metadata": {
                "run_id": run_id,
                "report_title": report_title,
                "filename_safe": filename_safe
            },
            "extra_headers": {"OpenAI-Hook-URL": webhook_url},
            "store": True,
            "background": True
        }

        response = client.responses.create(**request_payload)
        print(f"{Fore.GREEN}Submitted successfully. Response ID: {response.id}{Style.RESET_ALL}")

        try:
            payload = response.model_dump() if hasattr(response, "model_dump") else json.loads(response.json())
            with open("last_response.json", "w", encoding="utf-8") as f:
                json.dump(payload, f, indent=2)
        except Exception as e:
            print(f"{Fore.YELLOW}Warning: Could not save full response payload: {e}{Style.RESET_ALL}")

        log_job_submission(run_id, response.id, prompt, refined_prompt=updated_prompt)
        return response.id

    except Exception as e:
        print(f"{Fore.RED}Submission failed: {e}{Style.RESET_ALL}")
        return None


def generate_time_estimate(prompt):
    """
    Heuristic + LLM fallback. Translation of attached docs is fast.
    """
    p = (prompt or "").lower()
    # If this looks like a simple translation job, short-circuit to fast
    if any(k in p for k in ("translate", "translation")) and getattr(CLI_ARGS, "documents", None):
        return "1–3 minutes"
    try:
        instructions = (
            "Estimate the time required for this task. Return exactly one of: 1–3 minutes, 3–5 minutes, or 5–30 minutes.\n\n"
            f"Task: {prompt}\n"
        )
        response = client.chat.completions.create(
            model="gpt-4",
            messages=[{"role": "user", "content": instructions}]
        )
        ans = (response.choices[0].message.content or "").strip()
        if ans not in {"1–3 minutes", "3–5 minutes", "5–30 minutes"}:
            return "3–5 minutes"
        return ans
    except Exception:
        return "3–5 minutes"


def clean_message(message):
    message = message.strip()
    if message.startswith('"') and message.endswith('"'):
        message = message[1:-1]
    return message


def generate_waiting_message(research_request):
    """Generates a one-liner with the time estimate from heuristic/LLM."""
    time_estimate = generate_time_estimate(research_request)
    prompt = (
        f"Write a concise, friendly one-liner telling the user their request "
        f"will take approximately {time_estimate}."
    )
    try:
        response = client.chat.completions.create(
            model="gpt-4",
            messages=[{"role": "user", "content": prompt}]
        )
        return clean_message(response.choices[0].message.content.strip())
    except Exception:
        return f"Processing your request. Estimated time: {time_estimate}."


def download_report(job_id, retries=5, delay=30):
    """
    Fetch the completed report by ID with retries, then normalize and save in multiple formats.
    """
    print(f"{Fore.CYAN}Fetching report for job ID: {job_id}{Style.RESET_ALL}")

    attempt = 0
    while attempt < retries:
        try:
            response = client.responses.retrieve(job_id)

            if response.status != "completed":
                print(f"{Fore.YELLOW}Job status is {response.status}. Only completed jobs can be downloaded.{Style.RESET_ALL}")
                time.sleep(delay)
                attempt += 1
                continue

            blocks = response.output or []
            texts = [block.content[0].text for block in blocks if block.type == "message"]

            if not texts:
                print(f"{Fore.YELLOW}No output found in this job.{Style.RESET_ALL}")
                return

            final_text = "\n\n".join(texts)
            normalized_text = normalize.normalize_markdown(final_text)
            metadata = response.metadata

            save_output(job_id, {
                "metadata": metadata,
                "output": [{"type": "message", "content": [{"type": "output_text", "text": normalized_text}]}]
            })
            return

        except Exception as e:
            print(f"{Fore.RED}Error occurred during download: {e}{Style.RESET_ALL}")
            attempt += 1
            if attempt < retries:
                print(f"{Fore.YELLOW}Retrying download... (Attempt {attempt}/{retries}){Style.RESET_ALL}")
                time.sleep(delay)
            else:
                print(f"{Fore.RED}Max retries reached. Unable to download the report after {retries} attempts.{Style.RESET_ALL}")
                return


def poll_status(run_id, research_request, max_wait=1800):
    global polling_stopped

    start_time = time.time()
    print(f"Job in Queue, ID: {run_id}")

    waiting_message = generate_waiting_message(research_request)
    print(f"{Fore.LIGHTCYAN_EX}{waiting_message}{Style.RESET_ALL}")

    last_status = "queued"
    in_progress_displayed = False

    while time.time() - start_time < max_wait:
        if polling_stopped:
            print("\nPolling stopped due to webhook update.")
            return

        try:
            elapsed = int(time.time() - start_time)
            minutes = elapsed // 60
            seconds = elapsed % 60

            sys.stdout.write(f"\rElapsed time: {minutes:02}:{seconds:02}")
            sys.stdout.flush()

            if elapsed % 30 == 0:
                result = client.responses.retrieve(run_id)

                if result is None or not hasattr(result, 'status'):
                    print(f"\n{Fore.RED}Error: No valid response received. Please check the request.{Style.RESET_ALL}")
                    return

                status = result.status

                if status != last_status:
                    if status == "in_progress" and not in_progress_displayed:
                        print(f"\n{Fore.GREEN}Job is now in progress...{Style.RESET_ALL}")
                        in_progress_displayed = True

                    sys.stdout.write(f"\rStatus: {status.capitalize()} | Elapsed time: {minutes:02}:{seconds:02}")
                    sys.stdout.flush()
                    last_status = status

                if status == "completed":
                    print(f"\n{Fore.GREEN}Research complete. Waiting 5 seconds before fetching results.\n{Style.RESET_ALL}")
                    time.sleep(5)
                    try:
                        download_report(run_id)
                        update_job_status(run_id, "completed")
                    except Exception as e:
                        print(f"{Fore.RED}Error retrieving final output: {e}{Style.RESET_ALL}")
                    finally:
                        _cleanup_vector_store_for(run_id)  # <- cleanup VS here too
                    return

                elif status in {"failed", "cancelled", "expired"}:
                    print(f"\n{Fore.RED}Research {status}. Status: {status}{Style.RESET_ALL}")
                    update_job_status(run_id, status)
                    _cleanup_vector_store_for(run_id)  # <- cleanup on failure as well
                    return

            time.sleep(1)

        except Exception as e:
            print(f"\n{Fore.RED}Polling error: {e}{Style.RESET_ALL}")
            time.sleep(30)


@app.route("/webhook", methods=["POST"])
def webhook():
    global polling_stopped

    data = request.json
    run_id = data.get("metadata", {}).get("run_id", "unknown")
    status = data.get("status", "unknown")

    print(f"\n{Fore.BLUE}[{datetime.now()}] Webhook update for run {run_id}:{Style.RESET_ALL}")

    if data.get("output"):
        save_output(run_id, data)
        update_job_status(run_id, "completed")
        _cleanup_vector_store_for(run_id)  # <- cleanup after success
        polling_stopped = True
    elif status in ["cancelled", "failed", "expired"]:
        print(f"{Fore.RED}Job {run_id} ended with status: {status}{Style.RESET_ALL}")
        update_job_status(run_id, status)
        _cleanup_vector_store_for(run_id)  # <- cleanup after failure
        polling_stopped = True
    else:
        print(f"{Fore.YELLOW}Webhook received but no output available yet. Status: {status}{Style.RESET_ALL}")

    return "", 200


# === WEBHOOK SERVER ===
def start_webhook_server():
    print(f"{Fore.YELLOW}Starting webhook server on port {PORT}...{Style.RESET_ALL}")
    app.run(host="0.0.0.0", port=PORT)


# === CLI ===
def main():
    print(f"{Fore.GREEN}=== Deepr CLI OpenAI Deep Research ==={Style.RESET_ALL}")

    # Start webhook server in background first
    server_thread = Thread(target=start_webhook_server, daemon=True)
    server_thread.start()

    try:
        # Start ngrok and capture both process and public webhook URL
        ngrok_process, webhook_url = start_ngrok()
        print(f"{Fore.CYAN}Webhook URL: {webhook_url}{Style.RESET_ALL}")

    except Exception as e:
        print(f"{Fore.RED}{e}{Style.RESET_ALL}")
        return

    if CLI_ARGS.briefing:
        print(f"{Fore.YELLOW}Using custom system message override (--briefing):{Style.RESET_ALL}")
        print(f"{CLI_ARGS.briefing.strip()}\n")

    # --- Batch mode ---
    if CLI_ARGS.batch_file:
        if not os.path.isfile(CLI_ARGS.batch_file):
            print(f"{Fore.RED}Batch file not found: {CLI_ARGS.batch_file}{Style.RESET_ALL}")
            stop_ngrok(ngrok_process)
            return
        try:
            with open(CLI_ARGS.batch_file, "r", encoding="utf-8") as f:
                prompts = [line.strip() for line in f if line.strip()]
            print(f"{Fore.CYAN}Running batch of {len(prompts)} prompts...{Style.RESET_ALL}")
            for i, prompt in enumerate(prompts, 1):
                print(f"\n{Fore.MAGENTA}[Batch {i}/{len(prompts)}]{Style.RESET_ALL}")
                # Upload docs for batch if provided
                document_refs = collect_document_refs(client, getattr(CLI_ARGS, "documents", []))
                response_id = submit_research_query(
                    prompt,
                    webhook_url,
                    force_web_search=not CLI_ARGS.no_web_search,
                    document_refs=document_refs if document_refs else None
                )
                if response_id:
                    print(f"{Fore.YELLOW}Tracking job status for Response ID: {response_id}{Style.RESET_ALL}")
                    poll_status(response_id, prompt)
                else:
                    print(f"{Fore.RED}Submission failed for prompt {i}.{Style.RESET_ALL}")
                # Pause every 5 prompts for 3 minutes
                if i % 5 == 0 and i != len(prompts):
                    print(f"{Fore.YELLOW}Pausing for 3 minutes to avoid rate limits...{Style.RESET_ALL}")
                    time.sleep(180)
        except Exception as e:
            print(f"{Fore.RED}Failed to process batch file: {e}{Style.RESET_ALL}")
        finally:
            stop_ngrok(ngrok_process)
        return

    # --- Single-shot non-interactive mode ---
    if CLI_ARGS.research:
        # Always upload documents BEFORE submission in non-interactive mode
        document_refs = collect_document_refs(client, getattr(CLI_ARGS, "documents", []))
        response_id = submit_research_query(
            CLI_ARGS.research,
            webhook_url,
            force_web_search=not CLI_ARGS.no_web_search,
            document_refs=document_refs if document_refs else None
        )
        if response_id:
            print(f"{Fore.YELLOW}Tracking job status for Response ID: {response_id}{Style.RESET_ALL}")
            poll_status(response_id, CLI_ARGS.research)
        else:
            print(f"{Fore.RED}Research task did not start successfully.{Style.RESET_ALL}")
        stop_ngrok(ngrok_process)
        return

    # --- Interactive mode ---
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
        stop_ngrok(ngrok_process)
        return

    prompt = "\n".join(lines).strip()

    # Handle document upload if --documents is provided
    document_refs = collect_document_refs(client, getattr(CLI_ARGS, "documents", []))

    if not CLI_ARGS.cost_sensitive:
        cost = input("Use cost-sensitive mode (lower cost, fewer resources)? (y/N): ").strip().lower()
        if cost in ("y", "yes"):
            CLI_ARGS.cost_sensitive = True

    if not CLI_ARGS.raw:
        clarify = input("Clarify and refine this prompt with GPT-5? (Y/n): ").strip().lower()
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
                print(f"{Fore.YELLOW}No clarification needed. Proceeding...{Style.RESET_ALL}")
                prompt = refine_prompt(prompt)

    if not CLI_ARGS.append_references:
        refs = input("Append extracted URLs as references at the end? (y/N): ").strip().lower()
        if refs in ("y", "yes"):
            CLI_ARGS.append_references = True

    print(f"\n{Fore.CYAN}=== Review the Research Request ==={Style.RESET_ALL}")
    print(f"Research Request: {prompt}")
    if document_refs:
        print(f"Documents for research: {document_refs}")
    print(f"\n{Fore.CYAN}=== Selected Options ==={Style.RESET_ALL}")
    print(f"Cost-sensitive mode: {'Yes' if CLI_ARGS.cost_sensitive else 'No'}")
    print(f"Clarification applied: {'Yes' if not CLI_ARGS.raw else 'No'}")
    print(f"Append references: {'Yes' if CLI_ARGS.append_references else 'No'}")

    confirm = input("\nGo ahead with the research? Press Enter to confirm or 'n' to revise: ").strip().lower()
    if confirm == "n":
        print(f"{Fore.YELLOW}Prompt revision canceled. You can make edits to the prompt before submitting.{Style.RESET_ALL}")
        stop_ngrok(ngrok_process)
        return

    response_id = submit_research_query(
        prompt,
        webhook_url,
        force_web_search=True,
        document_refs=document_refs if document_refs else None
    )
    if response_id:
        print(f"{Fore.YELLOW}Tracking job status for Response ID: {response_id}{Style.RESET_ALL}")
        poll_status(response_id, prompt)

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
    stop_ngrok(ngrok_process)


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
    parser.add_argument(
        "--documents",
        type=str,
        nargs="+",
        metavar="PATH",
        help="Path(s) to document(s) (PDF, Word, text, CSV) to upload and use in research request."
    )
    parser.add_argument("--cost-sensitive", action="store_true", help="Limit tool usage and model to reduce cost")
    parser.add_argument("--no-web-search", action="store_true", help="Disable web search tool for this run")
    parser.add_argument("--output-title", type=str, metavar="TITLE", help="Optional custom title for output report files")
    parser.add_argument("--append-references", action="store_true", help="Append extracted links at the end under a References section")
    parser.add_argument("--no-pdf", action="store_true", help="Skip PDF generation from the Word document")
    global CLI_ARGS
    CLI_ARGS = parser.parse_args()
    try:
        main()
    except KeyboardInterrupt:
        print(f"\n{Fore.RED}Interrupted by user. Exiting...{Style.RESET_ALL}")
        sys.exit(1)


# === ENTRY ===
if __name__ == "__main__":
    cli_entry()
