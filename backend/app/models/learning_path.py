from typing import Annotated

from pydantic import BaseModel, ConfigDict, Field, model_validator

ConceptId = Annotated[str, Field(pattern=r'^[a-f0-9]{64}$')]


class PathUpdate(BaseModel):
    model_config = ConfigDict(extra='forbid')
    version: int = Field(ge=0, strict=True)
    edges: list[tuple[ConceptId, ConceptId]] = Field(max_length=180)


class PlanConfirm(BaseModel):
    model_config = ConfigDict(extra='forbid')
    fingerprint: str = Field(pattern=r'^[a-f0-9]{64}$')
    minutes: int = Field(ge=5, le=60, strict=True)
    timezone: str = Field(default='Asia/Shanghai', min_length=1, max_length=64)
    confirmed: bool = Field(strict=True)

    @model_validator(mode='after')
    def consent(self):
        if not self.confirmed:
            raise ValueError('请明确确认计划')
        return self
