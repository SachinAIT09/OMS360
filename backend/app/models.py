"""OMS360 domain model (SQLAlchemy 2.0)."""
from datetime import datetime, timezone

from sqlalchemy import JSON, Boolean, DateTime, Float, ForeignKey, Integer, String, Text
from sqlalchemy.types import TypeDecorator
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


class Base(DeclarativeBase):
    pass


class UTCDateTime(TypeDecorator):
    """Stores UTC; always returns timezone-aware datetimes (SQLite drops tzinfo)."""
    impl = DateTime
    cache_ok = True

    def process_bind_param(self, value, dialect):
        if value is not None and value.tzinfo is not None:
            value = value.astimezone(timezone.utc).replace(tzinfo=None)
        return value

    def process_result_value(self, value, dialect):
        return value.replace(tzinfo=timezone.utc) if value is not None else None


TS = UTCDateTime()


# ------------------------------------------------------------------ people
class User(Base):
    __tablename__ = "users"
    id: Mapped[int] = mapped_column(primary_key=True)
    email: Mapped[str] = mapped_column(String(120), unique=True, index=True)
    name: Mapped[str] = mapped_column(String(80))
    title: Mapped[str] = mapped_column(String(80), default="")
    role: Mapped[str] = mapped_column(String(20))  # executive | ops_manager | dispatcher | comms | admin
    password_hash: Mapped[str] = mapped_column(String(200))
    active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(TS, default=utcnow)
    last_login_at: Mapped[datetime | None] = mapped_column(TS, nullable=True)


class AuthToken(Base):
    __tablename__ = "auth_tokens"
    token: Mapped[str] = mapped_column(String(64), primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"))
    created_at: Mapped[datetime] = mapped_column(TS, default=utcnow)
    expires_at: Mapped[datetime] = mapped_column(TS)
    user: Mapped[User] = relationship()


# ------------------------------------------------------------------ network & assets
class Zone(Base):
    __tablename__ = "zones"
    id: Mapped[str] = mapped_column(String(10), primary_key=True)
    code: Mapped[str] = mapped_column(String(6))
    name: Mapped[str] = mapped_column(String(80))
    short: Mapped[str] = mapped_column(String(40))
    lat: Mapped[float] = mapped_column(Float)
    lng: Mapped[float] = mapped_column(Float)
    customers: Mapped[int] = mapped_column(Integer)
    water_customers: Mapped[int] = mapped_column(Integer)
    vulnerability: Mapped[float] = mapped_column(Float)
    coastal: Mapped[bool] = mapped_column(Boolean, default=False)
    critical: Mapped[bool] = mapped_column(Boolean, default=False)
    medical: Mapped[bool] = mapped_column(Boolean, default=False)


class Feeder(Base):
    __tablename__ = "feeders"
    id: Mapped[str] = mapped_column(String(20), primary_key=True)  # FDR-TPA-01
    zone_id: Mapped[str] = mapped_column(ForeignKey("zones.id"))
    customers: Mapped[int] = mapped_column(Integer)
    overhead_pct: Mapped[int] = mapped_column(Integer)
    last_trimmed: Mapped[int] = mapped_column(Integer)  # year of last vegetation cycle


class Facility(Base):
    __tablename__ = "facilities"
    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(80))
    kind: Mapped[str] = mapped_column(String(2))  # H W E S M
    type: Mapped[str] = mapped_column(String(30))
    lat: Mapped[float] = mapped_column(Float)
    lng: Mapped[float] = mapped_column(Float)
    zone_id: Mapped[str] = mapped_column(ForeignKey("zones.id"))
    feeder_id: Mapped[str] = mapped_column(String(20))
    backup: Mapped[str] = mapped_column(String(60))


class StagingYard(Base):
    __tablename__ = "staging_yards"
    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(80))
    lat: Mapped[float] = mapped_column(Float)
    lng: Mapped[float] = mapped_column(Float)
    capacity: Mapped[int] = mapped_column(Integer)
    active: Mapped[bool] = mapped_column(Boolean, default=False)


# ------------------------------------------------------------------ storms
class StormEvent(Base):
    __tablename__ = "storm_events"
    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(80))
    kind: Mapped[str] = mapped_column(String(30), default="Hurricane")
    source: Mapped[str] = mapped_column(String(10), default="manual")  # manual | nhc
    nhc_id: Mapped[str | None] = mapped_column(String(20), nullable=True)
    status: Mapped[str] = mapped_column(String(12), default="monitoring")  # monitoring|preparing|active|restoring|closed
    category: Mapped[int] = mapped_column(Integer, default=1)
    max_wind_mph: Mapped[int] = mapped_column(Integer, default=75)
    pressure_mb: Mapped[int] = mapped_column(Integer, default=990)
    lat: Mapped[float] = mapped_column(Float, default=25.0)
    lng: Mapped[float] = mapped_column(Float, default=-85.0)
    movement: Mapped[str] = mapped_column(String(40), default="")
    landfall_at: Mapped[datetime | None] = mapped_column(TS, nullable=True)
    track: Mapped[list] = mapped_column(JSON, default=list)  # [{lat,lng,at,observed}]
    notes: Mapped[str] = mapped_column(Text, default="")
    created_by: Mapped[int | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    created_at: Mapped[datetime] = mapped_column(TS, default=utcnow)
    activated_at: Mapped[datetime | None] = mapped_column(TS, nullable=True)
    restoring_at: Mapped[datetime | None] = mapped_column(TS, nullable=True)
    closed_at: Mapped[datetime | None] = mapped_column(TS, nullable=True)
    updated_at: Mapped[datetime] = mapped_column(TS, default=utcnow, onupdate=utcnow)


class PredictionRun(Base):
    __tablename__ = "prediction_runs"
    id: Mapped[int] = mapped_column(primary_key=True)
    event_id: Mapped[int] = mapped_column(ForeignKey("storm_events.id", ondelete="CASCADE"), index=True)
    category: Mapped[int] = mapped_column(Integer)
    result: Mapped[dict] = mapped_column(JSON)
    created_by: Mapped[int | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    created_at: Mapped[datetime] = mapped_column(TS, default=utcnow)


# ------------------------------------------------------------------ field operations
class Crew(Base):
    __tablename__ = "crews"
    id: Mapped[int] = mapped_column(primary_key=True)
    code: Mapped[str] = mapped_column(String(20), unique=True)
    kind: Mapped[str] = mapped_column(String(12))  # line | tree | assessment
    company: Mapped[str] = mapped_column(String(60))
    source: Mapped[str] = mapped_column(String(12), default="internal")  # internal | mutual_aid
    size: Mapped[int] = mapped_column(Integer, default=4)
    status: Mapped[str] = mapped_column(String(12), default="available")  # available|staged|assigned|working|off_shift|released
    lead: Mapped[str] = mapped_column(String(60), default="")
    lat: Mapped[float] = mapped_column(Float)
    lng: Mapped[float] = mapped_column(Float)
    yard_id: Mapped[int | None] = mapped_column(ForeignKey("staging_yards.id"), nullable=True)
    mutual_aid_id: Mapped[int | None] = mapped_column(ForeignKey("mutual_aid_requests.id"), nullable=True)
    updated_at: Mapped[datetime] = mapped_column(TS, default=utcnow, onupdate=utcnow)


class Outage(Base):
    __tablename__ = "outages"
    id: Mapped[int] = mapped_column(primary_key=True)
    number: Mapped[str] = mapped_column(String(16), unique=True, index=True)
    event_id: Mapped[int | None] = mapped_column(ForeignKey("storm_events.id"), nullable=True, index=True)
    zone_id: Mapped[str] = mapped_column(ForeignKey("zones.id"), index=True)
    feeder_id: Mapped[str] = mapped_column(String(20))
    device: Mapped[str] = mapped_column(String(40), default="")  # e.g. Transformer T-4471
    cause: Mapped[str] = mapped_column(String(20), default="unknown")  # wind|tree|surge|equipment|flooding|unknown
    damage: Mapped[str] = mapped_column(String(20), default="unknown")  # pole|conductor|transformer|service|none|unknown
    customers: Mapped[int] = mapped_column(Integer)
    priority: Mapped[str] = mapped_column(String(10), default="normal")  # critical | high | normal
    facility_id: Mapped[int | None] = mapped_column(ForeignKey("facilities.id"), nullable=True)
    status: Mapped[str] = mapped_column(String(12), default="reported", index=True)  # reported|assessed|assigned|in_progress|restored|cancelled
    source: Mapped[str] = mapped_column(String(12), default="AMI")  # AMI | customer | field | SCADA
    lat: Mapped[float] = mapped_column(Float)
    lng: Mapped[float] = mapped_column(Float)
    crew_id: Mapped[int | None] = mapped_column(ForeignKey("crews.id"), nullable=True)
    reported_at: Mapped[datetime] = mapped_column(TS, default=utcnow)
    assigned_at: Mapped[datetime | None] = mapped_column(TS, nullable=True)
    started_at: Mapped[datetime | None] = mapped_column(TS, nullable=True)
    restored_at: Mapped[datetime | None] = mapped_column(TS, nullable=True)
    etr_at: Mapped[datetime | None] = mapped_column(TS, nullable=True)  # committed ETR (set at assignment / override)
    etr_override: Mapped[bool] = mapped_column(Boolean, default=False)
    notes: Mapped[str] = mapped_column(Text, default="")
    crew: Mapped[Crew | None] = relationship()
    zone: Mapped[Zone] = relationship()
    history: Mapped[list["OutageEvent"]] = relationship(order_by="OutageEvent.id", cascade="all, delete-orphan")


class OutageEvent(Base):
    __tablename__ = "outage_events"
    id: Mapped[int] = mapped_column(primary_key=True)
    outage_id: Mapped[int] = mapped_column(ForeignKey("outages.id", ondelete="CASCADE"), index=True)
    at: Mapped[datetime] = mapped_column(TS, default=utcnow)
    kind: Mapped[str] = mapped_column(String(20))  # created|status|assigned|note|etr
    text: Mapped[str] = mapped_column(Text)
    user_name: Mapped[str] = mapped_column(String(80), default="System")


class MutualAidRequest(Base):
    __tablename__ = "mutual_aid_requests"
    id: Mapped[int] = mapped_column(primary_key=True)
    event_id: Mapped[int] = mapped_column(ForeignKey("storm_events.id"), index=True)
    company: Mapped[str] = mapped_column(String(80))
    origin: Mapped[str] = mapped_column(String(40))
    kind: Mapped[str] = mapped_column(String(12), default="line")
    workers: Mapped[int] = mapped_column(Integer)
    status: Mapped[str] = mapped_column(String(12), default="requested")  # requested|confirmed|en_route|arrived|released|cancelled
    eta: Mapped[datetime | None] = mapped_column(TS, nullable=True)
    cost_per_worker_day: Mapped[int] = mapped_column(Integer, default=4200)
    requested_by: Mapped[str] = mapped_column(String(80), default="")
    requested_at: Mapped[datetime] = mapped_column(TS, default=utcnow)
    arrived_at: Mapped[datetime | None] = mapped_column(TS, nullable=True)
    released_at: Mapped[datetime | None] = mapped_column(TS, nullable=True)


class Task(Base):
    """Logistics / preparation tasks created from recommendations or by hand."""
    __tablename__ = "tasks"
    id: Mapped[int] = mapped_column(primary_key=True)
    event_id: Mapped[int | None] = mapped_column(ForeignKey("storm_events.id"), nullable=True, index=True)
    title: Mapped[str] = mapped_column(String(200))
    owner_role: Mapped[str] = mapped_column(String(20), default="ops_manager")
    status: Mapped[str] = mapped_column(String(12), default="open")  # open | done
    due_at: Mapped[datetime | None] = mapped_column(TS, nullable=True)
    created_at: Mapped[datetime] = mapped_column(TS, default=utcnow)
    done_at: Mapped[datetime | None] = mapped_column(TS, nullable=True)


# ------------------------------------------------------------------ intelligence
class Recommendation(Base):
    __tablename__ = "recommendations"
    id: Mapped[int] = mapped_column(primary_key=True)
    event_id: Mapped[int] = mapped_column(ForeignKey("storm_events.id", ondelete="CASCADE"), index=True)
    key: Mapped[str] = mapped_column(String(30))
    priority: Mapped[str] = mapped_column(String(10))  # Critical | High | Medium
    title: Mapped[str] = mapped_column(String(200))
    detail: Mapped[str] = mapped_column(Text)
    impact: Mapped[str] = mapped_column(String(200))
    why: Mapped[str] = mapped_column(Text)
    status: Mapped[str] = mapped_column(String(10), default="open")  # open | approved | dismissed
    created_at: Mapped[datetime] = mapped_column(TS, default=utcnow)
    decided_by: Mapped[str | None] = mapped_column(String(80), nullable=True)
    decided_at: Mapped[datetime | None] = mapped_column(TS, nullable=True)
    outcome: Mapped[str] = mapped_column(Text, default="")


# ------------------------------------------------------------------ customer communications
class Message(Base):
    __tablename__ = "messages"
    id: Mapped[int] = mapped_column(primary_key=True)
    event_id: Mapped[int | None] = mapped_column(ForeignKey("storm_events.id"), nullable=True, index=True)
    channel: Mapped[str] = mapped_column(String(10))  # x | facebook | sms | email | ivr | website
    audience: Mapped[str] = mapped_column(String(60))
    subject: Mapped[str] = mapped_column(String(200), default="")
    body: Mapped[str] = mapped_column(Text)
    status: Mapped[str] = mapped_column(String(12), default="draft")  # draft|pending|scheduled|sent|rejected
    ai_generated: Mapped[bool] = mapped_column(Boolean, default=False)
    recipients: Mapped[int] = mapped_column(Integer, default=0)
    created_by: Mapped[str] = mapped_column(String(80))
    approved_by: Mapped[str | None] = mapped_column(String(80), nullable=True)
    reject_reason: Mapped[str] = mapped_column(String(200), default="")
    scheduled_for: Mapped[datetime | None] = mapped_column(TS, nullable=True)
    sent_at: Mapped[datetime | None] = mapped_column(TS, nullable=True)
    created_at: Mapped[datetime] = mapped_column(TS, default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(TS, default=utcnow, onupdate=utcnow)


class NotificationRule(Base):
    __tablename__ = "notification_rules"
    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(200))
    trigger: Mapped[str] = mapped_column(String(40))
    channel: Mapped[str] = mapped_column(String(20))
    enabled: Mapped[bool] = mapped_column(Boolean, default=True)
    sent_count: Mapped[int] = mapped_column(Integer, default=0)


class PublishedEtr(Base):
    __tablename__ = "published_etrs"
    event_id: Mapped[int] = mapped_column(ForeignKey("storm_events.id", ondelete="CASCADE"), primary_key=True)
    zone_id: Mapped[str] = mapped_column(ForeignKey("zones.id"), primary_key=True)
    published_by: Mapped[str] = mapped_column(String(80))
    published_at: Mapped[datetime] = mapped_column(TS, default=utcnow)


# ------------------------------------------------------------------ platform
class Setting(Base):
    __tablename__ = "settings"
    key: Mapped[str] = mapped_column(String(60), primary_key=True)
    value: Mapped[str] = mapped_column(Text, default="")


class ChatConversation(Base):
    """One AI Assistant thread; titled by its first question."""
    __tablename__ = "chat_conversations"
    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    title: Mapped[str] = mapped_column(String(120), default="New conversation")
    created_at: Mapped[datetime] = mapped_column(TS, default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(TS, default=utcnow)


class ChatMessage(Base):
    __tablename__ = "chat_messages"
    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    conversation_id: Mapped[int | None] = mapped_column(ForeignKey("chat_conversations.id", ondelete="CASCADE"), index=True, nullable=True)
    role: Mapped[str] = mapped_column(String(10))  # user | jarvis
    payload: Mapped[dict] = mapped_column(JSON)
    saved: Mapped[bool] = mapped_column(Boolean, default=False)  # bookmarked answer
    created_at: Mapped[datetime] = mapped_column(TS, default=utcnow)


class AuditLog(Base):
    __tablename__ = "audit_log"
    id: Mapped[int] = mapped_column(primary_key=True)
    at: Mapped[datetime] = mapped_column(TS, default=utcnow, index=True)
    user_name: Mapped[str] = mapped_column(String(80))
    action: Mapped[str] = mapped_column(String(60))
    entity: Mapped[str] = mapped_column(String(30))
    entity_id: Mapped[str] = mapped_column(String(30), default="")
    event_id: Mapped[int | None] = mapped_column(Integer, nullable=True, index=True)
    detail: Mapped[str] = mapped_column(Text, default="")
