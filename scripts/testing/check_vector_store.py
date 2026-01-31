"""Check vector store file status"""
import asyncio
import os
from dotenv import load_dotenv
from openai import AsyncOpenAI

load_dotenv()

async def check_vector_store():
    client = AsyncOpenAI(api_key=os.getenv("OPENAI_API_KEY"))

    # Microsoft AI Expert vector store ID
    vector_store_id = "vs_69710e818bd081919cc0a7ca2d32f4e3"

    print(f"Checking vector store: {vector_store_id}\n")

    # Get vector store details
    vs = await client.vector_stores.retrieve(vector_store_id)
    print(f"Vector Store: {vs.name}")
    print(f"File counts:")
    print(f"  Total: {vs.file_counts.total}")
    print(f"  In progress: {vs.file_counts.in_progress}")
    print(f"  Completed: {vs.file_counts.completed}")
    print(f"  Failed: {vs.file_counts.failed}")
    print(f"  Cancelled: {vs.file_counts.cancelled}")
    print(f"Status: {vs.status}")
    print()

    # List recent files
    print("Recent files:")
    files = await client.vector_stores.files.list(vector_store_id, limit=5)
    for f in files.data:
        print(f"  {f.id}: status={f.status}, created={f.created_at}")

    await client.close()

if __name__ == "__main__":
    asyncio.run(check_vector_store())
