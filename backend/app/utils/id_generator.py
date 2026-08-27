"""ID 生成工具"""

import uuid


def gen_quiz_id() -> str:
    return f"quiz_{uuid.uuid4().hex[:12]}"
