# Deployment / 部署边界

## 当前状态

2026-09-17 重启后的共享入口已恢复，三个站点入口及原 API、学习 API ready 已重新验证。
此前游客、登录与隐私修复以及本次日志策略仍需完成独立应用发布；新版开发小程序已上传不代表服务器代码已更新。
每次发布前须重新验证实际版本、健康、备份与全部旧站，再执行下述流程。

## 历史验证

2026-09-15 已部署到 [在线 H5](https://lux-umbra.xyz/ai-learn/)，API 前缀为 `/ai-learn/api/v1`。
真实浏览器已完成注册、讲义上传与索引、付费引用问答、五题型练习、服务端判分、
三类梳理图和指定错题本。旧站入口、原 API 与 HTTPS 健康检查保持通过。
项目库 SQL 备份已在隔离 schema 恢复；迁移 17 只新增两张账号安全表，迁移 1–16 均保留。
2026-09-15 云库执行后原有用户、凭据和学习任务行数不变，不重建现有表。
这些结果不代表并发容量、全部旧站登录后流程、完整灾备或微信真机已经验收。

## 运行结构

一个非 root 的 Python API 进程，内嵌一个受控 worker，共用嵌入式 Chroma。
继续使用项目专属的现有云 MySQL 连接，不在小内存主机另外部署 MySQL。
H5 静态构建可由应用进程提供。原 HTTPS 网关保留 80/443 及已有证书，
新应用仅使用独立容器、项目名、持久化目录与唯一网络别名。

生产设置要求：`APP_ENV=production`、`APP_DEBUG=false`、`MYSQL_AUTO_INIT=false`、
`REQUIRE_PAID_MODELS=true`、`WORKER_ENABLED=true`、强随机 JWT、明确 CORS origin、
内部 H5 静态目录、私有持久化 Chroma/上传目录。文本与 Embedding 的真实 Key 必须分别有效。
密钥通过私有服务器文件安全传输，不进入镜像、GitHub 仓库或 Actions secrets。

## 日志与 IO 预算

应用在启动时实际读取 `LOG_LEVEL`；生产 Compose 使用 `WARNING`，保留错误类型和 trace ID，
不输出常规 INFO/DEBUG，Uvicorn HTTP access log 已关闭。容器日志限制为 `3m × 2`，
使用 `64k` 非阻塞缓冲，避免日志写入反压阻塞业务；极端日志风暴可能丢弃缓冲外的诊断行，
任务状态和执行记录仍独立持久化在数据库中。临时诊断后应恢复低日志量设置。

日志轮转限制的是保留量，不是磁盘总 IO；内存换页、数据库写入和文件索引仍需要独立采样。
修改 Docker 日志选项必须重建对应容器才生效，不能把仅编辑配置当作已经应用。
不要直接清空 Docker 正在管理的日志文件；系统 journal 使用自身 rotate/vacuum 维护，
先保存故障证据，再设容量与保留期。MySQL binlog、redo/undo、PostgreSQL WAL 不属于普通垃圾日志，
不能用文件删除命令清理。学习项目继续使用外部云 MySQL，不增加本机数据库服务。

参考：[Docker 日志配置](https://docs.docker.com/engine/logging/configure/)、
[MySQL 日志维护](https://dev.mysql.com/doc/refman/8.0/en/log-file-maintenance.html)。

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
账号安全升级后，旧代码不识别会话撤销版本，不能直接退回旧鉴权代码：须保留新鉴权层，
或受控轮换本项目 JWT 使旧会话全部失效，绝不轮换其他站点凭据。新增账号数据不通过恢复旧备份覆盖。
如果数据模型不兼容，必须先停止本项目写入、评估恢复点和新增数据损失，不能盲目覆盖数据库。
服务器路径、备份文件和个人运维命令保留在被忽略的私人部署指南，公开文档不复制私人连接信息。

## 本次部署观测

- Ubuntu 22.04.5、2 vCPU，可见内存约 1608 MiB；运行中旧服务未停止。
- 新应用限制 256 MiB / 0.75 CPU，完成索引后观测约 156.7 MiB；这是单次观测，不是压力测试。
- 延续既有项目专属云 MySQL；实测云端为 Cynos MySQL 5.7 兼容版本，本地隔离测试为 MySQL 8.0.45。
  没有把 MySQL 8 降级，也没有为了部署另建线上 MySQL 容器。CI 分别测试 MySQL 5.7 与 8。
- 网关只新增 `/ai-learn/` 必要路径，原 `/api/`、其他站点的 HTTPS 上游校验和证书保持不变。
- 单文件挂载曾与宿主机 inode 不同；首次候选未生效时没有 reload。
  隔离演练后更新实际挂载文件，恢复只读，核对字节并通过 `nginx -t` 后平滑加载，没有重启网关容器。
- 文本/Embedding 分别使用真实付费供应商；凭据仅在本地和服务器私有配置中，未上传 GitHub。
- 当前例行更新在锁定依赖镜像上只读挂载对应提交的后端源码和 H5 产物；部署记录分别保存源码版本与依赖镜像版本。
  不在小内存主机重复冷构建依赖，不重新添加网关 location；完整回滚入口保存在私人运维记录。

## English Summary

The public H5 core flow is deployed and verified; full capacity, disaster recovery and native-device
acceptance remain separate. Use one non-root API/embedded worker, existing
project-owned cloud MySQL, isolated persistent data and a unique gateway-network alias.
Reuse the shared TLS gateway without changing existing routes, certificates or upstream verification.
Strip only `/ai-learn`; API errors must never become the SPA HTML. Back up and inspect effective
configuration, test the new service internally, validate Nginx and reload gently, then regress all sites.
Explicit migrations require ownership checks, backup and isolated restoration. Credentials remain
private and never enter GitHub, CI secrets or images. Actual production evidence, not this document,
determines readiness; rollback must be limited to this project's changes.
