import os
from sqlalchemy import event
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession, async_sessionmaker
from sqlalchemy.orm import declarative_base

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DB_PATH = os.path.join(BASE_DIR, "jobs.db")
DATABASE_URL = f"sqlite+aiosqlite:///{DB_PATH}"

engine = create_async_engine(
    DATABASE_URL,
    echo=False,
    connect_args={"check_same_thread": False, "timeout": 30}
)

@event.listens_for(engine.sync_engine, "connect")
def set_sqlite_pragma(dbapi_connection, connection_record):
    cursor = dbapi_connection.cursor()
    cursor.execute("PRAGMA journal_mode=WAL")
    cursor.execute("PRAGMA synchronous=NORMAL")
    cursor.execute("PRAGMA busy_timeout=30000")
    cursor.close()

AsyncSessionLocal = async_sessionmaker(
    bind=engine,
    class_=AsyncSession,
    expire_on_commit=False,
    autoflush=False
)

Base = declarative_base()

async def get_db():
    async with AsyncSessionLocal() as session:
        try:
            yield session
        finally:
            await session.close()

async def init_db():
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
        # Migrate columns for jobs table if not present
        from sqlalchemy import text
        res = await conn.execute(text("PRAGMA table_info(jobs)"))
        existing_cols = {row[1] for row in res.fetchall()}
        if "is_expired" not in existing_cols:
            await conn.execute(text("ALTER TABLE jobs ADD COLUMN is_expired BOOLEAN DEFAULT 0"))
        if "expired_at" not in existing_cols:
            await conn.execute(text("ALTER TABLE jobs ADD COLUMN expired_at DATETIME"))
        if "expired_reason" not in existing_cols:
            await conn.execute(text("ALTER TABLE jobs ADD COLUMN expired_reason VARCHAR(255)"))
        if "role_track" not in existing_cols:
            await conn.execute(text("ALTER TABLE jobs ADD COLUMN role_track VARCHAR(50)"))
        if "role_level" not in existing_cols:
            await conn.execute(text("ALTER TABLE jobs ADD COLUMN role_level VARCHAR(50)"))
        if "role_discipline" not in existing_cols:
            await conn.execute(text("ALTER TABLE jobs ADD COLUMN role_discipline VARCHAR(50)"))
        if "autopilot_status" not in existing_cols:
            await conn.execute(text("ALTER TABLE jobs ADD COLUMN autopilot_status VARCHAR(50)"))
        if "autopilot_reason" not in existing_cols:
            await conn.execute(text("ALTER TABLE jobs ADD COLUMN autopilot_reason VARCHAR(500)"))
        if "answers_json" not in existing_cols:
            await conn.execute(text("ALTER TABLE jobs ADD COLUMN answers_json TEXT"))
        if "bot_traps_json" not in existing_cols:
            await conn.execute(text("ALTER TABLE jobs ADD COLUMN bot_traps_json TEXT"))
        # Migrate columns for autopilot_configs table if not present
        ac_res = await conn.execute(text("PRAGMA table_info(autopilot_configs)"))
        ac_cols = {row[1] for row in ac_res.fetchall()}
        if "imap_server" not in ac_cols:
            await conn.execute(text("ALTER TABLE autopilot_configs ADD COLUMN imap_server VARCHAR(255) DEFAULT 'imap.gmail.com'"))
        if "imap_email" not in ac_cols:
            await conn.execute(text("ALTER TABLE autopilot_configs ADD COLUMN imap_email VARCHAR(255) DEFAULT ''"))
        if "imap_password" not in ac_cols:
            await conn.execute(text("ALTER TABLE autopilot_configs ADD COLUMN imap_password VARCHAR(255) DEFAULT ''"))
        # Migrate any legacy 'WISHLIST' status jobs to 'TO_APPLY'
        await conn.execute(text("UPDATE jobs SET status = 'TO_APPLY' WHERE status = 'WISHLIST'"))
