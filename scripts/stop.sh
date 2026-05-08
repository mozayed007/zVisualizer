#!/bin/bash
# Stop script for Visualizer Agent project
# Stops all running backend and frontend processes

QUIET=false
FORCE=false

# Parse arguments
while [[ $# -gt 0 ]]; do
    case $1 in
        --quiet)
            QUIET=true
            shift
            ;;
        --force)
            FORCE=true
            shift
            ;;
        *)
            echo "Unknown option: $1"
            exit 1
            ;;
    esac
done

PROJECT_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
LOG_DIR="$PROJECT_ROOT/scripts/logs"
PID_FILE="$LOG_DIR/processes.pid"

STOPPED=false

# Function to stop a process by PID
stop_process() {
    local pid=$1
    local name=$2
    
    if kill -0 "$pid" 2>/dev/null; then
        if [ "$FORCE" = true ]; then
            kill -9 "$pid" 2>/dev/null
        else
            kill "$pid" 2>/dev/null
        fi
        
        if [ "$QUIET" = false ]; then
            echo "Stopped $name process (PID: $pid)"
        fi
        STOPPED=true
    fi
}

# Stop processes from PID file
if [ -f "$PID_FILE" ]; then
    while IFS= read -r line; do
        if [[ $line =~ backend=([0-9]+) ]]; then
            stop_process "${BASH_REMATCH[1]}" "backend"
        fi
        if [[ $line =~ frontend=([0-9]+) ]]; then
            stop_process "${BASH_REMATCH[1]}" "frontend"
        fi
    done < "$PID_FILE"
    
    # Remove PID file
    rm -f "$PID_FILE"
fi

# Also try to find and stop any remaining uvicorn or node/vite processes
if [ "$STOPPED" = false ]; then
    # Stop uvicorn processes
    pgrep -f "uvicorn.*app.main" | while read -r pid; do
        stop_process "$pid" "uvicorn"
    done
    
    # Stop node/vite processes in frontend
    pgrep -f "vite" | while read -r pid; do
        # Verify it's actually in our frontend directory
        if readlink -f "/proc/$pid/cwd" | grep -q "$PROJECT_ROOT/apps/frontend"; then
            stop_process "$pid" "vite"
        fi
    done
fi

if [ "$QUIET" = false ]; then
    if [ "$STOPPED" = true ]; then
        echo ""
        echo "✓ All services stopped."
    else
        echo ""
        echo "No running services found."
    fi
fi

# Return exit code
if [ "$STOPPED" = true ] || [ "$QUIET" = true ]; then
    exit 0
else
    exit 1
fi
