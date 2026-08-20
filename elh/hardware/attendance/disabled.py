class DisabledAttendanceDevice:
    def fetch_events(self):
        return []

    def fetch_users(self):
        return []

    def health(self) -> tuple[bool, str]:
        return True, "Attendance integration disabled"


class UnavailableAttendanceDevice:
    def __init__(self, reason: str):
        self.reason = reason

    def fetch_events(self):
        raise RuntimeError(self.reason)

    def fetch_users(self):
        raise RuntimeError(self.reason)

    def health(self) -> tuple[bool, str]:
        return False, self.reason
