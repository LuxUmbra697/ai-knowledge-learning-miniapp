"""COS 上传服务单元测试"""

from unittest.mock import MagicMock, patch

import pytest

from app.services import cos_service


@pytest.mark.asyncio
class TestUploadImageBytes:
    async def test_missing_config_raises(self):
        with patch("app.services.cos_service.get_settings") as mock_settings:
            mock_settings.return_value = MagicMock(
                cos_secret_id="", cos_secret_key="", cos_bucket="", cos_region="",
            )
            with pytest.raises(RuntimeError, match="未配置"):
                await cos_service.upload_image_bytes(b"data", "key.png")

    async def test_uploads_and_returns_default_domain_url(self):
        settings = MagicMock(
            cos_secret_id="id",
            cos_secret_key="key",
            cos_bucket="my-bucket-123",
            cos_region="ap-shanghai",
            cos_domain="",
        )
        with patch("app.services.cos_service.get_settings", return_value=settings), patch(
            "app.services.cos_service._put_object_sync"
        ) as mock_put:
            url = await cos_service.upload_image_bytes(b"data", "quiz-images/quiz_1/q1.png")

        mock_put.assert_called_once()
        assert url == "https://my-bucket-123.cos.ap-shanghai.myqcloud.com/quiz-images/quiz_1/q1.png"

    async def test_uses_custom_domain_when_configured(self):
        settings = MagicMock(
            cos_secret_id="id",
            cos_secret_key="key",
            cos_bucket="my-bucket-123",
            cos_region="ap-shanghai",
            cos_domain="img.example.com",
        )
        with patch("app.services.cos_service.get_settings", return_value=settings), patch(
            "app.services.cos_service._put_object_sync"
        ):
            url = await cos_service.upload_image_bytes(b"data", "quiz-images/quiz_1/q1.png")

        assert url == "https://img.example.com/quiz-images/quiz_1/q1.png"
