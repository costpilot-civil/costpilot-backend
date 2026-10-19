from datetime import datetime

from pydantic import BaseModel, ConfigDict, field_validator


class ProjectCreate(BaseModel):
    name: str
    project_number: str | None = None
    client: str | None = None
    location: str | None = None
    description: str | None = None

    @field_validator("name")
    @classmethod
    def validate_name(cls, value: str) -> str:
        value = value.strip()

        if not value:
            raise ValueError("Project name must not be empty.")

        return value


class ProjectResponse(BaseModel):
    id: int
    name: str
    project_number: str | None
    client: str | None
    location: str | None
    description: str | None
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)


class ProjectUpdate(BaseModel):
    name: str | None = None
    project_number: str | None = None
    client: str | None = None
    location: str | None = None
    description: str | None = None

    model_config = ConfigDict(extra="forbid")

    @field_validator("name")
    @classmethod
    def validate_name(cls, value: str | None) -> str:
        if value is None or not value.strip():
            raise ValueError("Project name must not be empty.")

        return value.strip()
