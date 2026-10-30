"""Prefect flows.

Deliberately empty. ``fetch.py`` imports ``prefect``, which is in its own
dependency group and absent from the web process's environment, so importing
this package must not drag it in.

The import direction is one way: a flow may import ``server``, never the
reverse. The work a flow does lives in ``server.health.fetcher``, which has no
Prefect dependency at all and is shared with the backfill CLI.
"""
