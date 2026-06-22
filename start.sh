#!/bin/bash

# Setup cleanup trap to kill all background processes spawned by this script on exit
cleanup() {
  echo ""
  echo "=========================="
  echo "Stopping MyPhotos Stack..."
  echo "=========================="
  
  # Kill uvicorn, celery, vite, etc started by this shell session
  PIDS=$(jobs -p)
  if [ -n "$PIDS" ]; then
    echo "Killing background tasks: $PIDS"
    kill $PIDS 2>/dev/null
    wait $PIDS 2>/dev/null
  fi
  
  echo "MyPhotos Stack stopped."
  exit 0
}

# Trap SIGINT (Ctrl+C), SIGTERM, and EXIT
trap cleanup SIGINT SIGTERM EXIT

echo "Checking for and cleaning up existing processes..."
# Find and kill any uvicorn process running backend.main
pkill -f "uvicorn backend.main:app" 2>/dev/null || true
# Find and kill any celery background worker process running backend.tasks
pkill -f "celery -A backend.tasks" 2>/dev/null || true
# Find and kill any vite process running in frontend
pkill -f "node.*/vite" 2>/dev/null || true

# Check if port 8000 is still busy
if lsof -i :8000 >/dev/null 2>&1; then
  echo "Warning: Port 8000 is still occupied by another process. Attempting to free it..."
  lsof -ti :8000 | xargs kill -9 2>/dev/null || true
  sleep 1
fi

# Check if port 5173 is still busy
if lsof -i :5173 >/dev/null 2>&1; then
  echo "Warning: Port 5173 is still occupied by another process. Attempting to free it..."
  lsof -ti :5173 | xargs kill -9 2>/dev/null || true
  sleep 1
fi

source .venv/bin/activate
echo "Starting MyPhotos Stack..."
echo "=========================="
echo "-> Starting Redis Server..."
redis-server --daemonize yes

echo "-> Starting FastAPI Backend (Port 8000)..."
uvicorn backend.main:app --host 127.0.0.1 --port 8000 > backend.log 2>&1 &

# Wait for backend to start up and bind to port 8000
echo "Waiting for backend to start on port 8000..."
BACKEND_SUCCESS=0
for i in {1..15}; do
  if lsof -i :8000 >/dev/null 2>&1; then
    BACKEND_SUCCESS=1
    break
  fi
  sleep 1
done

if [ $BACKEND_SUCCESS -ne 1 ]; then
  echo "Error: FastAPI Backend failed to start on port 8000. Check backend.log for details."
  cat backend.log
  exit 1
fi
echo "FastAPI Backend is up and running!"

echo "-> Starting Celery Background Worker..."
celery -A backend.tasks worker --loglevel=info > celery.log 2>&1 &
sleep 1

echo "-> Starting Vite Frontend (Port 5173)..."
cd frontend
npm run dev > frontend.log 2>&1 &
cd ..

# Wait for frontend to start up and bind to port 5173
echo "Waiting for frontend to start on port 5173..."
FRONTEND_SUCCESS=0
for i in {1..10}; do
  if lsof -i :5173 >/dev/null 2>&1; then
    FRONTEND_SUCCESS=1
    break
  fi
  sleep 1
done

if [ $FRONTEND_SUCCESS -ne 1 ]; then
  echo "Error: Vite Frontend failed to start on port 5173. Check frontend/frontend.log for details."
  cat frontend/frontend.log
  exit 1
fi

echo "=========================="
echo "MyPhotos is running!"
echo "Frontend: http://localhost:5173"
echo "Backend:  http://localhost:8000"
echo "Press Ctrl+C to stop all services."
echo "=========================="

# Wait for background jobs to finish
wait
