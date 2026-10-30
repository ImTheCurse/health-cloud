"""Errors raised while triggering a flow run."""


class TriggerError(RuntimeError):
    """A flow run could not be started.

    Always swallowed by the caller, and that is safe rather than sloppy: the
    notification is already durably queued, so a missed trigger delays the work
    until the next trigger or the reconcile sweep. It never loses it. What must
    never happen is letting this turn a successfully queued notification into a
    503, which is why the trigger runs after the response is sent.
    """
