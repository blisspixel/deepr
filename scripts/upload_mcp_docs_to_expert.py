"""Upload MCP documentation to Agentic Digital Consciousness expert."""
import asyncio
from pathlib import Path
from deepr.experts.profile import ExpertProfile, ExpertStore
from openai import AsyncOpenAI

async def main():
    # Load expert
    store = ExpertStore()
    expert = store.load("Agentic Digital Consciousness")

    if not expert:
        print("Expert not found!")
        return

    # Read MCP documentation
    mcp_doc_path = Path("docs/documentation openai deep research api and MCP details.txt")
    with open(mcp_doc_path, 'r', encoding='utf-8') as f:
        content = f.read()

    # Save to expert's documents folder
    docs_dir = store.get_documents_dir(expert.name)
    docs_dir.mkdir(parents=True, exist_ok=True)

    target_path = docs_dir / "openai_mcp_deep_research_documentation.md"
    with open(target_path, 'w', encoding='utf-8') as f:
        f.write(f"""# OpenAI MCP and Deep Research Documentation

Source: Internal OpenAI documentation
Date: 2025

---

{content}
""")

    print(f"Saved to: {target_path}")

    # Upload to vector store
    client = AsyncOpenAI()

    print("Uploading to vector store...")
    with open(target_path, 'rb') as f:
        file_obj = await client.files.create(
            file=f,
            purpose="assistants"
        )

    print(f"File uploaded: {file_obj.id}")

    # Add to vector store
    await client.beta.vector_stores.files.create(
        vector_store_id=expert.vector_store_id,
        file_id=file_obj.id
    )

    print("Added to vector store")

    # Update expert profile
    expert.total_documents += 1
    expert.source_files.append(str(target_path))
    store.save(expert)

    print(f"\n✓ MCP documentation added to expert")
    print(f"  Total documents: {expert.total_documents}")
    print(f"  Vector store: {expert.vector_store_id}")

if __name__ == "__main__":
    asyncio.run(main())
