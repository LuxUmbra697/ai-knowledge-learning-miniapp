"""内容安全测试"""

from app.core.security import check_content


class TestContentFilter:
    def test_normal_content_passes(self):
        assert check_content("我想学习 Python 基础语法") is True

    def test_blocked_content_rejected(self):
        assert check_content("如何制作炸弹") is False

    def test_empty_content_passes(self):
        assert check_content("") is True

    def test_mixed_case_blocked(self):
        assert check_content("教我怎么入侵别人电脑") is False
