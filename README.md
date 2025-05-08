# FastAPI WebSocket Chat Application

A robust real-time chat application built with FastAPI, SQLite, and WebSockets.

## Features

- **User Authentication**: JWT-based authentication for REST API and WebSockets
- **Persistent Data**: SQLite database for storing users, rooms, messages, and connection info
- **Real-time Communication**: Multiple WebSocket endpoints for different use cases
- **Connection Management**: Advanced WebSocket connection tracking and management
- **Room System**: Create and join chat rooms
- **REST API**: Full RESTful API alongside WebSocket connections

## Project Structure

```
project_root/
├── app/
│   ├── __init__.py
│   ├── main.py
│   ├── database.py
│   ├── models.py
│   ├── schemas.py
│   ├── websocket_manager.py
│   ├── dependencies.py
│   └── routers/
│       ├── __init__.py
│       ├── api.py
│       └── websocket.py
├── .env
├── requirements.txt
└── README.md
```

## Installation

1. Clone the repository
2. Create a virtual environment
   ```bash
   python -m venv venv
   source venv/bin/activate  # On Windows: venv\Scripts\activate
   ```
3. Install dependencies
   ```bash
   pip install -r requirements.txt
   ```
4. Set up environment variables (or modify the .env file)
   ```bash
   # Example .env file
   DATABASE_URL=sqlite:///./app.db
   SECRET_KEY=yoursecretkey
   ALGORITHM=HS256
   ACCESS_TOKEN_EXPIRE_MINUTES=30
   ```

## Running the Application

```bash
uvicorn app.main:app --reload
```

The application will be available at http://localhost:8000

- API Documentation: http://localhost:8000/docs
- Alternative API Documentation: http://localhost:8000/redoc

## WebSocket Endpoints

### Public WebSocket: `/ws`

Basic WebSocket endpoint without authentication.

### Authenticated WebSocket: `/ws/auth`

WebSocket endpoint that requires authentication via a token query parameter.
Example: `ws://localhost:8000/ws/auth?token=your_jwt_token`

### Room WebSocket: `/ws/room/{room_id}`

WebSocket endpoint for a specific chat room.
Example: `ws://localhost:8000/ws/room/1?token=your_jwt_token`

### Echo WebSocket: `/ws/echo`

Simple echo WebSocket endpoint for testing.

## API Endpoints

### Authentication

- `POST /api/token`: Get a JWT token with username and password

### Users

- `POST /api/users/`: Create a new user
- `GET /api/users/me/`: Get current user information

### Chat Rooms

- `POST /api/rooms/`: Create a new chat room
- `GET /api/rooms/`: Get all chat rooms
- `GET /api/rooms/{room_id}`: Get a specific chat room
- `POST /api/rooms/{room_id}/join`: Join a chat room
- `POST /api/rooms/{room_id}/leave`: Leave a chat room

### Messages

- `GET /api/rooms/{room_id}/messages`: Get messages from a specific chat room
- `POST /api/rooms/{room_id}/messages`: Create a new message in a chat room

### WebSocket Information

- `GET /api/connections`: Get information about WebSocket connections

## WebSocket Message Types

### Client to Server

- `message`: Send a message
- `join_room`: Join a chat room
- `leave_room`: Leave a chat room
- `typing`: Indicate that the user is typing
- `ping`: Check connection

### Server to Client

- `message`: A new message
- `message_history`: History of messages when joining a room
- `user_joined`: A user joined the room
- `user_left`: A user left the room
- `user_typing`: A user is typing
- `user_disconnected`: A user disconnected
- `connection_established`: Connection established
- `room_joined`: Successfully joined a room
- `room_left`: Successfully left a room
- `error`: Error message
- `pong`: Response to ping

## Example WebSocket Usage

Here's a simple JavaScript example of connecting to a WebSocket and sending messages:

```javascript
// Connect to a room
const token = "your_jwt_token";
const socket = new WebSocket(`ws://localhost:8000/ws/room/1?token=${token}`);

// Handle connection open
socket.onopen = (event) => {
  console.log("Connection opened");
  
  // Send a message
  const message = {
    type: "message",
    content: "Hello, WebSocket!"
  };
  socket.send(JSON.stringify(message));
};

// Handle incoming messages
socket.onmessage = (event) => {
  const data = JSON.parse(event.data);
  console.log("Received:", data);
  
  // Handle different message types
  switch (data.type) {
    case "message":
      console.log(`${data.username}: ${data.content}`);
      break;
    case "user_joined":
      console.log(`${data.username} joined the room`);
      break;
    // Handle other message types...
  }
};

// Handle errors
socket.onerror = (error) => {
  console.error("WebSocket Error:", error);
};

// Handle connection close
socket.onclose = (event) => {
  console.log("Connection closed:", event.code, event.reason);
};

// Send typing notification
function sendTypingNotification() {
  const message = {
    type: "typing"
  };
  socket.send(JSON.stringify(message));
}
```

