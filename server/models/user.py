"""The ``users`` table.

One row per Google Health user. ``health_user_id`` comes from the Health API's
getIdentity endpoint and is the single identifier used across sessions, tokens,
and every data row -- the token response does not contain it, so onboarding
always makes that extra call.

OAuth tokens are stored as Tink AEAD ciphertext, never in the clear. The access
token is encrypted too: it is short-lived, but for that hour it can read the
same health data the refresh token can.
"""

from datetime import datetime

from sqlmodel import Column, DateTime, Field, SQLModel


def _utc_column(*, nullable: bool = True) -> Column:
    """Timezone-aware timestamp.

    sa_column bypasses SQLModel's nullability inference, so it is stated
    explicitly here.
    """
    return Column(DateTime(timezone=True), nullable=nullable)


class User(SQLModel, table=True):
    __tablename__ = "users"

    health_user_id: str = Field(primary_key=True)

    google_sub: str | None = Field(default=None, unique=True, index=True)
    email: str | None = Field(default=None)
    display_name: str | None = Field(default=None)

    refresh_token_enc: bytes
    access_token_enc: bytes | None = Field(default=None)
    access_token_expiry: datetime | None = Field(default=None, sa_column=_utc_column())

    granted_scopes: str

    consented_at: datetime = Field(sa_column=_utc_column(nullable=False))
    #: Load-bearing: the 7-day testing-mode expiry countdown and the push alert
    #: are both computed from this.
    refreshed_at: datetime = Field(sa_column=_utc_column(nullable=False))
    revoked_at: datetime | None = Field(default=None, sa_column=_utc_column())
