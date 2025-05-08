import contextlib
from fastapi import FastAPI, WebSocket, WebSocketDisconnect, Depends, HTTPException, status
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy.orm import Session
import os
import json

from . import models
from .database import engine, get_db
from .routers import api, websocket
from .websocket_manager import manager

# Create database tables
models.Base.metadata.create_all(bind=engine)

app = FastAPI(
    title="FastAPI WebSocket Chat",
    description="A real-time chat application using FastAPI, SQLite, and WebSockets",
    version="1.0.0"
)

# Add CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # Modify this in production to be more specific
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Include routers
app.include_router(api.router, prefix="/api", tags=["api"])
app.include_router(websocket.router, tags=["websocket"])


@app.get("/")
async def root():
    """Root endpoint"""
    return {
        "message": "Welcome to FastAPI WebSocket Chat API",
        "documentation": "/docs",
        "websocket_endpoints": [
            "/ws",
            "/ws/auth",
            "/ws/room/{room_id}"
        ]
    }


@app.on_event("startup")
async def startup_event():
    """Initialize the application on startup"""
    # You can add initialization code here
    print("Starting up the FastAPI WebSocket Chat API...")


@app.on_event("shutdown")
async def shutdown_event():
    """Clean up on application shutdown"""
    # You can add cleanup code here
    print("Shutting down the FastAPI WebSocket Chat API...")


# For testing purposes, a simple WebSocket echo endpoint
@app.websocket("/ws/echo")
async def websocket_echo(websocket: WebSocket):
    """Simple echo WebSocket endpoint for testing"""
    await websocket.accept()
    with contextlib.suppress(WebSocketDisconnect):
        while True:
            data = await websocket.receive_text()
            await websocket.send_text(f"Echo: {data}")