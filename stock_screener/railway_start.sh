#!/bin/bash
# Railway.app startup script

echo "Installing dependencies..."
pip install -r requirements.txt

echo "Running stock screener..."
python screener.py

echo "Complete!"
