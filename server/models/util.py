"""Column helpers shared by the table definitions."""

from sqlmodel import Column, DateTime


def utc_column(*, nullable: bool = True) -> Column:
    """Timezone-aware timestamp.

    sa_column bypasses SQLModel's nullability inference, so it is stated
    explicitly here.
    """
    return Column(DateTime(timezone=True), nullable=nullable)
