"""End-to-end test: Create a keyboards expert with minimal research.

This test actually creates an expert, runs 1 doc + 1 quick research,
then validates the expert learned something useful.

Cost: ~$0.004 (very cheap)
"""

import asyncio
import tempfile
from datetime import datetime
from pathlib import Path

import pytest

from deepr.config import AppConfig
from deepr.experts.curriculum import CurriculumGenerator
from deepr.experts.learner import AutonomousLearner
from deepr.experts.profile import ExpertProfile, ExpertStore, get_expert_system_message
from deepr.providers import create_provider


@pytest.mark.integration
@pytest.mark.asyncio
async def test_keyboards_expert_e2e():
    """Create a keyboards expert with 1 doc + 1 quick research, validate learning."""

    # Setup
    expert_name = "Keyboards Test Expert"
    test_doc_content = """# Mechanical Keyboards Guide

## What are Mechanical Keyboards?

Mechanical keyboards use individual mechanical switches for each key,
providing tactile feedback and durability. Unlike membrane keyboards,
each key has its own switch mechanism.

## Popular Switch Types

1. **Cherry MX Red** - Linear, smooth, no tactile bump
2. **Cherry MX Brown** - Tactile bump, quiet
3. **Cherry MX Blue** - Tactile and clicky, loud

## Benefits

- Durability (50-100 million keystrokes)
- Better typing experience
- Customizable keycaps
- N-key rollover support

## Common Brands

- Keychron
- Ducky
- Leopold
- Varmilo
"""

    # Create temporary test document
    with tempfile.TemporaryDirectory() as tmpdir:
        doc_path = Path(tmpdir) / "keyboard_guide.md"
        doc_path.write_text(test_doc_content)

        print(f"\n{'=' * 70}")
        print("  Creating Keyboards Expert (E2E Test)")
        print(f"{'=' * 70}\n")

        # Step 1: Create expert with initial document
        print("Step 1: Creating expert with initial document...")

        config = AppConfig.from_env()
        provider = create_provider("openai", api_key=config.provider.openai_api_key)

        # Upload document
        file_id = await provider.upload_document(str(doc_path))
        print(f"  ✓ Uploaded document: {file_id}")

        # Create vector store
        vector_store = await provider.create_vector_store(
            name=f"test-keyboards-{datetime.utcnow().strftime('%Y%m%d%H%M%S')}", file_ids=[file_id]
        )
        print(f"  ✓ Created vector store: {vector_store.id}")

        # Wait for indexing
        success = await provider.wait_for_vector_store(vector_store.id, timeout=120)
        assert success, "Vector store indexing failed"
        print("  ✓ Indexing complete")

        # Create expert profile
        now = datetime.utcnow()
        profile = ExpertProfile(
            name=expert_name,
            vector_store_id=vector_store.id,
            description="Expert on mechanical keyboards",
            domain="Mechanical Keyboards",
            source_files=[str(doc_path)],
            total_documents=1,
            knowledge_cutoff_date=now,
            last_knowledge_refresh=now,
            system_message=get_expert_system_message(knowledge_cutoff_date=now, domain_velocity="medium"),
            provider="openai",
        )

        # Save profile
        store = ExpertStore()
        store.save(profile)
        print("  ✓ Expert profile saved\n")

        try:
            # Step 2: Generate curriculum (1 doc + 1 quick)
            print("Step 2: Generating curriculum (1 doc + 1 quick)...")

            generator = CurriculumGenerator(config)
            curriculum = await generator.generate_curriculum(
                expert_name=expert_name,
                domain="Mechanical Keyboards",
                initial_documents=["keyboard_guide.md"],
                target_topics=2,
                budget_limit=0.01,  # Very small budget
                docs_count=1,
                quick_count=1,
                deep_count=0,
                enable_discovery=False,  # Skip discovery for speed
            )

            assert curriculum is not None, "Curriculum generation failed"
            assert len(curriculum.topics) == 2, f"Expected 2 topics, got {len(curriculum.topics)}"
            print(f"  ✓ Generated {len(curriculum.topics)} topics")
            print(f"  ✓ Estimated cost: ${curriculum.total_estimated_cost:.4f}")
            print(f"  ✓ Estimated time: {curriculum.total_estimated_minutes}min\n")

            # Display topics
            for i, topic in enumerate(curriculum.topics, 1):
                print(f"  Topic {i}: {topic.title}")
                print(f"    Mode: {topic.research_mode}")
                print(f"    Type: {topic.research_type}")
                print(f"    Cost: ${topic.estimated_cost:.4f}")
            print()

            # Step 3: Execute curriculum
            print("Step 3: Executing curriculum...")

            learner = AutonomousLearner(config)
            progress = await learner.execute_curriculum(
                expert=profile, curriculum=curriculum, budget_limit=0.01, dry_run=False
            )

            assert progress is not None, "Curriculum execution failed"
            print(f"  ✓ Completed: {len(progress.completed_topics)} topics")
            print(f"  ✓ Failed: {len(progress.failed_topics)} topics")
            print(f"  ✓ Actual cost: ${progress.total_cost:.4f}")

            duration = (progress.completed_at - progress.started_at).total_seconds()
            print(f"  ✓ Duration: {duration:.0f}s\n")

            # Step 4: Validate expert learned something
            print("Step 4: Validating expert knowledge...")

            # Reload expert profile
            updated_profile = store.load(expert_name)
            assert updated_profile is not None, "Failed to reload expert"

            # Check metadata updates
            assert updated_profile.total_documents > 1, "No new documents added"
            print(f"  ✓ Documents: {profile.total_documents} → {updated_profile.total_documents}")

            assert len(updated_profile.research_jobs) > 0, "No research jobs recorded"
            print(f"  ✓ Research jobs: {len(updated_profile.research_jobs)}")

            # Check beliefs were formed
            if hasattr(updated_profile, "beliefs") and updated_profile.beliefs:
                print(f"  ✓ Beliefs formed: {len(updated_profile.beliefs)}")

                # Display sample beliefs
                for belief_key, belief_data in list(updated_profile.beliefs.items())[:3]:
                    confidence = belief_data.get("confidence", 0)
                    statement = belief_data.get("statement", "")[:80]
                    print(f"    - {statement}... (confidence: {confidence:.2f})")
            else:
                print("  ⚠ No beliefs formed yet (may need synthesis)")

            print()

            # Step 5: Test expert can answer questions
            print("Step 5: Testing expert responses...")

            from deepr.experts.chat import ExpertChatSession

            session = ExpertChatSession(updated_profile, agentic=False, budget=0.0)

            test_questions = [
                "What are the main types of mechanical keyboard switches?",
                "What are the benefits of mechanical keyboards?",
            ]

            for question in test_questions:
                print(f"\n  Q: {question}")
                try:
                    response = await session.chat(question)

                    # Validate response quality
                    assert len(response) > 50, "Response too short"

                    # Check for key terms from the document
                    response_lower = response.lower()

                    if "switch" in question.lower():
                        # Should mention switch types
                        has_switches = any(
                            term in response_lower for term in ["cherry", "red", "brown", "blue", "linear", "tactile"]
                        )
                        assert has_switches, "Response doesn't mention switch types"
                        print("  ✓ Mentioned switch types")

                    if "benefit" in question.lower():
                        # Should mention benefits
                        has_benefits = any(
                            term in response_lower for term in ["durability", "typing", "customizable", "rollover"]
                        )
                        assert has_benefits, "Response doesn't mention benefits"
                        print("  ✓ Mentioned benefits")

                    # Show excerpt
                    excerpt = response[:150] + "..." if len(response) > 150 else response
                    print(f"  A: {excerpt}")

                except Exception as e:
                    print(f"  ✗ Error: {e}")
                    raise

            print(f"\n{'=' * 70}")
            print("  ✅ E2E Test PASSED")
            print(f"{'=' * 70}\n")

            print("Summary:")
            print(f"  - Expert created: {expert_name}")
            print(f"  - Documents: {updated_profile.total_documents}")
            print(f"  - Research jobs: {len(updated_profile.research_jobs)}")
            print(f"  - Total cost: ${progress.total_cost:.4f}")
            print("  - Can answer domain questions: ✓")

        finally:
            # Cleanup
            print("\nCleaning up...")

            # Delete expert profile
            if store.load(expert_name):
                store.delete(expert_name)
                print("  ✓ Deleted expert profile")

            # Note: Vector store cleanup would require API call
            print(f"  ⚠ Vector store {vector_store.id} should be manually deleted")
            print(f"    Run: deepr knowledge delete {vector_store.id}")


if __name__ == "__main__":
    # Run with: python -m pytest tests/test_expert_keyboards_e2e.py -v -s
    asyncio.run(test_keyboards_expert_e2e())
