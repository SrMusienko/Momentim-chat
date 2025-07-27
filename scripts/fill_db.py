import sys
import os
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))
import json
import asyncio
import random
from datetime import datetime, timedelta

from sqlalchemy import select, and_

from DB.database import AsyncSessionLocal, engine, Base
from DB.models import User, Performance, Booking
from services import hash_password

#scripts/fill_bd.py
SEAT_ROWS = list(range(1, 21))
SEAT_LETTERS = list("ABCDEFGHIJKLMNOPQ")

def get_random_seat():
    row = random.choice(SEAT_ROWS)
    letter = random.choice(SEAT_LETTERS)
    seat_code = f"{row}-{letter}"
    return row, ord(letter) - ord("A") + 1, seat_code

async def seed_database():
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
        await conn.run_sync(Base.metadata.create_all)

    async with AsyncSessionLocal() as session:
        CURRENT_DIR = os.path.dirname(__file__)
        JSON_PATH = os.path.join(CURRENT_DIR, "seed_data.json")

        with open(JSON_PATH, encoding="utf-8") as f:
            data = json.load(f)

        # Users
        for user in data["users"]:
            hashed = hash_password(user["password"])
            session.add(User(
                username=user["username"],
                email=user["email"],
                hashed_password=hashed
            ))
        await session.commit()

        users = (await session.execute(select(User))).scalars().all()

        # Performances for 4 weeks
        today = datetime.now().date()
        for day_offset in range(28):
            current_day = today + timedelta(days=day_offset)
            
            # We choose ONE random performance for the current day
            perf_data = random.choice(data["weekly_performances"]) 
            
            performance = Performance(
                title=perf_data["title"],
                author=perf_data["author"],
                actors=perf_data["actors"],
                date=current_day
            )
            session.add(performance)
        await session.commit()

        performances = (await session.execute(select(Performance))).scalars().all()

        # Bookings
        for perf in performances:
            # We reserve from 1 to 4 random seats for each performance
            for _ in range(random.randint(1, 4)):
                user = random.choice(users)
                row, seat_num, seat_code = get_random_seat()

                # Checking if this seat is already taken for this performance
                exists = await session.scalar(
                    select(Booking).where(
                        and_(
                            Booking.performance_id == perf.id,
                            Booking.seat_code == seat_code
                        )
                    )
                )
                if exists:
                    continue # If the space is occupied, skip and try again (although the loop does not guarantee a new space)

                booking = Booking(
                    user_id=user.id,
                    performance_id=perf.id,
                    seat_code=seat_code
                )
                session.add(booking)

        await session.commit()
        print("The database has been successfully filled.")

if __name__ == "__main__":
    asyncio.run(seed_database())