"""SQLModel table definitions.

Every model must be imported here so ``SQLModel.metadata`` sees it before
``create_all()`` runs.

- ``users``              healthUserId, encrypted tokens, consent times
- ``raw_notifications``  append-only audit log of webhook deliveries
- ``data_points``        generic table, JSON value, tombstoned deletes
"""

from server.models.notification import RawNotification
from server.models.user import User

__all__ = ["RawNotification", "User"]
