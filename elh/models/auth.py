from dataclasses import dataclass, field


@dataclass(frozen=True)
class UserSession:
    user_id: int
    username: str
    role: str
    display_name: str = ""
    permissions: frozenset[str] = field(default_factory=frozenset)
    must_change_password: bool = False

    def can(self, permission_key: str) -> bool:
        return permission_key in self.permissions
