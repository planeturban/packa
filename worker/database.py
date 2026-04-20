from shared.db import make_engine, make_get_db, make_session_factory
from shared.models import Base  # noqa: F401 — imported so Base.metadata sees all models

engine = make_engine("sqlite:///./worker.db")
SessionLocal = make_session_factory(engine)
get_db = make_get_db(SessionLocal)
