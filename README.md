# China Weather Agent Skill

面向智能体的中国公开天气查询技能。项目把国家气象中心 / 中央气象台、中国气象局天气页面、中国天气网的公开天气信息整理为结构化 JSON，方便 OpenClaw、Codex 或其他 agent 在行程规划、通勤判断、户外活动和天气态势查询中调用。

本项目不是官方服务，也不代表任何数据来源网站。它只按需读取公开页面和公开接口，不提供商业气象决策、应急指挥、航空铁路运行或交通管制依据。

## 功能

- 城市实况、7 天预报、空气质量、预警信号、近期小时观测。
- 未来逐小时预报数据，用于判断具体时段的降水和天气趋势。
- 中国气象局天气页面读取，包括首页、城市预报页、预警地图、卫星、降水和交通气象页面。
- 全国实况地图、今天 / 明天城市预报地图。
- 全国降水、风速、最高气温、最低气温排行。
- 全国公开预警列表，支持按省份、预警类型和等级过滤。
- 雷达、卫星图层和国家气象中心官方产品页。
- 台风海洋、交通、环境、农业、灾害风险和数值预报相关公开产品页。

## 目录结构

```text
.
├── SKILL.md
├── agents/
│   └── openai.yaml
├── references/
│   └── nmc-source.md
└── scripts/
    └── nmc_weather.py
```

## 环境要求

- Python 3.10 或更高版本。
- 能访问相关公开天气站点的网络环境。
- 不需要 API Key。
- 不需要登录账号。

脚本只使用 Python 标准库。

## 快速开始

查看能力清单：

```bash
python scripts/nmc_weather.py catalog
```

查询城市天气：

```bash
python scripts/nmc_weather.py query 北京 --province 北京
```

查询未来逐小时天气，并同时读取中国气象局城市页：

```bash
python scripts/nmc_weather.py query 广州 --province 广东 --hourly-forecast --include-cma
```

查询全国实况地图：

```bash
python scripts/nmc_weather.py map-weather --kind real --city 广州 --limit 20
```

查询预警：

```bash
python scripts/nmc_weather.py alerts --province 天津 --limit 20
```

查询雷达或卫星图层：

```bash
python scripts/nmc_weather.py layers --kind radar --limit 12
python scripts/nmc_weather.py layers --kind satellite --limit 12
```

检查连通性和城市覆盖：

```bash
python scripts/nmc_weather.py healthcheck --limit 12
python scripts/nmc_weather.py cma-healthcheck
```

## OpenClaw 示例

把整个项目目录复制到 OpenClaw 的技能目录，例如：

```text
.openclaw/skills/china-weather/
```

然后让 agent 使用这个技能查询天气：

```text
使用 china-weather 查询北京到上海明天下午是否有雨，并查看预警、雷达和可用的官方页面数据。
```

技能不会规定 agent 的固定回复模板。脚本只返回结构化数据、来源、发布时间和风险字段，最终回答由调用方根据用户问题和上下文组织。

## 数据来源

项目按需读取以下公开来源：

- 国家气象中心 / 中央气象台：`https://www.nmc.cn`
- 中国气象局天气页面：`https://weather.cma.cn`
- 中国天气网：`https://www.weather.com.cn`

请始终检查返回数据中的发布时间、抓取时间、页面生成时间和图像产品时间。天气预报具有不确定性，不同来源或不同发布时间的数据可能存在差异。

## 合规与使用边界

本项目定位为公开天气数据查询工具，不是绕过网站限制的爬虫框架。使用和二次开发时应遵守以下边界：

- 只访问公开页面和公开接口。
- 不访问登录后内容。
- 不绕过验证码、反爬、安全防护、访问控制或权限限制。
- 不采集、存储、处理或分发个人信息。
- 不使用代理池、高并发或大规模批量采集压测来源站点。
- 不在来源站点拒绝访问、返回安全拦截、限流或要求停止访问时继续绕过。
- 不声称本项目获得官方授权或代表官方服务。
- 不把查询结果包装成确定性的安全、交通、应急或专业气象决策依据。

建议在应用层增加缓存、限速和失败即停策略。例如城市天气结果可以在数分钟内复用，产品页和图像产品按需查询即可。

## 免责声明

本项目仅用于学习、研究和公开天气信息的辅助查询。项目作者和贡献者不对数据来源的可用性、完整性、准确性、及时性或连续性作任何保证。

天气预报、逐小时预报、风险字段和页面摘要均只供参考，不构成出行、安全、应急、交通、航空、铁路、航海、农业生产或专业气象决策建议。遇到强降水、强对流、台风、暴雪、大风、高温、道路结冰、地质灾害、山洪、海上天气等风险场景时，请以最新官方预警、主管部门通知、交通管制信息和现场实际情况为准。

使用者应自行遵守目标网站规则、robots 协议及所在地适用法律法规。任何违反法律法规、绕过安全措施、干扰网站正常运行、非法采集数据或造成第三方损失的行为，均由使用者自行承担责任。

## 许可证

本项目使用 MIT License。详见 [LICENSE](LICENSE)。
