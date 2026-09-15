"""Explicit tutor commands; identity and tool capabilities come only from the server."""
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator


class TutorCreate(BaseModel):
    model_config = ConfigDict(extra='forbid', str_strip_whitespace=True)
    goal: str = Field(min_length=1, max_length=1000)
    mode: Literal['socratic', 'diagnosis'] = 'socratic'
    doc_ids: list[str] = Field(default_factory=list, max_length=3)
    card_id: str | None = Field(default=None, min_length=1, max_length=64)

    @model_validator(mode='after')
    def valid_scope(self):
        if self.mode == 'socratic' and (not self.doc_ids or self.card_id):
            raise ValueError('Socratic tutoring requires one to three selected documents')
        if self.mode == 'diagnosis' and (not self.card_id or self.doc_ids):
            raise ValueError('Diagnosis requires an owned wrong-answer card, not arbitrary documents')
        if any(not doc_id or len(doc_id) > 64 for doc_id in self.doc_ids):
            raise ValueError('Invalid document identity')
        self.doc_ids = sorted(set(self.doc_ids))
        return self


class TutorTurn(BaseModel):
    model_config = ConfigDict(extra='forbid', str_strip_whitespace=True)
    version: int = Field(ge=0, le=5, strict=True)
    message: str = Field(min_length=1, max_length=1000)


class TutorPracticeConfirm(BaseModel):
    model_config = ConfigDict(extra='forbid')
    version: int = Field(ge=1, le=6, strict=True)
    confirmed: bool = Field(strict=True)

    @model_validator(mode='after')
    def require_confirmation(self):
        if not self.confirmed:
            raise ValueError('Explicit confirmation is required')
        return self
