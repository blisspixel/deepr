#!/bin/bash
# Simple CLI test for keyboards expert
# Cost: ~$0.004

set -e

echo "=========================================="
echo "  Keyboards Expert CLI Test"
echo "=========================================="
echo ""

# Create test document
cat > /tmp/keyboard_guide.md << 'EOF'
# Mechanical Keyboards Guide

## What are Mechanical Keyboards?

Mechanical keyboards use individual mechanical switches for each key, 
providing tactile feedback and durability.

## Popular Switch Types

1. **Cherry MX Red** - Linear, smooth
2. **Cherry MX Brown** - Tactile, quiet
3. **Cherry MX Blue** - Clicky, loud

## Benefits

- Durability (50-100 million keystrokes)
- Better typing experience
- Customizable keycaps
EOF

echo "✓ Created test document"
echo ""

# Create expert with learning
echo "Creating expert with 1 doc + 1 quick research..."
deepr expert make "Keyboards Test" \
  --files /tmp/keyboard_guide.md \
  --description "Mechanical keyboards expert" \
  --learn \
  --docs 1 \
  --quick 1 \
  --no-discovery \
  --yes

echo ""
echo "✓ Expert created"
echo ""

# List experts
echo "Listing experts..."
deepr expert list

echo ""

# Get expert info
echo "Expert details..."
deepr expert info "Keyboards Test"

echo ""

# Test chat (non-agentic)
echo "Testing expert chat..."
echo "What are the main types of mechanical keyboard switches?" | \
  deepr chat expert "Keyboards Test" --message -

echo ""
echo "=========================================="
echo "  ✅ Test Complete"
echo "=========================================="
echo ""
echo "Cleanup:"
echo "  deepr expert delete 'Keyboards Test' --yes"
