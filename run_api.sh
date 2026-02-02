#!/bin/bash
# Wrapper script for Nexus 2 API server with auto-restart
# Used by /admin/restart endpoint for seamless restarts

cd ~/Nexus2

while true; do
  echo "[$(date)] Starting API server..."
  
  # Run uvicorn and log to both console and file
  python -m uvicorn nexus2.api.main:app --host 0.0.0.0 --port 8000 2>&1 | tee -a data/server.log
  
  EXIT_CODE=$?
  
  # Exit code 42 = intentional restart from /admin/restart endpoint
  if [ $EXIT_CODE -eq 42 ]; then
    echo "[$(date)] Intentional restart requested. Restarting in 2s..."
  else
    echo "[$(date)] Server exited with code $EXIT_CODE. Restarting in 2s..."
  fi
  
  sleep 2
done
