import re
from typing import Literal
from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

CharacterId = Literal['pink', 'orange']


class Command(BaseModel):
    model_config = ConfigDict(extra='forbid', str_strip_whitespace=True)
    version: int = Field(ge=0, strict=True)


class CompanionTurn(Command):
    message: str = Field(min_length=1, max_length=1000)


class MemoryItem(BaseModel):
    model_config = ConfigDict(extra='forbid', str_strip_whitespace=True)
    id: str = Field(pattern=r'^[a-zA-Z0-9_-]{1,40}$')
    kind: Literal['name', 'study', 'support']
    text: str = Field(min_length=1, max_length=160)

    @field_validator('text')
    @classmethod
    def no_credentials(cls, text):
        if re.search(r'(sk-[A-Za-z0-9_-]{12,}|-----BEGIN|密码|口令|私钥|身份证|银行卡|password|secret|token|api.?key)', text, re.I):
            raise ValueError('Do not store credentials or sensitive identity data as companion memory')
        return text


class MemoryUpdate(Command):
    items: list[MemoryItem] = Field(max_length=12)

    @model_validator(mode='after')
    def distinct(self):
        if len({item.id for item in self.items}) != len(self.items):
            raise ValueError('Memory IDs must be unique')
        return self


class ResetConversation(Command):
    mode: Literal['history', 'memory', 'all']
    confirmed: Literal[True]
