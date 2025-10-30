# Documentation Research Template

This template produces developer-focused documentation for APIs, services, and technologies.

## Usage

```bash
# Using template with CLI
deepr run single --template documentation "AWS Lambda" --provider gemini

# Direct prompt
deepr run single "Research AWS Lambda for documentation" --provider gemini
```

## Template Structure

**What makes documentation research different:**
1. Focus on current state (as of today's date)
2. Structured for developers (API details, code examples, best practices)
3. Emphasis on what changed recently
4. Architecture diagrams and patterns
5. Pricing and limits clearly stated

## Example Prompts

### Cloud Service Documentation
```
Research [SERVICE_NAME] as of [TODAY_DATE] for developer documentation:

1. Current Features & Capabilities
   - Core functionality
   - Latest additions (last 6 months)
   - Beta/preview features

2. API Reference
   - Key endpoints/methods
   - Authentication patterns
   - Rate limits and quotas

3. Pricing & Limits
   - Pricing tiers with specific numbers
   - Free tier details
   - Hard limits and soft limits

4. Architecture Patterns
   - Recommended architectures
   - Common integration patterns
   - Anti-patterns to avoid

5. Best Practices
   - Performance optimization
   - Security considerations
   - Cost optimization tips

Format as developer documentation with code examples. Include recent changes and deprecations.
```

### AI Model/API Documentation
```
Document [MODEL/API_NAME] as of [TODAY_DATE] for developers:

1. Models Available
   - Model names and variants
   - Capabilities and limitations
   - Context windows and token limits

2. Pricing Structure
   - Cost per token/request
   - Volume discounts
   - Enterprise pricing

3. API Details
   - Authentication
   - Request/response formats
   - Key parameters and their effects

4. Features & Capabilities
   - Reasoning/thinking features
   - Tool calling/function support
   - Multimodal support

5. Integration Guide
   - Code examples (Python, JavaScript)
   - SDK availability
   - Error handling patterns

6. Recent Updates
   - What changed in last 3 months
   - Upcoming features
   - Deprecations

Include specific examples and cite official documentation.
```

### Framework/Library Documentation
```
Create developer documentation for [FRAMEWORK] as of [TODAY_DATE]:

1. Getting Started
   - Installation
   - Quick start example
   - Core concepts

2. API Reference
   - Key classes/functions
   - Common patterns
   - Configuration options

3. Advanced Features
   - New capabilities (last 6 months)
   - Plugin/extension system
   - Performance tuning

4. Best Practices
   - Recommended project structure
   - Testing strategies
   - Production considerations

5. Migration & Updates
   - Breaking changes
   - Upgrade path
   - Compatibility notes

Focus on practical examples developers can copy-paste.
```

## Variables

These are automatically injected:
- `{TODAY_DATE}` - Current date from system
- `{SERVICE_NAME}` - Provided by user
- `{MODEL_NAME}` - Provided by user

## Output Format

Documentation research should produce:
- Structured markdown with clear sections
- Code examples in proper syntax highlighting
- Specific version numbers and dates
- Links to official sources
- Tables for pricing/limits
- Clear "last updated" timestamp

## Use Cases

**When to use documentation mode:**
- Researching cloud services (AWS, Azure, GCP)
- AI model capabilities and APIs
- Framework/library references
- Service pricing and limits
- Architecture patterns
- Best practices for specific technologies

**When to use regular research mode:**
- Strategic questions
- Market analysis
- Comparative research
- Opinion-based research
- Historical analysis
