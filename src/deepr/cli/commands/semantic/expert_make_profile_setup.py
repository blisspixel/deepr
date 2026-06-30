"""Cost-posture preview for API-backed ``expert make`` profile setup."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

GIB = 1024**3
MIB = 1024**2
VECTOR_STORE_INCLUDED_GIB = 1.0
VECTOR_STORE_STORAGE_USD_PER_GIB_DAY = {
    "openai": 0.10,
    "azure": 0.11,
}


@dataclass(frozen=True)
class ProviderProfileSetupPreview:
    """Human-readable cost posture for provider-backed profile creation."""

    provider: str
    file_count: int
    upload_bytes: int
    vector_store_storage_usd_per_gib_day: float | None

    @property
    def upload_mib(self) -> float:
        return self.upload_bytes / MIB

    @property
    def estimated_vector_storage_gib(self) -> float:
        return self.upload_bytes / GIB

    @property
    def estimated_storage_usd_per_day_after_free_tier(self) -> float:
        if self.vector_store_storage_usd_per_gib_day is None:
            return 0.0
        billable_gib = max(0.0, self.estimated_vector_storage_gib - VECTOR_STORE_INCLUDED_GIB)
        return billable_gib * self.vector_store_storage_usd_per_gib_day


def build_provider_profile_setup_preview(provider: str, files: tuple[str, ...]) -> ProviderProfileSetupPreview:
    upload_bytes = 0
    for file_path in files:
        upload_bytes += max(Path(file_path).stat().st_size, 0)
    normalized_provider = provider.strip().lower()
    return ProviderProfileSetupPreview(
        provider=normalized_provider,
        file_count=len(files),
        upload_bytes=upload_bytes,
        vector_store_storage_usd_per_gib_day=VECTOR_STORE_STORAGE_USD_PER_GIB_DAY.get(normalized_provider),
    )


def format_provider_profile_setup_preview(preview: ProviderProfileSetupPreview) -> list[str]:
    """Format a warning without binding this helper to Click or Rich."""
    lines = [
        "API-backed expert profile setup",
        f"Provider: {preview.provider} (metered API key path)",
        f"Files: {preview.file_count} file(s), {preview.upload_mib:.3f} MiB selected for upload",
    ]
    if preview.vector_store_storage_usd_per_gib_day is not None:
        lines.append(
            "Estimated retained vector-store storage: "
            f"{preview.estimated_vector_storage_gib:.6f} GiB; "
            "estimated storage after provider free tier: "
            f"${preview.estimated_storage_usd_per_day_after_free_tier:.6f}/day"
        )
        lines.append(
            "Provider invoices can differ because parsed vector-store size, retention, and current vendor pricing "
            "are outside Deepr's local ledger."
        )
    else:
        lines.append(
            "Estimated provider setup cost: vendor-billed file upload or file-processing path; no Deepr ledger "
            "reservation is available for this profile setup step."
        )
    lines.append("Use --local for provider-free $0 profile setup, then sync or absorb on local or plan capacity.")
    return lines


def confirm_provider_profile_setup(
    *, provider: str, files: tuple[str, ...], yes: bool, confirm_metered_profile: bool
) -> bool:
    import click

    from deepr.cli.colors import console, print_error, print_warning

    setup_preview = build_provider_profile_setup_preview(provider, files)
    for line in format_provider_profile_setup_preview(setup_preview):
        console.print(f"[yellow]{line}[/yellow]")
    if yes and not confirm_metered_profile:
        print_error(
            "API-backed expert setup with --yes requires --confirm-metered-profile after reviewing the setup estimate."
        )
        return False
    if not yes and not click.confirm("Create this API-backed expert profile now?", default=False):
        print_warning("Cancelled.")
        return False
    return True
