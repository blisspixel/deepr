"""Provider ownership resolution for persisted research jobs."""

from unittest.mock import MagicMock, patch

from deepr.queue.base import ResearchJob
from deepr.services.job_provider import create_job_provider


def test_create_job_provider_uses_job_owner_and_matching_key() -> None:
    job = ResearchJob(id="job-1", prompt="owner", provider="gemini")
    provider = MagicMock()

    with patch("deepr.services.job_provider.create_provider", return_value=provider) as create:
        result = create_job_provider(
            job,
            {"provider": "openai", "api_key": "openai-key", "gemini_api_key": "gemini-key"},
        )

    assert result is provider
    create.assert_called_once_with("gemini", api_key="gemini-key")


def test_create_job_provider_normalizes_grok_alias() -> None:
    job = ResearchJob(id="job-1", prompt="owner", provider="grok")

    with patch("deepr.services.job_provider.create_provider", return_value=MagicMock()) as create:
        create_job_provider(job, {"xai_api_key": "xai-key"})

    create.assert_called_once_with("xai", api_key="xai-key")


def test_create_job_provider_uses_foundry_configuration_without_api_key() -> None:
    job = ResearchJob(id="job-1", prompt="owner", provider="azure-foundry")
    config = {
        "azure_foundry_endpoint": "https://project.example",
        "azure_foundry_deep_research_deployment": "deep",
        "azure_foundry_gpt_deployment": "chat",
        "azure_foundry_bing_resource": "bing",
    }

    with patch("deepr.services.job_provider.create_provider", return_value=MagicMock()) as create:
        create_job_provider(job, config)

    create.assert_called_once_with(
        "azure-foundry",
        project_endpoint="https://project.example",
        deep_research_deployment="deep",
        gpt_deployment="chat",
        bing_resource_name="bing",
    )


def test_create_job_provider_does_not_infer_empty_job_owner_from_config() -> None:
    job = ResearchJob(id="job-1", prompt="legacy owner", provider="")

    with patch("deepr.services.job_provider.create_provider", return_value=MagicMock()) as create:
        create_job_provider(job, {"provider": "gemini", "api_key": "openai-key", "gemini_api_key": "gemini-key"})

    create.assert_called_once_with("openai", api_key="openai-key")
