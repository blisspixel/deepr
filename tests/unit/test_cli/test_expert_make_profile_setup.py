import pytest

from deepr.cli.commands.semantic.expert_make_profile_setup import (
    GIB,
    ProviderProfileSetupPreview,
    format_provider_profile_setup_preview,
)


def test_provider_profile_setup_uses_provider_specific_vector_storage_rate():
    preview = ProviderProfileSetupPreview(
        provider="azure",
        file_count=1,
        upload_bytes=3 * GIB,
        vector_store_storage_usd_per_gib_day=0.11,
    )

    assert preview.estimated_storage_usd_per_day_after_free_tier == pytest.approx(0.22)
    assert any("$0.220000/day" in line for line in format_provider_profile_setup_preview(preview))


def test_provider_profile_setup_uses_generic_warning_without_storage_rate():
    preview = ProviderProfileSetupPreview(
        provider="gemini",
        file_count=1,
        upload_bytes=GIB,
        vector_store_storage_usd_per_gib_day=None,
    )

    lines = format_provider_profile_setup_preview(preview)

    assert preview.estimated_storage_usd_per_day_after_free_tier == 0.0
    assert any("vendor-billed file upload or file-processing path" in line for line in lines)
