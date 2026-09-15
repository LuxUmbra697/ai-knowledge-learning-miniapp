# 账号与微信身份

## 使用方式

H5 和小程序共用账号密码注册、登录、找回密码及账号安全页面。
小程序微信登录由后端交换真实 `wx.login` code。未登记的微信必须选择注册、验证并绑定已有账号或取消；取消不建号。
注册微信账号时可以同时设置账号名和密码，也可以稍后在个人中心设置。
从网页扫码注册后，可在账号安全中生成并保存恢复码；不会把未展示的恢复码标记为已设置。

H5 的微信入口采用小程序扫码确认，不把小程序 AppID 冒充网站开放平台 AppID。
浏览器展示官方小程序码，微信内核对确认码并明确确认后，浏览器才能兑换登录结果。
微信扫码注册、绑定、找回和换绑均沿用这条身份通路。已绑定别人的微信会被拒绝，两个已有账号的资料不会自动合并。

## 找回与换绑

- 注册账号或更新密码时显示一次高随机性恢复码。服务端只保存其 SHA-256 摘要；使用成功后立即失效。
- 找回密码可使用已保存的恢复码，或新近验证过的已绑定微信。没有绑定微信且没有恢复码的旧账号不能仅凭昵称重置。
- 账号安全页面可以验证当前密码/已绑定微信，然后更新密码、生成新恢复码或扫码换绑。
- 密码重置与微信绑定变更增加服务端会话版本，旧 token 会被拒绝；资料归属的用户 ID 不变。
- 没有邮件发送配置，不提供虚假的“邮件已发送”状态；没有实现邮件找回或不经校验的账号合并。

## 事务与边界

```mermaid
sequenceDiagram
  participant H as H5
  participant A as API / MySQL
  participant W as 微信小程序
  H->>A: 创建短期扫码请求
  A-->>H: 小程序码 + 私有轮询凭据
  W->>A: 扫码 scene + wx.login code
  A-->>W: 待确认操作与确认码
  W->>A: 注册 / 绑定 / 登录 / 取消
  A->>A: 校验账号、锁定状态、事务提交
  H->>A: 凭私有凭据检查并兑换
  A-->>H: 登录结果或一次性验证凭据
```

二维码只含随机 scene，不含浏览器轮询密钥或 JWT。验证凭据有 5 分钟时效、用途及 AppID 约束，只能兑换一次。
数据库使用行锁、微信唯一约束和会话版本检查处理并发；重置与旧密码登录并发时，旧密码不能获得重置后的有效会话。
认证输入禁止额外身份字段，输入校验错误不回显密码/恢复码。身份接口设独立持久化限速，二维码轮询顺序执行并可取消。

`account_security` 和 `identity_challenges` 由显式迁移 17 创建，应用启动不自动建表。
上线前先备份现有库，在独立副本恢复并验证迁移；不重建用户表或搬动学习记录。

## 微信发布条件

`WECHAT_QR_ENV=release` 为默认值，需要对应页面已正式发布。
开发/体验环境分别设置 `develop` / `trial`，仍受微信成员权限约束，不等同正式发布。
2026-09-15 实测：固定 AppID 配置匹配，开发版小程序码生成成功；正式版页面未发布，微信返回页面不可用。
同日使用真实微信 code 校验、小程序确认及 H5 私有凭据兑换完成登录，身份接口未 Mock。
自动化只代替摄像头跳转到 scene，未证明真机摄像头扫码通过。
因此这时不能宣称所有微信用户都可在公网扫码登录。发布后需重新检查正式小程序码、真机扫码、合法域名与身份绑定完整流程。

参考：[微信小程序登录](https://developers.weixin.qq.com/miniprogram/dev/framework/open-ability/login.html)、
[微信小程序码](https://developers.weixin.qq.com/miniprogram/dev/OpenApiDoc/qrcode-link/qr-code/getUnlimitedQRCode.html)、
[OWASP 密码找回安全建议](https://cheatsheetseries.owasp.org/cheatsheets/Forgot_Password_Cheat_Sheet.html)。

## English

Both targets share account credentials and recovery. WeChat identities are exchanged server-side;
unknown identities require explicit registration/link/cancel. H5 uses an official mini-program scene
code and explicit in-mini-program approval, not website OAuth with a mismatched AppID.

Recovery uses a previously saved one-time high-entropy recovery code or freshly verified bound
WeChat identity. Password reset and identity changes invalidate previous sessions through a SQL
session version. Account ownership stays on the original user ID; independently existing accounts
are not automatically merged. No email recovery is advertised without a mail provider.

QR scenes never include the browser redemption secret. Proofs expire after five minutes, are
purpose-scoped and single-use. Migration 17 is additive and must be backed up/rehearsed explicitly.
Development QR generation was verified; release QR still requires publication of the login page.
Real-device scanning, platform membership and publication are distinct acceptance gates.
