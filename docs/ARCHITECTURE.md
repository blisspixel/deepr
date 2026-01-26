# Deepr Architecture

## Overview

Deepr is an agentic research platform that uses AI models to conduct deep research, build domain experts, and synthesize knowledge.

## Core Components

### 1. Research Engine
- **Location**: `deepr/research_agent/`
- **Purpose**: Conducts multi-step research using AI models
- **Modes**:
  - `FOCUS`: Quick research (5-10 min, ~$0.25)
  - `CAMPAIGN`: Deep research (30-60 min, ~$2.00)

### 2. Expert System
- **Location**: `deepr/experts/`
- **Purpose**: Creates domain experts that learn and answer questions
- **Components**:
  - `curriculum.py`: Generates learning plans
  - `base.py`: Expert creation and management
  - `router.py`: Routes queries to appropriate models

### 3. Provider System
- **Location**: `deepr/providers/`
- **Purpose**: Unified interface to AI providers
- **Providers**:
  - OpenAI (GPT-5.2, o4-mini-deep-research)
  - xAI (Grok 4 Fast, Grok 4)
  - Google (Gemini 2.5 Flash, Gemini 3 Pro)
  - Anthropic (Claude Sonnet 4.5)

### 4. Model Registry
- **Location**: `deepr/providers/registry.py`
- **Purpose**: Single source of truth for model capabilities
- **Contains**:
  - Model costs
  - Latency estimates
  - Context windows
  - Specializations (reasoning, speed, cost, etc.)

**CRITICAL**: When new models are released (GPT-5.3, Grok 5, etc.), update ONLY the registry. Never hardcode model names elsewhere.

### 5. Queue System
- **Location**: `deepr/queue/`
- **Purpose**: Manages research job execution
- **Supports**:
  - Local queue (SQLite)
  - Azure Queue Storage (production)

### 6. Storage System
- **Location**: `deepr/storage/`
- **Purpose**: Stores research results and expert knowledge
- **Supports**:
  - Local filesystem
  - Azure Blob Storage (production)

## Data Flow

### Research Flow
```
User Query
    |
Research Planner (generates plan)
    |
Queue System (schedules jobs)
    |
Research Agent (executes with AI model)
    |
Storage System (saves results)
    |
User receives report
```

### Expert Flow
```
Create Expert
    |
Curriculum Generator (plans learning topics)
    |
Research Agent (learns each topic)
    |
Vector Store (stores knowledge)
    |
Expert ready to answer questions
```

## Model Selection

**CRITICAL**: All models are defined in `deepr/providers/registry.py`. This is the SINGLE SOURCE OF TRUTH. When GPT-5.3 or Grok 5 are released, update ONLY the registry. Never hardcode model names.

### Current Models

- **GPT-5.2** (OpenAI): $0.25, 2s, best for planning/curriculum
- **o4-mini-deep-research** (OpenAI): $2.00, 60s, best for deep research
- **Grok 4 Fast** (xAI): $0.01, 1s, best for quick lookups
- **Gemini 3 Pro** (Google): $0.15, 4s, 1M context for large docs
- **Claude Sonnet 4.5** (Anthropic): $0.25, 3s, best for coding

Models are selected based on:
- **Task complexity**: Simple vs complex reasoning
- **Budget**: Cost constraints
- **Speed**: Latency requirements
- **Context size**: Amount of information to process

See `deepr/providers/registry.py` for full model capabilities.

## Configuration

Configuration is managed through:
- `deepr/config.py`: Main configuration
- `.env`: Environment variables (API keys, etc.)
- `deepr/config/`: Provider-specific configs

## Key Design Principles

1. **Single Source of Truth**: Model registry for all model info
2. **Provider Abstraction**: Unified interface across providers
3. **Async by Default**: All I/O operations are async
4. **Cost Tracking**: Every operation tracks costs
5. **Stateless**: Research jobs can be resumed/retried

## Directory Structure

```
deepr/
├── api/              # REST API (FastAPI)
├── cli/              # Command-line interface
├── config/           # Configuration management
├── core/             # Core business logic
├── experts/          # Expert system
├── providers/        # AI provider integrations
├── queue/            # Job queue system
├── research_agent/   # Research execution
├── storage/          # Data persistence
├── tools/            # Utility tools
└── web/              # Web interface
```

## Extension Points

To add new capabilities:

1. **New AI Provider**: Implement `BaseProvider` in `deepr/providers/`
2. **New Model**: Add to `MODEL_CAPABILITIES` in `registry.py`
3. **New Research Mode**: Extend `ResearchMode` enum
4. **New Storage Backend**: Implement `BaseStorage` interface

## Performance Considerations

- **Caching**: Prompt caching reduces costs by 90%
- **Parallel Execution**: Multiple research jobs run concurrently
- **Model Selection**: Router picks cheapest model that meets requirements
- **Context Management**: Automatic context window management

## Security

- API keys stored in environment variables
- No sensitive data in logs
- Rate limiting on API endpoints
- Input validation on all user inputs

## Monitoring

- Cost tracking per job
- Latency metrics per provider
- Error rates and retry logic
- Usage analytics in web dashboard
