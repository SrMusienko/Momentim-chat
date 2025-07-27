import json
import re
from datetime import date, datetime
from typing import Optional

from openai import AsyncOpenAI
from sqlalchemy import select, and_
from sqlalchemy.ext.asyncio import AsyncSession

from DB.database import API_KEY
from DB.models import Performance, Booking

# ai.py
client = AsyncOpenAI(api_key=API_KEY)

async def list_performances(
    db: AsyncSession,
    start_date: Optional[date] = None,
    end_date: Optional[date] = None
) -> str:
    query = select(Performance)

    if start_date and end_date:
        query = query.where(Performance.date.between(start_date, end_date))
    elif start_date:
        query = query.where(Performance.date >= start_date)
    elif end_date:
        query = query.where(Performance.date <= end_date)

    query = query.order_by(Performance.date)
    result = await db.execute(query)
    performances = result.scalars().all()

    if not performances:
        return "No performances found for the specified period."
    
    return "\n".join(f"{p.id}. {p.title} - {p.date}" for p in performances)

async def my_list_performances( 
    db: AsyncSession,
    user_id: int,
    start_date: Optional[date] = None,
    end_date: Optional[date] = None
) -> str:
    filters = [Booking.user_id == user_id]

    if start_date:
        filters.append(Performance.date >= start_date)
    if end_date:
        filters.append(Performance.date <= end_date)

    stmt = (
        select(Performance)
        .join(Booking)
        .where(and_(*filters))
        .order_by(Performance.date)
    )

    result = await db.execute(stmt)
    performances = result.scalars().all()

    if not performances:
        return "You have no booked performances for the selected dates."

    return "\n".join(
        f"{p.date}: {p.title} — {p.author or 'Author Unknown'}" for p in performances 
    )

async def check_book_ticket(
    db: AsyncSession,
    performance_id: int,
    seat_code: str
) -> tuple[bool, str]:
    result = await db.scalar(
        select(Booking).where(
            and_(
                Booking.performance_id == performance_id,
                Booking.seat_code == seat_code
            )
        )
    )
    if result:
        return False, f"Ticket for seat {seat_code} is already taken." 
    return True, f"Seat {seat_code} is available." 

def is_valid_seat_code(seat_code: str) -> bool:
    return bool(re.fullmatch(r"(1[0-9]|20|[1-9])-[A-Q]", seat_code.upper()))

async def book_ticket(
    db: AsyncSession,
    performance_id: int,
    seat_code: str,
    user_id: int,
) -> str:
    if not is_valid_seat_code(seat_code):
        return f"Invalid seat format: {seat_code}. Use format 3-B or 17-H." 
    is_free, message = await check_book_ticket(db, performance_id, seat_code)
    if not is_free:
        return message

    new_ticket = Booking(
        performance_id=performance_id,
        seat_code=seat_code,
        user_id=user_id
    )
    db.add(new_ticket)
    await db.commit()
    return f"Ticket for seat {seat_code} successfully booked." 

async def cancel_booking(
    db: AsyncSession,
    performance_id: int,
    seat_code: str,
    user_id: int,
) -> str:
    stmt = select(Booking).where(
        and_(
            Booking.performance_id == performance_id,
            Booking.seat_code == seat_code,
            Booking.user_id == user_id
        )
    )
    result = await db.execute(stmt)
    booking = result.scalar_one_or_none()

    if not booking:
        return f"Booking for seat {seat_code} not found."

    await db.delete(booking)
    await db.commit()
    return f"Booking for seat {seat_code} successfully cancelled."

# Dictionary of available functions for OpenAI
TOOLS = {
    "list_performances": {
        "function": list_performances,
        "config": {
            "type": "function",
            "function": { 
                "name": "list_performances",
                "description": "Get a list of theater performances by date",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "start_date": {"type": "string", "format": "date"},
                        "end_date": {"type": "string", "format": "date"}
                    }
                }
            }
        }
    },
    "book_ticket": {
        "function": book_ticket,
        "config": {
            "type": "function",  
            "function": { 
                "name": "book_ticket",
                "description": "Book a ticket for a performance", 
                "parameters": {
                    "type": "object",
                    "properties": {
                        "performance_id": {"type": "integer"},
                        "seat_code": {"type": "string", "description": "Seat code in XX-Y format, e.g., 3-B or 17-H"} # Changed "seat" to "seat_code" and added description
                    },
                    "required": ["performance_id", "seat_code"] 
                }
            }
        }
    },
    "cancel_booking": {
        "function": cancel_booking,
        "config": {
            "type": "function",
            "function": { 
                "name": "cancel_booking",
                "description": "Cancel a seat booking", 
                "parameters": {
                    "type": "object",
                    "properties": {
                        "performance_id": {"type": "integer"},
                        "seat_code": {
                            "type": "string",
                            "description": "Seat code in XX-Y format" 
                        }
                    },
                    "required": ["performance_id", "seat_code"]
                }
            }
        }
    },
    "my_list_performances": {
        "function": my_list_performances,
        "config": {
            "type": "function",
            "function": { 
                "name": "my_list_performances",
                "description": "View a list of performances for which you have booked tickets.", 
                "parameters": {
                    "type": "object",
                    "properties": {
                        "start_date": {
                            "type": "string",
                            "format": "date",
                            "description": "Start date of the period (YYYY-MM-DD format)"
                        },
                        "end_date": {
                            "type": "string",
                            "format": "date",
                            "description": "End date of the period (YYYY-MM-DD format)" 
                        }
                    }
                }
            }
        }
    }
}


def get_tools_configs():
    return [
        tool["config"]
        for tool in TOOLS.values()
    ]

async def execute_tool(tool_name: str, db: AsyncSession, **kwargs):
    """Executes the specified tool""" 
    if tool_name not in TOOLS:
        raise ValueError(f"Unknown tool: {tool_name}")
    
    return await TOOLS[tool_name]["function"](db=db, **kwargs)


async def handle_tool_calls(tool_calls, openai_messages, db, current_user):
    for tool_call in tool_calls:
        function_name = tool_call.function.name
        function_args = json.loads(tool_call.function.arguments)
        
        if function_name in ["book_ticket", "my_list_performances","cancel_booking"]:
            function_args["user_id"] = current_user.id

        result = await execute_tool(function_name, db=db, **function_args)
        
        openai_messages.append({
            "tool_call_id": tool_call.id,
            "role": "tool",
            "name": function_name,
            "content": result,
        })
    return openai_messages

def get_system_prompt():
    current_date = datetime.now().strftime("%Y-%m-%d, %A") 
    return (
        f"Today is {current_date}."
        f"You are a virtual assistant for booking theater tickets. " 
        f"Standard evening time is 7:00 PM. One performance per day." 
        f"You work with a real database and can perform the following actions via tools: "
        f"viewing performances, booking, viewing, and canceling bookings.\n\n"
        f"Seat format: XX-Y, XX ∈ [1..20], Y ∈ [A..Q]. Examples: 3-B, 17-H. "
        f"Do not allow booking of already taken seats or non-existent codes.\n"
        f"Save information to the database for further interaction.\n"
    )