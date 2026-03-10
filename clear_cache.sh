#!/bin/bash

# Script to clear all caches for the Alert Agent

echo "🧹 Clearing Alert Agent caches..."

# 1. Remove memory file if it exists
if [ -f "memory.json" ]; then
    echo "  ✓ Removing memory.json"
    rm memory.json
fi

# 2. Clear Ollama cache (restart Ollama service)
echo "  ✓ Clearing Ollama cache..."
if command -v ollama &> /dev/null; then
    # Stop Ollama
    pkill ollama 2>/dev/null
    sleep 2
    
    # Start Ollama in background
    nohup ollama serve > /dev/null 2>&1 &
    sleep 3
    
    echo "  ✓ Ollama restarted"
else
    echo "  ⚠ Ollama not found in PATH, skipping Ollama cache clear"
fi

# 3. Clear Python cache
echo "  ✓ Clearing Python cache..."
find . -type d -name "__pycache__" -exec rm -rf {} + 2>/dev/null
find . -type f -name "*.pyc" -delete 2>/dev/null

# 4. Clear any .DS_Store files (macOS)
find . -name ".DS_Store" -delete 2>/dev/null

echo "✅ Cache clearing complete!"
echo ""
echo "Next steps:"
echo "1. Run your agent again"
echo "2. The agent should now use fresh context without cached responses"
