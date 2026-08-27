# syntax=docker/dockerfile:1
# ------------------------------------------------------------------
# LuxUmbra - 微信云托管后端服务 Dockerfile
# 参考：微信云托管官方文档《快速入门-Python自定义部署》《构建方案-如何提高项目构建效率》
# 要点：
#   1. 容器需以 0.0.0.0 监听「创建服务版本」时填写的端口（本镜像默认 80，可通过环境变量 PORT 覆盖，
#      但需与云托管控制台「监听端口」保持一致，服务间内网调用也只认这个端口）。
#   2. 使用多阶段构建减小镜像体积、加快构建。
#   3. pip 使用腾讯云镜像源加速依赖安装（云托管构建机访问腾讯源更快更稳定）。
# ------------------------------------------------------------------

# ---------- 构建阶段：安装 Python 依赖 ----------
FROM python:3.11-slim AS builder

WORKDIR /app

# 更换为腾讯云 pip 镜像源，加速依赖下载
RUN pip config set global.index-url https://mirrors.cloud.tencent.com/pypi/simple \
    && pip config set global.trusted-host mirrors.cloud.tencent.com

COPY requirements.txt .
RUN pip install --no-cache-dir --user -r requirements.txt

# ---------- 运行阶段 ----------
FROM python:3.11-slim

LABEL org.opencontainers.image.title="LuxUmbra" \
      org.opencontainers.image.description="LuxUmbra backend service for WeChat Cloud Run" \
      org.opencontainers.image.vendor="LuxUmbra"

ENV TZ=Asia/Shanghai \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PATH=/root/.local/bin:$PATH \
    PORT=80

# 时区 + CA 证书（调用 HTTPS 外部接口，如百炼/COS/微信开放接口时需要）
RUN apt-get update \
    && apt-get install -y --no-install-recommends tzdata ca-certificates \
    && ln -snf /usr/share/zoneinfo/${TZ} /etc/localtime && echo ${TZ} > /etc/timezone \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# 拷贝构建阶段安装好的依赖
COPY --from=builder /root/.local /root/.local

# 拷贝项目代码
COPY . .

# 微信云托管：容器必须监听「创建版本」时填写的端口，此处默认暴露 80
EXPOSE 80

# 健康检查（可在云托管控制台「健康检查」中配置探活路径为 /api/v1/health，与此保持一致）
HEALTHCHECK --interval=30s --timeout=5s --start-period=20s --retries=3 \
    CMD python -c "import os,urllib.request; urllib.request.urlopen('http://127.0.0.1:' + os.environ.get('PORT', '80') + '/api/v1/health', timeout=3)" || exit 1

CMD ["sh", "-c", "uvicorn app.main:app --host 0.0.0.0 --port ${PORT:-80}"]
