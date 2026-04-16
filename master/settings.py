"""
Key-value settings table for master node.
"""

from sqlalchemy import Column, String
from sqlalchemy.orm import Session

from shared.base import Base


class MasterSetting(Base):
    __tablename__ = "master_settings"
    key = Column(String(64), primary_key=True)
    value = Column(String(512), nullable=False)


_DEFAULTS: dict[str, str] = {
    "scan_interval_seconds": "60",
    "scan_periodic_enabled": "false",
}


def get_setting(db: Session, key: str) -> str:
    row = db.query(MasterSetting).filter(MasterSetting.key == key).first()
    return row.value if row else _DEFAULTS.get(key, "")


def set_setting(db: Session, key: str, value: str) -> None:
    row = db.query(MasterSetting).filter(MasterSetting.key == key).first()
    if row:
        row.value = value
    else:
        db.add(MasterSetting(key=key, value=value))
    db.commit()
