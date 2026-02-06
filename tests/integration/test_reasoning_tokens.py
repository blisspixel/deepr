"""Test if we can see reasoning tokens from Chat Completions API"""

import asyncio
import os

from dotenv import load_dotenv
from openai import AsyncOpenAI

load_dotenv()


async def test():
    client = AsyncOpenAI(api_key=os.getenv("OPENAI_API_KEY"))

    print("Testing GPT-5 with reasoning_effort...")

    response = await client.chat.completions.create(
        model="gpt-5",
        messages=[
            {"role": "system", "content": "You are a helpful assistant."},
            {
                "role": "user",
                "content": "Should I search for information about quantum computing, or do you already know enough to explain it?",
            },
        ],
        reasoning_effort="medium",
    )

    print("\nResponse object attributes:")
    print(dir(response))

    print("\nUsage:")
    print(response.usage)

    print("\nMessage:")
    print(response.choices[0].message)

    print("\nFull response:")
    print(response.model_dump_json(indent=2))

    await client.close()


if __name__ == "__main__":
    asyncio.run(test())
