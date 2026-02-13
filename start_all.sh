#!/bin/bash
# Nexus 2 Full Startup Script
# Creates tmux session with backend (run_api.sh) and frontend
# Usage: ./start_all.sh (or via crontab @reboot)

cd ~/Nexus2

# Kill any existing tmux session
tmux kill-session -t nexus 2>/dev/null

# Create tmux session with backend
tmux new-session -d -s nexus -c ~/Nexus2

# Start backend with auto-restart wrapper
tmux send-keys -t nexus:0 'source .venv/bin/activate && ./run_api.sh' Enter

# Wait for backend to initialize
sleep 8

# Create frontend window and start it
tmux new-window -t nexus -n frontend -c ~/Nexus2/nexus2/frontend
tmux send-keys -t nexus:frontend 'npm start' Enter

echo "[$(date)] Nexus 2 started: backend (run_api.sh) + frontend in tmux session 'nexus'"
