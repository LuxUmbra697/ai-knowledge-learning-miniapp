"""报告相关数据模型"""

from pydantic import BaseModel, Field
from .quiz import Question, AnswerRecord


class ReportGenerateRequest(BaseModel):
    quiz_id: str
    topic: str
    questions: list[Question]
    answer_records: list[AnswerRecord]


class ReportOutput(BaseModel):
    """AI 生成报告的结构化输出 Schema"""

    accuracy: int = Field(description="正确率百分比")
    mastered_points: list[str] = Field(description="掌握较好的知识点")
    weak_points: list[str] = Field(description="薄弱知识点")
    three_line_summary: list[str] = Field(description="三句知识总结")
    advice: list[str] = Field(description="后续建议")
    share_quote: str = Field(description="一句可用于分享的学习金句")


class ReportGenerateResponse(BaseModel):
    accuracy: int
    mastered_points: list[str]
    weak_points: list[str]
    three_line_summary: list[str]
    advice: list[str]
    share_quote: str
