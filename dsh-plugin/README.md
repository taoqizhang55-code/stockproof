# dsh-plugin-marketmood

在 DeepSeek Harness（DSH）里直接问股票：新闻情绪、财报解读、公告、异动原因、财报日历、研究结论。
美股、A 股、港股都支持，**每条信息都附原文链接**，数字由工具计算，AI 只负责组织语言。

Ask DeepSeek Harness about stocks — news mood, earnings reports, announcements, why a stock moved, the
earnings calendar and research findings — for US, China A-share and Hong Kong stocks, with source links.

> Tested with DSH 0.2.x (developer preview). DSH may change its plugin interfaces; please open an issue if
> something breaks.

## 你可以这样问 / Try asking

- 宁德时代最近怎么样？ / How is NVDA doing?
- 茅台今天为什么跌了？ / Why did MSFT jump yesterday?
- 宁德时代这期财报和上期比，变了什么？
- 全市场业绩最强的 A 股有哪些？江波龙的证据评分卡怎么样？
- 下周哪些公司发财报？
- 我关注的股票今天有什么重要的事？
- 业绩超预期的股票，之后会继续涨吗？（基于 1 万多次财报的研究）

## 安装 / Install

适用于任何电脑（macOS / Windows / Linux，桌面版和 `dsh web` 都可以）。Works on any computer, desktop app included:

```bash
pip install "marketmood[mcp,cn]"        # Python 3.10+（A 股/港股需要 3.11+）
marketmood mcp --install-dsh            # 自动找到这台电脑上的 Python，写入 DSH 配置（会先备份）
```

然后重启 DSH，问它"我关注的股票今天有什么重要的事？"。工具名形如 `mcp__marketmood__stock_brief`。
Restart DSH and ask away.

- `--install-dsh` 写入 `~/.dsh/cordis.patch.yml`（DSH 所有配置都会读取它，包括桌面版；设置了 `DSH_HOME` 就写到那里）。
  原有内容保留，文件先备份；再运行一次是更新，不会重复添加。`marketmood mcp --uninstall-dsh` 可以删除。
- API key 不写进任何文件：从程序坞打开的 App 看不到终端里的环境变量，所以 marketmood 启动时自己从你的
  shell 读取 `DEEPSEEK_API_KEY`（只在内存中使用）。Windows 上系统环境变量本来就对所有程序可见。
- 数据默认放在运行安装命令时所在文件夹的 `marketmood_data` 里，可以用 `--data-dir` 指定。

**用 `dsh plugin` 安装（web 配置）/ As a DSH plugin package:** `dsh plugin --profile web add github:taoqizhang55-code/marketmood#main&path:/dsh-plugin`。
这种方式需要在启动 dsh 的终端里设置 `MARKETMOOD_PYTHON`（装了 marketmood 的 python）和 `MARKETMOOD_HOME`（数据文件夹）。
桌面版的插件由 App 自己管理，建议用上面的 `--install-dsh`。

第一次使用：对 DSH 说"关注 600519、AAPL、00700"，它会调用 `refresh_stock` 抓取数据（每只约 30–60 秒）。

## 工具 / Tools

在 DSH 里问"你能做什么？"，会调用 `marketmood_menu` 按下面四组列出全部功能和示例问题。

**日常看盘 / Daily**

| Tool | 作用 | LLM 费用 |
|---|---|---|
| `watchlist` | 关注列表：今日涨跌、新闻情绪、最新财报语气/SUE | 无 |
| `stock_brief` | 单只股票全貌：行情、新闻（附链接）、财报解读、业绩惊喜、历史同类财报表现、下次财报日、公告 | 无 |
| `why_did_it_move` | 解释某天的异动，只用当天前后的新闻/公告/财报，标注引用和把握程度 | 1 次（缓存） |
| `compare_with_last_report` | 最新两期财报对比：业绩、展望、风险、业务、分红回购的变化 | 1 次（缓存） |
| `company_announcements` | A 股/港股公告，分类、重要程度、AI 摘要 | 无 |
| `earnings_calendar` | 未来几天谁发财报（美股含盘前/盘后和分析师预期） | 无 |
| `daily_digest` | 今日简报 | 生成新的时有 |
| `refresh_stock` / `add_to_watchlist` / `remove_from_watchlist` | 关注新股票并抓取数据 / 管理关注列表 | 少量 / 无 |

**选股与评分卡 / Screen & scorecards**

| Tool | 作用 | LLM 费用 |
|---|---|---|
| `screen_stocks` | 全市场 A 股选股名单（附理由和历史检验），或查任意一只的排名 | 无 |
| `evidence_scorecard` | 证据评分卡：各维度分数、出处、利好/风险、每项是否经过历史检验 | 1 次（缓存） |

**量化实验室 / Quant lab**（DeepSeek 自己做不到的计算 / computation the model can't do alone）

| Tool | 作用 | LLM 费用 |
|---|---|---|
| `lab_capabilities` | 能检验哪些想法、数据范围、锁定区间、已尝试版本数 | 无 |
| `lab_backtest` | 回测任意想法（财报 / 业绩预告 / 政策信号 / 因子），扣费、涨跌停，自动打开图文报告；按尝试次数修正显著性 | 无 |
| `lab_confirm` | 在锁定的近两年数据上做一次样本外检验（每个策略只能一次） | 无 |
| `lab_similar` | 和这只股票最新财报类似的历史情况，之后一般怎么走 | 无 |
| `lab_screen` | 任意条件筛选全部 A 股（ROE、增长、估值、市值、行业…） | 无 |
| `lab_policy_history` | 新闻联播十年政策信号，以及之后行业表现 | 无 |
| `lab_experiments` / `research_findings` | 实验记录 / 内置研究结论 | 无 |

**持仓体检 / Portfolio**

| Tool | 作用 | LLM 费用 |
|---|---|---|
| `portfolio_checkup` | 集中度、同涨同跌、风险来源、历史大跌重演，自动打开报告 | 无 |

**网页看板 / Dashboard**

| Tool | 作用 | LLM 费用 |
|---|---|---|
| `open_dashboard` | 在后台启动本地网页看板并在浏览器打开（可指定页：首页、股票、选股、实验室、持仓体检、研究）；说"打开网页看板"即可 | 无 |

第一次使用时，DeepSeek 会在对话里介绍全部功能，并推荐打开网页看板体验（不会自己弹窗）；之后说"打开网页看板"随时打开，问"你能做什么"随时列出全部功能。

输入 `/marketmood` 可以在"技能"里选现成的问题（`marketmood mcp --install-dsh` 会一起装好）：打开网页看板、能做什么、看盘、为什么涨跌、财报对比、评分卡、选股、回测想法、类似情况、持仓体检。

## 数据与隐私 / Data and privacy

- 数据来源：Yahoo/Google 新闻 RSS、SEC EDGAR、东方财富与新浪（经 AKShare）、Nasdaq 公开日历。
  这些是免费的公开接口，可能变化或限流；东方财富请求过快会被暂时拒绝，marketmood 已自动放慢并在被拒时停止。
- 所有数据保存在本机 `MARKETMOOD_HOME/marketmood_data`，API 密钥不会写入任何文件。
- 仅供信息和研究参考，不构成投资建议。

MIT License.
