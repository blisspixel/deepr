# Expert Creation Testing Guide

This guide shows how to test expert creation with minimal cost (~$0.004) and validate that the expert actually learned something useful.

## Quick Test (CLI)

### Windows
```bash
tests\test_keyboards_cli.bat
```

### Linux/Mac
```bash
chmod +x tests/test_keyboards_cli.sh
./tests/test_keyboards_cli.sh
```

This will:
1. Create a test document about mechanical keyboards
2. Create an expert with 1 doc + 1 quick research
3. List experts
4. Show expert details
5. Test the expert with a question

**Cost:** ~$0.004

## Validation Script

After creating an expert, validate it learned properly:

```bash
python tests/validate_expert_learning.py "Keyboards Test"
```

This checks:
- Metadata (documents, research jobs, costs)
- Beliefs formed (if synthesis ran)
- Response quality to domain questions
- Knowledge coverage

## Full E2E Test (Pytest)

Run the complete end-to-end test:

```bash
python -m pytest tests/test_expert_keyboards_e2e.py -v -s
```

This test:
1. Creates an expert with initial document
2. Generates curriculum (1 doc + 1 quick)
3. Executes the curriculum
4. Validates expert learned something
5. Tests expert can answer questions
6. Cleans up automatically

**Cost:** ~$0.004

## Manual Testing Workflow

### 1. Create Test Document

```bash
# Create a simple test document
cat > /tmp/keyboards.md << 'EOF'
# Mechanical Keyboards

## Switch Types
- Cherry MX Red: Linear, smooth
- Cherry MX Brown: Tactile, quiet
- Cherry MX Blue: Clicky, loud

## Benefits
- Durability (50M+ keystrokes)
- Better typing feel
- Customizable
EOF
```

### 2. Create Expert with Learning

```bash
# Minimal learning (1 doc + 1 quick)
deepr expert make "Keyboards Test" \
  --files /tmp/keyboards.md \
  --learn \
  --docs 1 \
  --quick 1 \
  --no-discovery \
  --yes
```

**Options:**
- `--docs N`: Number of documentation-focused topics
- `--quick N`: Number of quick research topics
- `--deep N`: Number of deep research topics
- `--no-discovery`: Skip source discovery (faster)
- `--yes`: Skip confirmation prompts

### 3. Validate Expert

```bash
# Check expert details
deepr expert info "Keyboards Test"

# Validate learning
python tests/validate_expert_learning.py "Keyboards Test"
```

### 4. Test Expert Chat

```bash
# Ask a question
deepr chat expert "Keyboards Test" \
  --message "What are the main types of mechanical keyboard switches?"
```

### 5. Cleanup

```bash
# Delete expert
deepr expert delete "Keyboards Test" --yes

# Delete vector store (get ID from expert info)
deepr brain delete vs_XXXXX
```

## Cost Breakdown

| Test Type | Docs | Quick | Deep | Est. Cost |
|-----------|------|-------|------|-----------|
| Minimal   | 1    | 1     | 0    | $0.004    |
| Small     | 2    | 3     | 0    | $0.010    |
| Medium    | 3    | 5     | 1    | $1.016    |
| Full      | 5    | 10    | 3    | $3.030    |

**Actual costs:**
- Docs/Quick: ~$0.002 each (grok-4-fast)
- Deep: ~$1.00 each (o4-mini-deep-research)

## What to Check

### Expert Created Successfully
- Expert appears in `deepr expert list`
- Has vector store ID
- Has initial documents

### Learning Executed
- `total_documents` increased
- `research_jobs` list has entries
- `total_research_cost` > 0

### Expert Can Answer Questions
- Responses are substantive (>50 chars)
- Mentions domain-specific terms
- Shows understanding of concepts

### Beliefs Formed (Optional)
- Expert has `beliefs` attribute
- Beliefs have confidence scores
- Beliefs reference sources

## Common Issues

### Issue: "No files specified"
**Solution:** Add `--files` or use `--learn` with budget

### Issue: "Budget required"
**Solution:** Add `--budget 10` or use topic counts (`--docs 1 --quick 1`)

### Issue: "Curriculum generation failed"
**Solution:** Check API keys, try `--no-discovery` flag

### Issue: Expert gives generic answers
**Solution:** 
- Add more initial documents
- Increase topic counts
- Run synthesis: `deepr expert refresh "Name" --synthesize`

## Testing Different Domains

You can test with any domain:

```bash
# Python expert
deepr expert make "Python Expert" \
  --files docs/python/*.md \
  --learn --docs 2 --quick 2

# AWS expert
deepr expert make "AWS Expert" \
  --files docs/aws/*.md \
  --learn --docs 3 --quick 5

# Custom domain
deepr expert make "My Domain Expert" \
  --files docs/*.md \
  --description "Expert in my specific domain" \
  --learn --budget 5
```

## Automated Testing

Add to CI/CD:

```yaml
# .github/workflows/test-experts.yml
- name: Test Expert Creation
  run: |
    python -m pytest tests/test_expert_keyboards_e2e.py -v
  env:
    OPENAI_API_KEY: ${{ secrets.OPENAI_API_KEY }}
```

## Tips

1. **Start small:** Use 1 doc + 1 quick for initial testing
2. **Use --no-discovery:** Faster, cheaper, good for testing
3. **Validate immediately:** Run validation script right after creation
4. **Check costs:** Use `deepr cost summary` to track spending
5. **Clean up:** Delete test experts and vector stores

## Next Steps

After validating basic expert creation:

1. Test with real documents
2. Increase topic counts gradually
3. Enable discovery for comprehensive learning
4. Test agentic chat with `--agentic --budget 5`
5. Test knowledge refresh workflows
