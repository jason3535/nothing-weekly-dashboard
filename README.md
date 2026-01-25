# Nothing 用户反馈周报系统

自动化抓取、分析并生成 Nothing 品牌 Reddit 社区用户反馈的周度报告。

## 🌐 在线查看

[点击查看最新周报](https://jason3535.github.io/nothing-weekly-dashboard/)

## ✨ 功能特性

- **自动化抓取**：每周自动抓取 r/Nothing 社区的软件相关反馈
- **智能分类**：按 UI/UX、性能、相机、Glyph 灯效、连接问题等分类
- **情感分析**：识别正面/负面/中性反馈，支持讽刺检测
- **专有名词保护**：Nothing、CMF、Glyph 等品牌术语不被翻译
- **可视化看板**：交互式 HTML 报告，支持深色/浅色主题切换
- **自动部署**：GitHub Actions 自动生成并部署到 GitHub Pages

## 📊 报告示例

- **TOP 问题排行**：按热度排序的热门问题
- **情感分析**：负面反馈占比统计
- **分类分布**：各问题类别的分布情况
- **热门讨论**：高互动度帖子和评论
- **趋势分析**：问题出现的时序趋势

## 🚀 快速部署

### 方法一：GitHub Pages（推荐）

1. **Fork 仓库**到你的 GitHub 账户
2. **启用 GitHub Pages**：
   - 进入仓库 Settings → Pages
   - Branch 选择 `main`，文件夹选择 `/ (root)`
   - 点击 Save，等待部署完成（约1-2分钟）
3. **配置自动更新**：
   - GitHub Actions 工作流已配置为每周五自动运行
   - 如需立即生成，可手动触发 Actions → Weekly Report Update → Run workflow

### 方法二：本地部署

```bash
# 克隆仓库
git clone https://github.com/jason3535/nothing-weekly-dashboard.git
cd nothing-weekly-dashboard

# 安装依赖
pip install -r requirements.txt

# 生成最新周报（跳过抓取，使用现有数据）
python run.py --skip-scrape --open

# 完整运行（抓取+处理+生成）
python run.py
```

## ⚙️ 配置说明

### config.yaml 主要配置项

```yaml
reddit:
  subreddit: "Nothing"     # Reddit 社区名称
  posts_limit: 200         # 抓取数量限制
  request_delay: 2         # 请求间隔（秒）

# 排除关键词（不相关内容）
exclude_keywords:
  - "watch"                # 手表相关
  - "ear"                  # 耳机相关
  - "should i buy"         # 购买建议等

# 软件相关关键词
keywords:
  software: ["Nothing OS", "update", "bug", "issue"]
  ui_ux: ["UI", "UX", "interface", "design"]
  performance: ["lag", "slow", "battery", "drain"]
  # ... 其他分类

# 情感分析关键词
sentiment:
  negative: ["bug", "issue", "problem", "broken"]
  positive: ["love", "great", "good", "beautiful"]
  sarcasm_patterns: ["then i saw", "unfortunately", "but then"]
```

## 🔧 自定义配置

### 1. 修改分类规则
编辑 `config.yaml` 中的 `keywords` 部分，调整关键词列表

### 2. 调整情感分析
- 添加/删除 `sentiment.negative` 和 `sentiment.positive` 关键词
- 更新 `sarcasm_patterns` 优化讽刺检测

### 3. 专有名词保护
编辑 `src/processor.py` 中的 `protected_terms` 列表，添加需要保护的品牌术语

## 🔄 自动化流程

### GitHub Actions 工作流
- 每周五 17:00 UTC 自动运行
- 抓取最新 Reddit 数据
- 处理并生成 HTML 报告
- 自动提交并部署到 GitHub Pages

### 本地定时任务（macOS/Linux）
```bash
# 编辑 crontab
crontab -e

# 添加以下行（每周五下午5点执行）
0 17 * * 5 cd /path/to/nothing-weekly-dashboard && ./cron_job.sh
```

## 📁 项目结构

```
nothing-weekly-dashboard/
├── config.yaml              # 配置文件
├── run.py                   # 主入口脚本
├── cron_job.sh              # 定时任务脚本
├── requirements.txt         # Python 依赖
├── src/                     # 源代码
│   ├── scraper.py          # Reddit 爬虫
│   ├── processor.py        # 数据处理器
│   └── generator.py        # HTML 生成器
├── data/                    # 数据存储
│   ├── raw_data_*.json     # 原始 Reddit 数据
│   └── processed_data_*.json # 处理后的数据
├── templates/               # HTML 模板
│   └── dashboard.html
├── output/                  # 生成的文件
│   └── week_*.html         # 周报 HTML 文件
└── .github/workflows/      # GitHub Actions 工作流
    └── weekly-update.yml
```

## 🔍 调试工具

项目包含调试工具 `analyze_posts.py`，用于分析帖子过滤原因：

```bash
# 分析特定帖子为什么没有被包含
python analyze_posts.py
```

## 📈 数据统计

最新周报统计数据：
- 软件相关帖子：83篇
- 负面反馈占比：50.6%
- 分类分布：UI/UX 28篇，性能 20篇，相机 9篇等

## 🤝 贡献

欢迎提交 Issue 和 Pull Request 来改进项目：

1. Fork 项目
2. 创建功能分支 (`git checkout -b feature/improvement`)
3. 提交更改 (`git commit -am 'Add some improvement'`)
4. 推送到分支 (`git push origin feature/improvement`)
5. 创建 Pull Request

## 📄 许可证

MIT License

## 📧 联系方式

如有问题或建议，请通过 GitHub Issues 提交反馈。

---

**更新日期**: 2026年1月24日
**最新周报**: [2026年第4周（01月19日 - 01月25日）](https://jason3535.github.io/nothing-weekly-dashboard/)