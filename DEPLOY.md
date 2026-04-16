# 部署指南

本文档介绍如何将 `njust-schedule-mcp` 部署到 Ubuntu 服务器并接入 AstrBot。

---

## 前置条件

| 项目 | 要求 |
|------|------|
| 操作系统 | Ubuntu 20.04+ / Debian 11+ |
| Python | >= 3.10 |
| AstrBot | >= v3.5.0（MCP 支持），>= v4.14.0（定时提醒） |
| 网络 | 服务器需能访问 `202.119.81.112` 和 `202.119.81.113` |

> 如果你的服务器在校园网外，需要通过 VPN 或代理访问教务系统。

---

## 方式一：直接部署（推荐）

### Step 1. 安装系统依赖

```bash
# 中文字体（课表图片生成需要）
sudo apt update && sudo apt install -y fonts-noto-cjk-extra

# pip 和 uv
sudo apt install -y python3-pip
pip install uv --break-system-packages
```

### Step 2. 安装 MCP 服务器

```bash
pip install njust-schedule-mcp --break-system-packages
```

### Step 3. 配置 AstrBot

进入 AstrBot WebUI → **MCP 服务器** → **添加**：

```json
{
  "command": "env",
  "args": [
    "PORTAL_USERNAME=你的学号",
    "PORTAL_PASSWORD=你的密码",
    "uv",
    "tool",
    "run",
    "njust-schedule-mcp"
  ]
}
```

保存后重启 AstrBot。

### Step 4. 验证

对 QQ Bot 发送 `查一下这学期的课表`，如果返回课表信息则配置成功。

---

## 方式二：Docker 部署（AstrBot 容器内）

如果你的 AstrBot 通过 Docker 部署，需要在容器内安装依赖。

### Step 1. 进入容器

```bash
docker exec -it astrbot /bin/bash
```

### Step 2. 安装依赖

```bash
# 安装中文字体
apt update && apt install -y fonts-noto-cjk-extra

# 安装 uv 和 MCP 服务器
pip install uv --break-system-packages
pip install njust-schedule-mcp --break-system-packages
```

### Step 3. 退出并重启容器

```bash
exit
docker restart astrbot
```

### Step 4. 配置 AstrBot

与方式一相同，在 WebUI 中添加 MCP 服务器配置。

> **持久化提示**：Docker 容器重启后容器内安装的包会丢失。建议使用自定义 Dockerfile 或将安装命令写入 `docker-compose.yml` 的启动脚本中。

### Dockerfile 方案（推荐）

创建自定义 Dockerfile：

```dockerfile
FROM soulter/astrbot:latest

# 安装中文字体
RUN apt update && apt install -y fonts-noto-cjk-extra && rm -rf /var/lib/apt/lists/*

# 安装 MCP 服务器
RUN pip install uv njust-schedule-mcp --break-system-packages
```

```bash
docker build -t astrbot-njust .
docker run -d --name astrbot -p 6185:6185 astrbot-njust
```

---

## 方式三：从源码部署

适用于需要修改代码或贡献开发的场景。

### Step 1. 克隆仓库

```bash
git clone https://github.com/your-username/njust-schedule-mcp.git
cd njust-schedule-mcp
```

### Step 2. 安装系统依赖

```bash
sudo apt update && sudo apt install -y fonts-noto-cjk-extra
pip install uv --break-system-packages
```

### Step 3. 安装项目（开发模式）

```bash
pip install -e . --break-system-packages
```

### Step 4. 配置 AstrBot

在 WebUI 中添加 MCP 服务器配置，`args` 中的包名保持 `njust-schedule-mcp` 不变。

---

## 环境变量参考

所有环境变量通过 AstrBot MCP 配置中的 `env` 命令传入：

```json
{
  "command": "env",
  "args": [
    "PORTAL_USERNAME=学号",
    "PORTAL_PASSWORD=密码",
    "CACHE_DIR=/path/to/cache",
    "CAPTCHA_MAX_ATTEMPTS=5",
    "uv", "tool", "run", "njust-schedule-mcp"
  ]
}
```

| 变量 | 必填 | 默认值 | 说明 |
|------|------|--------|------|
| `PORTAL_USERNAME` | ✅ | — | 教务系统学号 |
| `PORTAL_PASSWORD` | ✅ | — | 教务系统密码 |
| `PORTAL_BASE_URL` | ❌ | `http://202.119.81.112:9080` | 教务系统地址 |
| `PORTAL_LOGIN_URL` | ❌ | `http://202.119.81.113:8080` | 登录地址 |
| `CACHE_DIR` | ❌ | `~/.njust-schedule-mcp/cache` | 缓存目录 |
| `CAPTCHA_MAX_ATTEMPTS` | ❌ | `3` | 验证码最大重试次数 |
| `SCHEDULE_CACHE_TTL_HOURS` | ❌ | `6` | 课表缓存有效期（小时） |
| `GRADES_CACHE_TTL_HOURS` | ❌ | `3` | 成绩缓存有效期（小时） |
| `EXAMS_CACHE_TTL_HOURS` | ❌ | `3` | 考试缓存有效期（小时） |

---

## 配置定时提醒

AstrBot v4.14.0+ 支持**主动型 Agent**，可以让 Bot 定时检查成绩和考试并主动推送。

### 启用主动型能力

在 AstrBot WebUI → **设置** 中启用"主动型能力"。

### 创建定时任务

直接对 Bot 发送自然语言指令：

| 指令 | 效果 |
|------|------|
| "每天晚上 8 点检查有没有新成绩" | 每日 20:00 调用 `check_grade_changes`，有变动则推送 |
| "每天早上 7 点告诉我今天有什么课" | 每日 07:00 调用 `query_today_schedule` 并推送 |
| "每天早上 7 点提醒我近 3 天的考试" | 每日 07:00 调用 `check_upcoming_exams(days=3)` |
| "每周一早上总结上周成绩变动" | 每周一调用 `check_grade_changes` |

也可以在 WebUI → **未来任务** 页面手动管理定时任务。

---

## 常见问题排查

### 课表图片中文显示为方块

```bash
# 检查字体是否安装
fc-list :lang=zh

# 如果没有输出，安装字体
sudo apt install -y fonts-noto-cjk-extra

# 刷新字体缓存
fc-cache -fv
```

### 登录频繁失败

- 检查服务器是否能访问教务系统：`curl -I http://202.119.81.113:8080`
- 增大验证码重试次数：在 MCP 配置中添加 `CAPTCHA_MAX_ATTEMPTS=5`
- 校园网外需要配置 VPN

### MCP 服务器启动失败

```bash
# 手动测试 MCP 服务器是否能启动
PORTAL_USERNAME=测试学号 PORTAL_PASSWORD=测试密码 uv tool run njust-schedule-mcp

# 检查依赖是否完整
python3 -c "import fastmcp, requests, bs4, ddddocr, PIL; print('OK')"
```

### Docker 容器重启后 MCP 失效

容器重启会丢失安装的包。使用 [Dockerfile 方案](#dockerfile-方案推荐) 或在 `docker-compose.yml` 中挂载持久化卷。

---

## 安全注意事项

1. **HTTP 明文传输**：NJUST 教务系统使用 HTTP（非 HTTPS），学号和密码在网络中以明文传输。建议仅在可信网络（校园网/VPN）中使用。
2. **密码保护**：不要将包含密码的 MCP 配置分享给他人或提交到 Git 仓库。
3. **文件权限**：缓存文件已设置为 `600`（仅 owner 可读写），请确保不要修改。
4. **日志安全**：敏感信息（密码、JSESSIONID、验证码）不会出现在 INFO 级别日志中，仅 DEBUG 级别可见。
