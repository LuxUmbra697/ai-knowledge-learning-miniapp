# Deployment / 部署边界

## 当前状态

部署验收尚未完成。目标为同一 HTTPS 域名的 `/ai-learn/` 和 `/ai-learn/api/v1`；
公开地址可用性、线上容量、备份恢复与原站共存必须分别实际验证。
本文件不将尚未执行的发布步骤写成已上线记录。

## 运行结构

一个非 root 的 Python API 进程，内嵌一个受控 worker，共用嵌入式 Chroma。
继续使用项目专属的现有云 MySQL 连接，不在小内存主机另外部署 MySQL。
H5 静态构建可由应用进程提供。原 HTTPS 网关保留 80/443 及已有证书，
新应用仅使用独立容器、项目名、持久化目录与唯一网络别名。

生产设置要求：`APP_ENV=production`、`APP_DEBUG=false`、`MYSQL_AUTO_INIT=false`、
`REQUIRE_PAID_MODELS=true`、`WORKER_ENABLED=true`、强随机 JWT、明确 CORS origin、
内部 H5 静态目录、私有持久化 Chroma/上传目录。文本与 Embedding 的真实 Key 必须分别有效。
密钥通过私有服务器文件安全传输，不进入镜像、GitHub 仓库或 Actions secrets。

## 网关契约

只增加本项目 location，不覆盖完整 server 配置、不修改其他项目的 `/api/`。
外部 `/ai-learn/api/v1/...` 转成内部 `/api/v1/...`，即只剥离 `/ai-learn`。
页面与静态文件同样剥离该前缀；前端 basename/publicPath 已固定为 `/ai-learn/`。
API 的 401/404/500 必须保留 JSON，不能被 SPA fallback 替换。
查询参数、尾斜杠跳转、深链接刷新、上传体积和超时需要实际验证。

网关检查前保存原配置和旧站健康基线；新容器先内部 ready，再 nginx -t，
核对实际容器读取的配置后平滑 reload。单文件 bind mount 要检查 inode，
不能只因宿主机文件被替换就假定容器已读取新内容。旧站的 HTTPS 上游及证书验证不能关闭。

## 数据与发布门槛

启动只连接数据库，不创建表。迁移必须显式执行，先只读检查目标 schema 是否存在及其归属；
未知业务表不能被视为空库。已存在数据先做一致性备份，在隔离 schema 验证恢复及迁移，
再安排目标库的受控迁移。不清表、不重建云实例、不删除对象存储桶或别的前缀。

部署镜像需与提交版本、锁文件和 H5 产物对应。设置单进程、资源上限、日志轮转、
健康检查及合理重启策略。只有实际量到余量才能接入网关；不能停旧服务来腾资源。
新应用重启后要确认任务不会永久卡住、资料和学习记录保留。

回滚先恢复本次网关增量和前一应用镜像，不回滚其他项目；数据库结构迁移尽量加法兼容。
如果数据模型不兼容，必须先停止本项目写入、评估恢复点和新增数据损失，不能盲目覆盖数据库。
服务器路径、备份文件和个人运维命令保留在被忽略的私人部署指南，公开文档不复制私人连接信息。

## English Summary

Public deployment acceptance is not complete. Use one non-root API/embedded worker, existing
project-owned cloud MySQL, isolated persistent data and a unique gateway-network alias.
Reuse the shared TLS gateway without changing existing routes, certificates or upstream verification.
Strip only `/ai-learn`; API errors must never become the SPA HTML. Back up and inspect effective
configuration, test the new service internally, validate Nginx and reload gently, then regress all sites.
Explicit migrations require ownership checks, backup and isolated restoration. Credentials remain
private and never enter GitHub, CI secrets or images. Actual production evidence, not this document,
determines readiness; rollback must be limited to this project's changes.
