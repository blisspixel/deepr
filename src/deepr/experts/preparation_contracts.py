"""Pure offline preparation contracts; these types grant no execution authority."""

from __future__ import annotations

import hashlib
import json
import re
from datetime import datetime
from typing import Annotated, Any, Literal

from pydantic import BaseModel, ConfigDict, Field, StrictBool, StrictInt, field_validator, model_validator

Digest = Annotated[str, Field(pattern=r"^[0-9a-f]{64}$")]
Identifier = Annotated[str, Field(pattern=r"^[A-Za-z0-9_-]{1,64}$")]
Text = Annotated[str, Field(min_length=1, max_length=4000)]
Reason = Annotated[str, Field(min_length=1, max_length=512)]


def canonical_bytes(value: BaseModel | dict[str, Any]) -> bytes:
    """Stable UTF-8 JSON; timestamps and field types remain explicit."""
    payload = value.model_dump(mode="json") if isinstance(value, BaseModel) else value
    return json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False, allow_nan=False).encode(
        "utf-8"
    )


def sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


_DECLARED = "uploader-declared metadata; not an install, import or runtime test"
_ARCHIVE_DIGEST = "digest of the archive bytes named by filename; not installed files or other archives"
_PUBLISHED = "as published at observed_at; may change later"
FIELD_SEMANTICS_VERSION = "pypi-field-semantics-v1"
# Fixed meaning of retained projection fields, versioned so frozen projections
# store only the identifier. Text describes form, never a verdict.
FIELD_SEMANTICS: dict[str, tuple[tuple[str, str], ...]] = {
    FIELD_SEMANTICS_VERSION: (
        ("requires_python", _DECLARED),
        ("yanked", _PUBLISHED),
        ("vulnerabilities", "PyPI's own list as returned; not an advisory database check"),
        ("versions", "listed at observed_at"),
        (
            "listing_at_observation",
            "listing at observation time only; not completeness, future currentness, or safety. "
            "highest_listed_final_unyanked_version excludes PEP 440 pre-releases, dev releases and versions "
            "with no listed file that is not yanked",
        ),
        ("files[].filename", "wheel tags in the name are " + _DECLARED),
        ("files[].python_version", _DECLARED),
        ("files[].requires_python", _DECLARED),
        ("files[].requires-python", _DECLARED),
        ("files[].digests", _ARCHIVE_DIGEST),
        ("files[].md5_digest", _ARCHIVE_DIGEST),
        ("files[].hashes", _ARCHIVE_DIGEST),
        ("files[].core-metadata", "sha256 of the separate core metadata file, not the archive"),
        ("files[].data-dist-info-metadata", "legacy name of core-metadata"),
        ("files[].yanked", _PUBLISHED),
    )
}


def field_semantics_for(version: str, projection: dict[str, Any]) -> dict[str, str]:
    """Fixed meanings for the fields present in one projection; unknown versions have none."""
    files = projection.get("files")
    file_keys = {key for file in files if isinstance(file, dict) for key in file} if isinstance(files, list) else set()
    present = set(projection) | {f"files[].{key}" for key in file_keys}
    return {path: meaning for path, meaning in FIELD_SEMANTICS.get(version, ()) if path in present}


class FrozenModel(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)


class PackageCoordinate(FrozenModel):
    name: Annotated[str, Field(min_length=1, max_length=200)]
    version: Annotated[str, Field(min_length=1, max_length=128)]

    @field_validator("name")
    @classmethod
    def normalize_name(cls, value: str) -> str:
        from packaging.utils import canonicalize_name

        if re.fullmatch(r"[A-Za-z0-9](?:[A-Za-z0-9._-]*[A-Za-z0-9])?", value) is None:
            raise ValueError("package name must be a project coordinate")
        return canonicalize_name(value)

    @field_validator("version")
    @classmethod
    def normalize_version(cls, value: str) -> str:
        from packaging.version import InvalidVersion, Version

        try:
            return str(Version(value))
        except InvalidVersion as error:
            raise ValueError("version must be concrete") from error

    @property
    def coordinate_id(self) -> str:
        return "pkg_" + sha256(canonical_bytes(self))[:24]


class PythonEnvironment(FrozenModel):
    interpreter_version: Annotated[str, Field(min_length=1, max_length=128)]
    platform: Annotated[str, Field(min_length=1, max_length=128)]
    lockfile_sha256: Digest | None = None
    declaration: Literal["caller_declared"] = "caller_declared"

    @field_validator("interpreter_version")
    @classmethod
    def concrete_interpreter(cls, value: str) -> str:
        if re.fullmatch(r"[0-9]+\.[0-9]+(?:\.[0-9]+)?", value) is None:
            raise ValueError("explicit Python interpreter version required")
        return value


class PreparationRequest(FrozenModel):
    schema_version: Literal["deepr-python-preparation-request-v1"]
    enabled: StrictBool
    request_id: Annotated[str, Field(pattern=r"^[A-Za-z0-9_-]{16,64}$")]
    environment: PythonEnvironment
    packages: Annotated[tuple[PackageCoordinate, ...], Field(min_length=1, max_length=3)]

    @field_validator("enabled")
    @classmethod
    def enabled_only(cls, value: bool) -> bool:
        if not value:
            raise ValueError("supplied preparation must be enabled")
        return value

    @field_validator("packages")
    @classmethod
    def coalesce_coordinates(cls, values: tuple[PackageCoordinate, ...]) -> tuple[PackageCoordinate, ...]:
        projects: dict[str, PackageCoordinate] = {}
        for value in values:
            if value.name in projects and projects[value.name].version != value.version:
                raise ValueError("contradictory project versions")
            projects[value.name] = value
        return tuple(sorted(projects.values(), key=lambda item: (item.name, item.version)))

    @classmethod
    def from_json(cls, data: bytes) -> PreparationRequest:
        if len(data) > 16_384:
            raise ValueError("preparation input exceeds 16 KiB")
        return cls.model_validate_json(data)


class CallerScope(FrozenModel):
    """Opaque service-derived namespace, never a client authentication proof."""

    namespace_sha256: Digest


class PreparationEnvelope(FrozenModel):
    """Internal operation binding; public request parsing must remain separate."""

    operation_id: Identifier
    owner: CallerScope
    request: PreparationRequest
    question: Annotated[str, Field(min_length=1, max_length=4000)]
    expert_revision: Digest
    stored_position_ids: Annotated[tuple[Identifier, ...], Field(max_length=120)] = ()

    @property
    def question_sha256(self) -> str:
        return sha256(self.question.encode("utf-8"))


class PreparationLimits(FrozenModel):
    requests: Annotated[StrictInt, Field(gt=0, le=6)] = 6
    sources: Annotated[StrictInt, Field(gt=0, le=6)] = 6
    per_source_bytes: Annotated[StrictInt, Field(gt=0, le=1_048_576)] = 1_048_576
    decoded_bytes: Annotated[StrictInt, Field(gt=0, le=2_097_152)] = 2_097_152
    acquisition_seconds: Annotated[StrictInt, Field(gt=0, le=30)] = 30
    model_calls: Annotated[StrictInt, Field(gt=0, le=2)] = 2
    model_output_tokens: Annotated[StrictInt, Field(gt=0, le=1024)] = 1024
    model_input_chars: Annotated[StrictInt, Field(gt=0, le=32768)] = 32768
    model_call_seconds: Annotated[StrictInt, Field(gt=0, le=90)] = 90
    preparation_seconds: Annotated[StrictInt, Field(gt=0, le=210)] = 210


class Assumption(FrozenModel):
    assumption_id: Identifier
    coordinate_ids: Annotated[tuple[Identifier, ...], Field(min_length=1, max_length=3)]
    text: Text
    status: Literal["checked", "unchecked", "not_needed"]
    reason: Reason


class SourceObservation(FrozenModel):
    observation_id: Identifier
    coordinate_id: Identifier
    source_class: Literal["pypi_release", "pypi_index"]
    requested_at: datetime
    observed_at: datetime
    status: Literal["ok", "failed", "offline", "partial"]
    applicable_versions: Annotated[tuple[Annotated[str, Field(max_length=128)], ...], Field(max_length=32)] = ()
    raw_sha256: Digest | None = None
    corpus_sha256: Digest | None = None
    parsed_sha256: Digest | None = None
    metadata_projection_json: Annotated[str, Field(max_length=32768)] | None = None
    metadata_projection_sha256: Digest | None = None
    response_date: Annotated[str, Field(max_length=256)] | None = None
    last_modified: Annotated[str, Field(max_length=256)] | None = None
    etag: Annotated[str, Field(max_length=512)] | None = None
    checks: Annotated[tuple[Reason, ...], Field(max_length=16)] = ()
    limitations: Annotated[tuple[Reason, ...], Field(max_length=16)] = ()
    advisory_coverage: Literal["not_examined"] = "not_examined"

    @field_validator("requested_at", "observed_at")
    @classmethod
    def aware_time(cls, value: datetime) -> datetime:
        if value.tzinfo is None or value.utcoffset() is None:
            raise ValueError("observation timestamps must include timezone")
        return value

    @model_validator(mode="after")
    def returned_bytes_identity(self) -> SourceObservation:
        if self.status == "ok" and (self.raw_sha256 is None or self.parsed_sha256 is None):
            raise ValueError("successful observations require raw and parsed identities")
        if (self.metadata_projection_json is None) != (self.metadata_projection_sha256 is None):
            raise ValueError("metadata projection requires bytes and identity together")
        if self.metadata_projection_json is not None:
            projection = json.loads(self.metadata_projection_json)
            encoded = self.metadata_projection_json.encode("utf-8")
            if (
                not isinstance(projection, dict)
                or canonical_bytes(projection) != encoded
                or sha256(encoded) != self.metadata_projection_sha256
            ):
                raise ValueError("metadata projection must be canonical and hash-bound")
        if self.observed_at < self.requested_at:
            raise ValueError("observation precedes request")
        return self


class Conflict(FrozenModel):
    stored_position_id: Identifier
    observation_ids: Annotated[tuple[Identifier, ...], Field(min_length=1, max_length=6)]
    note: Text


class Implication(FrozenModel):
    observation_ids: Annotated[tuple[Identifier, ...], Field(min_length=1, max_length=6)]
    guidance: Text


class Omission(FrozenModel):
    reference_id: Identifier
    reason: Reason


class Interpretation(FrozenModel):
    """Bounded model output form; code does not judge entailment or disagreement."""

    comparison_status: Literal["changed", "no_change", "unchecked"] = "unchecked"
    conflicts: Annotated[tuple[Conflict, ...], Field(max_length=24)] = ()
    implications: Annotated[tuple[Implication, ...], Field(max_length=24)] = ()
    limitations: Annotated[tuple[Reason, ...], Field(max_length=24)] = ()


class PreparationPacket(FrozenModel):
    schema_version: Literal["deepr-prepared-context-v1"] = "deepr-prepared-context-v1"
    envelope: PreparationEnvelope
    assumptions: Annotated[tuple[Assumption, ...], Field(max_length=6)] = ()
    observations: Annotated[tuple[SourceObservation, ...], Field(max_length=6)] = ()
    interpretation: Interpretation = Field(default_factory=Interpretation)
    omissions: Annotated[tuple[Omission, ...], Field(max_length=64)] = ()
    limits: PreparationLimits = Field(default_factory=PreparationLimits)
    attempts: Annotated[StrictInt, Field(ge=0, le=6)] = 0
    stop_reason: Literal["complete", "partial", "failed", "cancelled", "offline"]

    @model_validator(mode="after")
    def validate_references(self) -> PreparationPacket:
        coordinates = {package.coordinate_id for package in self.envelope.request.packages}
        observation_ids = {item.observation_id for item in self.observations}
        assumption_ids = {item.assumption_id for item in self.assumptions}
        if len(observation_ids) != len(self.observations) or len(assumption_ids) != len(self.assumptions):
            raise ValueError("duplicate record identity")
        if any(item.coordinate_id not in coordinates for item in self.observations):
            raise ValueError("observation coordinate not admitted")
        if any(set(item.coordinate_ids) - coordinates for item in self.assumptions):
            raise ValueError("assumption coordinate not admitted")
        if any(
            item.stored_position_id not in self.envelope.stored_position_ids for item in self.interpretation.conflicts
        ):
            raise ValueError("unknown stored position reference")
        references = [item.observation_ids for item in self.interpretation.conflicts]
        references.extend(item.observation_ids for item in self.interpretation.implications)
        for referenced_ids in references:
            if set(referenced_ids) - observation_ids:
                raise ValueError("unknown observation reference")
        if any(item.reference_id not in coordinates | observation_ids | assumption_ids for item in self.omissions):
            raise ValueError("unknown omission reference")
        if self.attempts > self.limits.requests or len(self.observations) > self.limits.sources:
            raise ValueError("packet exceeds operation limits")
        return self


class ProjectionManifest(FrozenModel):
    content_sha256: Digest
    review_markdown_sha256: Digest
    graph_sha256: Digest


class FrozenPreparation(FrozenModel):
    """Content freezes first; derived projection hashes never enter its identity."""

    content: bytes
    review_markdown: bytes
    graph: bytes
    manifest: ProjectionManifest

    @model_validator(mode="after")
    def verify_hashes(self) -> FrozenPreparation:
        if (sha256(self.content), sha256(self.review_markdown), sha256(self.graph)) != (
            self.manifest.content_sha256,
            self.manifest.review_markdown_sha256,
            self.manifest.graph_sha256,
        ):
            raise ValueError("projection identity mismatch")
        return self


def freeze_packet(packet: PreparationPacket) -> FrozenPreparation:
    """Derive a minimal review and graph from the same validated frozen bytes."""
    content = canonical_bytes(packet)
    restored = PreparationPacket.model_validate_json(content)
    lines = [
        "# Temporary preparation",
        "",
        f"Status: {restored.stop_reason}",
        f"Packet SHA256: {sha256(content)}",
        "",
        "Comprehensive advisory coverage: not examined. Returned adverse metadata remains evidence.",
    ]
    nodes = []
    for assumption in restored.assumptions:
        lines += [
            "",
            f"Assumption {assumption.assumption_id}: {assumption.text}",
            f"Check: {assumption.status}. {assumption.reason}",
        ]
    for observation in restored.observations:
        lines += ["", f"Source {observation.observation_id}: {observation.source_class}, {observation.status}"]
        lines += [
            f"Observed: {observation.observed_at.isoformat()}",
            "Applicable versions: " + ", ".join(observation.applicable_versions),
        ]
        lines += [f"Check: {check}" for check in observation.checks]
        lines += [f"Limit: {limit}" for limit in observation.limitations]
        lines += [
            f"Raw SHA256: {observation.raw_sha256}",
            f"Parsed SHA256: {observation.parsed_sha256}",
            f"Metadata projection SHA256: {observation.metadata_projection_sha256}",
            "Metadata projection (untrusted evidence):",
            "```json",
            observation.metadata_projection_json or "null",
            "```",
        ]
        nodes.append({"id": observation.observation_id, **observation.model_dump(mode="json")})
    for conflict in restored.interpretation.conflicts:
        lines += [
            "",
            f"Conflict with {conflict.stored_position_id}: {conflict.note}",
            "Sources: " + ", ".join(conflict.observation_ids),
        ]
    for implication in restored.interpretation.implications:
        lines += ["", implication.guidance, "Sources: " + ", ".join(implication.observation_ids)]
    for omission in restored.omissions:
        lines += ["", f"Omitted {omission.reference_id}: {omission.reason}"]
    lines += ["", *restored.interpretation.limitations]
    markdown = ("\n".join(lines) + "\n").encode("utf-8")
    graph = canonical_bytes(
        {
            "packet_sha256": sha256(content),
            "observations": nodes,
            "conflicts": [item.model_dump() for item in restored.interpretation.conflicts],
            "implications": [item.model_dump() for item in restored.interpretation.implications],
        }
    )
    return FrozenPreparation(
        content=content,
        review_markdown=markdown,
        graph=graph,
        manifest=ProjectionManifest(
            content_sha256=sha256(content), review_markdown_sha256=sha256(markdown), graph_sha256=sha256(graph)
        ),
    )
