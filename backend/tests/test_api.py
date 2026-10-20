import os
import pytest
import pytest_asyncio
from httpx import AsyncClient, ASGITransport
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker, AsyncSession
from app.main import app
from app.database import Base, get_db

TEST_DB_PATH = os.path.join(os.path.dirname(__file__), "test_jobs.db")
TEST_DATABASE_URL = f"sqlite+aiosqlite:///{TEST_DB_PATH}"

test_engine = create_async_engine(
    TEST_DATABASE_URL,
    echo=False,
    connect_args={"check_same_thread": False}
)

TestSessionLocal = async_sessionmaker(
    bind=test_engine,
    class_=AsyncSession,
    expire_on_commit=False,
    autoflush=False
)

async def override_get_db():
    async with TestSessionLocal() as session:
        try:
            yield session
        finally:
            await session.close()

app.dependency_overrides[get_db] = override_get_db

@pytest_asyncio.fixture(autouse=True)
async def setup_test_db():
    async with test_engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    yield
    async with test_engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
    if os.path.exists(TEST_DB_PATH):
        try:
            os.remove(TEST_DB_PATH)
        except Exception:
            pass

@pytest.mark.asyncio
async def test_health_check():
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        response = await ac.get("/api/health")
        assert response.status_code == 200
        assert response.json()["status"] == "healthy"

@pytest.mark.asyncio
async def test_create_and_list_job():
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        job_data = {
            "title": "Full Stack Engineer",
            "company": "Tech Innovators",
            "location": "Remote",
            "workplace_type": "remote",
            "salary_min": 120000,
            "salary_max": 150000,
            "description": "Looking for Python, React, and PostgreSQL expertise.",
            "source": "manual",
            "status": "WISHLIST"
        }
        res = await ac.post("/api/jobs", json=job_data)
        assert res.status_code == 200
        data = res.json()
        assert data["title"] == "Full Stack Engineer"
        assert data["company"] == "Tech Innovators"
        job_id = data["id"]

        # List jobs
        list_res = await ac.get("/api/jobs")
        assert list_res.status_code == 200
        jobs = list_res.json()
        assert any(j["id"] == job_id for j in jobs)

        # Update status
        patch_res = await ac.patch(f"/api/jobs/{job_id}", json={"status": "APPLIED"})
        assert patch_res.status_code == 200
        assert patch_res.json()["status"] == "APPLIED"

        # Check analytics
        analytics_res = await ac.get("/api/analytics/metrics")
        assert analytics_res.status_code == 200
        funnel = analytics_res.json()["funnel"]
        assert funnel["total_tracked"] >= 1

@pytest.mark.asyncio
async def test_discovery_search_with_location_and_radius():
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        res = await ac.get("/api/discovery/search", params={
            "query": "developer",
            "location": "Austin, TX",
            "radius": 25,
            "include_remote": True,
            "source": "arbeitnow"  # Use fast mockable/public endpoint for deterministic unit test
        })
        assert res.status_code == 200
        assert isinstance(res.json(), list)

@pytest.mark.asyncio
async def test_job_expiration_check_endpoints():
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        # Create a job with an expired deadline
        res = await ac.post("/api/jobs", json={
            "title": "Old Opening",
            "company": "Expired Corp",
            "deadline": "2020-01-01T00:00:00",
            "status": "WISHLIST"
        })
        assert res.status_code == 200
        job_id = res.json()["id"]

        # Check single job status
        chk_res = await ac.post(f"/api/jobs/{job_id}/check-status")
        assert chk_res.status_code == 200
        data = chk_res.json()
        assert data["is_expired"] is True
        assert "deadline passed" in (data["expired_reason"] or "").lower()

        # Check check-all-status
        all_res = await ac.post("/api/jobs/check-all-status")
        assert all_res.status_code == 200
        assert all_res.json()["checked"] >= 1
        assert all_res.json()["expired_found"] >= 1

