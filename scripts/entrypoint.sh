#!/bin/bash

# Start the FastAPI app with Uvicorn
uvicorn bluenaas.app:app --port 8000 --host 0.0.0.0