from contextlib import asynccontextmanager
import time
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from .database import init_db
from .routers import jobs, discovery, profile, assistant, analytics, search_profiles

BOOT_ID = str(int(time.time() * 1000))

@asynccontextmanager
async def lifespan(app: FastAPI):
    # Initialize DB tables on startup
    await init_db()
    yield

app = FastAPI(
    title="Local Job Dashboard API",
    description="Privacy-first local engine for job search discovery, ATS matching, AI tailoring, and pipeline management",
    version="1.0.0",
    lifespan=lifespan
)

# CORS config
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Mount API routers
app.include_router(jobs.router)
app.include_router(discovery.router)
app.include_router(profile.router)
app.include_router(search_profiles.router)
app.include_router(assistant.router)
app.include_router(analytics.router)

@app.get("/api/health")
async def health_check():
    return {"status": "healthy", "service": "job-dashboard-api", "boot_id": BOOT_ID}
