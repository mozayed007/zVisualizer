#!/bin/bash
# Start script for Visualizer Agent project
# Starts both backend (uvicorn) and frontend (vite)

set -e

PROJECT_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
BACKEND_DIR="$PROJECT_ROOT/apps/backend"
FRONTEND_DIR="$PROJECT_ROOT/apps/frontend"
LOG_DIR="$PROJECT_ROOT/scripts/logs"

# Default ports
BACKEND_PORT="${BACKEND_PORT:-8000}"
FRONTEND_PORT="${FRONTEND_PORT:-5173}"

# Parse arguments
BACKEND_ONLY=false
FRONTEND_ONLY=false

while [[ $# -gt 0 ]]; do
    case $1 in
        --backend-only)
            BACKEND_ONLY=true
            shift
            ;;
        --frontend-only)
            FRONTEND_ONLY=true
            shift
            ;;
        --backend-port)
            BACKEND_PORT="$2"
            shift 2
            ;;
        --frontend-port)
            FRONTEND_PORT="$2"
            shift 2
            ;;
        *)
            echo "Unknown option: $1"
            exit 1
            ;;
    esac
done

# Create logs directory
mkdir -p "$LOG_DIR"

BACKEND_LOG="$LOG_DIR/backend.log"
FRONTEND_LOG="$LOG_DIR/frontend.log"
PID_FILE="$LOG_DIR/processes.pid"

# Stop any existing processes first
"$PROJECT_ROOT/scripts/stop.sh" --quiet 2>/dev/null || true

# Function to start backend
start_backend() {
    echo "Starting backend on port $BACKEND_PORT..."
    
    cd "$BACKEND_DIR"
    
    # Check for conda environment
    if conda env list | grep -q "^ml "; then
        nohup bash -c "source \$(conda info --base)/etc/profile.d/conda.sh && conda activate ml && uvicorn app.main:app --host 0.0.0.0 --port $BACKEND_PORT" > "$BACKEND_LOG" 2>&1 &
    else
        echo "Warning: Conda environment 'ml' not found. Trying without conda..."
        nohup uvicorn app.main:app --host 0.0.0.0 --port $BACKEND_PORT > "$BACKEND_LOG" 2>&1 &
    fi
    
    echo $! >> "$PID_FILE"
    sleep 2
}

# Function to start frontend
start_frontend() {
    echo "Starting frontend on port $FRONTEND_PORT..."
    
    cd "$FRONTEND_DIR"
    
    # Check if bun or npm is available
    if command -v bun &> /dev/null; then
        PACKAGE_MANAGER="bun"
    else
        PACKAGE_MANAGER="npm"
    fi
    
    nohup $PACKAGE_MANAGER run dev -- --port $FRONTEND_PORT > "$FRONTEND_LOG" 2>&1 &
    echo $! >> "$PID_FILE"
    sleep 2
}

# Start services
if [ "$FRONTEND_ONLY" = false ]; then
    start_backend
fi

if [ "$BACKEND_ONLY" = false ]; then
    start_frontend
fi

echo ""
echo "Project started successfully!"
echo "Backend: http://localhost:$BACKEND_PORT"
echo "Frontend: http://localhost:$FRONTEND_PORT"
echo ""
echo "Logs:"
echo "  Backend:  $BACKEND_LOG"
echo "  Frontend: $FRONTEND_LOG"
echo ""
echo "Use 'check.sh' to verify status"
echo "Use 'stop.sh' to stop all services"
