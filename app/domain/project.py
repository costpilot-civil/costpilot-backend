from dataclasses import dataclass
from datetime import datetime


@dataclass(frozen=True, slots=True)
class Project:
    id: int
    name: str
    project_number: str | None
    client: str | None
    location: str | None
    description: str | None
    created_at: datetime
    updated_at: datetime
