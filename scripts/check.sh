#!/bin/bash
# Check script for Visualizer Agent project
# Verifies if backend and frontend are running and healthy

QUIET=false
BACKEND_PORT="${BACKEND_PORT:-8000}"
FRONTEND_PORT="${FRONTEND_PORT:-5173}"
TIMEOUT_SECONDS="${TIMEOUT_SECONDS:-5}"

# Parse arguments
while [[ $# -gt 0 ]]; do
    case $1 in
        --quiet)
            QUIET=true
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

PROJECT_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
LOG_DIR="$PROJECT_ROOT/scripts/logs"
BACKEND_LOG="$LOG_DIR/backend.log"
FRONTEND_LOG="$LOG_DIR/frontend.log"
PID_FILE="$LOG_DIR/processes.pid"

HEALTHY=true

# Check Backend
backend_healthy=false
backend_status="Not reachable"

if curl -s --max-time "$TIMEOUT_SECONDS" "http://localhost:$BACKEND_PORT/health" > /dev/null 2>&1; then
    backend_healthy=true
    backend_status="Healthy"
elif curl -s --max-time "$TIMEOUT_SECONDS" "http://localhost:$BACKEND_PORT/docs" > /dev/null 2>&1; then
    backend_healthy=true
    backend_status="Running (API docs available)"
else
    backend_status="Not reachable"
    HEALTHY=false
fi

# Check if backend process is running
backend_running=false
if [ -f "$PID_FILE" ]; then
    while IFS= read -r line; do
        if [[ $line =~ backend=([0-9]+) ]]; then
            backend_pid="${BASH_REMATCH[1]}"
            if kill -0 "$backend_pid" 2>/dev/null; then
                backend_running=true
            fi
        fi
    done < "$PID_FILE"
fi

# Check Frontend
frontend_healthy=false
frontend_status="Not reachable"

if curl -s --max-time "$TIMEOUT_SECONDS" "http://localhost:$FRONTEND_PORT" > /dev/null 2>&1; then
    frontend_healthy=true
    frontend_status="Healthy"
else
    frontend_status="Not reachable"
    HEALTHY=false
fi

# Check if frontend process is running
frontend_running=false
if [ -f "$PID_FILE" ]; then
    while IFS= read -r line; do
        if [[ $line =~ frontend=([0-9]+) ]]; then
            frontend_pid="${BASH_REMATCH[1]}"
            if kill -0 "$frontend_pid" 2>/dev/null; then
                frontend_running=true
            fi
        fi
    done < "$PID_FILE"
fi

# Output results
if [ "$QUIET" = false ]; then
    echo ""
    echo "Visualizer Agent Status Check"
    echo "============================="
    echo ""
    echo "Backend:"
    echo "  Port:     $BACKEND_PORT"
    echo "  Running:  $([ "$backend_running" = true ] && echo "Yes" || echo "No")"
    echo "  Status:   $backend_status"
    echo ""
    echo "Frontend:"
    echo "  Port:     $FRONTEND_PORT"
    echo "  Running:  $([ "$frontend_running" = true ] && echo "Yes" || echo "No")"
    echo "  Status:   $frontend_status"
    echo ""
    echo "Log Files:"
    echo "  Backend:  $BACKEND_LOG"
    echo "  Frontend: $FRONTEND_LOG"
    echo ""
    
    if [ "$HEALTHY" = true ]; then
        echo "✓ All services are healthy!"
    else
        echo "✗ Some services are not healthy."
        echo "  Check logs for details."
    fi
fi

# Return exit code
if [ "$HEALTHY" = true ]; then
    exit 0
else
    exit 1
fi
