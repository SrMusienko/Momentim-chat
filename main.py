import json
from typing import List, Optional

import uvicorn

from fastapi import (FastAPI, Depends, Request,
                     Form, status, Response,
                     HTTPException, WebSocket, WebSocketDisconnect, Query)
from fastapi.responses import RedirectResponse, HTMLResponse
from fastapi.templating import Jinja2Templates
from fastapi.staticfiles import StaticFiles

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from DB.database import get_db
from DB.models import User, Message, Chat
from services import (get_current_user_http, get_current_user_from_token, get_token_from_request,
                      create_access_token, hash_password, verify_password, ConnectionManager)
from schemas import ChatResponse, MessageResponse, MessageCreate
from ai import client, get_tools_configs, get_system_prompt, handle_tool_calls

#main.py
OPENAI_MODEL = "gpt-4.1-mini"
ACCESS_TOKEN_EXPIRE_MINUTES = 60 * 24  # Token for 24 hours
manager = ConnectionManager()

app = FastAPI()
templates = Jinja2Templates(directory="templates")
app.mount("/static", StaticFiles(directory="static"), name="static")

@app.get("/login", response_class=HTMLResponse)
async def login_page(request: Request):
    return templates.TemplateResponse("login.html", {"request": request})

@app.post("/login")
async def login(
    request: Request,
    username: str = Form(...),
    password: str = Form(...),
    db: AsyncSession = Depends(get_db)
):
    user = await db.scalar(select(User).where(User.email == username))
    if not (user and verify_password(password, user.hashed_password)):
        return templates.TemplateResponse("login.html", {
            "request": request,
            "error": "Invalid email or password"
        })

    token = create_access_token(data={"sub": str(user.id)})
    response = RedirectResponse(url="/", status_code=303)
    response.set_cookie("access_token", f"Bearer {token}")
    return response

@app.get("/logout")
async def logout(response: Response):
    response = RedirectResponse(url="/login")
    response.delete_cookie("access_token")
    return response

@app.get("/register", response_class=HTMLResponse)
async def register_page(request: Request):
    return templates.TemplateResponse("register.html", {"request": request})

def render_error(request: Request, template: str, error: str) -> HTMLResponse:
    return templates.TemplateResponse(template, {
        "request": request,
        "error": error
    })

@app.post("/register")
async def register(
    request: Request,
    username: str = Form(...),
    email: str = Form(...),
    password: str = Form(...),
    confirm_password: str = Form(...),
    db: AsyncSession = Depends(get_db)
):
    if password != confirm_password:
        return render_error(request, "register.html", "Passwords do not match") # Changed from "Пароли не совпадают"

    if await db.scalar(select(User).where(User.email == email)):
        return render_error(request, "register.html", "Email already registered") # Changed from "Email уже занят"

    try:
        user = User(username=username, email=email, hashed_password=hash_password(password))
        db.add(user)
        await db.commit()
        return RedirectResponse(url="/login", status_code=303)
    except Exception as e:
        await db.rollback()
        return render_error(request, "register.html", f"Registration error: {e}") # Changed from "Ошибка регистрации"

@app.get("/", response_class=HTMLResponse)
async def index(
    request: Request,
    db: AsyncSession = Depends(get_db),
):
    
    token = await get_token_from_request(request)
    if token is None:
        return RedirectResponse(url="/login", status_code=status.HTTP_303_SEE_OTHER)

    current_user = await get_current_user_from_token(token=token, db=db)
    if current_user is None:
        return RedirectResponse(url="/login", status_code=status.HTTP_303_SEE_OTHER)

    result = await db.execute(
        select(Chat).where(Chat.user_id == current_user.id).order_by(Chat.created_at.desc())
    )
    chats = result.scalars().all()

    active_chat: Optional[Chat] = None
    messages: List[Message] = []

    if chats:
        active_chat = chats[0]
        result = await db.execute(
            select(Message).where(Message.chat_id == active_chat.id).order_by(Message.timestamp)
        )
        messages = result.scalars().all()

    return templates.TemplateResponse("index.html", {
        "request": request,
        "user": current_user,
        "chats": chats,
        "messages": messages,
        "active_chat": active_chat
    })

@app.post("/api/chats", response_model=ChatResponse)
async def create_chat(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user_http)
):
    if not current_user:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Not authenticated")

    new_chat = Chat(user_id=current_user.id)
    db.add(new_chat)
    await db.commit()
    await db.refresh(new_chat)
    return ChatResponse.from_orm(new_chat)

@app.get("/api/chats/{chat_id}/messages", response_model=List[MessageResponse])
async def get_chat_messages(
    chat_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user_http)
):
    if not current_user:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Not authenticated")

    chat_result = await db.execute(select(Chat).where(Chat.id == chat_id, Chat.user_id == current_user.id))
    chat = chat_result.scalar_one_or_none()

    if not chat:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Chat not found or not authorized")

    result = await db.execute(
        select(Message).where(Message.chat_id == chat_id).order_by(Message.timestamp)
    )
    messages = result.scalars().all()
    return [MessageResponse.from_orm(m) for m in messages]

@app.post("/api/chats/{chat_id}/messages", response_model=MessageResponse)
async def send_message_to_ai(
    chat_id: int,
    message_data: MessageCreate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user_http)
):
    # 1. Auth & chat validation
    if not current_user:
        raise HTTPException(status_code=401, detail="Unauthorized")
    
    chat = await db.scalar(select(Chat).where(Chat.id == chat_id, Chat.user_id == current_user.id))
    if not chat:
        raise HTTPException(status_code=404, detail="Chat not found")

    # 2. Save user message
    user_message = Message(
        chat_id=chat_id,
        sender=current_user.username,
        content=message_data.content
    )
    db.add(user_message)
    await db.commit()

    # 3. Get chat history (last 10 messages)
    messages = await db.scalars(
    select(Message)
    .where(Message.chat_id == chat_id)
    .order_by(Message.timestamp.desc())
    .limit(10)
)
    messages = messages.all()
    
    # 4. Prepare OpenAI request
    
    openai_messages = [
        {"role": "system", "content": get_system_prompt()},
        *[{"role": "user" if m.sender == current_user.username else "assistant", 
           "content": m.content} 
          for m in reversed(messages)]
    ]

    # 5. Get AI response
    try:
        response = await client.chat.completions.create(
        model=OPENAI_MODEL,
        messages=openai_messages,
        tools=get_tools_configs(),
        tool_choice="auto"
        )
    
        response_message = response.choices[0].message
        tool_calls = response_message.tool_calls

        if tool_calls:
            openai_messages.append(response_message)
            
            await handle_tool_calls(tool_calls, openai_messages, db, current_user)
            
            # Second API call with tool responses
            second_response = await client.chat.completions.create(
                model=OPENAI_MODEL,
                messages=openai_messages,
            )
            ai_content = second_response.choices[0].message.content
        else:
            ai_content = response_message.content
    except Exception as e:
        print(f"OpenAI error: {e}")
        ai_content = "Error processing request" 

    # 6. Save & send AI response
    ai_message = Message(chat_id=chat_id, sender="AI", content=ai_content)
    db.add(ai_message)
    await db.commit()

    await manager.send_message_to_chat(
        chat_id,
        json.dumps({
            "type": "new_message",
            "message": MessageResponse.from_orm(ai_message).dict()
        }, default=str)
    )

    return MessageResponse.from_orm(ai_message)

 

@app.get("/chat/{chat_id}", response_class=HTMLResponse)
async def get_specific_chat(
    request: Request,
    chat_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user_http)
):
    if not current_user:
        return RedirectResponse(url="/login", status_code=status.HTTP_303_SEE_OTHER)

    result_chats = await db.execute(
        select(Chat).where(Chat.user_id == current_user.id).order_by(Chat.created_at.desc())
    )
    chats = result_chats.scalars().all()

    active_chat: Optional[Chat] = None
    messages: List[Message] = []

    requested_chat_result = await db.execute(
        select(Chat).where(Chat.id == chat_id, Chat.user_id == current_user.id)
    )
    requested_chat = requested_chat_result.scalar_one_or_none()

    if requested_chat:
        active_chat = requested_chat
        result_messages = await db.execute(
            select(Message).where(Message.chat_id == active_chat.id).order_by(Message.timestamp)
        )
        messages = result_messages.scalars().all()
    else:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Chat not found or not authorized")

    return templates.TemplateResponse("index.html", {
        "request": request,
        "user": current_user,
        "chats": chats,
        "messages": messages,
        "active_chat": active_chat
    })

@app.delete("/api/chats/{chat_id}")
async def delete_chat(
    chat_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user_http)
):
    if not current_user:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Not authenticated")

    chat_to_delete_result = await db.execute(select(Chat).where(Chat.id == chat_id, Chat.user_id == current_user.id))
    chat_to_delete = chat_to_delete_result.scalar_one_or_none()

    if not chat_to_delete:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Chat not found or not authorized")

    await db.delete(chat_to_delete)
    await db.commit()

    manager.disconnect(chat_id)

    return {"message": "Chat deleted successfully"} 


@app.delete("/api/messages/{message_id}")
async def delete_message(
    message_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user_http)
):
    if not current_user:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Not authenticated")

    message_to_delete_result = await db.execute(
        select(Message).where(Message.id == message_id)
    )
    message_to_delete = message_to_delete_result.scalar_one_or_none()

    if not message_to_delete:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Message not found")

    chat_check_result = await db.execute(
        select(Chat).where(Chat.id == message_to_delete.chat_id, Chat.user_id == current_user.id)
    )
    chat_owner = chat_check_result.scalar_one_or_none()

    if not chat_owner:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Not authorized to delete this message")
    
    if message_to_delete.sender != current_user.username and message_to_delete.sender != "AI":
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Only owner or AI messages can be deleted.")

    await db.delete(message_to_delete)
    await db.commit()

    return {"message": "Message deleted successfully"} 

@app.websocket("/ws/chat/{chat_id}")
async def websocket_endpoint(
    websocket: WebSocket,
    chat_id: int,
    token: str = Query(...), 
    db: AsyncSession = Depends(get_db)
):
    current_user: User = await get_current_user_from_token(token=token, db=db)

    if not current_user:
        print("WebSocket authentication failed: Invalid or missing token.") 
        await websocket.close(code=status.WS_1008_POLICY_VIOLATION) 
        return

    chat_result = await db.execute(select(Chat).where(Chat.id == chat_id, Chat.user_id == current_user.id))
    chat = chat_result.scalar_one_or_none()

    if not chat:
        print(f"User {current_user.id} tried to connect to unauthorized chat {chat_id}")
        await websocket.close(code=status.WS_1008_POLICY_VIOLATION)
        return

    try:
        await manager.connect(chat_id, websocket)
        while True:
            await websocket.receive_text()

    except WebSocketDisconnect:
        manager.disconnect(chat_id)
    except Exception as e:
        print(f"WebSocket error: {e}") 
        manager.disconnect(chat_id)

if __name__ == "__main__":
    uvicorn.run(app, host="127.0.0.1", port=5000)