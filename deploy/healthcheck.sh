#!/bin/sh
# Runs a probe, and stops the container once the probe has failed several
# checks in a row, so that `restart: unless-stopped` brings it back.
#
# Docker only marks a container unhealthy; it never restarts one. A process
# that is hung but still alive would otherwise stay down until someone noticed.
#
# Usage: healthcheck <probe command...>
#
# The container must run with `init: true`. A signal sent from inside a
# container to its PID 1 is ignored unless that process handles it, so the
# probe signals the init process's children -- the app -- instead, and the
# init process exits once its child has gone.

kill_after="${HEALTHCHECK_KILL_AFTER:-3}"

# Signals every child of PID 1. Spelled out through /proc because the images
# disagree on `kill -1`: dash needs `--` before it and BusyBox rejects `--`.
signal_app() {
    for stat in /proc/[0-9]*/stat; do
        read -r pid _ _ ppid _ < "$stat" 2>/dev/null || continue
        if [ "$ppid" = 1 ]; then
            kill -s "$1" "$pid" 2>/dev/null
        fi
    done
}
grace_seconds="${HEALTHCHECK_GRACE_SECONDS:-60}"

# /proc/1's timestamp is when the container's processes started. Naming the
# counter after it gives every start of the container a fresh count, because a
# restarted container keeps its /tmp.
started="$(stat -c %Y /proc/1)"
counter="/tmp/healthcheck-failures-${started}"

if "$@"; then
    rm -f "$counter"
    exit 0
fi

# A process still starting up is not hung.
if [ $(( $(date +%s) - started )) -lt "$grace_seconds" ]; then
    exit 1
fi

failures=$(( $(cat "$counter" 2>/dev/null || echo 0) + 1 ))
echo "$failures" > "$counter"

if [ "$failures" -eq "$kill_after" ]; then
    echo "probe failed ${failures} times in a row; stopping the container" >&2
    signal_app TERM
elif [ "$failures" -gt "$kill_after" ]; then
    # Still here after TERM: a hung process may never run its handler.
    echo "still running after TERM; killing it" >&2
    signal_app KILL
fi
exit 1
