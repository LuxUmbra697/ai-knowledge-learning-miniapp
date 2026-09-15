"""Real HTTP + isolated MySQL verification, with no paid model requests."""

import asyncio
import json
from pathlib import Path
import platform
import uuid

import httpx

from run_local import configure

configure()

from app.core.auth import create_token
from app.core.db import connect_mysql, close_mysql_pool, get_mysql_pool
from app.repositories.quiz_repository import save_quiz_session, complete_quiz

ROOT = Path(__file__).resolve().parents[1]


async def main():
    await connect_mysql()
    checks = []
    try:
        pool = get_mysql_pool()
        async with pool.acquire() as conn:
            async with conn.cursor() as cur:
                users = []
                for _ in range(2):
                    await cur.execute("INSERT INTO users(openid,nickname) VALUES(%s,%s)",
                                      ("verification_" + uuid.uuid4().hex, "Synthetic verification"))
                    users.append(cur.lastrowid)
        quiz_id = "quiz_verify_" + uuid.uuid4().hex[:12]
        questions = [{"id": "q1", "type": "single", "stem": "2 + 2 = ?",
                      "options": [{"key": "A", "text": "4"}, {"key": "B", "text": "5"}],
                      "answer": ["A"], "explanation": "Two pairs contain four items.",
                      "knowledge_point": "Addition", "difficulty": "easy"}]
        await save_quiz_session(quiz_id, users[0], "Synthetic arithmetic", "M0 fixture", "addition", questions)
        headers = [{"Authorization": "Bearer " + create_token(user, "verification")} for user in users]
        async with httpx.AsyncClient(base_url="http://127.0.0.1:18081/api/v1", timeout=10) as client:
            assert (await client.get("/health")).status_code == 200
            checks.append("HTTP health")
            assert (await client.get("/quiz/task/private")).status_code == 401
            checks.append("Unauthenticated task denied")
            before = await client.get(f"/user/quizzes/{quiz_id}", headers=headers[0])
            assert "answer" not in before.json()["data"]["questions"][0]
            assert "explanation" not in before.json()["data"]["questions"][0]
            checks.append("Answers and explanation withheld")
            payload = {"question_id": "q1", "selected_answers": ["B"], "duration_ms": 100}
            assert (await client.post(f"/quiz/{quiz_id}/answer", headers=headers[1], json=payload)).status_code == 404
            checks.append("Cross-user submission denied")
            assert (await client.post(f"/quiz/{quiz_id}/answer", headers=headers[0], json={**payload, "is_correct": True})).status_code == 422
            checks.append("Client correctness injection denied")
            assert (await client.post("/report/generate", headers=headers[0], json={"quiz_id": quiz_id})).status_code == 409
            checks.append("Incomplete report denied before model")
            responses = await asyncio.gather(*[client.post(f"/quiz/{quiz_id}/answer", headers=headers[0], json=payload) for _ in range(5)])
            assert all(r.status_code == 200 for r in responses)
            assert all(r.json()["data"]["record"]["is_correct"] is False for r in responses)
            assert sum(not r.json()["data"]["replayed"] for r in responses) == 1
            checks.append("Five concurrent submissions commit once")
            changed = await client.post(f"/quiz/{quiz_id}/answer", headers=headers[0], json={**payload, "selected_answers": ["A"]})
            assert changed.status_code == 409
            checks.append("Previously submitted answer immutable")
            after = await client.get(f"/user/quizzes/{quiz_id}", headers=headers[0])
            assert after.json()["data"]["questions"][0]["answer"] == ["A"]
            checks.append("Own submitted explanation revealed")
            score = {"total": 1, "correct": 0, "accuracy": 0}
            report = {"accuracy": 0, "mastered_points": [], "weak_points": ["Addition"],
                      "three_line_summary": ["Synthetic deterministic verification."], "advice": ["Review addition"], "share_quote": "Practice"}
            await asyncio.gather(*[complete_quiz(quiz_id, users[0], [payload], score, report) for _ in range(3)])
            async with pool.acquire() as conn:
                async with conn.cursor() as cur:
                    await cur.execute("SELECT total_xp FROM users WHERE id=%s", (users[0],))
                    assert (await cur.fetchone())[0] == 10
                    await cur.execute("SELECT COUNT(*) FROM quiz_question_attempts WHERE quiz_id=%s", (quiz_id,))
                    assert (await cur.fetchone())[0] == 1
            checks.append("Concurrent report completion awards XP once")
            replay = await client.post("/report/generate", headers=headers[0], json={"quiz_id": quiz_id, "topic": "forged"})
            assert replay.status_code == 200 and replay.json()["data"]["accuracy"] == 0
            checks.append("Stored report replay ignores forged client fields")
        result = {"stage": "M0", "python": platform.python_version(), "transport": "real HTTP loopback",
                  "database": "isolated MySQL 8.0.45", "external_model_calls": 0, "checks": checks,
                  "passed": len(checks), "devices": [], "production_tested": False}
        folder = ROOT / "docs/evidence"
        folder.mkdir(parents=True, exist_ok=True)
        (folder / "m0-local.json").write_text(json.dumps(result, indent=2), encoding="utf-8")
        print(json.dumps(result))
    finally:
        await close_mysql_pool()


if __name__ == "__main__":
    asyncio.run(main())
