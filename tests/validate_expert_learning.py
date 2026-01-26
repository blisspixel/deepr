"""Validate that an expert actually learned something useful.

This script checks:
1. Expert profile metadata (documents, research jobs, costs)
2. Beliefs formed (if synthesis ran)
3. Response quality to domain questions
4. Knowledge coverage
"""

import asyncio
import sys
from pathlib import Path

from deepr.experts.profile import ExpertStore
from deepr.experts.chat import ExpertChatSession


async def validate_expert(expert_name: str):
    """Validate an expert's learning and capabilities."""
    
    print(f"\n{'='*70}")
    print(f"  Validating Expert: {expert_name}")
    print(f"{'='*70}\n")
    
    # Load expert
    store = ExpertStore()
    profile = store.load(expert_name)
    
    if not profile:
        print(f"❌ Expert not found: {expert_name}")
        return False
    
    print(f"✓ Expert loaded: {profile.name}")
    print()
    
    # Check 1: Metadata
    print("1. Metadata Check")
    print(f"   Documents: {profile.total_documents}")
    print(f"   Research jobs: {len(profile.research_jobs)}")
    print(f"   Total cost: ${profile.total_research_cost:.4f}")
    print(f"   Conversations: {profile.conversations}")
    
    if profile.total_documents < 2:
        print(f"   ⚠ Warning: Only {profile.total_documents} document(s)")
    else:
        print(f"   ✓ Has multiple documents")
    
    if len(profile.research_jobs) == 0:
        print(f"   ⚠ Warning: No research jobs executed")
    else:
        print(f"   ✓ Executed {len(profile.research_jobs)} research job(s)")
    
    print()
    
    # Check 2: Beliefs (if available)
    print("2. Beliefs Check")
    
    if hasattr(profile, 'beliefs') and profile.beliefs:
        print(f"   ✓ Formed {len(profile.beliefs)} belief(s)")
        
        # Show sample beliefs
        for i, (key, belief) in enumerate(list(profile.beliefs.items())[:5], 1):
            confidence = belief.get('confidence', 0)
            statement = belief.get('statement', '')
            sources = belief.get('sources', [])
            
            print(f"\n   Belief {i}:")
            print(f"     Statement: {statement[:100]}...")
            print(f"     Confidence: {confidence:.2f}")
            print(f"     Sources: {len(sources)}")
    else:
        print(f"   ⚠ No beliefs formed (synthesis may not have run)")
    
    print()
    
    # Check 3: Response Quality
    print("3. Response Quality Check")
    
    # Create chat session
    session = ExpertChatSession(profile, agentic=False, budget=0.0)
    
    # Test questions based on domain
    domain_lower = (profile.domain or profile.name).lower()
    
    if 'keyboard' in domain_lower:
        test_questions = [
            "What are the main types of mechanical keyboard switches?",
            "What are the benefits of mechanical keyboards?",
            "What brands make mechanical keyboards?"
        ]
    else:
        # Generic questions
        test_questions = [
            f"What are the key concepts in {profile.domain or profile.name}?",
            f"What are the main benefits or advantages?",
            f"What are common best practices?"
        ]
    
    passed = 0
    failed = 0
    
    for i, question in enumerate(test_questions, 1):
        print(f"\n   Question {i}: {question}")
        
        try:
            response = await session.chat(question)
            
            # Basic quality checks
            if len(response) < 50:
                print(f"   ❌ Response too short ({len(response)} chars)")
                failed += 1
                continue
            
            if "I don't know" in response or "I'm not sure" in response:
                print(f"   ⚠ Expert uncertain")
            
            # Check for substantive content
            words = response.split()
            if len(words) < 20:
                print(f"   ❌ Response lacks detail ({len(words)} words)")
                failed += 1
                continue
            
            print(f"   ✓ Response: {len(response)} chars, {len(words)} words")
            
            # Show excerpt
            excerpt = response[:120] + "..." if len(response) > 120 else response
            print(f"   Preview: {excerpt}")
            
            passed += 1
            
        except Exception as e:
            print(f"   ❌ Error: {e}")
            failed += 1
    
    print()
    print(f"   Results: {passed}/{len(test_questions)} passed")
    
    # Check 4: Knowledge Coverage
    print()
    print("4. Knowledge Coverage")
    
    if profile.source_files:
        print(f"   Source files: {len(profile.source_files)}")
        for f in profile.source_files[:5]:
            print(f"     - {Path(f).name}")
        if len(profile.source_files) > 5:
            print(f"     ... and {len(profile.source_files) - 5} more")
    
    if profile.knowledge_cutoff_date:
        freshness = profile.get_freshness_status()
        age_days = freshness.get('age_days', 0)
        status = freshness.get('status', 'unknown')
        print(f"   Knowledge age: {age_days} days [{status}]")
    
    # Final verdict
    print()
    print(f"{'='*70}")
    
    all_checks_passed = (
        profile.total_documents >= 2 and
        len(profile.research_jobs) > 0 and
        passed >= len(test_questions) * 0.6  # At least 60% of questions
    )
    
    if all_checks_passed:
        print(f"  ✅ VALIDATION PASSED")
        print(f"  Expert has learned and can answer domain questions")
    else:
        print(f"  ⚠ VALIDATION INCOMPLETE")
        print(f"  Expert may need more learning or synthesis")
    
    print(f"{'='*70}\n")
    
    return all_checks_passed


async def main():
    """Main entry point."""
    if len(sys.argv) < 2:
        print("Usage: python validate_expert_learning.py <expert_name>")
        print()
        print("Example:")
        print("  python validate_expert_learning.py 'Keyboards Test'")
        sys.exit(1)
    
    expert_name = sys.argv[1]
    success = await validate_expert(expert_name)
    
    sys.exit(0 if success else 1)


if __name__ == "__main__":
    asyncio.run(main())
