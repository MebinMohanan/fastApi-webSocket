import json
from typing import Optional
from fastapi import APIRouter, WebSocket, WebSocketDisconnect, Depends
from sqlalchemy.orm import Session
from datetime import datetime

from .. import models, schemas
from ..database import get_db
from ..dependencies import get_user_from_ws_token
from ..websocket_manager import manager

router = APIRouter()


@router.websocket("/ws")
async def websocket_endpoint(
    websocket: WebSocket,
    db: Session = Depends(get_db)
):
    """Main WebSocket endpoint for general notifications"""
    client_id = await manager.connect(websocket)
    
    try:
        while True:
            data = await websocket.receive_text()
            try:
                # Parse the incoming message
                message_data = json.loads(data)
                message_type = message_data.get("type", "message")
                
                # Handle different message types
                if message_type == "ping":
                    await manager.send_personal_message(
                        {"type": "pong", "timestamp": datetime.now().isoformat()},
                        client_id
                    )
                else:
                    # Echo the message back
                    await manager.send_personal_message(
                        {"type": "echo", "content": f"Received: {data}"},
                        client_id
                    )
            except json.JSONDecodeError:
                await manager.send_personal_message(
                    {"type": "error", "content": "Invalid JSON format"},
                    client_id
                )
    except WebSocketDisconnect:
        manager.disconnect(client_id, db)


@router.websocket("/ws/auth")
async def websocket_auth_endpoint(
    websocket: WebSocket,
    db: Session = Depends(get_db)
):
    """Authenticated WebSocket endpoint"""
    user = await get_user_from_ws_token(websocket, db)
    if not user:
        return  # WebSocket already closed in the dependency

    client_id = await manager.connect(websocket, user_id=user.id, db=db)

    # Notify user of successful connection
    await manager.send_personal_message(
        {
            "type": "connection_established",
            "user_id": user.id,
            "username": user.username,
            "client_id": client_id
        },
        client_id
    )

    try:
        while True:
            data = await websocket.receive_text()
            try:
                # Parse the incoming message
                message_data = json.loads(data)
                message_type = message_data.get("type", "message")

                if message_type == "message":
                    content = message_data.get("content")
                    room_id = message_data.get("room_id")

                    if content and room_id:
                        # Store the message in the database
                        db_message = models.Message(
                            content=content,
                            user_id=user.id,
                            room_id=room_id
                        )
                        db.add(db_message)
                        db.commit()
                        db.refresh(db_message)

                        # Broadcast the message to the room
                        await manager.broadcast_to_room(
                            {
                                "type": "message",
                                "id": db_message.id,
                                "content": content,
                                "user_id": user.id,
                                "username": user.username,
                                "room_id": room_id,
                                "timestamp": db_message.created_at.isoformat()
                            },
                            room_id
                        )
                    else:
                        await manager.send_personal_message(
                            {"type": "error", "content": "Missing content or room_id"},
                            client_id
                        )

                elif message_type == "join_room":
                    if room_id := message_data.get("room_id"):
                        if (
                            room := db.query(models.ChatRoom)
                            .filter(models.ChatRoom.id == room_id)
                            .first()
                        ):
                            # Add user to room if not already a member
                            user_room = db.query(models.UserRoom).filter(
                                models.UserRoom.user_id == user.id,
                                models.UserRoom.room_id == room_id
                            ).first()

                            if not user_room:
                                user_room = models.UserRoom(user_id=user.id, room_id=room_id)
                                db.add(user_room)
                                db.commit()

                            if success := manager.join_room(
                                client_id, room_id, db
                            ):
                                # Notify the user
                                await manager.send_personal_message(
                                    {"type": "room_joined", "room_id": room_id, "room_name": room.name},
                                    client_id
                                )

                                # Notify other users in the room
                                await manager.broadcast_to_room(
                                    {
                                        "type": "user_joined",
                                        "user_id": user.id,
                                        "username": user.username,
                                        "room_id": room_id,
                                        "timestamp": datetime.now().isoformat()
                                    },
                                    room_id
                                )
                            else:
                                await manager.send_personal_message(
                                    {"type": "error", "content": "Failed to join room"},
                                    client_id
                                )
                        else:
                            await manager.send_personal_message(
                                {"type": "error", "content": f"Room {room_id} does not exist"},
                                client_id
                            )
                    else:
                        await manager.send_personal_message(
                            {"type": "error", "content": "Missing room_id"},
                            client_id
                        )

                elif message_type == "leave_room":
                    if room_id := message_data.get("room_id"):
                        if success := manager.leave_room(
                            client_id, room_id, db
                        ):
                            # Notify the user
                            await manager.send_personal_message(
                                {"type": "room_left", "room_id": room_id},
                                client_id
                            )

                            # Notify other users in the room
                            await manager.broadcast_to_room(
                                {
                                    "type": "user_left",
                                    "user_id": user.id,
                                    "username": user.username,
                                    "room_id": room_id,
                                    "timestamp": datetime.now().isoformat()
                                },
                                room_id
                            )
                        else:
                            await manager.send_personal_message(
                                {"type": "error", "content": "Failed to leave room"},
                                client_id
                            )
                    else:
                        await manager.send_personal_message(
                            {"type": "error", "content": "Missing room_id"},
                            client_id
                        )

                elif message_type == "typing":
                    if room_id := message_data.get("room_id"):
                        # Broadcast typing notification to room
                        await manager.broadcast_to_room(
                            {
                                "type": "user_typing",
                                "user_id": user.id,
                                "username": user.username,
                                "room_id": room_id,
                                "timestamp": datetime.now().isoformat()
                            },
                            room_id
                        )

                elif message_type == "ping":
                    await manager.send_personal_message(
                        {"type": "pong", "timestamp": datetime.now().isoformat()},
                        client_id
                    )

                else:
                    # Handle unknown message types
                    await manager.send_personal_message(
                        {"type": "error", "content": f"Unknown message type: {message_type}"},
                        client_id
                    )

            except json.JSONDecodeError:
                await manager.send_personal_message(
                    {"type": "error", "content": "Invalid JSON format"},
                    client_id
                )
    except WebSocketDisconnect:
        # Handle disconnect
        manager.disconnect(client_id, db)

        if room_id := manager.connection_info.get(client_id, {}).get(
            "room_id"
        ):
            # Notify others in the room
            await manager.broadcast_to_room(
                {
                    "type": "user_disconnected",
                    "user_id": user.id,
                    "username": user.username,
                    "room_id": room_id,
                    "timestamp": datetime.now().isoformat()
                },
                room_id
            )


@router.websocket("/ws/room/{room_id}")
async def websocket_room_endpoint(
    websocket: WebSocket,
    room_id: int,
    db: Session = Depends(get_db)
):
    """Room-specific WebSocket endpoint"""
    user = await get_user_from_ws_token(websocket, db)
    if not user:
        return  # WebSocket already closed in the dependency

    # Check if room exists
    room = db.query(models.ChatRoom).filter(models.ChatRoom.id == room_id).first()
    if not room:
        await websocket.close(code=1008, reason=f"Room {room_id} does not exist")
        return

    # Check if user is a member of the room
    user_room = db.query(models.UserRoom).filter(
        models.UserRoom.user_id == user.id,
        models.UserRoom.room_id == room_id
    ).first()

    if not user_room:
        # Auto-join the room
        user_room = models.UserRoom(user_id=user.id, room_id=room_id)
        db.add(user_room)
        db.commit()

    # Connect to WebSocket and join room
    client_id = await manager.connect(websocket, user_id=user.id, room_id=room_id, db=db)

    # Send recent messages from the room
    recent_messages = db.query(models.Message).filter(
        models.Message.room_id == room_id
    ).order_by(models.Message.created_at.desc()).limit(50).all()

    # Reverse to get chronological order
    recent_messages = list(reversed(recent_messages))

    # Send message history
    await manager.send_personal_message(
        {
            "type": "message_history",
            "room_id": room_id,
            "messages": [
                {
                    "id": msg.id,
                    "content": msg.content,
                    "user_id": msg.user_id,
                    "timestamp": msg.created_at.isoformat()
                }
                for msg in recent_messages
            ]
        },
        client_id
    )

    # Notify other users in the room about the new user
    await manager.broadcast_to_room(
        {
            "type": "user_joined",
            "user_id": user.id,
            "username": user.username,
            "room_id": room_id,
            "timestamp": datetime.now().isoformat()
        },
        room_id
    )

    try:
        while True:
            data = await websocket.receive_text()
            try:
                # Parse the incoming message
                message_data = json.loads(data)
                message_type = message_data.get("type", "message")

                if message_type == "message":
                    if content := message_data.get("content"):
                        # Store the message in the database
                        db_message = models.Message(
                            content=content,
                            user_id=user.id,
                            room_id=room_id
                        )
                        db.add(db_message)
                        db.commit()
                        db.refresh(db_message)

                        # Broadcast the message to the room
                        await manager.broadcast_to_room(
                            {
                                "type": "message",
                                "id": db_message.id,
                                "content": content,
                                "user_id": user.id,
                                "username": user.username,
                                "room_id": room_id,
                                "timestamp": db_message.created_at.isoformat()
                            },
                            room_id
                        )
                    else:
                        await manager.send_personal_message(
                            {"type": "error", "content": "Missing content"},
                            client_id
                        )

                elif message_type == "typing":
                    # Broadcast typing notification to room
                    await manager.broadcast_to_room(
                        {
                            "type": "user_typing",
                            "user_id": user.id,
                            "username": user.username,
                            "room_id": room_id,
                            "timestamp": datetime.now().isoformat()
                        },
                        room_id
                    )

                elif message_type == "ping":
                    await manager.send_personal_message(
                        {"type": "pong", "timestamp": datetime.now().isoformat()},
                        client_id
                    )

                else:
                    # Handle unknown message types
                    await manager.send_personal_message(
                        {"type": "error", "content": f"Unknown message type: {message_type}"},
                        client_id
                    )

            except json.JSONDecodeError:
                await manager.send_personal_message(
                    {"type": "error", "content": "Invalid JSON format"},
                    client_id
                )
    except WebSocketDisconnect:
        # Handle disconnect
        manager.disconnect(client_id, db)

        # Notify others in the room
        await manager.broadcast_to_room(
            {
                "type": "user_disconnected",
                "user_id": user.id,
                "username": user.username,
                "room_id": room_id,
                "timestamp": datetime.now().isoformat()
            },
            room_id
        )


@router.get("/connections", response_model=schemas.WSConnectionInfo)
async def get_connection_info():
    """Get information about WebSocket connections"""
    return manager.get_connections_info()