from datetime import datetime, timedelta, timezone
from typing import Optional, Dict

from fastapi import Depends, Request, WebSocket, HTTPException, Response
from jose import jwt
from jose.exceptions import ExpiredSignatureError
from passlib.context import CryptContext
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from DB.database import SECRET_KEY, get_db
from DB.models import User

# services.py
ALGORITHM = "HS256"
async def get_token_from_request(request: Request) -> Optional[str]:
    auth_header = request.headers.get("Authorization")
    if auth_header and auth_header.startswith("Bearer "):
        return auth_header.split(" ")[1]
    
    access_token_cookie = request.cookies.get("access_token")
    if access_token_cookie and access_token_cookie.startswith("Bearer "):
        return access_token_cookie.split(" ")[1]
    return None


async def get_current_user_from_token(
    token: str,
    db: AsyncSession,
    refresh_expired: bool = False 
) -> Optional[User]:
    if not token:
        return None

    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        user_id = int(payload["sub"])
        user = await db.scalar(select(User).where(User.id == user_id))
        return user

    except ExpiredSignatureError:
        if refresh_expired:  # If token refresh is allowed
            new_token = create_access_token(data={"sub": payload["sub"]})
            # Here you could return both the user and the new token
            user = await db.scalar(select(User).where(User.id == int(payload["sub"])))
            return user
        return None

    except (jwt.PyJWTError, ValueError, KeyError):
        return None


async def get_current_user_http(
    request: Request,
    response: Response,
    db: AsyncSession = Depends(get_db)
) -> User:
    token = await get_token_from_request(request)
    if not token:
        raise HTTPException(status_code=401, detail="Authorization required") 

    user = await get_current_user_from_token(token, db, refresh_expired=True)
    if not user:
        raise HTTPException(status_code=401, detail="Invalid or expired token")

    # If the token was refreshed, set the new one in the cookie
    if isinstance(user, tuple):  # If returning (user, new_token)
        user, new_token = user
        response.set_cookie("access_token", f"Bearer {new_token}")

    return user

def create_access_token(data: dict, expires_delta: Optional[timedelta] = None):
    to_encode = data.copy()
    expire = datetime.now(timezone.utc) + (expires_delta or timedelta(minutes=15))
    to_encode.update({"exp": expire})
    return jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")
def hash_password(password: str) -> str:
    return pwd_context.hash(password)

def verify_password(plain_password: str, hashed_password: str) -> bool:
    return pwd_context.verify(plain_password, hashed_password)


class ConnectionManager:
    def __init__(self):
        self.active_connections: Dict[int, WebSocket] = {}

    async def connect(self, chat_id: int, websocket: WebSocket):
        if chat_id in self.active_connections:
            await self.active_connections[chat_id].close()
        await websocket.accept()
        self.active_connections[chat_id] = websocket

    def disconnect(self, chat_id: int):
        self.active_connections.pop(chat_id, None)

    async def send_message_to_chat(self, chat_id: int, message: str):
        websocket = self.active_connections.get(chat_id)
        if websocket:
            try:
                await websocket.send_text(message)
            except RuntimeError:
                self.disconnect(chat_id)