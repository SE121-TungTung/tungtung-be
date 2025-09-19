from fastapi import FastAPI
import database

app = FastAPI(title="English Center Management API")

db = database.get_db()

@app.get("/")
def root():
    return {"message": "Hello from FastAPI + Supabase backend 🚀"}