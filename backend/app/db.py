"""Database engine, sessions and settings helpers."""
import json
import os
from pathlib import Path

from sqlalchemy import create_engine, event
from sqlalchemy.orm import Session, sessionmaker

from .models import Base, Setting

DB_PATH = Path(os.environ.get("OMS360_DB", Path(__file__).resolve().parent.parent / "data" / "oms360.sqlite"))
DB_PATH.parent.mkdir(parents=True, exist_ok=True)
engine = create_engine(f"sqlite:///{DB_PATH}", connect_args={"check_same_thread": False, "timeout": 30})


@event.listens_for(engine, "connect")
def _sqlite_pragmas(conn, _):
    cur = conn.cursor()
    cur.execute("PRAGMA journal_mode=WAL")  # readers don't block the background connector
    cur.execute("PRAGMA foreign_keys=ON")
    cur.close()


SessionLocal = sessionmaker(engine, expire_on_commit=False)


def get_session():
    with SessionLocal() as s:
        yield s


def _upgrade_chat() -> None:
    """Databases created before conversations existed: add the new chat columns and file old messages under one conversation per user."""
    with engine.begin() as c:
        cols = {r[1] for r in c.exec_driver_sql("PRAGMA table_info(chat_messages)")}
        if "conversation_id" not in cols:
            c.exec_driver_sql("ALTER TABLE chat_messages ADD COLUMN conversation_id INTEGER REFERENCES chat_conversations(id) ON DELETE CASCADE")
            c.exec_driver_sql("CREATE INDEX IF NOT EXISTS ix_chat_messages_conversation_id ON chat_messages (conversation_id)")
        if "saved" not in cols:
            c.exec_driver_sql("ALTER TABLE chat_messages ADD COLUMN saved BOOLEAN NOT NULL DEFAULT 0")
        for (user_id,) in c.exec_driver_sql("SELECT DISTINCT user_id FROM chat_messages WHERE conversation_id IS NULL").all():
            first = c.exec_driver_sql("SELECT payload, created_at FROM chat_messages WHERE user_id = ? AND conversation_id IS NULL AND role = 'user' "
                                      "ORDER BY id LIMIT 1", (user_id,)).first()
            title = (json.loads(first[0]).get("text") or "Conversation")[:120] if first else "Conversation"
            stamp = c.exec_driver_sql("SELECT MAX(created_at) FROM chat_messages WHERE user_id = ? AND conversation_id IS NULL", (user_id,)).scalar()
            conv = c.exec_driver_sql("INSERT INTO chat_conversations (user_id, title, created_at, updated_at) VALUES (?, ?, ?, ?)",
                                     (user_id, title, first[1] if first else stamp, stamp)).lastrowid
            c.exec_driver_sql("UPDATE chat_messages SET conversation_id = ? WHERE user_id = ? AND conversation_id IS NULL", (conv, user_id))


def _add_columns(table: str, columns: dict[str, str]) -> None:
    """Databases created before a column existed: add it (create_all only creates missing tables)."""
    with engine.begin() as c:
        have = {r[1] for r in c.exec_driver_sql(f"PRAGMA table_info({table})")}
        for name, ddl in columns.items():
            if name not in have:
                c.exec_driver_sql(f"ALTER TABLE {table} ADD COLUMN {name} {ddl}")


def init_db() -> None:
    from .seed import ensure_demo_activity, ensure_forecast_demo, ensure_network_hierarchy, ensure_rain_demo, seed_if_empty
    Base.metadata.create_all(engine)
    _upgrade_chat()
    _add_columns("storm_events", {"rain_total_in": "FLOAT", "rain_rate_in_hr": "FLOAT", "duration_h": "FLOAT", "soil_saturation": "FLOAT"})
    _add_columns("zones", {"region_id": "VARCHAR(20) REFERENCES regions(id)"})
    _add_columns("feeders", {"substation_id": "VARCHAR(20) REFERENCES substations(id)", "route": "JSON", "route_source": "VARCHAR(12)"})
    with SessionLocal() as s:
        seed_if_empty(s)
        ensure_network_hierarchy(s)
        ensure_demo_admin(s)
        ensure_demo_activity(s)
        ensure_rain_demo(s)
        ensure_forecast_demo(s)


DEMO_ADMINS = [
    ("steve@powerconnect.ai", "admin", "Steve Dawson", "PowerConnect.AI"),
    ("admin@gmail.com", "admin@123", "Admin", "Administrator"),
]
DEMO_ADMIN_EMAILS = {email for email, *_ in DEMO_ADMINS}


def ensure_demo_admin(s: Session) -> None:
    """Demo admin logins (DEMO_ADMINS) — added to new and existing databases, and healed if someone
    deactivated, demoted or re-passworded them, so the shared demo logins always work."""
    from sqlalchemy import select
    from .auth import hash_password, verify_password
    from .models import User
    for email, password, name, title in DEMO_ADMINS:
        u = s.scalars(select(User).where(User.email == email)).first()
        if not u:
            s.add(User(email=email, name=name, title=title, role="admin", password_hash=hash_password(password)))
            continue
        u.active, u.role = True, "admin"
        if not verify_password(password, u.password_hash):
            u.password_hash = hash_password(password)
    s.commit()


def get_setting(s: Session, key: str, default: str = "") -> str:
    row = s.get(Setting, key)
    return row.value if row else default


def set_setting(s: Session, key: str, value: str) -> None:
    row = s.get(Setting, key)
    if row:
        row.value = value
    else:
        s.add(Setting(key=key, value=value))
