# Theatre Ticket Booking System with AI Chat

This web app is a theater ticket booking service implemented as a chat with artificial intelligence. Users can interact with the AI bot to view the schedule of performances, book seats, check their reservations and cancel them.

## Project Description

The project is developed using Python and FastAPI for the server part, as well as OpenAI Chat Completions API with function calling support for the AI bot logic.

### Project goal

The main goal is to provide users with an intuitive interface to interact with the ticket booking service through a dialogue with AI, automating the process of selecting and booking seats.

### Tech stack

* **Backend:** Python 3.10+, FastAPI
* **Database:** SQLAlchemy ORM (SQLite by default, but can be easily configured for PostgreSQL, MySQL, etc.)
* **Artificial intelligence:** OpenAI Agents (via `openai` library)
* **Dependency management:** `pip` (via `requirements.txt`)
* **Web server:** `uvicorn`

### Minimum functionality

* **Authentication:** User registration and login.
* **Two pages:**
* **Login/registration page (`/login`, `/register`):** Standard forms for authentication.
* **Chat Page (`/`, `/chat/{chat_id}`):** Interface for communicating with the AI bot, including the chat window, input field, and send button.
* **AI System (based on OpenAI Agents):**
* Greeting and suggestion of available actions.
* **Book Tickets:** Search for upcoming shows, make seat reservations.
* **View Bookings:** View information about the user's booked tickets.
* **Cancel Booking:** Cancel existing bookings.
* **Working with the DB:** AI interacts with the database to save, retrieve, and update booking information. Prevent duplicate bookings.
* **DB Entities:**
* `User`: System users.
* `Performance`: Performances (date, title, author, actors).
* `Booking`: Bookings (link to performance, user, row, seat number).
* **Unique chat for each user:** Users see only their own chat history.
### Additional functionality (Pros)

* **Docker configuration:** For ease of launch
* **Deleting chat history:** Implemented deleting chat messages and the ability to delete the entire chat.
* **Complex processing of seat numbers:** Seats are numbered in the format `XX-Y`, where `XX` is the row number (from 1 to 20), `Y` is the seat letter (from A to Q). AI checks the correctness of the format and the availability of seats.
* **Filling the system with test data:** Implemented through the `fill_db.py` script and the `seed_data.json` file.
## json file
<details>
<summary>seed_data.json</summary>

```json

{
    "users": [
      {"username": "alice", "email": "alice@example.com", "password": "alice123"},
      {"username": "bob", "email": "bob@example.com", "password": "bob123"},
      {"username": "carol", "email": "carol@example.com", "password": "carol123"},
      {"username": "dave", "email": "dave@example.com", "password": "dave123"}
    ],
  
    "weekly_performances": [
      {
        "title": "Ревізор",
        "author": "Микола Гоголь",
        "actors": "Іванов, Петренко"
      },
      {
        "title": "Гамлет",
        "author": "Вільям Шекспір",
        "actors": "Коваленко, Сидорчук"
      },
      {
        "title": "Кайдашева сім’я",
        "author": "Іван Нечуй-Левицький",
        "actors": "Омельченко, Лесько"
      },
      {
        "title": "За двома зайцями",
        "author": "Михайло Старицький",
        "actors": "Шевченко, Гнатюк"
      }
    ]
  }
```
</details> 

## DB structure

![BD](/static/images/0.png)
## Project structure
```

├── BD/
│   ├── database.py         # Setting up SQLAlchemy database and sessions
│   ├── models.py           # Definition of ORM models (User, Chat, Message, Performance, Booking)
│   └── test.db             # SQLite database file (if used)
├── scripts/
│   ├── fill_db.py          # Script for filling the database with test data
│   ├── init_db.py          # Script for initializing the DB schema
│   └── seed_data.json      # File with test data for filling the database
├── static/                 # Static files (CSS, JS, images)
│   └── css/
│   └── js/
├── templates/
│   ├── index.html          # Basic chat page template
│   ├── login.html          # Login page template
│   └── register.html       # Registration page template
├── ai.py                   # AI agent logic and tools definition
├── main.py                 # Main FastAPI application file, routes, authorization logic and working with chat
├── requirements.txt        # List of Python Dependencies
├── schemas.py              # Pydantic models for API data validation
└── services.py             # Helper functions (password hashing, JWT, WebSocket management)
```

## Installation and launch

### 1. Cloning the repository

```bash
git clone https://github.com/SrMusienko/Momentim-chat.git
cd Momentim-chat
```
### 2. Creating a virtual environment and installing dependencies
```bash
python3.10 -m venv venv
source venv/bin/activate # For Linux/macOS
# venv\Scripts\activate # For Windows
pip install -r requirements.txt
```
### 3. Setting up environment variables
You will need an API key from OpenAI. Create a .env file in the root directory of the project. There is an example of filling in the .env.example file and add your key:
```bash
OPENAI_API_KEY="YOUR_OPENAI_KEY"
```
### 4. Initializing the database
```bash
python scripts/init_db.py
```
### 5. Filling the database with test data (optional)
```bash
python scripts/fill_db.py
```
### 6. Running the application
```bash
uvicorn main:app --reload --host 0.0.0.0 --port 5000
```
The application will be available at http://127.0.0.1:5000.


## Install and run via Docker(Podman)
### 1. Build the image
```bash
podman build -t theater-chat-app .
```

### 2. Run the container
```bash
podman run -d -p 8000:8000 --name theater-chat-container theater-chat-app
```

### 3. Test
Open in browser:

http://localhost:8000

or

http://127.0.0.1:8000

## Usage

1. **Register or Login:**
- Create a new account or log in using your existing credentials.
![login](/static/images/6.png)![register](/static/images/7.png)

2. **You can request a program of performances for a week or a specific day.**

![question1](/static/images/1.png)
![question2](/static/images/2.png)

3. **You can ask about the availability of a seat for a specific performance:**

![question3](/static/images/3.png)

4. **Book a seat and make sure it is booked**

![question4](/static/images/4.png)

5. **And finally, cancel the reservation**

![question6](/static/images/5.png)