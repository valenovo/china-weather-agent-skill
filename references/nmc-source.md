# 天气来源说明

数据源：国家气象中心 / 中央气象台，`https://www.nmc.cn`。

## 城市天气端点

`scripts/nmc_weather.py query` 使用的国家气象中心端点：

- `GET /rest/province/all`：省级列表。
- `GET /rest/province/{province_code}`：某省城市和站点列表。
- `GET /rest/weather?stationid={station_code}`：单城市天气数据。

`/rest/weather` 常用字段：

- `data.real`：实况、城市预警信号、日出日落。
- `data.predict`：7 天预报和发布时间。
- `data.air`：空气质量字段。
- `data.passedchart`：近期小时观测。
- `data.tempchart`：日温度图，可能包含过去、当前和未来日期。
- `data.climate`：月度气候常年值。
- `data.radar`：区域雷达图片元数据。

## 全国地图和排行端点

- `GET /rest/real/map/latestHour.json`：全国国家级站点最新小时实况地图数据，包含站名、经纬度、1 小时降水、气温、湿度、气压、风向、风速。
- `GET /dataservice/weather/map/ALL/day1.json`：全国今天城市预报地图。
- `GET /dataservice/weather/map/ALL/day2.json`：全国明天城市预报地图。
- `GET /rest/realrank/{type}/{hours}/{ymdh}`：实况排行。`type` 使用 `rain`、`maxtemp`、`mintemp`、`wind`；`hours` 使用 `1`、`6`、`24`，其中风速只使用 1 小时。
- `GET /rest/findAlarm`：全国预警信号列表，支持 `pageNo`、`pageSize`、`signaltype`、`signallevel`、`province`。

排行默认时次来自国家气象中心首页里公开展示的下拉时次。若自动解析失败，调用时传 `--ymdh YYYYMMDDHH`。

## 图像和官方产品页

`product` 命令读取国家气象中心公开产品页，提取：

- 产品标识、中文名、所属栏目、网址。
- 页面标题、页面生成时间。
- 正文摘要。
- 页面中的官方图片地址。
- 页面中的相关链接。

覆盖的产品组包括：

- 天气实况：天气图、卫星云图、雷达图、逐小时降水/气温/风、能见度、强对流、土壤水分。
- 天气预报：天气公报、每日天气提示、气象灾害预警、降水量预报、气温预报、大风预报、强对流天气预报、中期天气、交通气象、山洪、地灾、中小河流洪水、渍涝、森林/草原火险。
- 台风海洋：台风快讯、台风路径、台风公报、台风预警、海区预报、海事公报、海洋天气、近海海雾、海区风力。
- 全球、环境、农业和数值预报：全球天气、全球灾害性天气、雾、霾、沙尘、空气污染气象条件、农业土壤水分、农业干旱、农业周/月报、作物发育期、中国气象局模式和海浪模式。

`layers --kind radar` 使用 `https://typhoon.nmc.cn/publish/radar/latest.json` 返回最新雷达图层序列。

`layers --kind satellite` 使用国家气象中心的 FY-4B 卫星云图产品页提取卫星图片地址。图片文件名时次可能与页面展示的北京时间存在差异，必须同时看 `page_generated_time` 和正文里的产品制作时间。

## 中国天气网逐小时预报

逐小时预报数据源：中国天气网，`https://www.weather.com.cn`。

当用户需要未来具体时段降水判断时，脚本可以返回中国天气网逐小时预报数据：

- `GET https://toy1.weather.com.cn/search?cityname={city}&callback=success_jsonpCallback&_={timestamp}`：解析中国天气网城市代码。
- `GET https://www.weather.com.cn/weather1dn/{weather_code}.shtml`：读取逐小时预报页面。

逐小时页面使用边界：

- 脚本只解析页面中的 `hour3data`、`uptime` 等天气变量，不抓广告、新闻或页面装饰内容。
- `hourly_forecast.hours[]` 中的 `time` 是未来小时预报时间。
- `weather` 是天气现象中文名，`weather_code` 是页面原始天气编码。
- `precipitation_signal` 只表示天气现象中出现雨、雪、冰雹等降水/降雪信号，不能等同于精确降水量。
- `update_text` 是页面显示的更新时间文本，不一定等同于正式发布时间戳；同时查看 `source.retrieved_at`。

## 中国气象局天气页面

官方展示页数据源：中国气象局天气页面，`https://weather.cma.cn`。

脚本提供：

- `cma-healthcheck`：检测本机脚本环境能否访问 `weather.cma.cn` 的首页、城市预报地图和预警地图。
- `cma-page <id>`：按需读取已知官方展示页摘要、图片和链接。当前页面标识包括 `home`、`city-map`、`alarm-map`、`satellite-fy4b`、`daily-tip`、`precipitation-24h`、`traffic`。
- `cma-city <city> --province <province>`：先用国家气象中心全国实况地图解析数值站号，再尝试读取 `weather.cma.cn/web/weather/{station_code}` 城市页。
- `query --include-cma`：在国家气象中心城市查询结果里附带 `cma_city_page`，用于显式要求双源核对的场景。

使用边界：

- `weather.cma.cn` 是官方展示页，但本地脚本直接访问可能被站点安全策略拦截或断开连接。此时脚本返回 `ok:false`、`error`、`url`、`blocked` 和 `details`。
- 如果 `cma_city_page.ok` 或 `cma-page.ok` 为 false，不要尝试绕过安全策略，保留失败状态。
- 如果中国气象局页面可访问，返回内容以页面摘要、链接、图片和来源时间为主；调用智能体自行结合国家气象中心与中国气象局返回字段比较。

## 更新特征

- 国家气象中心实况通常接近实时，但会受站点和页面产品影响，可能有分钟到小时级延迟。
- 国家气象中心城市预报按产品批次发布，公开页面常见 08:00 或 20:00 中国时间批次，不是连续实时刷新。
- 预警信号可独立于普通预报更新，行程判断需要纳入这个字段。
- 雷达、卫星、天气图和产品页有各自的产品制作时间；不要只看网页抓取时间。
- 中国天气网逐小时预报页面会显示 `update_text`，它是未来预报数据，不是实况。
- 中国气象局天气页面是展示页，是否能被脚本访问取决于站点安全策略和网络环境；先看 `ok`、`error` 和 `source.retrieved_at`。

## 可靠性规则

- 结构化数据中包含 `publish_time`、`publish_age_minutes` 或对应来源的 `retrieved_at`、`update_text`、`page_generated_time`、图像 `time`。不要在技能内部把时效分级；调用智能体自行比较发布时间和查询时间。
- 不要硬编码站点代码，除非用户明确提供；通常通过省份和城市端点解析。
- 把 `9999`、`9999.0`、空字符串等占位值视为缺失。
- 城市名跨省歧义时要求使用 `--province`。
- 产品页解析用于按需查询，避免大规模批量抓取。
- 安装后或大范围部署前运行 `python scripts/nmc_weather.py healthcheck`。健康检查应能加载站点表，并返回抽样城市的实况和预报数据。

## 边界

- 本技能适合公开城市级天气查询、全国态势查询和日常行程判断。
- 它不是地方应急预警、航空/铁路运行系统或专业气象决策系统的替代品。
