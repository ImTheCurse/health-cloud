"""SQLModel table definitions.

Every model must be imported here so ``SQLModel.metadata`` sees it before
``create_all()`` runs.

- ``users``              step 2 - healthUserId, encrypted tokens, consent times
- ``raw_notifications``  step 3 - append-only audit log of webhook deliveries
- ``data_points``        step 5 - generic table, JSON value, tombstoned deletes
"""

from server.models.user import User

__all__ = ["User"]
