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
            "status": "TO_APPLY"
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
            "status": "TO_APPLY"
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


@pytest.mark.asyncio
async def test_search_profiles_directives_and_ingest():
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        # 1. Default seeded profiles
        res = await ac.get("/api/search-profiles")
        assert res.status_code == 200
        profiles = res.json()
        assert len(profiles) >= 2
        assert any(p["is_default"] for p in profiles)

        # 2. Create custom search profile scoped to X-User-Id
        create_res = await ac.post(
            "/api/search-profiles",
            headers={"X-User-Id": "friend_wolffm"},
            json={
                "name": "Staff Platform Engineer (IC)",
                "is_default": True,
                "keywords": ["Rust", "Go", "Kubernetes"],
                "target_companies": ["Cloudflare", "Anthropic"],
                "track": "ic",
                "levels": ["staff", "principal"],
                "remote_pref": "remote",
                "location": "Seattle, WA",
                "radius_miles": 25,
            },
        )
        assert create_res.status_code == 200
        created = create_res.json()
        assert created["user_id"] == "friend_wolffm"
        assert created["track"] == "ic"
        assert "staff" in created["levels"]

        # 3. Check directives pull endpoint (union of companies and keywords)
        dir_res = await ac.get("/api/directives")
        assert dir_res.status_code == 200
        directives = dir_res.json()
        assert "Cloudflare" in directives["companies"]
        assert "Rust" in directives["keywords"]

        # 4. Ingest webhook batch from scraper
        ingest_res = await ac.post(
            "/api/ingest",
            json={
                "source": "greenhouse",
                "batch_number": 1,
                "is_final": True,
                "jobs": [
                    {
                        "id": "gh_101",
                        "title": "Senior Backend Engineer, Core APIs",
                        "company": "Stripe",
                        "url": "https://boards.greenhouse.io/stripe/jobs/101",
                        "location": "Remote, US",
                        "remote_type": "remote",
                        "description": "Build scalable services in Python, Go, and SQL.",
                    }
                ],
            },
        )
        assert ingest_res.status_code == 200
        assert ingest_res.json()["inserted"] == 1

        # 5. Re-score pipeline with profile
        score_res = await ac.post(
            f"/api/search-profiles/{created['id']}/score-pipeline",
            headers={"X-User-Id": "friend_wolffm"},
        )
        assert score_res.status_code == 200
        assert score_res.json()["jobs_scored"] >= 1
        scored_job = score_res.json()["jobs"][0]
        assert scored_job["role_track"] == "ic"
        assert scored_job["role_level"] == "senior"

        # 6. Verify chunked resume blocks endpoint (/api/profile/resume-blocks)
        blocks_res = await ac.get("/api/profile/resume-blocks")
        assert blocks_res.status_code == 200
        blocks_data = blocks_res.json()
        assert blocks_data["count"] >= 2
        assert any(b["type"] == "header" for b in blocks_data["blocks"])
        assert any(b["type"] == "skills" for b in blocks_data["blocks"])


@pytest.mark.asyncio
async def test_autopilot_config_and_pipeline_routing():
    import shutil
    from app.services.question_answerer import PACKETS_DIR

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        # 1. Configure candidate profile & skills
        await ac.put(
            "/api/profile",
            json={
                "full_name": "Justin Kilpatrick",
                "email": "justin@example.com",
                "phone": "555-0199",
                "location": "Austin, TX",
                "title": "Software Engineer",
                "summary": "Backend engineer specializing in Python, FastAPI, and SQL.",
                "work_authorization": "Authorized to work in the US without sponsorship",
                "desired_salary": "$140,000",
                "notice_period": "2 weeks",
            },
        )
        await ac.post("/api/profile/skills", json={"name": "Python", "category": "languages", "proficiency": "expert"})
        await ac.post("/api/profile/skills", json={"name": "FastAPI", "category": "frameworks", "proficiency": "expert"})
        await ac.post("/api/profile/skills", json={"name": "SQL", "category": "databases", "proficiency": "expert"})

        # 2. Get and update Autopilot config
        cfg_res = await ac.get("/api/autopilot/config")
        assert cfg_res.status_code == 200
        assert cfg_res.json()["min_auto_apply_score"] == 70

        upd_cfg = await ac.put(
            "/api/autopilot/config",
            json={"min_discover_score": 45, "min_auto_apply_score": 75, "auto_submit": True},
        )
        assert upd_cfg.status_code == 200
        assert upd_cfg.json()["min_auto_apply_score"] == 75

        # 3. Create a job on an auth-gated portal (Workday) -> should generate tailored resume, cover letter,
        #    answer all questions, and route to TO_APPLY ("Need to Apply") with reason explaining login wall
        job_res = await ac.post(
            "/api/jobs",
            json={
                "title": "Backend Python Engineer",
                "company": "EnterpriseCloud",
                "location": "Remote, US",
                "workplace_type": "remote",
                "url": "https://enterprise.wd5.myworkdayjobs.com/en-US/careers/job/Backend-Python-Engineer_R123",
                "description": "Seeking a Backend Python Engineer experienced with Python, FastAPI, and SQL.",
                "status": "TO_APPLY",
            },
        )
        assert job_res.status_code == 200
        job_id = job_res.json()["id"]

        run_job_res = await ac.post(
            f"/api/autopilot/jobs/{job_id}/run",
            json={"ai_provider": "template"},
        )
        assert run_job_res.status_code == 200
        payload = run_job_res.json()
        assert payload["result"]["outcome"] == "needs_manual_apply"
        assert payload["result"]["documents_generated"] is True
        assert payload["result"]["questions_answered"] >= 11

        updated_job = payload["job"]
        assert updated_job["status"] == "TO_APPLY"
        assert updated_job["autopilot_status"] == "needs_manual_apply"
        assert "Need to Apply" in (updated_job["autopilot_reason"] or "")
        assert len(updated_job["answers"]) >= 11
        doc_types = {d["doc_type"] for d in updated_job["tailored_documents"]}
        assert "tailored_resume" in doc_types
        assert "cover_letter" in doc_types
        assert "application_kit" in doc_types

        # 4. Answer an on-demand custom question for the job
        qa_res = await ac.post(
            f"/api/autopilot/jobs/{job_id}/answer-question",
            json={"question": "How many years of experience do you have with Python?"},
        )
        assert qa_res.status_code == 200
        assert "5" in qa_res.json()["answer_item"]["answer"]

        # 5. Run batch queue cycle (scrape_new=False, process_existing_queue=True)
        cycle_res = await ac.post(
            "/api/autopilot/run",
            json={"scrape_new": False, "process_existing_queue": True, "ai_provider": "template"},
        )
        assert cycle_res.status_code == 200
        summary = cycle_res.json()["summary"]
        assert summary["processed_count"] >= 1
        assert summary["routed_to_need_to_apply_count"] >= 1

        shutil.rmtree(PACKETS_DIR, ignore_errors=True)




