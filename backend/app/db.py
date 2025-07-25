

#Path use to handle file systems paths in safe, cross-platform way. used to build path to db file
from pathlib import Path
#use to type-hint return type of get_db func. generator implies "thing that gives one value at a time"
from typing import Generator
#create_engine connects app to database
from sqlalchemy import create_engine
#declarative base, used to define models, session maker factory for making temp db connections for each request
from sqlalchemy.orm import DeclarativeBase, sessionmaker





'''Set up a DB connection (create_engine)
Create reusable sessions to interact with DB (sessionmaker)
Define base classes for your DB models (DeclarativeBase)
gives FastAPI a safe way to use database during requests

# SQLite chosen because: zero install, single file committed to .gitignore.
# Swap to Postgres later by replacing this URL with:
# "postgresql+asyncpg://user:pass@host:5432/dbname"

#Sets up SQLite file path one folder up(backend/cal.db)
__file__ → The current file (db.py)
.resolve() → Get the full absolute path
.parents[1] → Go one folder up (from backend/app/ to backend/)
/ 'cal.db' → Append the name of the database file
sqlite:///... → The format SQLAlchemy expects for SQLite file paths
'''


SQLITE_URL = f"sqlite:///{Path(__file__).resolve().parents[1] / 'cal.db'}"



'''engine manages the connection to the SQLite file.
echo=False: don’t print every query to the terminal.
future=True: use newer SQLAlchemy behavior.
object knows where databse is, how to speak SQL, and how to run transactions'''

engine = create_engine(SQLITE_URL, echo=False, future=True)


SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False)
'''This factory makes sessions, single-use temp database connections per request.
bind = engine ties it to db
autoflush and autocommit set to False means control when changes get saved, which is safer
controls when things get saved?'''




class Base(DeclarativeBase):
    """Foundation class for all DB models, every model will inherit from this so SQLAlchemy can track table defs
    builds schema and manages metadata
    Base.metadata.create_all(...) uses this to generate tables
    base keeps all blueprints organized 
    CREATES A SHARED PARENT CLASS FOR ALL MODELS
    Declarative base every model inherits—keeps metadata in one place."""
    pass

def get_db() -> Generator:
    """FastAPI dependency: gives a DB session and guarantees close().
    used with Depends(get_db)
    injects database session into route. yield db give fresh connection when request omes in, temp hands db session like /events
    ,finally runs and closes when done so no memory leaks or locked files"""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
        


'''
 main.py uses this file like this:

@app.get("/events")
def list_events(db: Session = Depends(get_db)):
So:

FastAPI calls get_db()
get_db() creates a session using SessionLocal
That session is used to make queries like:
db.scalars(select(Event)).all()
When the route finishes, the session is automatically closed

Tool	            Purpose

create_engine()	    Opens connection to SQLite file
SessionLocal	    Makes temporary DB connections
Base	            Base class for defining tables
get_db()	        FastAPI hook to safely use DB per request
SQLITE_URL	        Points to where .db file is stored

'''