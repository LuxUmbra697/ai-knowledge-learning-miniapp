"""pytest 配置"""

import pytest


@pytest.fixture
def sample_quiz_request():
    return {
        "user_input": "我想学习什么是 RAG，以及它和传统搜索有什么区别",
        "question_count": 5,
        "difficulty": "mixed",
    }


@pytest.fixture
def sample_quiz_response_data():
    return {
        "quiz_id": "quiz_abc123",
        "title": "RAG 入门闯关",
        "summary": "围绕 RAG 基础概念与应用场景生成的题库",
        "questions": [
            {
                "id": "q1",
                "type": "single",
                "stem": "RAG 的全称是什么？",
                "options": [
                    {"key": "A", "text": "Retrieval-Augmented Generation"},
                    {"key": "B", "text": "Random Access Generation"},
                    {"key": "C", "text": "Rapid AI Generation"},
                    {"key": "D", "text": "Recursive Augmented Generation"},
                ],
                "answer": ["A"],
                "explanation": "RAG 全称是 Retrieval-Augmented Generation，即检索增强生成。",
                "knowledge_point": "RAG 基础概念",
                "difficulty": "easy",
            },
            {
                "id": "q2",
                "type": "single",
                "stem": "RAG 中 R 代表什么环节？",
                "options": [
                    {"key": "A", "text": "推理"},
                    {"key": "B", "text": "检索"},
                    {"key": "C", "text": "训练"},
                    {"key": "D", "text": "评估"},
                ],
                "answer": ["B"],
                "explanation": "R 代表 Retrieval（检索），是从外部知识库中检索相关文档。",
                "knowledge_point": "RAG 流程",
                "difficulty": "easy",
            },
            {
                "id": "q3",
                "type": "single",
                "stem": "RAG 相比纯大模型最大的优势是？",
                "options": [
                    {"key": "A", "text": "速度更快"},
                    {"key": "B", "text": "减少幻觉，提高准确性"},
                    {"key": "C", "text": "模型更小"},
                    {"key": "D", "text": "不需要 GPU"},
                ],
                "answer": ["B"],
                "explanation": "RAG 通过引入外部知识减少大模型的幻觉问题。",
                "knowledge_point": "RAG 优势",
                "difficulty": "medium",
            },
            {
                "id": "q4",
                "type": "multiple",
                "stem": "以下哪些是 RAG 系统的关键组件？",
                "options": [
                    {"key": "A", "text": "向量数据库"},
                    {"key": "B", "text": "Embedding 模型"},
                    {"key": "C", "text": "区块链"},
                    {"key": "D", "text": "大语言模型"},
                ],
                "answer": ["A", "B", "D"],
                "explanation": "RAG 的关键组件包括向量数据库、Embedding 模型和大语言模型。",
                "knowledge_point": "RAG 架构",
                "difficulty": "medium",
            },
            {
                "id": "q5",
                "type": "judge",
                "stem": "RAG 必须使用 GPT-4 才能工作。",
                "options": [
                    {"key": "A", "text": "正确"},
                    {"key": "B", "text": "错误"},
                ],
                "answer": ["B"],
                "explanation": "RAG 可以使用任何大语言模型，不限于 GPT-4。",
                "knowledge_point": "RAG 通用性",
                "difficulty": "easy",
            },
        ],
    }


@pytest.fixture
def sample_answer_records():
    return [
        {
            "question_id": "q1",
            "selected_answers": ["A"],
            "is_correct": True,
            "duration_ms": 3200,
        },
        {
            "question_id": "q2",
            "selected_answers": ["B"],
            "is_correct": True,
            "duration_ms": 4100,
        },
        {
            "question_id": "q3",
            "selected_answers": ["A"],
            "is_correct": False,
            "duration_ms": 5500,
        },
        {
            "question_id": "q4",
            "selected_answers": ["A", "B", "D"],
            "is_correct": True,
            "duration_ms": 8200,
        },
        {
            "question_id": "q5",
            "selected_answers": ["B"],
            "is_correct": True,
            "duration_ms": 2100,
        },
    ]


@pytest.fixture
def sample_report_request(sample_quiz_response_data, sample_answer_records):
    return {
        "quiz_id": sample_quiz_response_data["quiz_id"],
        "topic": sample_quiz_response_data["title"],
        "questions": sample_quiz_response_data["questions"],
        "answer_records": sample_answer_records,
    }
