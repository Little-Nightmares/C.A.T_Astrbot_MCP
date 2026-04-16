# NJUST 教务系统 MCP 服务器

> 让你的 QQ Bot 帮你查课表、查成绩、查考试，还能定时提醒。

基于 [cat-schedule](https://github.com/ExSaltedFishPro/cat-schedule) 的数据获取方式，为 [AstrBot](https://github.com/Soulter/AstrBot) 提供 **NJUST（南京理工大学）** 教务系统的课表、成绩、考试查询功能。通过 MCP 协议挂载后，你的 QQ Bot 可以直接查询教务信息并定时提醒。

## 它能做什么

| 功能 | 说明 | 示例 |
|------|------|------|
| 📚 课表查询 | 按学期/周次查询，自动过滤当前周的课程 | "这周有什么课？" |
| 📅 今日课程 | 自动识别今天是周几、第几周 | "今天有什么课？" |
| 🖼️ 课表图片 | 生成日历样式的周课表图片 | "生成本周课表图片" |
| 📊 成绩查询 | 查询全部或按学期的成绩 | "查一下我的成绩" |
| 🔔 成绩变动 | 检测是否有新出分的科目 | "有没有新成绩？" |
| 📝 考试安排 | 查询考试时间和地点 | "考试安排是什么？" |
| ⏰ 定时提醒 | 每天自动推送今日课表、成绩变动等 | "每天早上 7 点提醒我今天的课" |

## 效果预览

对 Bot 说 **"生成本周课表图片"**，会返回这样的图片：

```
┌─────────────────────────────────────────────┐
│         📚 课表 · 第 7 周 · 2025-2026-2      │
├──────┬──────┬──────┬──────┬──────┬──────┬────┤
│ 周一 │ 周二 │ 周三 │ 周四 │ 周五 │ 周六 │周日│
├──────┼──────┼──────┼──────┼──────┼──────┼────┤
│      │ 高数 │      │      │ 心理 │      │    │
│      │      │      │      │      │      │    │
├──────┼──────┼──────┼──────┼──────┼──────┼────┤
│      │ 体育 │      │ Python│ 英语 │      │    │
│ 程设 │      │ 网安 │      │      │      │    │
├──────┼──────┼──────┼──────┼──────┼──────┼────┤
│ 高数 │ Python│      │ 高数 │ 创业 │      │    │
│      │ 物理 │      │ 近代史│ 物理 │      │    │
├──────┼──────┼──────┼──────┼──────┼──────┼────┤
│      │ 创业 │      │ 近代史│ 形策 │      │    │
│      │ 物实 │      │ 工实 │ 网安 │      │    │
└──────┴──────┴──────┴──────┴──────┴──────┴────┘
```

## 前置条件

- 一个运行中的 [AstrBot](https://github.com/Soulter/AstrBot) 实例（>= v3.5.0）
- 服务器能访问南京理工大学教务系统（校园网或 VPN）
- Python >= 3.10

> **注意**：本项目目前仅支持 **单用户** 使用（一个 Bot 绑定一个教务系统账号）。如果多人需要使用，每人需要部署自己的 MCP 服务器。

## 快速开始（3 分钟）

### Step 1: 安装

```bash
# 安装中文字体（课表图片需要）
sudo apt update && sudo apt install -y fonts-noto-cjk-extra

# 从 GitHub 克隆并安装
git clone https://github.com/Little-Nightmares/C.A.T_Astrbot_MCP.git
cd C.A.T_Astrbot_MCP
pip install . --break-system-packages
```

> 如果你的 AstrBot 运行在 Docker 中，先进入容器再执行上述命令：
> ```bash
> docker exec -it astrbot /bin/bash
> ```

### Step 2: 在 AstrBot 中配置

进入 AstrBot WebUI → **MCP 服务器** → **添加**，填入：

```json
{
  "command": "python3",
  "args": [
    "-m", "njust_schedule_mcp.server",
    "--username", "你的学号",
    "--password", "你的密码",
    "--semester-start-date", "2026-03-02"
  ]
}
```

**参数说明：**

| 参数 | 必填 | 说明 |
|------|------|------|
| `--username` | ✅ | 教务系统学号 |
| `--password` | ✅ | 教务系统密码 |
| `--semester-start-date` | 推荐 | 学期第一周周一的日期（YYYY-MM-DD），用于自动计算当前是第几周 |

> **如何确定 `semester-start-date`？** 查看教务系统课表页面，找到第一周周一的日期。例如 2025-2026 学年第二学期第一周周一是 2026 年 3 月 2 日，就填 `2026-03-02`。

### Step 3: 重启 AstrBot 并测试

重启 AstrBot 后，对 QQ Bot 发送：

```
帮我查一下这学期的课表
```

如果返回课表信息，说明配置成功！

你也可以直接让 Bot 帮你绑定（对话中说出学号和密码即可），Bot 会自动调用绑定工具。

## 使用方式

配置完成后，直接对 QQ Bot 用自然语言说话就行：

**课表相关：**
- "查一下这学期的课表"
- "今天有什么课？"
- "下周有什么课？"
- "生成本周课表图片"
- "生成第 5 周的课表图片"

**成绩相关：**
- "查一下我的成绩"
- "2024-2025-1 学期的成绩"
- "有没有新出的成绩？"

**考试相关：**
- "考试安排是什么？"
- "近期有考试吗？"

**其他：**
- "刷新一下缓存"（教务系统数据有更新时使用）

## 定时提醒

AstrBot v4.14.0+ 支持**主动型 Agent**，可以让 Bot 定时帮你检查并推送。

**启用方式：** 在 AstrBot WebUI → **设置** 中开启"主动型能力"，然后直接对 Bot 说：

| 你说的话 | 效果 |
|---------|------|
| "每天早上 7 点告诉我今天有什么课" | 每天自动推送当日课表 |
| "每天晚上 8 点检查有没有新成绩" | 有新成绩时自动通知你 |
| "每天早上提醒我近 3 天的考试" | 考试前 3 天开始提醒 |

## 进阶配置

### 通过 .env 文件配置（替代命令行参数）

如果你不想在 MCP 配置中写密码，可以用 `.env` 文件：

```bash
mkdir -p ~/.njust-schedule-mcp
cat > ~/.njust-schedule-mcp/.env << 'EOF'
PORTAL_USERNAME=你的学号
PORTAL_PASSWORD=你的密码
SEMESTER_START_DATE=2026-03-02
EOF
chmod 600 ~/.njust-schedule-mcp/.env
```

然后 MCP 配置简化为：

```json
{
  "command": "python3",
  "args": ["-m", "njust_schedule_mcp.server"]
}
```

### 完整环境变量列表

| 变量 | 说明 | 默认值 |
|------|------|--------|
| `PORTAL_USERNAME` | 教务系统学号 | 无（必填） |
| `PORTAL_PASSWORD` | 教务系统密码 | 无（必填） |
| `SEMESTER_START_DATE` | 学期第一天日期（周一，YYYY-MM-DD） | 无（建议配置） |
| `PORTAL_BASE_URL` | 教务系统地址 | `http://202.119.81.112:9080` |
| `PORTAL_LOGIN_URL` | 登录地址（多个用逗号分隔） | `http://202.119.81.113:8080,http://202.119.81.112:9080` |
| `CAPTCHA_MAX_ATTEMPTS` | 验证码最大重试次数 | `3` |
| `SCHEDULE_CACHE_TTL_HOURS` | 课表缓存时间（小时） | `6` |
| `GRADES_CACHE_TTL_HOURS` | 成绩缓存时间（小时） | `3` |
| `EXAMS_CACHE_TTL_HOURS` | 考试缓存时间（小时） | `3` |

### Docker 部署

详见 [DEPLOY.md](DEPLOY.md)，包含 Dockerfile 方案和数据持久化配置。

## 常见问题

### Q: 课表图片中文显示为方块？

```bash
sudo apt install -y fonts-noto-cjk-extra
```

### Q: 登录失败？

1. 确认学号密码正确
2. 确认服务器能访问教务系统（校园网或 VPN）
3. 验证码识别偶尔会失败，默认自动重试 3 次

### Q: 课表显示了所有周次的课，没有按当前周过滤？

需要配置 `--semester-start-date` 参数（学期第一周周一的日期），Bot 才能算出当前是第几周。

### Q: 提示"教务系统会话已过期"？

正常现象，会自动重新登录。频繁出现则检查网络。

### Q: 支持其他学校吗？

目前仅适配 NJUST 强智科技教务系统。

## 工作原理

```
┌─────────┐    MCP (stdio)    ┌──────────────────┐    HTTP    ┌──────────────┐
│ AstrBot │ ◄──────────────► │ njust-schedule-mcp │ ◄────────► │ NJUST 教务系统 │
│ (QQ Bot)│                   │   (本 MCP 服务器)   │            │  (强智科技)   │
└─────────┘                   └──────────────────┘            └──────────────┘
```

1. AstrBot 通过 MCP 协议与本服务器通信
2. 本服务器用 requests + BeautifulSoup 抓取教务系统
3. 验证码通过 ddddocr 本地 OCR 识别，自动重试
4. 会话自动续期，数据智能缓存

## 技术栈

- [FastMCP](https://github.com/jlowin/fastmcp) — MCP 协议 Python SDK
- requests + BeautifulSoup4 — 教务系统抓取与解析
- [ddddocr](https://github.com/sml2h3/ddddocr) — 验证码识别
- Pillow — 课表图片生成
- python-dotenv — 配置管理

## 致谢

- [cat-schedule](https://github.com/ExSaltedFishPro/cat-schedule) — 教务系统数据获取方式参考
- [AstrBot](https://github.com/Soulter/AstrBot) — MCP 协议支持和主动型 Agent

## 许可证

[MIT License](LICENSE)
