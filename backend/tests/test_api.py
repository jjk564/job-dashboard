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

        for d in PACKETS_DIR.glob(f"job_{job_id}_*"):
            shutil.rmtree(d, ignore_errors=True)


@pytest.mark.asyncio
async def test_bot_trap_api_and_native_extension_endpoints(monkeypatch, tmp_path):
    import shutil
    from app.services import autopilot as ap_mod
    from app.services.question_answerer import PACKETS_DIR
    from app.routers import assistant as assistant_mod

    monkeypatch.setattr(assistant_mod, "NATIVE_QUEUE_PATH", tmp_path / "native_browser_queue.json")

    async def _fake_not_expired(url, deadline=None):
        return False, None

    monkeypatch.setattr(ap_mod, "check_job_expiration", _fake_not_expired)

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        await ac.put(
            "/api/profile",
            json={
                "full_name": "Justin Kilpatrick",
                "email": "jkilpatrick50@gmail.com",
                "phone": "781-879-4389",
                "location": "Boston, Massachusetts (Remote)",
                "title": "Software Engineer",
                "work_authorization": "Authorized to work in the US without sponsorship",
                "desired_salary": "$75,000",
                "notice_period": "2 weeks",
            },
        )

        # 1. Creating a job with a bot trap persists & returns bot_traps automatically
        create_res = await ac.post(
            "/api/jobs",
            json={
                "title": "Junior AI Engineer",
                "company": "RoastTech",
                "location": "Remote",
                "workplace_type": "remote",
                "url": "https://careers.roasttech.invalid/jobs/999",
                "description": "Great entry-level role! Please mention coffee in your application so we know that you read this. Build Python, FastAPI, and AI tools.",
                "source": "indeed",
                "status": "TO_APPLY",
            },
        )
        assert create_res.status_code == 200
        created = create_res.json()
        job_id = created["id"]
        assert len(created["bot_traps"]) == 1
        assert created["bot_traps"][0]["trigger_phrase"].lower() == "coffee"

        # 2. Autopilot single-job run MUST NOT auto-submit when a human_check bot trap is present
        ap_res = await ac.post(f"/api/autopilot/jobs/{job_id}/run", json={"ai_provider": "template", "min_auto_apply_score": 0})
        assert ap_res.status_code == 200
        assert ap_res.json()["result"]["outcome"] == "needs_manual_apply"
        assert "bot trap" in ap_res.json()["result"]["reason"].lower()

        # 3. Stage native Regular Chrome extension queue without opening a browser window
        stage_res = await ac.post(
            "/api/assistant/stage-browser-queue",
            json={"job_ids": [job_id], "open_browser": False},
        )
        assert stage_res.status_code == 200
        assert stage_res.json()["success"] is True
        assert stage_res.json()["count"] == 1

        # 4. Extension fetches active-autofill context for that URL
        ctx_res = await ac.get(
            "/api/assistant/active-autofill",
            params={"url": "https://careers.roasttech.invalid/jobs/999"},
        )
        assert ctx_res.status_code == 200
        ctx = ctx_res.json()
        assert ctx["matched"] is True
        assert ctx["job"]["id"] == job_id
        assert len(ctx["job"]["bot_traps"]) == 1
        assert ctx["job"]["resume_pdf_url"] == f"/api/assistant/jobs/{job_id}/packet-file/resume_pdf"

        # 5. Extension downloads tailored Resume PDF
        pdf_res = await ac.get(ctx["job"]["resume_pdf_url"])
        assert pdf_res.status_code == 200
        assert pdf_res.content.startswith(b"%PDF-1.4")

        # 6. Extension batch-answers fields + detects live-page traps
        ans_res = await ac.post(
            "/api/assistant/answer-fields",
            json={
                "job_id": job_id,
                "fields": [
                    {"id": "f1", "label": "First Name", "field_type": "text", "required": True},
                    {"id": "f2", "label": "Are you legally authorized to work in the US?", "options": ["Yes", "No"], "field_type": "select", "required": True},
                    {"id": "f3", "label": "Internal Secret Project Number", "field_type": "text", "required": True},
                ],
                "page_text": "Note: start your cover letter with 'Latte Art' to prove you are human.",
            },
        )
        assert ans_res.status_code == 200
        ans_data = ans_res.json()
        by_id = {a["id"]: a for a in ans_data["answers"]}
        assert by_id["f1"]["answer"] == "Justin"
        assert by_id["f2"]["answer"] == "Yes"
        assert by_id["f3"]["confidence"] == "manual_needed"
        assert by_id["f3"]["answer"] == ""
        assert len(ans_data["bot_traps"]) >= 2

        # 7. Extension marks job Applied via queue action
        act_res = await ac.post(
            "/api/assistant/active-autofill/action",
            json={"action": "mark_applied_next", "job_id": job_id},
        )
        assert act_res.status_code == 200
        assert act_res.json()["done"] is True
        job_after = (await ac.get(f"/api/jobs/{job_id}")).json()
        assert job_after["status"] == "APPLIED"

        for d in PACKETS_DIR.glob(f"job_{job_id}_*"):
            shutil.rmtree(d, ignore_errors=True)


@pytest.mark.asyncio
async def test_smartrecruiters_redirect_url_matching_and_shadow_dom_extension(monkeypatch, tmp_path):
    import base64
    from pathlib import Path
    from playwright.sync_api import sync_playwright
    from app.routers import assistant as assistant_mod
    from app.services.question_answerer import answer_single_question

    monkeypatch.setattr(assistant_mod, "NATIVE_QUEUE_PATH", tmp_path / "native_browser_queue.json")

    # 1. Verify SmartRecruiters OneClick UI & smartr.me redirect URL matching
    job_url = "https://jobs.smartrecruiters.com/M3USA/744000158547269-software-engineer-remote-"
    oneclick_url = "https://jobs.smartrecruiters.com/oneclick-ui/company/M3USA/publication/cc594d71-901b-4886-a5df-a7c64f37aebf?dcr_ci=M3USA"
    smartr_url = "https://www.smartr.me/oneclick-ui/company/M3USA/publication/cc594d71-901b-4886-a5df-a7c64f37aebf?dcr_ci=M3USA"
    assert assistant_mod._urls_roughly_match(oneclick_url, job_url, "m3usa") is True
    assert assistant_mod._urls_roughly_match(smartr_url, job_url, "m3usa") is True
    assert assistant_mod._urls_roughly_match("https://jobs.smartrecruiters.com/OtherCo/99999", job_url, "m3usa") is False

    # 2. Verify Shadow DOM SmartRecruiters form autofill via extension/content.js in real Chromium
    content_js = (Path(__file__).resolve().parents[2] / "extension" / "content.js").read_text(encoding="utf-8")
    profile = {
        "full_name": "Justin Kilpatrick",
        "email": "jkilpatrick50@gmail.com",
        "phone": "781-879-4389",
        "location": "Boston, Massachusetts (Remote)",
        "title": "Software Engineer",
        "linkedin_url": "https://www.linkedin.com/in/justin-kilpatrick-a05369110/",
        "github_url": "https://github.com/jjk564",
        "work_authorization": "Authorized to work in the US without sponsorship",
        "desired_salary": "$65,000 - $100,000",
        "notice_period": "Immediate / 2 weeks",
    }
    job = {
        "id": 135,
        "title": "Software Engineer (Remote)",
        "company": "m3usa",
        "cover_letter_text": "Dear M3USA Hiring Team, I am excited to apply!",
    }

    html = """<!doctype html><html><body>
    <form id="sr-form">
      <spl-input data-test="first-name-input" label="First name" required></spl-input>
      <spl-input data-test="last-name-input" label="Last name" required></spl-input>
      <spl-input data-test="email-input" label="Email" required></spl-input>
      <spl-input data-test="confirm-email-input" label="Confirm your email" required></spl-input>
      <spl-autocomplete data-test="city-input" label="Place of residence"></spl-autocomplete>
      <spl-input data-test="phone-input" label="Phone number"></spl-input>
      <spl-input data-test="linkedin-input" label="LinkedIn"></spl-input>
      <spl-input data-test="twitter-input" label="Twitter"></spl-input>
      <spl-textarea data-test="hiring-msg" label="Message to the Hiring Team"></spl-textarea>
      <spl-dropzone data-test="resume-upload" label="Resume"></spl-dropzone>
      <spl-checkbox data-test="privacy-consent" label="I agree to the Privacy Policy"></spl-checkbox>
    </form>
    <script>
      window.__composedEvents = [];
      class SplInput extends HTMLElement {
        connectedCallback() {
          const sr = this.attachShadow({ mode: 'open' });
          sr.innerHTML = `<label for="spl-input-1">${this.getAttribute('label')}</label><input id="spl-input-1" type="text" />`;
          this.addEventListener('input', () => window.__composedEvents.push(this.getAttribute('data-test')));
        }
      }
      class SplAutocomplete extends HTMLElement {
        connectedCallback() {
          const sr = this.attachShadow({ mode: 'open' });
          sr.innerHTML = `<input id="spl-ac-1" type="search" role="combobox" aria-autocomplete="list" />`;
        }
      }
      class SplTextarea extends HTMLElement {
        connectedCallback() {
          const sr = this.attachShadow({ mode: 'open' });
          sr.innerHTML = `<textarea id="spl-ta-1"></textarea>`;
        }
      }
      class SplDropzone extends HTMLElement {
        connectedCallback() {
          const sr = this.attachShadow({ mode: 'open' });
          sr.innerHTML = `<div class="dz">Drop resume here<input type="file" accept=".pdf,.doc,.docx" style="display:none" /></div>`;
        }
      }
      class SplCheckbox extends HTMLElement {
        connectedCallback() {
          const sr = this.attachShadow({ mode: 'open' });
          sr.innerHTML = `<label><input type="checkbox" /> <span>${this.getAttribute('label')}</span></label>`;
        }
      }
      customElements.define('spl-input', SplInput);
      customElements.define('spl-autocomplete', SplAutocomplete);
      customElements.define('spl-textarea', SplTextarea);
      customElements.define('spl-dropzone', SplDropzone);
      customElements.define('spl-checkbox', SplCheckbox);
    </script></body></html>"""

    def _run_shadow_check():
        with sync_playwright() as p:
            b = p.chromium.launch(headless=True)
            page = b.new_page()
            page.set_content(html)

            def handle_msg(msg):
                t = msg.get("type")
                if t == "GET_ACTIVE_AUTOFILL":
                    return {
                        "ok": True,
                        "data": {
                            "matched": True,
                            "job": {**job, "resume_pdf_url": "/fake/resume.pdf", "resume_filename": "Resume.pdf", "bot_traps": []},
                            "queue": {"is_speed_run": False, "index": 0, "total": 1},
                        },
                    }
                if t == "FETCH_PDF":
                    return {"ok": True, "base64": base64.b64encode(b"%PDF-1.4\n%%EOF").decode()}
                if t == "ANSWER_FIELDS":
                    out = []
                    for f in msg["payload"]["fields"]:
                        qa = answer_single_question(
                            question_text=f["label"],
                            job_data=job,
                            profile_data=profile,
                            candidate_skills=["Python", "TypeScript"],
                            options=f.get("options"),
                            field_type=f.get("field_type", "text"),
                            required=f.get("required", False),
                        )
                        out.append({
                            "id": f["id"],
                            "label": f["label"],
                            "answer": qa["answer"],
                            "confidence": qa["confidence"],
                            "category": qa["category"],
                        })
                    return {"ok": True, "data": {"answers": out, "bot_traps": []}}
                return {"ok": False}

            page.expose_function("__pySendMsg", handle_msg)
            page.evaluate("""() => {
                window.chrome = {
                    runtime: {
                        lastError: null,
                        sendMessage: (msg, cb) => { window.__pySendMsg(msg).then(cb); },
                        onMessage: { addListener: () => {} },
                    }
                };
            }""")
            page.add_script_tag(content=content_js)
            page.wait_for_timeout(1800)

            res = page.evaluate("""() => {
                const vals = {};
                document.querySelectorAll('spl-input, spl-autocomplete, spl-textarea').forEach(el => {
                    vals[el.getAttribute('data-test')] = el.shadowRoot.querySelector('input, textarea').value;
                });
                const fileInp = document.querySelector('spl-dropzone').shadowRoot.querySelector('input[type="file"]');
                const cb = document.querySelector('spl-checkbox').shadowRoot.querySelector('input[type="checkbox"]');
                return {
                    vals,
                    fileCount: fileInp.files.length,
                    checkboxChecked: cb.checked,
                    composedEventsCount: window.__composedEvents.length,
                    twitterOutline: document.querySelector('spl-input[data-test="twitter-input"]').style.outline,
                    hudPresent: Boolean(document.getElementById('jobpulse-native-hud')),
                };
            }""")
            b.close()
            return res

    import asyncio
    state = await asyncio.to_thread(_run_shadow_check)
    assert state["vals"]["first-name-input"] == "Justin"
    assert state["vals"]["last-name-input"] == "Kilpatrick"
    assert state["vals"]["email-input"] == "jkilpatrick50@gmail.com"
    assert state["vals"]["confirm-email-input"] == "jkilpatrick50@gmail.com"
    assert state["vals"]["city-input"] == "Boston, MA"
    assert state["vals"]["phone-input"] == "781-879-4389"
    assert state["vals"]["linkedin-input"] == "https://www.linkedin.com/in/justin-kilpatrick-a05369110/"
    assert state["vals"]["twitter-input"] == ""
    assert state["twitterOutline"] == ""
    assert "Dear M3USA Hiring Team" in state["vals"]["hiring-msg"]
    assert state["fileCount"] == 1
    assert state["checkboxChecked"] is True
    assert state["composedEventsCount"] >= 6
    assert state["hudPresent"] is True

    # 3. Verify screening radio questions (both native shadow radios & [role="radio"] shadow radios)
    #    AND in-place multi-step wizard transition at the SAME URL (like SmartRecruiters Step 1 -> Step 2)
    def _run_multistep_screening_radios():
        step_html = """<!doctype html><html><body>
        <div id="wizard-root">
          <form id="step1">
            <spl-input data-test="first-name-input" label="First name"></spl-input>
          </form>
        </div>
        <button id="next-step-btn" type="button">Next</button>
        <script>
          class SplInput extends HTMLElement {
            connectedCallback() {
              const sr = this.attachShadow({ mode: 'open' });
              sr.innerHTML = `<label for="i1">${this.getAttribute('label')}</label><input id="i1" type="text" />`;
            }
          }
          class SplRadioGroup extends HTMLElement {}
          class SplRadioNative extends HTMLElement {
            connectedCallback() {
              const sr = this.attachShadow({ mode: 'open' });
              sr.innerHTML = `<label><input type="radio" name="sr-opt" /><slot></slot></label>`;
            }
          }
          class SplRadioRole extends HTMLElement {
            connectedCallback() {
              const sr = this.attachShadow({ mode: 'open' });
              sr.innerHTML = `<div role="radio" aria-checked="false" tabindex="0"></div><slot></slot>`;
              const r = sr.querySelector('[role="radio"]');
              r.addEventListener('click', () => {
                this.parentElement.querySelectorAll('spl-radio-role').forEach(el => {
                  el.shadowRoot.querySelector('[role="radio"]').setAttribute('aria-checked', 'false');
                });
                r.setAttribute('aria-checked', 'true');
              });
            }
          }
          customElements.define('spl-input', SplInput);
          customElements.define('spl-radio-group', SplRadioGroup);
          customElements.define('spl-radio-native', SplRadioNative);
          customElements.define('spl-radio-role', SplRadioRole);

          document.getElementById('next-step-btn').addEventListener('click', () => {
            document.getElementById('wizard-root').innerHTML = `
              <form id="step2">
                <div class="screening-q" id="q1">
                  <div class="q-text">Are you currently legally eligible to work in the United States of America? *</div>
                  <spl-radio-group>
                    <spl-radio-native>Yes</spl-radio-native>
                    <spl-radio-native>No</spl-radio-native>
                  </spl-radio-group>
                </div>
                <div class="screening-q" id="q2">
                  <div class="q-text">Are you eligible to work at M3USA without required sponsorship now or in the future? *</div>
                  <spl-radio-group>
                    <spl-radio-role>Yes</spl-radio-role>
                    <spl-radio-role>No</spl-radio-role>
                  </spl-radio-group>
                </div>
                <div class="screening-q" id="q3">
                  <p>Are you able to independently perform the essential functions of the position for which you are applying? *</p>
                  <label><input type="radio" name="q3_ef" value="yes" /> Yes</label>
                  <label><input type="radio" name="q3_ef" value="no" /> No</label>
                </div>
              </form>
            `;
          });
        </script></body></html>"""

        with sync_playwright() as p:
            b = p.chromium.launch(headless=True)
            page = b.new_page()
            page.set_content(step_html)

            def handle_msg(msg):
                t = msg.get("type")
                if t == "GET_ACTIVE_AUTOFILL":
                    return {"ok": True, "data": {"matched": True, "job": job, "queue": {"is_speed_run": False, "index": 0, "total": 1}}}
                if t == "ANSWER_FIELDS":
                    out = []
                    for f in msg["payload"]["fields"]:
                        qa = answer_single_question(
                            question_text=f["label"],
                            job_data=job,
                            profile_data=profile,
                            candidate_skills=["Python"],
                            options=f.get("options"),
                            field_type=f.get("field_type", "text"),
                            required=f.get("required", False),
                        )
                        out.append({
                            "id": f["id"],
                            "label": f["label"],
                            "answer": qa["answer"],
                            "confidence": qa["confidence"],
                            "category": qa["category"],
                        })
                    return {"ok": True, "data": {"answers": out, "bot_traps": []}}
                return {"ok": False}

            page.expose_function("__pySendMsg", handle_msg)
            page.evaluate("""() => {
                window.chrome = {
                    runtime: {
                        lastError: null,
                        sendMessage: (msg, cb) => { window.__pySendMsg(msg).then(cb); },
                        onMessage: { addListener: () => {} },
                    }
                };
            }""")
            page.add_script_tag(content=content_js)
            page.wait_for_timeout(1200)
            # Advance to Step 2 WITHOUT changing URL
            page.click("#next-step-btn")
            page.wait_for_timeout(2400)
            res = page.evaluate("""() => {
                const q1Yes = document.querySelector('#q1 spl-radio-native').shadowRoot.querySelector('input').checked;
                const q2Yes = document.querySelector('#q2 spl-radio-role').shadowRoot.querySelector('[role="radio"]').getAttribute('aria-checked') === 'true';
                const q3Yes = document.querySelector('#q3 input[value="yes"]').checked;
                return { q1Yes, q2Yes, q3Yes };
            }""")
            b.close()
            return res

    step2 = await asyncio.to_thread(_run_multistep_screening_radios)
    assert step2 == {"q1Yes": True, "q2Yes": True, "q3Yes": True}

    # 4. Also verify tricky work-auth & essential-functions phrasings never invert
    qa_without = answer_single_question(
        "Are you able to work without sponsorship now or in the future?",
        job, profile, ["Python"], options=["Yes", "No"], field_type="radio",
    )
    assert qa_without["answer"] == "Yes"
    qa_accomm = answer_single_question(
        "Can you perform the essential functions of this job with or without reasonable accommodation?",
        job, profile, ["Python"], options=["Yes", "No"], field_type="radio",
    )
    assert qa_accomm["answer"] == "Yes"
    qa_need_accomm = answer_single_question(
        "Do you require any reasonable accommodation during the interview process?",
        job, profile, ["Python"], options=["Yes", "No"], field_type="radio",
    )
    assert qa_need_accomm["answer"] == "No"


@pytest.mark.asyncio
async def test_ukg_ultipro_profile_fields_and_no_combobox_overlay_flicker():
    import asyncio
    from pathlib import Path
    from playwright.sync_api import sync_playwright
    from app.services.question_answerer import answer_single_question, _extract_current_company

    # 1. Profile API persists street_address, zip_code, current_company
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        put_res = await ac.put(
            "/api/profile",
            json={
                "full_name": "Justin Kilpatrick",
                "email": "jkilpatrick50@gmail.com",
                "phone": "781-879-4389",
                "location": "Boston, Massachusetts (Remote)",
                "street_address": "123 Beacon St",
                "zip_code": "02108",
                "current_company": "Hyperice",
                "title": "Software Engineer",
            },
        )
        assert put_res.status_code == 200
        saved = put_res.json()
        assert saved["street_address"] == "123 Beacon St"
        assert saved["zip_code"] == "02108"
        assert saved["current_company"] == "Hyperice"

    # 2. _extract_current_company parses Company | City, ST instead of job title
    resume_prof = {
        "master_resume_text": (
            "PROFESSIONAL EXPERIENCE\n"
            "Hyperice | Watertown, MA\n"
            "Product Service Technician | November 2025 – Present\n"
        )
    }
    assert _extract_current_company(resume_prof) == "Hyperice"

    # 3. UKG / UltiPro label variants (including leading '*' markers and optional personal fields)
    job = {"title": "AI Product Engineer", "company": "Milliman"}
    assert answer_single_question("* Address 1", job, saved, ["Python"])["answer"] == "123 Beacon St"
    assert answer_single_question("Address 1 Required", job, saved, ["Python"])["answer"] == "123 Beacon St"
    assert answer_single_question("Address 2 (Optional)", job, saved, ["Python"], required=False)["confidence"] == "high"
    assert answer_single_question("Address 2 (Optional)", job, saved, ["Python"], required=False)["answer"] == ""
    assert answer_single_question("* City", job, saved, ["Python"])["answer"] == "Boston"
    assert answer_single_question("Zip", job, saved, ["Python"])["answer"] == "02108"
    assert answer_single_question("* Zip / Postal Code", job, saved, ["Python"])["answer"] == "02108"
    assert answer_single_question("Zip / Postal Code Required", job, saved, ["Python"])["answer"] == "02108"
    assert answer_single_question("Company Required", job, saved, ["Python"])["answer"] == "Hyperice"
    assert answer_single_question("Employer Name", job, saved, ["Python"])["answer"] == "Hyperice"
    assert answer_single_question("Job Title Required", job, saved, ["Python"])["answer"] == "Software Engineer"
    assert answer_single_question("Phone Device Type", job, saved, ["Python"], options=["Mobile", "Home", "Work"])["answer"] == "Mobile"
    # Optional fields that should stay cleanly blank (no amber warning, no duplicate phone)
    for opt_lbl in ("Middle", "Suffix", "Suffix Choose...", "Former Name", "Secondary Phone"):
        opt_res = answer_single_question(opt_lbl, job, saved, ["Python"], required=False)
        assert opt_res["confidence"] == "high" and opt_res["answer"] == "", f"Unexpected for {opt_lbl}: {opt_res}"

    # 4. Real Chromium check: extension NEVER clicks header language picker or unknown comboboxes (no overlay flicker!)
    content_js = (Path(__file__).resolve().parents[2] / "extension" / "content.js").read_text(encoding="utf-8")

    def _run_no_flicker_check():
        html = """<!doctype html><html><body>
        <header>
          <button id="lang-picker" aria-haspopup="listbox" aria-label="Language">U.S. English</button>
        </header>
        <main>
          <form>
            <div>
              <label for="unknown-cb">Internal Milliman Cost Center Code *</label>
              <button id="unknown-cb" type="button" role="combobox">Select...</button>
            </div>
            <div>
              <label for="phone-type-cb">Phone Device Type *</label>
              <button id="phone-type-cb" type="button" role="combobox" aria-controls="pt-menu">Select...</button>
              <ul id="pt-menu" role="listbox" style="display:none">
                <li role="option">Home</li>
                <li role="option">Mobile</li>
              </ul>
            </div>
          </form>
        </main>
        <script>
          window.__clicks = [];
          document.getElementById('lang-picker').addEventListener('click', () => window.__clicks.push('lang'));
          document.getElementById('unknown-cb').addEventListener('click', () => window.__clicks.push('unknown'));
          document.getElementById('phone-type-cb').addEventListener('click', () => {
            window.__clicks.push('phone-type');
            document.getElementById('pt-menu').style.display = 'block';
          });
          document.querySelectorAll('#pt-menu [role="option"]').forEach(li => {
            li.addEventListener('click', () => {
              document.getElementById('phone-type-cb').innerText = li.innerText;
              document.getElementById('pt-menu').style.display = 'none';
            });
          });
        </script></body></html>"""

        with sync_playwright() as p:
            b = p.chromium.launch(headless=True)
            page = b.new_page()
            page.set_content(html)

            def handle_msg(msg):
                if msg["type"] == "GET_ACTIVE_AUTOFILL":
                    return {"ok": True, "data": {"matched": True, "job": job, "queue": {"is_speed_run": False, "index": 0, "total": 1}}}
                if msg["type"] == "ANSWER_FIELDS":
                    out = []
                    for f in msg["payload"]["fields"]:
                        qa = answer_single_question(
                            f["label"], job, saved, ["Python"],
                            options=f.get("options"), field_type=f.get("field_type", "text"), required=f.get("required", False),
                        )
                        out.append({"id": f["id"], "label": f["label"], "answer": qa["answer"], "confidence": qa["confidence"], "category": qa["category"]})
                    return {"ok": True, "data": {"answers": out, "bot_traps": []}}
                return {"ok": False}

            page.expose_function("__pySendMsg", handle_msg)
            page.evaluate("""() => {
                window.chrome = { runtime: { lastError: null, sendMessage: (m, cb) => window.__pySendMsg(m).then(cb), onMessage: { addListener: () => {} } } };
            }""")
            page.add_script_tag(content=content_js)
            page.wait_for_timeout(1600)
            res = page.evaluate("""() => ({
                clicks: window.__clicks,
                phoneTypeText: document.getElementById('phone-type-cb').innerText,
                unknownOutlined: Boolean(document.getElementById('unknown-cb').style.outline),
            })""")
            b.close()
            return res

    res = await asyncio.to_thread(_run_no_flicker_check)
    assert "lang" not in res["clicks"]
    assert "unknown" not in res["clicks"]
    assert "phone-type" in res["clicks"]
    assert res["phoneTypeText"] == "Mobile"
    assert res["unknownOutlined"] is True


@pytest.mark.asyncio
async def test_ziprecruiter_sponsorship_explanatory_text_and_react_controlled_inputs():
    import asyncio
    from pathlib import Path
    from playwright.sync_api import sync_playwright
    from app.services.question_answerer import answer_single_question

    profile = {
        "full_name": "Justin Kilpatrick",
        "email": "jkilpatrick50@gmail.com",
        "phone": "781-879-4389",
        "location": "Boston, Massachusetts (Remote)",
        "work_authorization": "Authorized to work in the US without sponsorship",
        "title": "Software Engineer",
    }
    job = {"title": "Software Engineer", "company": "Acme"}

    # 1. Exact sponsorship paragraph from ZipRecruiter/Greenhouse screenshot mentioning "current work authorization" MUST answer "No"!
    spon_q = (
        '"Will you in the future require sponsorship" means that even if you currently have U.S. employment '
        'authorization (for example, through F-1 Optional Practical Training (OPT) or Curricular Practical '
        'Training (CPT)), you will require sponsorship in the future to continue working when your current '
        'work authorization ends. *'
    )
    res_spon = answer_single_question(spon_q, job, profile, ["Python"], options=["Select...", "Yes", "No"], field_type="select")
    assert res_spon["answer"] == "No"

    # Positive work-auth & without-sponsorship questions MUST still answer "Yes"
    assert answer_single_question(
        "Are you legally authorized to work in the United States without the need for visa sponsorship?",
        job, profile, ["Python"], options=["Yes", "No"], field_type="select",
    )["answer"] == "Yes"
    assert answer_single_question(
        "Do you have unrestricted work authorization in the U.S. (i.e., you will not require sponsorship)?",
        job, profile, ["Python"], options=["Yes", "No"], field_type="select",
    )["answer"] == "Yes"
    assert answer_single_question(
        "Are you currently legally authorized to work in the United States?",
        job, profile, ["Python"], options=["Yes", "No"], field_type="select",
    )["answer"] == "Yes"

    # 2. Real Chromium test: controlled inputs/selects with value-tracker + focusout/blur validation unlock Continue button
    content_js = (Path(__file__).resolve().parents[2] / "extension" / "content.js").read_text(encoding="utf-8")

    def _run_controlled_form():
        html = f"""<!doctype html><html><body>
        <form id="zr-form">
          <label for="fn">First Name *</label><input id="fn" type="text" required />
          <label for="ln">Last Name *</label><input id="ln" type="text" required />
          <label for="em">Email *</label><input id="em" type="email" required />
          <label for="ph">Phone *</label><input id="ph" type="tel" required />
          <label for="sp">{spon_q}</label>
          <select id="sp" required>
            <option value="">Select...</option>
            <option value="Yes">Yes</option>
            <option value="No">No</option>
          </select>
          <button id="continue-btn" type="submit" disabled>Continue</button>
        </form>
        <script>
          // Simulate React 18 controlled value tracker + Formik onChange/onBlur validation
          window.__formState = {{ fn: '', ln: '', em: '', ph: '', sp: '' }};
          window.__blurred = {{}};
          function bindControlled(id, isSelect) {{
            const el = document.getElementById(id);
            let tracked = el.value;
            const proto = isSelect ? HTMLSelectElement.prototype : HTMLInputElement.prototype;
            const desc = Object.getOwnPropertyDescriptor(proto, 'value');
            Object.defineProperty(el, 'value', {{
              get() {{ return desc.get.call(this); }},
              set(v) {{ tracked = String(v); desc.set.call(this, v); }},
              configurable: true,
            }});
            const sync = () => {{
              const cur = desc.get.call(el);
              if (cur !== tracked) {{
                tracked = cur;
                window.__formState[id] = cur;
              }}
              checkValid();
            }};
            el.addEventListener('input', sync);
            el.addEventListener('change', sync);
            el.addEventListener('focusout', () => {{ window.__blurred[id] = true; checkValid(); }});
          }}
          function checkValid() {{
            const s = window.__formState;
            const b = window.__blurred;
            const ok = Boolean(s.fn && s.ln && s.em && s.ph && s.sp && b.fn && b.em && b.sp);
            document.getElementById('continue-btn').disabled = !ok;
          }}
          ['fn', 'ln', 'em', 'ph'].forEach(id => bindControlled(id, false));
          bindControlled('sp', true);
        </script></body></html>"""

        with sync_playwright() as p:
            b = p.chromium.launch(headless=True)
            page = b.new_page()
            page.set_content(html)

            def handle_msg(msg):
                if msg["type"] == "GET_ACTIVE_AUTOFILL":
                    return {"ok": True, "data": {"matched": True, "job": job, "queue": {"is_speed_run": False, "index": 0, "total": 1}}}
                if msg["type"] == "ANSWER_FIELDS":
                    out = []
                    for f in msg["payload"]["fields"]:
                        qa = answer_single_question(
                            f["label"], job, profile, ["Python"],
                            options=f.get("options"), field_type=f.get("field_type", "text"), required=f.get("required", False),
                        )
                        out.append({"id": f["id"], "label": f["label"], "answer": qa["answer"], "confidence": qa["confidence"], "category": qa["category"]})
                    return {"ok": True, "data": {"answers": out, "bot_traps": []}}
                return {"ok": False}

            page.expose_function("__pySendMsg", handle_msg)
            page.evaluate("""() => {
                window.chrome = { runtime: { lastError: null, sendMessage: (m, cb) => window.__pySendMsg(m).then(cb), onMessage: { addListener: () => {} } } };
            }""")
            page.add_script_tag(content=content_js)
            page.wait_for_timeout(1600)
            res = page.evaluate("""() => ({
                state: window.__formState,
                blurred: window.__blurred,
                continueDisabled: document.getElementById('continue-btn').disabled,
            })""")
            b.close()
            return res

    out = await asyncio.to_thread(_run_controlled_form)
    assert out["state"] == {
        "fn": "Justin",
        "ln": "Kilpatrick",
        "em": "jkilpatrick50@gmail.com",
        "ph": "781-879-4389",
        "sp": "No",
    }
    assert out["continueDisabled"] is False






