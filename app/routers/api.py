from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.security import OAuth2PasswordRequestForm
from sqlalchemy.orm import Session
from typing import List
from datetime import timedelta

from .. import models, schemas
from ..database import get_db
from ..dependencies import (
    get_current_active_user,
    authenticate_user,
    create_access_token,
    get_password_hash,
    ACCESS_TOKEN_EXPIRE_MINUTES
)
from ..websocket_manager import manager

router = APIRouter()


@router.post("/token", response_model=schemas.Token)
async def login_for_access_token(
    form_data: OAuth2PasswordRequestForm = Depends(),
    db: Session = Depends(get_db)
):
    """
    Get an access token for authentication
    """
    print(111)
    print(form_data)
    user = authenticate_user(db, form_data.username, form_data.password)
    if not user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect username or password",
            headers={"WWW-Authenticate": "Bearer"},
        )
    access_token_expires = timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)
    access_token = create_access_token(
        data={"sub": user.username}, expires_delta=access_token_expires
    )
    return {"access_token": access_token, "token_type": "bearer"}


@router.post("/users/", response_model=schemas.User)
async def create_user(user: schemas.UserCreate, db: Session = Depends(get_db)):
    """
    Create a new user
    """
    # Check if username already exists
    db_user = db.query(models.User).filter(models.User.username == user.username).first()
    if db_user:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Username already registered"
        )
    
    # Check if email already exists
    db_user = db.query(models.User).filter(models.User.email == user.email).first()
    if db_user:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Email already registered"
        )
    
    # Create new user
    hashed_password = get_password_hash(user.password)
    db_user = models.User(
        username=user.username,
        email=user.email,
        hashed_password=hashed_password
    )
    db.add(db_user)
    db.commit()
    db.refresh(db_user)
    return db_user


@router.get("/users/me/", response_model=schemas.User)
async def read_users_me(current_user: models.User = Depends(get_current_active_user)):
    """
    Get current user information
    """
    return current_user


@router.post("/rooms/", response_model=schemas.ChatRoom)
async def create_chat_room(
    room: schemas.ChatRoomCreate,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_active_user)
):
    """
    Create a new chat room
    """
    # Check if room name already exists
    db_room = db.query(models.ChatRoom).filter(models.ChatRoom.name == room.name).first()
    if db_room:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Room name already exists"
        )
    
    # Create new room
    db_room = models.ChatRoom(
        name=room.name,
        description=room.description
    )
    db.add(db_room)
    db.commit()
    db.refresh(db_room)
    
    # Add current user to the room
    user_room = models.UserRoom(user_id=current_user.id, room_id=db_room.id)
    db.add(user_room)
    db.commit()
    
    return db_room


@router.get("/rooms/", response_model=List[schemas.ChatRoom])
async def get_chat_rooms(
    skip: int = 0,
    limit: int = 100,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_active_user)
):
    """
    Get all chat rooms
    """
    return db.query(models.ChatRoom).offset(skip).limit(limit).all()


@router.get("/rooms/{room_id}", response_model=schemas.ChatRoom)
async def get_chat_room(
    room_id: int,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_active_user)
):
    """
    Get a specific chat room
    """
    if (
        room := db.query(models.ChatRoom)
        .filter(models.ChatRoom.id == room_id)
        .first()
    ):
        return room
    else:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Chat room not found"
        )


@router.post("/rooms/{room_id}/join")
async def join_chat_room(
    room_id: int,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_active_user)
):
    """
    Join a chat room
    """
    # Check if room exists
    room = db.query(models.ChatRoom).filter(models.ChatRoom.id == room_id).first()
    if not room:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Chat room not found"
        )
    
    # Check if user is already in the room
    user_room = db.query(models.UserRoom).filter(
        models.UserRoom.user_id == current_user.id,
        models.UserRoom.room_id == room_id
    ).first()
    
    if user_room:
        return {"message": "Already a member of this room"}
    
    # Add user to room
    user_room = models.UserRoom(user_id=current_user.id, room_id=room_id)
    db.add(user_room)
    db.commit()
    
    # Notify users in the room
    await manager.broadcast_to_room(
        {
            "type": "user_joined",
            "user_id": current_user.id,
            "username": current_user.username,
            "room_id": room_id
        },
        room_id
    )
    
    return {"message": "Successfully joined the room"}


@router.post("/rooms/{room_id}/leave")
async def leave_chat_room(
    room_id: int,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_active_user)
):
    """
    Leave a chat room
    """
    # Check if room exists
    room = db.query(models.ChatRoom).filter(models.ChatRoom.id == room_id).first()
    if not room:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Chat room not found"
        )
    
    # Check if user is in the room
    user_room = db.query(models.UserRoom).filter(
        models.UserRoom.user_id == current_user.id,
        models.UserRoom.room_id == room_id
    ).first()
    
    if not user_room:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="You are not a member of this room"
        )
    
    # Remove user from room
    db.delete(user_room)
    db.commit()
    
    # Notify users in the room
    await manager.broadcast_to_room(
        {
            "type": "user_left",
            "user_id": current_user.id,
            "username": current_user.username,
            "room_id": room_id
        },
        room_id
    )
    
    return {"message": "Successfully left the room"}


@router.get("/rooms/{room_id}/messages", response_model=List[schemas.Message])
async def get_room_messages(
    room_id: int,
    skip: int = 0,
    limit: int = 100,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_active_user)
):
    """
    Get messages from a specific chat room
    """
    # Check if room exists
    room = db.query(models.ChatRoom).filter(models.ChatRoom.id == room_id).first()
    if not room:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Chat room not found"
        )
    
    # Check if user is in the room
    user_room = db.query(models.UserRoom).filter(
        models.UserRoom.user_id == current_user.id,
        models.UserRoom.room_id == room_id
    ).first()
    
    if not user_room:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="You are not a member of this room"
        )
    
    # Get messages
    messages = db.query(models.Message).filter(
        models.Message.room_id == room_id
    ).order_by(models.Message.created_at.desc()).offset(skip).limit(limit).all()
    
    # Return in reverse order to get chronological order
    return list(reversed(messages))


@router.post("/rooms/{room_id}/messages", response_model=schemas.Message)
async def create_message(
    room_id: int,
    message: schemas.MessageCreate,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_active_user)
):
    """
    Create a new message in a chat room
    """
    # Check if room exists
    room = db.query(models.ChatRoom).filter(models.ChatRoom.id == room_id).first()
    if not room:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Chat room not found"
        )
    
    # Check if user is in the room
    user_room = db.query(models.UserRoom).filter(
        models.UserRoom.user_id == current_user.id,
        models.UserRoom.room_id == room_id
    ).first()
    
    if not user_room:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="You are not a member of this room"
        )
    
    # Create message
    db_message = models.Message(
        content=message.content,
        user_id=current_user.id,
        room_id=room_id
    )
    db.add(db_message)
    db.commit()
    db.refresh(db_message)
    
    # Broadcast message to WebSocket clients
    await manager.broadcast_to_room(
        {
            "type": "message",
            "id": db_message.id,
            "content": db_message.content,
            "user_id": current_user.id,
            "username": current_user.username,
            "room_id": room_id,
            "timestamp": db_message.created_at.isoformat()
        },
        room_id
    )
    
    return db_message