"""题库相关数据模型"""

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator


class QuestionOption(BaseModel):
    key: str = Field(description="选项标识，如 A、B、C、D")
    text: str = Field(description="选项文本")


class QuestionCitation(BaseModel):
    model_config = ConfigDict(extra='forbid')
    evidence_id: str = Field(min_length=1, max_length=40)
    quote: str = Field(min_length=2, max_length=500)
    doc_id: str | None = None
    chunk_id: str | None = None
    revision: int | None = None
    index_version: str | None = None
    file_name: str | None = None
    page: int = 0
    section: str = ''
    status: Literal['verified'] = 'verified'


class Question(BaseModel):
    id: str = Field(description="题目编号，如 q1")
    type: Literal["single", "multiple", "judge", "fill", "written"] = Field(description="题型")
    stem: str = Field(description="题干")
    options: list[QuestionOption] = Field(description="选项列表")
    answer: list[str] = Field(description="正确答案的 key 列表")
    explanation: str = Field(description="详细讲解")
    knowledge_point: str = Field(description="知识点标签")
    difficulty: Literal["easy", "medium", "hard"] = Field(description="难度")
    image_url: str | None = Field(default=None, description="AI 生成的题目配图 URL（可选）")
    citations: list[QuestionCitation] = Field(default_factory=list, max_length=3)
    accepted_answers: list[list[str]] = Field(default_factory=list, max_length=4)
    rubric: list[str] = Field(default_factory=list, max_length=5)


class QuizOutput(BaseModel):
    """AI 生成题库的结构化输出 Schema"""

    title: str = Field(description="学习主题")
    summary: str = Field(description="本次题库的主题摘要")
    questions: list[Question] = Field(description="题目列表")


class QuestionCounts(BaseModel):
    model_config = ConfigDict(extra='forbid')
    single: int = Field(default=0, ge=0, le=20, strict=True)
    multiple: int = Field(default=0, ge=0, le=20, strict=True)
    judge: int = Field(default=0, ge=0, le=20, strict=True)
    fill: int = Field(default=0, ge=0, le=20, strict=True)
    written: int = Field(default=0, ge=0, le=20, strict=True)


class QuizGenerateRequest(BaseModel):
    model_config = ConfigDict(extra='forbid', str_strip_whitespace=True)
    user_input: str = Field(
        min_length=1,
        max_length=2000,
        description="用户输入的学习内容",
    )
    question_count: int = Field(default=5, ge=1, le=20, strict=True, description="题目数量")
    question_counts: QuestionCounts | None = None
    difficulty: Literal["easy", "medium", "hard", "mixed"] = Field(
        default="mixed", description="难度"
    )
    doc_id: str | None = Field(
        default=None, min_length=1, max_length=64, description="可选，指定基于某篇知识库文档出题"
    )
    generate_images: bool = Field(
        default=False, description="是否为每道题目生成配图"
    )
    use_web_search: bool = Field(default=False, strict=True, description="是否将本次公开主题发送给网页搜索服务")

    @model_validator(mode='after')
    def validate_counts(self):
        if self.doc_id and self.use_web_search:
            raise ValueError('私人材料练习不向网页搜索发送内容')
        if self.question_counts is not None:
            total = sum(self.question_counts.model_dump().values())
            if not 1 <= total <= 20:
                raise ValueError('题型数量合计须为 1 至 20')
            if 'question_count' in self.model_fields_set and self.question_count != total:
                raise ValueError('题型数量合计必须等于题目总数')
            self.question_count = total
        return self


class QuizGenerateResponse(BaseModel):
    quiz_id: str
    title: str
    summary: str
    questions: list[Question]
    source_context: dict | None = None
    image_notice: str | None = Field(
        default=None, description="配图相关的提示信息（如未登录/额度已用完/部分题目未配图等），无异常时为 None"
    )


class AnswerRecord(BaseModel):
    question_id: str
    selected_answers: list[str]
    is_correct: bool
    duration_ms: int = Field(ge=0)


# ---- 异步任务模型 ----

class QuizTaskCreateResponse(BaseModel):
    """创建出题任务的响应"""
    task_id: str


class QuizTaskStatusResponse(BaseModel):
    """轮询任务状态的响应"""
    task_id: str
    status: Literal["pending", "running", "completed", "failed"]
    stage: str | None = None
    result: "QuizGenerateResponse | None" = None
    error_message: str | None = None
