#!/bin/bash
source .venv/bin/activate
echo "Starting MyPhotos Stack..."
echo "=========================="
echo "-> Starting Redis Server..."
redis-server --daemonize yes
echo "-> Starting FastAPI Backend (Port 8000)..."
uvicorn backend.main:app --host 127.0.0.1 --port 8000 > backend.log 2>&1 &
echo "-> Starting Celery Background Worker..."
celery -A backend.tasks worker --loglevel=info > celery.log 2>&1 &
echo "-> Starting Vite Frontend (Port 5173)..."
cd frontend
npm run dev > frontend.log 2>&1 &
echo "=========================="
echo "MyPhotos is running!"
echo "Frontend: http://localhost:5173"
echo "Backend:  http://localhost:8000"
echo "Press Ctrl+C to stop all services."
echo "=========================="
wait
