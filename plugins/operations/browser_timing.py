"""Keep queue admission short; allow a claimed browser command time for slow proxy loads."""
EXECUTION_SECONDS = 600
ACK_GRACE_SECONDS = 35


def workflow_deadline(expires, wall_now, monotonic_now):
    # The command is granted its execution budget only when a worker actually claims it.
    return monotonic_now + max(0, expires - wall_now) + ACK_GRACE_SECONDS
