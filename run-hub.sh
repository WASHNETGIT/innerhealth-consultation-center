#!/bin/bash
# Business Hub startup script
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

# Check for dependencies
if ! python3 -c "import fastapi, uvicorn, sqlalchemy" 2>/dev/null; then
    echo "=========================================="
    echo "Business Hub - Missing Dependencies"
    echo "=========================================="
    echo "Please install required packages:"
    echo ""
    echo "  pip install -r requirements.txt"
    echo ""
    echo "Or with sudo:"
    echo "  sudo apt-get install python3-fastapi python3-sqlalchemy python3-pydantic python3-uvicorn"
    echo ""
    echo "Or with Homebrew:"
    echo "  brew install fastapi uvicorn sqlalchemy pydantic"
    echo ""
    read -p "Press Enter to exit..."
    exit 1
fi

# Start the server
echo "Starting Business Hub on http://localhost:8000"
python3 -m uvicorn main:app --host 0.0.0.0 --port 8000 --reload
