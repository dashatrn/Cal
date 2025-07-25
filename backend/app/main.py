# app/main.py

''' 
import Fast API to create web routes (GET/POST)
Depends: handles dependency injection, auto plugging in database when necessary
Get a database session for each request
select from database table, makes queries like SELECT * FROM events
in a clean way
'''
from fastapi import FastAPI, Depends
from sqlalchemy.orm import Session
from sqlalchemy import select

'''
db: builds engine and gives access to db
models: defines the structure of event table
schemas: defines shapes of data coming in/out
'''
# ── local modules ─────────────────────────────────────────────
from .db import Base, engine, get_db
from .models import Event
from .schemas import EventIn, EventOut
# ───────────────────────────────────────

# Creates API
app = FastAPI(title="Cal API")


# runs when app starts and creats table if it doesn't existyet
'''Base.metadata.create_all(...) scans all your SQLAlchemy models (like Event) and 
creates the actual table in the SQLite database — if it doesn't already exist.
'''

@app.on_event("startup")
def init_db() -> None:
    Base.metadata.create_all(bind=engine)

#simple check to confirm server running
@app.get("/health")
def health_check():
    return {"status": "ok"}


#https://silver-goldfish-44r7x5x9qg5255jv-8000.app.github.dev/health



'''
backend route, sits on server waiting for GET request to /events. request comes from React frontend. 
When react code runs, send get request here.
Receving get request, sends from database. 
response_model = list[EventOUT] means return value shuold be list EventOut objects, defined by schemas.oy
db: Session = Depends(get_db) means FASTAPI will run get_db() and give result to this func as db
select(Event) = Give all rows from events table, like writing SELECT * FROM events in SQL
db.scalars(...).all() - Execute that query, return that into a Python list of event objects
FastAPI autoconverst into JSON
sends back to frontend
events are stored in SQLite database file on server


[
  {
    "id": 1,
    "title": "Dentist",
    "start": "2025-08-01T09:00:00",
    "end": "2025-08-01T10:00:00"
  },
  ...
]


The website requests the events, 
events live in database
backend is middle layer speaks to db and internet

React code runs and sends
fetch("https://your-url-8000.app.github.dev/events")

'''

@app.get("/events", response_model=list[EventOut])
def list_events(db: Session = Depends(get_db)):
    return db.scalars(select(Event)).all()



'''runs when someone sends a POST to /events with JSON body
JSON must match shape of EventIn
data:Event in means FastAPI will validate with Pydantic
data.model()dump turns it into a dictionary. '''


@app.post("/events", response_model=EventOut, status_code=201)
def create_event(data: EventIn, db: Session = Depends(get_db)):
    #creeates SQLAlchemy object
    evt = Event(**data.model_dump())

    # queues it to be saved
    db.add(evt)

    #saves object to SQLite .db file
    db.commit()

    # updates evt.id with real DB generated ID
    db.refresh(evt)

    #event returned with new id
    return evt





'''
| Concept                    | What It Does                                                                                                        |
| -------------------------- | ------------------------------------------------------------------------------------------------------------------- |
| `FastAPI()`                | Creates the app — API brain.                                                                           |
| `@app.on_event("startup")` | Runs once when the server starts. builds the `events` table using `Base.metadata`.                          |
| `@app.get("/health")`      | A simple check to make sure the API is alive and running. Returns `{"status": "ok"}`.                               |
| `@app.get("/events")`      | Responds to GET requests from the frontend. Grabs all `Event` rows from the database and sends them back as JSON.   |
| `@app.post("/events")`     | Responds to POST requests. Takes in a JSON event, validates it, adds it to the database, and returns it with an ID. |
| `Depends(get_db)`          | Tells FastAPI: “Give this route a fresh database connection, and close it afterward.”                               |
| `response_model=...`       | Makes sure your API returns clean, well-shaped JSON that matches your schema (`EventOut`).                          |

'''