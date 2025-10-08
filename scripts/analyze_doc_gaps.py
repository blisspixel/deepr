"""
Analyze existing documentation and identify gaps.

Uses GPT-5 to review what docs we have and what we need.
"""

import os
from pathlib import Path
from dotenv import load_dotenv
from openai import OpenAI
import json

load_dotenv()

def main():
    client = OpenAI(api_key=os.getenv('OPENAI_API_KEY'))

    # Scan existing docs
    docs_path = Path('docs/research and documentation')
    doc_files = list(docs_path.glob('*.txt')) + list(docs_path.glob('*.md'))

    print(f'Found {len(doc_files)} existing documents\n')

    # Build document inventory
    doc_inventory = []
    for doc in doc_files:
        try:
            with open(doc, 'r', encoding='utf-8') as f:
                content = f.read(1000)  # First 1000 chars
                doc_inventory.append({
                    'name': doc.name,
                    'size_kb': doc.stat().st_size / 1024,
                    'preview': content[:500]
                })
        except Exception as e:
            print(f'Could not read {doc.name}: {e}')

    # Ask GPT-5 to analyze gaps
    system_prompt = """You are a technical documentation analyst. Your job is to review existing documentation for a software project and identify what's missing.

The project is: Deepr - a multi-provider research automation platform with agentic planning, context chaining, and intelligent task routing.

Key components:
- Multi-phase research campaigns
- Smart task mix (documentation vs analysis)
- Intelligent doc reuse
- Context chaining across phases
- Multi-provider support (OpenAI, Azure, Anthropic)
- CLI interface
- Queue-based architecture
- Cost optimization

Analyze the existing documentation and identify:
1. What topics are well-covered (sufficient, don't need more)
2. What topics are missing or insufficient (need new research)
3. Recommend up to 6 specific research topics to fill the gaps

Focus on documentation that would help implement or use the platform effectively.

Return your analysis as JSON:
{
  "well_covered": ["topic 1", "topic 2"],
  "gaps": [
    {"title": "Brief title", "reason": "Why we need this", "priority": "high|medium|low"}
  ],
  "recommendations": "Brief summary of what to research next"
}"""

    user_prompt = f"""Project context: Building Deepr - multi-provider research automation platform

Existing documentation ({len(doc_inventory)} files):

"""

    for doc in doc_inventory:
        user_prompt += f"\n{doc['name']} ({doc['size_kb']:.1f}KB):\n{doc['preview'][:300]}...\n"

    user_prompt += """

Please analyze what we have and what documentation gaps exist. Recommend up to 6 specific research topics to fill the most important gaps.

Return ONLY JSON, no other text."""

    print('Asking GPT-5 to analyze documentation gaps...\n')

    try:
        response = client.responses.create(
            model='gpt-5-mini',
            input=[
                {'role': 'system', 'content': system_prompt},
                {'role': 'user', 'content': user_prompt}
            ],
        )

        # Extract response
        response_text = ''
        if hasattr(response, 'output_text'):
            response_text = response.output_text
        elif hasattr(response, 'output') and response.output:
            for item in response.output:
                if hasattr(item, 'type') and item.type == 'message':
                    for content in item.content:
                        if hasattr(content, 'type') and content.type == 'output_text':
                            response_text = content.text
                            break

        # Parse JSON
        if '```json' in response_text:
            response_text = response_text.split('```json')[1].split('```')[0].strip()
        elif '```' in response_text:
            response_text = response_text.split('```')[1].split('```')[0].strip()

        analysis = json.loads(response_text)

        print('=== ANALYSIS ===\n')
        print(f'Well-covered topics ({len(analysis.get("well_covered", []))}):'
)
        for topic in analysis.get('well_covered', []):
            print(f'  [OK] {topic}')

        print(f'\nDocumentation gaps ({len(analysis.get("gaps", []))}):')
        for i, gap in enumerate(analysis.get('gaps', []), 1):
            priority = gap.get('priority', 'medium')
            print(f'  {i}. [{priority.upper()}] {gap["title"]}')
            print(f'     {gap["reason"]}')

        print(f'\nRecommendations:')
        print(f'  {analysis.get("recommendations", "N/A")}')

        # Save to file
        output_file = Path('.deepr/doc_analysis.json')
        output_file.parent.mkdir(parents=True, exist_ok=True)
        with open(output_file, 'w') as f:
            json.dump(analysis, f, indent=2)

        print(f'\n✓ Analysis saved to {output_file}')
        return analysis

    except Exception as e:
        print(f'Error: {e}')
        import traceback
        traceback.print_exc()
        return None

if __name__ == '__main__':
    main()
