"""Key-value settings table for master node.

Populated via `master.config_store` — every master config value is stored
under a `config.*` key in this table, plus a `config_initialized` marker.
"""

from sqlalchemy import Column, String, Text

from shared.models import Base


class MasterSetting(Base):
    __tablename__ = "master_settings"
    key = Column(String(64), primary_key=True)
    value = Column(Text, nullable=False)
