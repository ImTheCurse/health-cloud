"""Constants describing the runtime environment.

Lives here rather than in each module that needs it: three copies of the same
string literal had appeared, and "is this a developer's machine?" is one fact
about the deployment, not three unrelated ones.
"""

#: The value of ENVIRONMENT that means "running on a developer's own machine".
#: Behaviour gated on this is convenience or introspection that would be
#: inappropriate anywhere real -- full request logging, and direct reads of the
#: queue.
LOCAL_ENV = "local"
