from pydantic import BaseModel, EmailStr, Field
from typing import List, Optional
from datetime import datetime


class UserBase(BaseModel):
    username: str
    email: EmailStr


class UserCreate(UserBase):
    password: str


class User(UserBase):
    id: int
    is_active: bool

    class Config:
        orm_mode = True


class Token(BaseModel):
    access_token: str
    token_type: str


class TokenData(BaseModel):
    username: Optional[str] = None


class ChatRoomBase(BaseModel):
    name: str
    description: Optional[str] = None


class ChatRoomCreate(ChatRoomBase):
    pass


class ChatRoom(ChatRoomBase):
    id: int
    created_at: datetime
    
    class Config:
        orm_mode = True


class MessageBase(BaseModel):
    content: str
    room_id: int


class MessageCreate(MessageBase):
    pass


class Message(MessageBase):
    id: int
    created_at: datetime
    user_id: int
    
    class Config:
        orm_mode = True


class WebSocketMessage(BaseModel):
    type: str  # message, join, leave, etc.
    content: Optional[str] = None
    room_id: Optional[int] = None
    user_id: Optional[int] = None
    timestamp: Optional[datetime] = Field(default_factory=datetime.now)


class WSConnectionStatus(BaseModel):
    client_id: str
    is_connected: bool
    connected_at: Optional[datetime] = None
    user_id: Optional[int] = None
    room_id: Optional[int] = None


class WSConnectionInfo(BaseModel):
    total_connections: int
    active_connections: int
    connections_by_room: dict