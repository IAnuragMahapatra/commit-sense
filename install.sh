#!/usr/bin/env bash
set -euo pipefail

# CommitSense pre-push hook installer (Unix)

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
HOOK_FILE=".git/hooks/pre-push"

# Check we're in a git repo
if [ ! -d ".git" ]; then
    echo "Error: not a git repository (no .git/ found)"
    echo "Run this from the root of a git repo."
    exit 1
fi

# Check Python 3
if ! command -v python3 &> /dev/null && ! command -v python &> /dev/null; then
    echo "Error: Python 3 is required but not found"
    exit 1
fi

PYTHON_CMD="python3"
if ! command -v python3 &> /dev/null; then
    PYTHON_CMD="python"
fi

# Create hooks dir if missing
mkdir -p .git/hooks

# Back up existing hook
if [ -f "$HOOK_FILE" ]; then
    cp "$HOOK_FILE" "${HOOK_FILE}.bak"
    echo "Backed up existing pre-push hook → ${HOOK_FILE}.bak"
fi

# Write the hook shim
cat > "$HOOK_FILE" << EOF
#!/usr/bin/env bash
cd "$SCRIPT_DIR"
$PYTHON_CMD -m hooks.pre_push
EOF

chmod +x "$HOOK_FILE"

echo "✓ CommitSense pre-push hook installed"
echo "  Hook: $HOOK_FILE"
echo "  Root: $SCRIPT_DIR"
