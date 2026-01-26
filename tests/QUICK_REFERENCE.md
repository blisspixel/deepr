# Expert Testing Quick Reference

## One-Liners

```bash
# Unit test (free, 2s) - catches f-string errors
pytest tests/test_expert_keyboards_simple.py -v

# CLI test (Windows, $0.004, 2min)
tests\test_keyboards_cli.bat

# CLI test (Linux/Mac, $0.004, 2min)
./tests/test_keyboards_cli.sh

# Validate learning (free, 30s)
python tests/validate_expert_learning.py "Keyboards Test"

# E2E test ($0.004, 3min)
pytest tests/test_expert_keyboards_e2e.py -v -s

# Cleanup
deepr expert delete "Keyboards Test" --yes
```

## Create & Test Any Expert

```bash
# 1. Create test doc
cat > /tmp/test.md << 'EOF'
# Your Domain
Key concepts here...
EOF

# 2. Create expert (minimal)
deepr expert make "Test Expert" \
  --files /tmp/test.md \
  --learn --docs 1 --quick 1 \
  --no-discovery --yes

# 3. Validate
python tests/validate_expert_learning.py "Test Expert"

# 4. Test chat
deepr chat expert "Test Expert" \
  --message "What are the key concepts?"

# 5. Cleanup
deepr expert delete "Test Expert" --yes
```

## Cost Guide

| Test | Cost | Time | Use When |
|------|------|------|----------|
| Unit | $0 | 2s | Every change |
| CLI | $0.004 | 2min | Before commit |
| E2E | $0.004 | 3min | CI/CD |
| Validate | ~$0.001 | 30s | After creation |

## What Each Test Does

### Unit Test
- F-string syntax
- Parameter validation
- Command structure
- No API calls

### CLI Test
- Real expert creation
- Document upload
- Curriculum generation
- Research execution
- Chat functionality

### Validation
- Documents added
- Research completed
- Beliefs formed
- Can answer questions

### E2E Test
- Full workflow
- Automated assertions
- Auto cleanup
- CI/CD ready

## Troubleshooting

### "No files specified"
```bash
# Add --files or use --learn
deepr expert make "Name" --files test.md --learn --docs 1 --quick 1
```

### "Budget required"
```bash
# Use topic counts instead
deepr expert make "Name" --files test.md --learn --docs 1 --quick 1
```

### Expert gives generic answers
```bash
# Validate learning
python tests/validate_expert_learning.py "Name"

# Check documents
deepr expert info "Name"

# Try synthesis
deepr expert refresh "Name" --synthesize
```

## Files

- `tests/test_expert_keyboards_simple.py` - Unit tests
- `tests/test_expert_keyboards_e2e.py` - E2E test
- `tests/test_keyboards_cli.bat` - Windows CLI
- `tests/test_keyboards_cli.sh` - Linux/Mac CLI
- `tests/validate_expert_learning.py` - Validation
- `tests/TEST_EXPERT_CREATION.md` - Full guide
- `tests/TESTING_SUMMARY.md` - Strategy
