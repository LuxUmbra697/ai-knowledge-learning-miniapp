# Development / 本地开发

## 环境与隔离

本次实际使用 Windows、Python 3.13.9、Node 22.19.0、MySQL 8.0.45、uv 0.12.5。
Linux 的隔离 CI 使用 Python 3.13、Node 22.19.0 和 MySQL 服务容器；macOS 尚无本机验收。
前端保持 Taro 4.1.11，不使用新的 Vite 工程。依赖以 npm lockfile 和带哈希的 Python 锁文件为准。

从仓库根目录操作：

```sh
python -m venv .venv
```

PowerShell：`.\.venv\Scripts\Activate.ps1`。Linux/macOS：`source .venv/bin/activate`。

```sh
python -m pip install uv==0.12.5
uv pip sync --require-hashes backend/requirements-dev.txt
npm --prefix frontend ci
```

将 MySQL 8 的 mysqld 放入 PATH，或使用 `--mysqld` 指定已安装的服务端程序。

```sh
python scripts/local_mysql.py start
python scripts/local_mysql.py status
python scripts/run_local.py --initialize
```

此 MySQL 仅监听 127.0.0.1:23308，数据库目录为仓库内 `.local/mysql/data`，禁用 mysqlx。
本地开发账户无密码且只供回环隔离开发，不能用于线上。脚本核验服务端真实数据目录，
遇到其他服务或非空未知目录会停止，不删除已有文件。初始化使用 `ai_learn_local`；
数据库测试另用 `ai_learn_test`。两者均不读取云数据库连接。

## 启动顺序

先数据库、显式迁移，再 API/worker，最后前端。当前嵌入式 Chroma 部署只开一个 API 进程；
`run_local.py` 在该进程中启动一个 worker，不需要另开 worker 终端。

```sh
npm --prefix frontend run build:h5
npm --prefix frontend run build:weapp
node frontend/scripts/check-build.mjs --both
python scripts/run_local.py --serve-h5 --port 18081
```

另一终端：

```sh
npm --prefix frontend run preview
```

H5：`http://127.0.0.1:18082/ai-learn/`。本地 API：`http://127.0.0.1:18081/api/v1/ready`。
开发 API 文档：`http://127.0.0.1:18081/docs`。生产关闭 Swagger/OpenAPI。
预览会将 `/ai-learn/api/` 转发到 API；生产风格验收可将 `PREVIEW_BACKEND_H5=1`
置于预览进程环境，让所有页面也经后端静态服务。

日常 H5 热更新可用 `npm --prefix frontend run dev:h5`，地址
`http://127.0.0.1:10086/ai-learn/`，仍需先运行 API。

## 启用真实服务

仅当 `backend/.env` 不存在时创建：

PowerShell：

```powershell
if (-not (Test-Path backend/.env)) { Copy-Item backend/.env.example backend/.env }
```

Linux/macOS：

```sh
test -e backend/.env || cp backend/.env.example backend/.env
```

在编辑器填写私有 Key；不要写进 shell 参数或截图。文本与 Embedding 是独立 Key，
生图另有独立 Key，不能互相回退。生图 Base URL 和 COS 域名允许留空，由现有逻辑推导。
替换 API 启动命令：

```sh
python scripts/run_local.py --with-models --with-search --serve-h5 --port 18081
```

本地仍强制独立数据库、JWT、向量/上传目录及 COS 测试前缀。不开 `--with-search` 时，
公开搜索关闭。不开 `--with-models` 时，不读取模型 Key，AI 操作会返回配置错误而非合成答案。
生产配置不得直接使用该开发启动器；见 [部署边界](deployment.md)。

## 微信小程序

导入 `frontend/`，不是仓库根目录或旧 `dist/`。项目配置指定 `dist/weapp/`。
仓库固定 AppID `wx7abde39fb8222887`，后端使用匹配的 AppSecret；密钥不进入前端。
生产构建使用正式 HTTPS API 前缀。Fork 到其他 AppID 必须同步修改项目配置和构建断言。

公开背景、看板娘与图标统一由 `src/services/assets.ts` 指向 OSS，不再打进代码包。
保留源码素材即可，不要重新添加 `require(...assets...)`。后台合法域名配置需核对实际使用的 API
以及图片下载能力所用的 OSS 域名；`Image` 显示和 `getImageInfo/downloadFile` 不应混为同一项验收。
上传前使用生产构建并执行 `check-build.mjs --both`，检查压缩、按需注入、媒体总量和 JS 语法。

```sh
npm --prefix frontend run dev:weapp
```

开发构建的 API 为 `http://127.0.0.1:18081/api/v1`，仅适用于本机模拟器。
真实手机不能通过手机的回环地址访问电脑；真机应使用经验证、已配置合法域名的 HTTPS 后端。
不能将开发工具关闭域名校验视为发布验收。开发工具自动化需要官方服务端口与登录授权，
这不会由普通 GitHub runner 代替。H5 使用独立账号，微信使用真实 code 交换，不自动合并。

官方 WXSS 检查与自动化入口（仓库根目录，需本机已安装并登录开发工具）：

```powershell
$env:WECHAT_WXSS_COMPILER = '你的开发工具安装目录/resources/app.asar.unpacked/node_modules/wcc-exec/wcsc.exe'
node frontend/scripts/check-weapp-native.mjs
& '你的开发工具安装目录/cli.bat' auto --project (Resolve-Path frontend).Path --auto-port 9420 --trust-project
$env:WEAPP_AUTOMATION_ENDPOINT = 'ws://127.0.0.1:9420'
node frontend/scripts/check-weapp-selection.mjs
```

先在工具里完成微信登录，脚本仅切换角色、读取页面，不发送聊天或购买模型调用。
端口已被其他项目窗口占用时改用空闲端口，并让 CLI 与检查脚本保持一致。
构建成功不等于工具使用了新代码：核对导入路径 `frontend/` 和窗口，必要时只清理本项目编译缓存。
不要清除其他窗口、登录缓存或私人数据。服务端口属于本机开发能力，不应公开到互联网。

## 停止与常见问题

Ctrl+C 分别停止预览和 API；再运行 `python scripts/local_mysql.py stop`。数据保留。
API 重启后通过 MySQL 租约恢复任务；外部调用结果不确定时任务明确失败，不盲目重复购买。

| 现象 | 检查 |
| --- | --- |
| 23308 被占用 | 先运行 status；不是本项目数据目录时不要关闭它 |
| API 无法启动 | 数据库是否启动、是否执行 initialize、端口是否被占用 |
| AI 提示未配置 | 是否使用 with-models、各 Key 权限是否匹配；禁止反复试模型 |
| H5 页面正常但 API 502 | API 18081 是否 ready，预览是否仍在运行 |
| 深链接刷新 404 | H5 basename、静态 publicPath 和网关剥离前缀应一致 |
| 小程序导入后空白 | 检查 dist/weapp/app.json，重新构建，确认导入目录 |
| 字体/图片或大图表加载慢 | 核对 OSS 可达性、图片域名与 CSP；Mermaid 仅 H5 异步加载，小程序走原生 Canvas |

更新依赖应修改 `.in` 和 package.json，重新锁定、双端构建及回归；不要直接升级整个 Taro 栈。
Python 锁定器 `python scripts/lock_dependencies.py` 使用 uv，固定 Python 3.13 和跨平台哈希；
当前环境约束文件留在 `.local/locks`，不公开。锁文件改变后必须在新的虚拟环境重装检验。

## English Notes

Run every command from the repository root. Activate `.venv` with the platform-specific command,
install hash-locked Python dependencies and `npm ci`, start the isolated MySQL, explicitly initialize,
build both targets, then start API/embedded worker and the H5 preview in separate terminals.
The commands and troubleshooting table above are the canonical sequence. `--with-models` reads
private provider settings but still forces isolated local storage. The developer launcher is not
a production launcher. MySQL shutdown validates the data directory and never deletes it.
Import `frontend/` into WeChat DevTools; real devices require a verified public backend and platform
permissions. Windows was locally verified; do not infer macOS or real-device acceptance from CI/builds.
