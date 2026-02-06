# /expert Command

Create, manage, and interact with domain experts that maintain persistent knowledge with belief formation and gap awareness.

## Syntax

```
/expert <subcommand> [arguments] [options]
```

## Subcommands

### Discovery

#### `list`

List all available experts with stats and knowledge freshness.

```
deepr expert list
```

#### `info <name>`

Show detailed expert information: provider, model, vector store, document count, usage stats.

```
deepr expert info "AWS Architect"
```

### Planning

#### `plan <domain>`

Preview a research curriculum without creating an expert. Shows topics, costs, and prompts. Great for previewing before committing to `--learn`.

| Option | Default | Description |
|--------|---------|-------------|
| `--budget` | none | Budget limit for the plan |
| `--topics` | 15 | Total number of topics |
| `--no-discovery` | false | Skip source discovery (faster, cheaper) |
| `--json` | false | Output as JSON |
| `--csv` | false | Output as CSV |
| `-q, --quiet` | false | Output prompts only, one per line |

```
deepr expert plan "Kubernetes security" --budget 10
deepr expert plan "FastAPI" --json
deepr expert plan "React hooks" -q
```

### Creation

#### `make <name>`

Create a new expert with a knowledge base from documents and/or autonomous learning.

| Option | Default | Description |
|--------|---------|-------------|
| `-f, --files` | none | Files to include in knowledge base |
| `-d, --description` | none | Expert domain description |
| `-p, --provider` | openai | AI provider (openai, azure, gemini) |
| `--learn` | false | Generate and execute autonomous learning curriculum |
| `--budget` | none | Budget limit for learning (requires `--learn`) |
| `--topics` | 15 | Total number of topics |
| `--docs` | none | Number of documentation topics (~$0.25 each) |
| `--quick` | none | Number of quick research topics (~$0.25 each) |
| `--deep` | none | Number of deep research topics (~$2.00 each) |
| `--no-discovery` | false | Skip source discovery phase |
| `-y, --yes` | false | Skip confirmation |

```
deepr expert make "Python Expert" -f docs/*.md -d "Python best practices"
deepr expert make "AI Expert" -f docs/*.md --learn --budget 10
deepr expert make "Azure Architect" --learn --docs 3 --quick 5 --deep 2
```

### Learning

#### `learn <name> [topic]`

Add knowledge to an expert by researching a topic, uploading files, or both. Re-synthesizes consciousness after learning.

| Option | Default | Description |
|--------|---------|-------------|
| `-f, --files` | none | Files to upload to knowledge base |
| `-b, --budget` | $1 | Budget limit for topic research |
| `--no-synthesize` | false | Skip re-synthesis after learning |
| `-y, --yes` | false | Skip confirmation |

```
deepr expert learn "AWS Expert" "Latest Lambda features 2026"
deepr expert learn "Python Expert" --files docs/*.md
deepr expert learn "AI Expert" "Transformer architectures" -f papers/*.pdf --budget 5
```

#### `resume <name>`

Resume paused learning when autonomous learning hit a spending limit. Loads saved progress and continues with remaining topics.

| Option | Default | Description |
|--------|---------|-------------|
| `-b, --budget` | auto | Budget for remaining topics |
| `-y, --yes` | false | Skip confirmation |

```
deepr expert resume "AWS Expert"
deepr expert resume "AWS Expert" --budget 10
```

#### `fill-gaps <name>`

Proactively research and fill the expert's highest-priority knowledge gaps, then re-synthesize consciousness.

| Option | Default | Description |
|--------|---------|-------------|
| `-b, --budget` | $5 | Budget limit for gap filling |
| `-t, --top` | 3 | Number of top-priority gaps to fill |
| `-y, --yes` | false | Skip confirmation |

```
deepr expert fill-gaps "AWS Expert"
deepr expert fill-gaps "Python Expert" --top 5 --budget 10
```

#### `refresh <name>`

Scan expert's documents directory for new files and upload them. Optionally re-synthesize consciousness.

| Option | Default | Description |
|--------|---------|-------------|
| `--synthesize` | false | Re-synthesize consciousness after refresh |
| `-y, --yes` | false | Skip confirmation |

```
deepr expert refresh "Azure Architect" --synthesize
```

### Portability

#### `export <name>`

Export an expert's full consciousness (documents, beliefs, worldview) to a portable corpus directory.

| Option | Default | Description |
|--------|---------|-------------|
| `-o, --output` | `.` | Output directory |
| `-y, --yes` | false | Skip confirmation |

```
deepr expert export "AWS Expert" --output ./exports
```

#### `import <name>`

Create a new expert from an exported corpus.

| Option | Default | Description |
|--------|---------|-------------|
| `-c, --corpus` | required | Path to corpus directory |
| `-y, --yes` | false | Skip confirmation |

```
deepr expert import "My AWS Expert" --corpus ./aws-expert
```

### Interaction

#### `chat <name>`

Start an interactive chat session with an expert. Supports in-session commands: `/quit`, `/status`, `/clear`, `/trace`, `/learn <file>`, `/synthesize`.

| Option | Default | Description |
|--------|---------|-------------|
| `-b, --budget` | $5 | Session budget limit |
| `--no-research` | false | Disable agentic research |

```
deepr expert chat "AWS Solutions Architect"
deepr expert chat "Python Expert" --budget 10 --no-research
```

### Administration

#### `delete <name>`

Delete an expert profile. Knowledge base (vector store) must be deleted separately.

| Option | Default | Description |
|--------|---------|-------------|
| `-y, --yes` | false | Skip confirmation |

```
deepr expert delete "Old Expert" -y
```

## When to Use Experts vs Fresh Research

| Scenario | Recommendation |
|----------|---------------|
| Domain-specific question within expert knowledge | Query the expert |
| Current events or recent developments | Use `/research` |
| Topic outside expert domain | Use `/research` |
| Complex question requiring new research | Use expert `--agentic` mode |

See `references/expert_system.md` for the full expert system architecture, confidence levels, and best practices.
