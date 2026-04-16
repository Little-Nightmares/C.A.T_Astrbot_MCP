# NJUST 教务系统 MCP 服务器

基于 [cat-schedule](https://github.com/ExSaltedFishPro/cat-schedule) 的数据获取方式，为 [AstrBot](https://github.com/Soulter/AstrBot) 提供 NJUST（南京理工大学）教务系统的课表、成绩、考试查询功能。通过 MCP 协议挂载后，你的 QQ Bot 可以直接查询教务信息并定时提醒。

## 功能特性

- **课表查询** — 按学期/周次查询课表，支持生成日历样式的课表图片
- **成绩查询** — 查询全部/按学期的成绩，支持成绩变动检测
- **考试安排** — 查询考试安排，支持近期考试提醒
- **自动登录** — 验证码自动识别（ddddocr），会话自动续期
- **智能缓存** — 内存 + 文件多级缓存，减少对教务系统的请求
- **定时提醒** — 配合 AstrBot 主动型 Agent 实现定时检查和推送
- **图片课表** — Pillow 绘制精美的日历样式周课表图片

## 环境要求

- Python >= 3.10
- AstrBot >= v3.5.0（MCP 支持）
- AstrBot >= v4.14.0（主动型 Agent 定时提醒）
- 操作系统：Ubuntu / Debian / macOS / Windows（已适配 Ubuntu 服务器环境）

## 快速开始

### 1. 安装系统依赖

```bash
# 安装中文字体（课表图片生成需要）
sudo apt update && sudo apt install -y fonts-noto-cjk-extra

# 安装 uv（AstrBot MCP 启动工具）
pip install uv --break-system-packages
```

### 2. 安装 MCP 服务器

```bash
pip install njust-schedule-mcp --break-system-packages
```

### 3. 配置凭据

创建配置文件（**不要提交到 Git**）：

```bash
mkdir -p ~/.njust-schedule-mcp
cat > ~/.njust-schedule-mcp/.env << 'EOF'
PORTAL_USERNAME=你的学号
PORTAL_PASSWORD=你的密码
EOF
chmod 600 ~/.njust-schedule-mcp/.env
```

### 4. 在 AstrBot 中配置

进入 AstrBot WebUI → **MCP 服务器** → **添加**，填入以下配置：

```json
{
  "command": "python3",
  "args": ["-m", "njust_schedule_mcp.server"]
}
```

> **说明**：`python3` 是 AstrBot 允许的 MCP 启动命令。凭据通过 `~/.njust-schedule-mcp/.env` 文件传递，不需要在 MCP 配置中填写。
>
> 如果你的 AstrBot 通过 Docker 部署，请确保容器内已安装 `njust-schedule-mcp` 包（`pip install njust-schedule-mcp --break-system-packages`）。

### 5. 验证

对 QQ Bot 发送 `帮我查一下这学期的课表`，如果返回课表信息则配置成功。

## 使用方式

绑定账号后，可以直接对 QQ Bot 发送自然语言：

| 你说的话 | Bot 调用的工具 |
|---------|--------------|
| "查一下这学期的课表" | `query_schedule` |
| "今天有什么课？" | `query_today_schedule` |
| "生成本周课表图片" | `generate_schedule_image` |
| "查一下我的成绩" | `query_grades` |
| "2024-2025-1 学期的成绩" | `query_grades(term="2024-2025-1")` |
| "考试安排是什么？" | `query_exams` |
| "刷新一下缓存" | `refresh_cache` |

## MCP 工具列表

| 工具名 | 参数 | 说明 |
|--------|------|------|
| `bind_account` | `username`, `password` | 绑定教务系统账号密码 |
| `query_schedule` | `term`（可选） | 查询指定学期的课表 |
| `query_today_schedule` | 无 | 查询今天的课程 |
| `query_week_schedule` | 无 | 查询本周课程 |
| `generate_schedule_image` | `week`（可选，0=本周） | 生成日历样式的课表图片 |
| `query_grades` | `term`（可选） | 查询成绩 |
| `query_exams` | `term`（可选） | 查询考试安排 |
| `check_grade_changes` | 无 | 检查成绩变动（供定时任务调用） |
| `check_upcoming_exams` | `days`（可选，默认7） | 检查近期考试（供定时任务调用） |
| `refresh_cache` | 无 | 手动刷新所有缓存 |

## 定时提醒配置

确保 AstrBot 配置中 **"主动型能力"** 已启用（v4.14.0+），然后直接对 Bot 说：

- "每天晚上 8 点检查有没有新成绩"
- "每天早上 7 点告诉我今天有什么课和近期考试"
- "每周一早上提醒我这周的考试安排"

AstrBot 会自动创建 FutureTask，定时调用 MCP 工具并通过 QQ 推送结果。

## 环境变量

凭据和配置通过 `~/.njust-schedule-mcp/.env` 文件或系统环境变量设置。`.env` 文件优先级更高。

| 变量 | 说明 | 默认值 |
|------|------|--------|
| `PORTAL_USERNAME` | 教务系统学号 | 无（必填） |
| `PORTAL_PASSWORD` | 教务系统密码 | 无（必填） |
| `PORTAL_BASE_URL` | 教务系统地址 | `http://202.119.81.112:9080` |
| `PORTAL_LOGIN_URL` | 登录地址 | `http://202.119.81.112:9080` |
| `PORTAL_LOGIN_PATH` | 登录路径 | `/` |
| `PORTAL_LESSONS_PATH` | 课表路径 | `/njlgdx/xskb/xskb_list.do` |
| `PORTAL_GRADES_PATH` | 成绩路径 | `/njlgdx/kscj/cjcx_list` |
| `PORTAL_EXAMS_PATH` | 考试路径 | `/njlgdx/xspjgl/kscjcx_list.do` |
| `PORTAL_TIMEOUT` | 请求超时（秒） | `20` |
| `CAPTCHA_MAX_ATTEMPTS` | 验证码最大重试次数 | `3` |
| `CACHE_DIR` | 缓存目录 | `~/.njust-schedule-mcp/cache` |
| `CACHE_TTL_MINUTES` | 默认缓存有效期（分钟） | `30` |
| `SCHEDULE_CACHE_TTL_HOURS` | 课表缓存有效期（小时） | `6` |
| `GRADES_CACHE_TTL_HOURS` | 成绩缓存有效期（小时） | `3` |
| `EXAMS_CACHE_TTL_HOURS` | 考试缓存有效期（小时） | `3` |

## 项目结构

```
njust-schedule-mcp/
├── pyproject.toml                          # 项目配置 + 依赖
├── README.md                               # 本文件
├── DEPLOY.md                               # 详细部署指南
├── .env.example                            # 环境变量模板
├── .gitignore
├── LICENSE
└── src/njust_schedule_mcp/
    ├── server.py                           # MCP 服务器入口 + 工具定义
    ├── config.py                           # 环境变量 / .env 配置管理
    ├── cache.py                            # 缓存管理（内存 + 文件）
    ├── image_gen.py                        # 课表图片生成（Pillow）
    └── portal/
        ├── client.py                       # 教务系统 HTTP 客户端
        ├── captcha.py                      # 验证码识别（ddddocr）
        └── parsers.py                      # HTML 解析器
```

## 工作原理

```
┌─────────┐    MCP (stdio)    ┌──────────────────┐    HTTP    ┌──────────────┐
│ AstrBot │ ◄──────────────► │ njust-schedule-mcp │ ◄────────► │ NJUST 教务系统 │
│ (QQ Bot)│                   │   (本 MCP 服务器)   │            │  (强智科技)   │
└─────────┘                   └──────────────────┘            └──────────────┘
                                      │
                              ┌───────┴───────┐
                              │  .env + 缓存    │
                              │ ~/.njust-...   │
                              └───────────────┘
```

1. AstrBot 通过 MCP 协议（stdio）与本服务器通信
2. 本服务器从 `~/.njust-schedule-mcp/.env` 读取凭据
3. 使用 requests + BeautifulSoup 抓取 NJUST 教务系统
4. 登录验证码通过 ddddocr 本地识别，自动重试
5. JSESSIONID 会话持久化到文件，过期自动重新登录
6. 课表/成绩/考试数据缓存到本地文件，减少重复请求

## 技术栈

- **MCP 框架**：[FastMCP](https://github.com/jlowin/fastmcp) — MCP 协议 Python SDK
- **HTTP 请求**：requests — 教务系统页面抓取
- **HTML 解析**：BeautifulSoup4 — 课表/成绩/考试页面解析
- **验证码识别**：ddddocr — 本地 OCR 验证码识别
- **图片生成**：Pillow — 日历样式课表图片绘制
- **配置管理**：python-dotenv — .env 文件加载

## 常见问题

### Q: 课表图片中文显示为方块/乱码？

**A:** Ubuntu 服务器需要安装中文字体：

```bash
sudo apt install -y fonts-noto-cjk-extra
```

安装后无需重启，下次生成图片时自动生效。

### Q: 登录失败，提示验证码识别错误？

**A:** ddddocr 对部分验证码识别率不是 100%，默认会自动重试 3 次。可以在 `.env` 中增大重试次数：

```bash
echo "CAPTCHA_MAX_ATTEMPTS=5" >> ~/.njust-schedule-mcp/.env
```

### Q: 提示"教务系统会话已过期"？

**A:** 正常现象，服务器会自动重新登录。如果频繁过期，可能是教务系统维护或网络不稳定。

### Q: 如何在 Docker 中使用？

**A:** 参考 [DEPLOY.md](DEPLOY.md) 中的 Docker 部署方案。

### Q: 支持其他学校吗？

**A:** 目前仅适配 NJUST（南京理工大学）强智科技教务系统。如需适配其他学校，需要修改 `config.py` 中的教务系统地址和 `parsers.py` 中的 HTML 解析逻辑。

## 致谢

- [cat-schedule](https://github.com/ExSaltedFishPro/cat-schedule) — 教务系统数据获取方式参考
- [AstrBot](https://github.com/Soulter/AstrBot) — MCP 协议支持和主动型 Agent
- [FastMCP](https://github.com/jlowin/fastmcp) — MCP 协议 Python SDK
- [ddddocr](https://github.com/sml2h3/ddddocr) — 验证码识别

## 许可证

MIT License
