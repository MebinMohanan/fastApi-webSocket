import json
import uuid
from typing import Dict, List, Set, Optional
from fastapi import WebSocket, WebSocketDisconnect
from sqlalchemy.orm import Session
from datetime import datetime

from . import models, schemas


class ConnectionManager:
    def __init__(self):
        # Active connections by client_id
        self.active_connections: Dict[str, WebSocket] = {}
        
        # Map of room_id to set of client_ids
        self.room_connections: Dict[int, Set[str]] = {}
        
        # Map of user_id to set of client_ids (a user might have multiple devices connected)
        self.user_connections: Dict[int, Set[str]] = {}
        
        # Keep metadata about connections
        self.connection_info: Dict[str, dict] = {}

    async def connect(self, websocket: WebSocket, client_id: str = None, user_id: Optional[int] = None, room_id: Optional[int] = None, db: Session = None):
        """Connect a client to the WebSocket manager"""
        await websocket.accept()
        
        # Generate a client ID if none provided
        if not client_id:
            client_id = str(uuid.uuid4())
        
        # Store the connection
        self.active_connections[client_id] = websocket
        
        # Store connection metadata
        self.connection_info[client_id] = {
            "user_id": user_id,
            "room_id": room_id,
            "connected_at": datetime.now(),
            "last_active": datetime.now()
        }
        
        # If room_id is provided, add to room connections
        if room_id:
            if room_id not in self.room_connections:
                self.room_connections[room_id] = set()
            self.room_connections[room_id].add(client_id)
        
        # If user_id is provided, add to user connections
        if user_id:
            if user_id not in self.user_connections:
                self.user_connections[user_id] = set()
            self.user_connections[user_id].add(client_id)
        
        # If database session is provided, store connection info
        if db:
            db_connection = models.WebSocketConnection(
                id=client_id,
                user_id=user_id,
                room_id=room_id,
                client_id=client_id,
                connected_at=datetime.now(),
                is_active=True
            )
            db.add(db_connection)
            db.commit()
        
        return client_id

    def disconnect(self, client_id: str, db: Session = None):
        """Disconnect a client from the WebSocket manager"""
        if client_id not in self.active_connections:
            return
        # Get metadata before removing
        metadata = self.connection_info.get(client_id, {})
        user_id = metadata.get("user_id")
        room_id = metadata.get("room_id")

        # Remove from active connections
        self.active_connections.pop(client_id)
        self.connection_info.pop(client_id, None)

        # Remove from room connections
        if room_id and room_id in self.room_connections:
            if client_id in self.room_connections[room_id]:
                self.room_connections[room_id].remove(client_id)
            if not self.room_connections[room_id]:  # If room is empty
                self.room_connections.pop(room_id)

        # Remove from user connections
        if user_id and user_id in self.user_connections:
            if client_id in self.user_connections[user_id]:
                self.user_connections[user_id].remove(client_id)
            if not self.user_connections[user_id]:  # If user has no connections
                self.user_connections.pop(user_id)

            # Update database if session provided
        if db:
            if (
                db_connection := db.query(models.WebSocketConnection)
                .filter(models.WebSocketConnection.id == client_id)
                .first()
            ):
                db_connection.is_active = False
                db.commit()

    async def send_personal_message(self, message: dict, client_id: str):
        """Send a message to a specific client"""
        if client_id in self.active_connections:
            websocket = self.active_connections[client_id]
            await websocket.send_text(json.dumps(message))
            # Update last active
            if client_id in self.connection_info:
                self.connection_info[client_id]["last_active"] = datetime.now()

    async def broadcast(self, message: dict):
        """Broadcast a message to all connected clients"""
        disconnected = []
        for client_id, websocket in self.active_connections.items():
            try:
                await websocket.send_text(json.dumps(message))
                # Update last active
                if client_id in self.connection_info:
                    self.connection_info[client_id]["last_active"] = datetime.now()
            except WebSocketDisconnect:
                disconnected.append(client_id)
        
        # Clean up any disconnected clients
        for client_id in disconnected:
            self.disconnect(client_id)

    async def broadcast_to_room(self, message: dict, room_id: int):
        """Broadcast a message to all clients in a specific room"""
        if room_id not in self.room_connections:
            return
        
        disconnected = []
        for client_id in self.room_connections[room_id]:
            if client_id in self.active_connections:
                websocket = self.active_connections[client_id]
                try:
                    await websocket.send_text(json.dumps(message))
                    # Update last active
                    if client_id in self.connection_info:
                        self.connection_info[client_id]["last_active"] = datetime.now()
                except WebSocketDisconnect:
                    disconnected.append(client_id)
        
        # Clean up any disconnected clients
        for client_id in disconnected:
            self.disconnect(client_id)

    async def broadcast_to_user(self, message: dict, user_id: int):
        """Broadcast a message to all connections of a specific user"""
        if user_id not in self.user_connections:
            return
        
        disconnected = []
        for client_id in self.user_connections[user_id]:
            if client_id in self.active_connections:
                websocket = self.active_connections[client_id]
                try:
                    await websocket.send_text(json.dumps(message))
                    # Update last active
                    if client_id in self.connection_info:
                        self.connection_info[client_id]["last_active"] = datetime.now()
                except WebSocketDisconnect:
                    disconnected.append(client_id)
        
        # Clean up any disconnected clients
        for client_id in disconnected:
            self.disconnect(client_id)

    def get_connections_info(self) -> schemas.WSConnectionInfo:
        """Get information about all active connections"""
        connections_by_room = {
            room_id: len(clients)
            for room_id, clients in self.room_connections.items()
        }
        return schemas.WSConnectionInfo(
            total_connections=len(self.connection_info),
            active_connections=len(self.active_connections),
            connections_by_room=connections_by_room
        )

    def join_room(self, client_id: str, room_id: int, db: Session = None):
        """Add a client to a room"""
        if client_id not in self.active_connections:
            return False

        # Add to room connections
        if room_id not in self.room_connections:
            self.room_connections[room_id] = set()
        self.room_connections[room_id].add(client_id)

        # Update metadata
        if client_id in self.connection_info:
            self.connection_info[client_id]["room_id"] = room_id

        # Update database if session provided
        if db:
            if (
                db_connection := db.query(models.WebSocketConnection)
                .filter(models.WebSocketConnection.id == client_id)
                .first()
            ):
                db_connection.room_id = room_id
                db.commit()

        return True

    def leave_room(self, client_id: str, room_id: int, db: Session = None):
        """Remove a client from a room"""
        if (
            room_id not in self.room_connections
            or client_id not in self.room_connections[room_id]
        ):
            return False
        self.room_connections[room_id].remove(client_id)

        # Clean up empty room
        if not self.room_connections[room_id]:
            self.room_connections.pop(room_id)

        # Update metadata
        if client_id in self.connection_info:
            self.connection_info[client_id]["room_id"] = None

            # Update database if session provided
        if db:
            if (
                db_connection := db.query(models.WebSocketConnection)
                .filter(models.WebSocketConnection.id == client_id)
                .first()
            ):
                db_connection.room_id = None
                db.commit()

        return True


# Global connection manager instance
manager = ConnectionManager()