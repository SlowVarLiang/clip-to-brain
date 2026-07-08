# Ubuntu API 服务器部署

## 最简单（推荐）

1. 把 **整个 `video-parser` 文件夹** 复制到 Ubuntu（U 盘 / scp 均可）
2. 一条命令：

```bash
cd ~/video-parser
sudo bash install-ubuntu.sh --lan-only
```

`--lan-only`：防火墙只允许局域网访问 8765 端口。

脚本结束时会打印 **API Key** 和测试 curl，请保存 Key。

---

## 从 Windows 复制

```powershell
scp -r D:\0-CryptoLumis\5-automedia\video-parser 用户名@Ubuntu的IP:~/
```

---

## 调用示例

```bash
curl -X POST "http://Ubuntu的IP:8765/pipeline" \
  -H "Content-Type: application/json" \
  -H "X-API-Key: 你的密钥" \
  -d '{"url":"https://www.xiaohongshu.com/discovery/item/xxx"}'
```

---

## 默认安全配置

| 项 | 值 |
|----|-----|
| API Key | 必须（自动生成） |
| Swagger /docs | 关闭 |
| Web UI | 关闭 |
| 限流 | 20 次/分钟/IP |
| 转写 URL | CDN 白名单 + 禁止内网 |
| GTX 1050 Ti | small + int8 |

---

## 运维

```bash
sudo systemctl status video-parser-api
sudo systemctl restart video-parser-api
sudo journalctl -u video-parser-api -f
```

---

## 商业多租户（每客户独立 API Key）

适合 SaaS / 按量计费：每个客户一个 Key，独立限流与月度转写额度。

```bash
cd ~/video-parser
source .venv/bin/activate

# 新增客户：每月 1000 次转写，每分钟最多 30 次
python scripts/manage_accounts.py add --name "客户A" --quota 1000 --rate 30

# 查看所有账户与本月用量
python scripts/manage_accounts.py list

# 禁用 / 启用 / 轮换 Key
python scripts/manage_accounts.py disable acct_xxxx
python scripts/manage_accounts.py rotate acct_xxxx
```

客户调用时在 Header 带上自己的 Key：

```bash
curl -H "X-API-Key: vp_客户专属密钥" http://IP:8765/account/me
```

| 能力 | 说明 |
|------|------|
| 独立 Key | 每账户 `vp_` 前缀，哈希存储，创建时仅显示一次 |
| 按账户限流 | `--rate 30` 或 0=用全局 `RATE_LIMIT_PER_MINUTE` |
| 月度额度 | `--quota 1000`，仅 **转写成功** 计 1 次；解析不计费 |
| 兼容旧模式 | `.env` 的 `API_KEY` 仍可作为管理员/自用 Key |

`accounts.json` 含密钥哈希，勿提交 Git（已在 `.gitignore`）。

---

## 调优（编辑 `.env` 后 restart）

- 显存够：`WHISPER_MODEL=medium`
- 放宽限流：`RATE_LIMIT_PER_MINUTE=30`
- 开发调试：`DOCS_ENABLED=true` `SERVE_WEB_UI=true`（勿公网）
