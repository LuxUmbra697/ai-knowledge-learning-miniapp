"""计分服务"""

from app.models.quiz import AnswerRecord


def compute_score_summary(answer_records: list[AnswerRecord]) -> dict:
    total = len(answer_records)
    correct = sum(1 for r in answer_records if r.is_correct)
    accuracy = round(correct / total * 100) if total > 0 else 0
    avg_duration = (
        round(sum(r.duration_ms for r in answer_records) / total) if total > 0 else 0
    )

    return {
        "total": total,
        "correct": correct,
        "wrong": total - correct,
        "accuracy": accuracy,
        "avg_duration_ms": avg_duration,
    }
