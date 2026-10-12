import pytest
import pytest_asyncio
from httpx import AsyncClient, ASGITransport
from app.main import app
from app.database import init_db

@pytest_asyncio.fixture(autouse=True)
async def setup_test_db():
    await init_db()

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
