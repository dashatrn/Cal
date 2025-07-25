# new lines — load .env automatically 
from dotenv import load_dotenv
load_dotenv()

#This line gets executed when the app package is imported, meaning .env will be loaded before any os.getenv(...) calls happen (like in  CORS middleware).