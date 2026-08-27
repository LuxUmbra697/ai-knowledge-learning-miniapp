"""敏感词过滤"""

# MVP 阶段使用简单的关键词列表过滤
BLOCKED_KEYWORDS = [
    "暴力",
    "色情",
    "赌博",
    "毒品",
    "自杀",
    "恐怖",
    "炸弹",
    "爆炸",
    "入侵",
    "黑客攻击",
    "武器",
]


def check_content(text: str) -> bool:
    """检查文本是否包含敏感词，返回 True 表示安全"""
    text_lower = text.lower()
    for kw in BLOCKED_KEYWORDS:
        if kw in text_lower:
            return False
    return True
