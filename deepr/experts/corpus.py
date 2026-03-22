"""Corpus module for expert consciousness export/import.

This module enables packaging an expert's consciousness (documents, worldview,
beliefs) for portability and reuse. An exported corpus can be imported to
create a new expert with the same knowledge and understanding.

Corpus Structure:
    corpus_name/
    ├── manifest.json       # Corpus metadata and file list
    ├── metadata.json       # Expert profile information
    ├── worldview.json      # Beliefs and knowledge gaps
    ├── worldview.md        # Human-readable worldview
    ├── README.md           # Summary for humans
    └── documents/          # All knowledge documents
        ├── doc1.md
        ├── doc2.md
        └── ...
"""

import json
import logging
import shutil
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)


@dataclass
class CorpusManifest:
    """Manifest describing a corpus package."""

    name: str
    version: str = "1.0"
    created_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    source_expert: str = ""
    domain: str = ""
    description: str = ""

    # File counts
    document_count: int = 0
    belief_count: int = 0
    gap_count: int = 0

    # File list
    files: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for JSON serialization."""
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "CorpusManifest":
        """Create from dictionary."""
        return cls(**data)

    def save(self, path: Path) -> None:
        """Save manifest to JSON file."""
        with open(path, "w", encoding="utf-8") as f:
            json.dump(self.to_dict(), f, indent=2)

    @classmethod
    def load(cls, path: Path) -> "CorpusManifest":
        """Load manifest from JSON file."""
        with open(path, encoding="utf-8") as f:
            data = json.load(f)
        return cls.from_dict(data)


async def export_corpus(
    expert_name: str,
    output_dir: Path,
    store: Any,  # ExpertStore
) -> CorpusManifest:
    """Export an expert's consciousness to a portable corpus.

    Args:
        expert_name: Name of the expert to export
        output_dir: Directory to create corpus in
        store: ExpertStore instance

    Returns:
        CorpusManifest describing the exported corpus

    Raises:
        ValueError: If expert not found or has no knowledge
    """
    from deepr.experts.synthesis import Worldview

    # Load expert profile
    profile = store.load(expert_name)
    if not profile:
        raise ValueError(f"Expert not found: {expert_name}")

    # Get paths
    knowledge_dir = store.get_knowledge_dir(expert_name)
    docs_dir = store.get_documents_dir(expert_name)
    worldview_path = knowledge_dir / "worldview.json"
    worldview_md_path = knowledge_dir / "worldview.md"

    # Create output directory
    corpus_name = expert_name.lower().replace(" ", "-")
    corpus_dir = output_dir / corpus_name
    corpus_dir.mkdir(parents=True, exist_ok=True)

    # Create documents subdirectory
    corpus_docs_dir = corpus_dir / "documents"
    corpus_docs_dir.mkdir(exist_ok=True)

    # Track files
    files = []
    document_count = 0
    belief_count = 0
    gap_count = 0

    # Copy documents
    if docs_dir.exists():
        for doc_file in docs_dir.glob("*.md"):
            dest = corpus_docs_dir / doc_file.name
            shutil.copy2(doc_file, dest)
            files.append(f"documents/{doc_file.name}")
            document_count += 1

    # Copy worldview
    worldview = None
    if worldview_path.exists():
        shutil.copy2(worldview_path, corpus_dir / "worldview.json")
        files.append("worldview.json")

        try:
            worldview = Worldview.load(worldview_path)
            belief_count = len(worldview.beliefs)
            gap_count = len(worldview.knowledge_gaps)
        except Exception as e:
            logger.warning("Failed to parse worldview from %s: %s", worldview_path, e)

    if worldview_md_path.exists():
        shutil.copy2(worldview_md_path, corpus_dir / "worldview.md")
        files.append("worldview.md")

    # Generate metadata.json
    metadata = {
        "name": profile.name,
        "description": profile.description,
        "domain": profile.domain,
        "provider": profile.provider,
        "model": profile.model,
        "created_at": profile.created_at.isoformat() if profile.created_at else None,
        "total_documents": profile.total_documents,
        "conversations": profile.conversations,
        "research_triggered": profile.research_triggered,
        "total_research_cost": profile.total_research_cost,
    }

    metadata_path = corpus_dir / "metadata.json"
    with open(metadata_path, "w", encoding="utf-8") as f:
        json.dump(metadata, f, indent=2)
    files.append("metadata.json")

    # Generate README.md
    readme_content = _generate_readme(profile, worldview, document_count)
    readme_path = corpus_dir / "README.md"
    with open(readme_path, "w", encoding="utf-8") as f:
        f.write(readme_content)
    files.append("README.md")

    # Create manifest
    manifest = CorpusManifest(
        name=corpus_name,
        source_expert=expert_name,
        domain=profile.domain or profile.description or "",
        description=profile.description or "",
        document_count=document_count,
        belief_count=belief_count,
        gap_count=gap_count,
        files=files,
    )

    manifest.save(corpus_dir / "manifest.json")

    return manifest


def _generate_readme(profile: Any, worldview: Any, doc_count: int) -> str:
    """Generate human-readable README for corpus."""
    lines = [
        f"# {profile.name}",
        "",
        f"**Domain**: {profile.domain or profile.description or 'General'}",
        "",
        "## Overview",
        "",
        f'This corpus contains the exported consciousness of the "{profile.name}" expert.',
        "",
        "## Contents",
        "",
        f"- **Documents**: {doc_count} knowledge files",
    ]

    if worldview:
        lines.extend(
            [
                f"- **Beliefs**: {len(worldview.beliefs)} formed beliefs",
                f"- **Knowledge Gaps**: {len(worldview.knowledge_gaps)} identified gaps",
            ]
        )

    lines.extend(
        [
            "",
            "## Usage",
            "",
            "Import this corpus to create a new expert:",
            "",
            "```bash",
            f'deepr expert import "New Expert Name" --corpus ./{profile.name.lower().replace(" ", "-")}',
            "```",
            "",
            "## Worldview Summary",
            "",
        ]
    )

    if worldview and worldview.beliefs:
        lines.append("### Top Beliefs")
        lines.append("")
        for belief in sorted(worldview.beliefs, key=lambda b: b.confidence, reverse=True)[:5]:
            lines.append(f"- {belief.statement} (confidence: {belief.confidence:.0%})")
        lines.append("")

    if worldview and worldview.knowledge_gaps:
        lines.append("### Knowledge Gaps")
        lines.append("")
        for gap in sorted(worldview.knowledge_gaps, key=lambda g: g.priority, reverse=True)[:3]:
            lines.append(f"- {gap.topic} (priority: {gap.priority}/5)")
        lines.append("")

    lines.extend(
        [
            "---",
            "",
            f"*Exported on {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M:%S')} UTC*",
        ]
    )

    return "\n".join(lines)


async def import_corpus(
    new_expert_name: str,
    corpus_dir: Path,
    store: Any,  # ExpertStore
    provider: Any,  # Provider instance
) -> Any:  # ExpertProfile
    """Import a corpus to create a new expert.

    Args:
        new_expert_name: Name for the new expert
        corpus_dir: Directory containing the corpus
        store: ExpertStore instance
        provider: Provider instance for vector store operations

    Returns:
        ExpertProfile of the newly created expert

    Raises:
        ValueError: If corpus is invalid or expert already exists
    """
    from deepr.experts.profile import ExpertProfile, get_expert_system_message
    from deepr.experts.synthesis import Worldview

    # Validate corpus structure
    manifest_path = corpus_dir / "manifest.json"
    if not manifest_path.exists():
        raise ValueError(f"Invalid corpus: manifest.json not found in {corpus_dir}")

    manifest = CorpusManifest.load(manifest_path)

    # Check if expert already exists
    if store.load(new_expert_name):
        raise ValueError(f"Expert already exists: {new_expert_name}")

    # Load metadata
    metadata_path = corpus_dir / "metadata.json"
    metadata = {}
    if metadata_path.exists():
        with open(metadata_path, encoding="utf-8") as f:
            metadata = json.load(f)

    # Create vector store
    vector_store = await provider.create_vector_store(
        name=f"expert-{new_expert_name.lower().replace(' ', '-')}", file_ids=[]
    )

    # Upload documents to vector store
    corpus_docs_dir = corpus_dir / "documents"
    uploaded_files = []

    if corpus_docs_dir.exists():
        for doc_file in corpus_docs_dir.glob("*.md"):
            file_id = await provider.upload_document(str(doc_file))
            await provider.add_file_to_vector_store(vector_store.id, file_id)
            uploaded_files.append(doc_file.name)

    # Wait for indexing
    if uploaded_files:
        await provider.wait_for_vector_store(vector_store.id, timeout=300)

    # Create expert profile
    now = datetime.now(timezone.utc)
    profile = ExpertProfile(
        name=new_expert_name,
        vector_store_id=vector_store.id,
        description=metadata.get("description") or manifest.description,
        domain=metadata.get("domain") or manifest.domain,
        source_files=uploaded_files,
        total_documents=len(uploaded_files),
        knowledge_cutoff_date=now,
        last_knowledge_refresh=now,
        system_message=get_expert_system_message(knowledge_cutoff_date=now, domain_velocity="medium"),
        provider=metadata.get("provider", "openai"),
    )

    # Save profile
    store.save(profile)

    # Copy worldview files
    knowledge_dir = store.get_knowledge_dir(new_expert_name)
    knowledge_dir.mkdir(parents=True, exist_ok=True)

    corpus_worldview = corpus_dir / "worldview.json"
    if corpus_worldview.exists():
        # Load and update worldview with new expert name
        worldview = Worldview.load(corpus_worldview)
        worldview.expert_name = new_expert_name
        worldview.save(knowledge_dir / "worldview.json")

        # Also save markdown version (best-effort, JSON is source of truth)
        try:
            md_lines = [f"# Worldview: {worldview.expert_name}\n"]
            for belief in worldview.beliefs:
                conf = getattr(belief, "confidence", "?")
                claim = getattr(belief, "claim", str(belief))
                md_lines.append(f"- [{conf}] {claim}")
            (knowledge_dir / "worldview.md").write_text("\n".join(md_lines), encoding="utf-8")
        except Exception:
            pass  # Non-critical

    # Copy documents to expert's documents folder
    docs_dir = store.get_documents_dir(new_expert_name)
    docs_dir.mkdir(parents=True, exist_ok=True)

    if corpus_docs_dir.exists():
        for doc_file in corpus_docs_dir.glob("*.md"):
            shutil.copy2(doc_file, docs_dir / doc_file.name)

    return profile


async def import_structured_bundle(
    expert_name: str,
    bundle_path: Path,
    store: Any,  # ExpertStore
    auto_detect_gaps: bool = True,
) -> dict[str, Any]:
    """Import a structured document bundle into an existing expert's knowledge.

    Supports MD, JSON, and JSONL files. Does not require a provider or vector
    store — documents are stored locally and integrated into the worldview.

    This is the "one-command ingest" for research reports, synthesis docs,
    company briefs, or any structured output.

    Args:
        expert_name: Name of the target expert (must exist).
        bundle_path: Path to a file or directory of files to import.
        store: ExpertStore instance.
        auto_detect_gaps: If True, scan imports for unanswered questions.

    Returns:
        Dict with import results: documents_imported, gaps_detected, citations_mapped.
    """
    profile = store.load(expert_name)
    if not profile:
        raise ValueError(f"Expert not found: {expert_name}")

    docs_dir = store.get_documents_dir(expert_name)
    docs_dir.mkdir(parents=True, exist_ok=True)

    # Collect files to import
    files_to_import: list[Path] = []
    bundle = Path(bundle_path)

    if bundle.is_file():
        files_to_import.append(bundle)
    elif bundle.is_dir():
        for ext in ("*.md", "*.json", "*.jsonl"):
            files_to_import.extend(bundle.glob(ext))
    else:
        raise ValueError(f"Bundle path does not exist: {bundle_path}")

    if not files_to_import:
        raise ValueError(f"No importable files (MD/JSON/JSONL) found in {bundle_path}")

    documents_imported = 0
    citations_mapped = 0
    gaps_detected: list[dict[str, str]] = []

    for file_path in sorted(files_to_import):
        try:
            content = file_path.read_text(encoding="utf-8")
        except Exception as e:
            logger.warning("Failed to read %s: %s", file_path, e)
            continue

        # Convert JSON/JSONL to markdown for storage
        if file_path.suffix == ".json":
            content = _json_to_markdown(content, file_path.name)
        elif file_path.suffix == ".jsonl":
            content = _jsonl_to_markdown(content, file_path.name)

        # Write to expert's documents directory
        dest_name = file_path.stem + ".md"
        dest = docs_dir / dest_name
        # Avoid overwriting by appending counter
        counter = 1
        while dest.exists():
            dest = docs_dir / f"{file_path.stem}_{counter}.md"
            counter += 1

        dest.write_text(content, encoding="utf-8")
        documents_imported += 1

        # Count citations (links/references in content)
        citations_mapped += content.count("http://") + content.count("https://")

        # Auto-detect gaps (questions without answers)
        if auto_detect_gaps:
            for line in content.split("\n"):
                stripped = line.strip()
                if stripped.endswith("?") and len(stripped) > 15:
                    gaps_detected.append({"question": stripped, "source": file_path.name})

    # Update profile
    profile.total_documents = (profile.total_documents or 0) + documents_imported
    # Preserve order while deduplicating
    existing = profile.source_files or []
    new_names = [f.name for f in files_to_import]
    seen: set[str] = set()
    deduped: list[str] = []
    for name in existing + new_names:
        if name not in seen:
            seen.add(name)
            deduped.append(name)
    profile.source_files = deduped
    profile.last_knowledge_refresh = datetime.now(timezone.utc)
    store.save(profile)

    logger.info(
        "Imported %d documents into expert '%s' (%d citations, %d gaps detected)",
        documents_imported,
        expert_name,
        citations_mapped,
        len(gaps_detected),
    )

    return {
        "expert_name": expert_name,
        "documents_imported": documents_imported,
        "citations_mapped": citations_mapped,
        "gaps_detected": gaps_detected[:20],  # Cap at 20 for display
        "files": [f.name for f in files_to_import],
    }


def _json_to_markdown(content: str, filename: str) -> str:
    """Convert JSON content to markdown for expert knowledge storage."""
    try:
        data = json.loads(content)
    except json.JSONDecodeError:
        return f"# {filename}\n\n```json\n{content}\n```"

    lines = [f"# {filename}", ""]

    if isinstance(data, dict):
        for key, value in data.items():
            if isinstance(value, str):
                lines.append(f"## {key}")
                lines.append("")
                lines.append(value)
                lines.append("")
            elif isinstance(value, list):
                lines.append(f"## {key}")
                lines.append("")
                for item in value:
                    lines.append(f"- {item}")
                lines.append("")
            else:
                lines.append(f"**{key}**: {value}")
                lines.append("")
    elif isinstance(data, list):
        for i, item in enumerate(data):
            lines.append(f"## Entry {i + 1}")
            lines.append("")
            if isinstance(item, dict):
                for k, v in item.items():
                    lines.append(f"**{k}**: {v}")
            else:
                lines.append(str(item))
            lines.append("")

    return "\n".join(lines)


def _jsonl_to_markdown(content: str, filename: str) -> str:
    """Convert JSONL content to markdown for expert knowledge storage."""
    lines = [f"# {filename}", ""]
    entry_num = 0

    for line in content.strip().split("\n"):
        line = line.strip()
        if not line:
            continue
        try:
            data = json.loads(line)
            entry_num += 1
            lines.append(f"## Entry {entry_num}")
            lines.append("")
            if isinstance(data, dict):
                for k, v in data.items():
                    lines.append(f"**{k}**: {v}")
            else:
                lines.append(str(data))
            lines.append("")
        except json.JSONDecodeError:
            continue

    return "\n".join(lines)


def validate_corpus(corpus_dir: Path) -> dict[str, Any]:
    """Validate a corpus directory structure.

    Args:
        corpus_dir: Path to corpus directory

    Returns:
        Dict with validation results:
        - valid: bool
        - errors: List[str]
        - manifest: CorpusManifest or None
    """
    errors = []
    manifest = None

    # Check manifest exists
    manifest_path = corpus_dir / "manifest.json"
    if not manifest_path.exists():
        errors.append("manifest.json not found")
    else:
        try:
            manifest = CorpusManifest.load(manifest_path)
        except Exception as e:
            errors.append(f"Invalid manifest.json: {e}")

    # Check documents directory
    docs_dir = corpus_dir / "documents"
    if not docs_dir.exists():
        errors.append("documents/ directory not found")
    elif not list(docs_dir.glob("*.md")):
        errors.append("No .md files in documents/ directory")

    # Check worldview (optional but recommended)
    if not (corpus_dir / "worldview.json").exists():
        errors.append("worldview.json not found (expert will have no beliefs)")

    return {"valid": len(errors) == 0, "errors": errors, "manifest": manifest}
