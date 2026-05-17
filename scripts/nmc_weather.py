#!/usr/bin/env python3
"""查询中国公开天气数据，并输出适合智能体使用的 JSON。"""

from __future__ import annotations

import argparse
import html
import json
import os
import re
import sys
import time
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from html.parser import HTMLParser
from pathlib import Path
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.parse import quote, urlencode, urljoin, urlparse
from urllib.request import Request, urlopen


BASE_URL = "https://www.nmc.cn"
TYPHOON_BASE_URL = "https://typhoon.nmc.cn"
CHINA_WEATHER_BASE_URL = "https://www.weather.com.cn"
CHINA_WEATHER_SEARCH_URL = "https://toy1.weather.com.cn/search"
CMA_WEATHER_BASE_URL = "https://weather.cma.cn"
CN_TZ = timezone(timedelta(hours=8), "Asia/Shanghai")
STATION_CACHE_TTL_SECONDS = 7 * 24 * 60 * 60
DEFAULT_TIMEOUT_SECONDS = 12
SCHEMA_VERSION = "1.6.0"

ARGPARSE_TRANSLATIONS = {
    "usage: ": "用法：",
    "positional arguments": "位置参数",
    "options": "选项",
    "optional arguments": "可选参数",
    "show this help message and exit": "显示此帮助信息并退出",
}

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/124.0 Safari/537.36"
    ),
    "Accept": "application/json,text/plain,*/*",
    "Referer": "https://www.nmc.cn/",
}

CHINA_WEATHER_HEADERS = {
    **HEADERS,
    "Referer": "https://www.weather.com.cn/",
}

CMA_WEATHER_HEADERS = {
    **HEADERS,
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.6",
    "Referer": "https://weather.cma.cn/",
}

CHINA_WEATHER_TEXT = {
    "00": "晴",
    "01": "多云",
    "02": "阴",
    "03": "阵雨",
    "04": "雷阵雨",
    "05": "雷阵雨伴有冰雹",
    "06": "雨夹雪",
    "07": "小雨",
    "08": "中雨",
    "09": "大雨",
    "10": "暴雨",
    "11": "大暴雨",
    "12": "特大暴雨",
    "13": "阵雪",
    "14": "小雪",
    "15": "中雪",
    "16": "大雪",
    "17": "暴雪",
    "18": "雾",
    "19": "冻雨",
    "20": "沙尘暴",
    "21": "小到中雨",
    "22": "中到大雨",
    "23": "大到暴雨",
    "24": "暴雨到大暴雨",
    "25": "大暴雨到特大暴雨",
    "26": "小到中雪",
    "27": "中到大雪",
    "28": "大到暴雪",
    "29": "浮尘",
    "30": "扬沙",
    "31": "强沙尘暴",
    "53": "霾",
}

PRODUCT_CATALOG = {
    "weather-chart": {"name": "天气图", "group": "天气实况", "path": "/publish/observations/china/dm/weatherchart-h000.htm"},
    "satellite-fy4b": {"name": "FY-4B 卫星云图", "group": "天气实况", "path": "/publish/satellite/fy4b-visible.htm"},
    "satellite-fy4a-true-color": {"name": "FY-4A 真彩色卫星云图", "group": "天气实况", "path": "/publish/satellite/FY4A-true-color.htm"},
    "satellite-fy4a-infrared": {"name": "FY-4A 红外卫星云图", "group": "天气实况", "path": "/publish/satellite/FY4A-infrared.htm"},
    "satellite-fy4a-visible": {"name": "FY-4A 可见光卫星云图", "group": "天气实况", "path": "/publish/satellite/FY4A-visible.htm"},
    "satellite-fy4a-water-vapour": {"name": "FY-4A 水汽卫星云图", "group": "天气实况", "path": "/publish/satellite/FY4A-water-vapour.htm"},
    "radar-china": {"name": "全国雷达拼图", "group": "天气实况", "path": "/publish/radar/chinaall.html"},
    "radar-northeast": {"name": "东北雷达拼图", "group": "天气实况", "path": "/publish/radar/dongbei.html"},
    "radar-north": {"name": "华北雷达拼图", "group": "天气实况", "path": "/publish/radar/huabei.html"},
    "radar-south": {"name": "华南雷达拼图", "group": "天气实况", "path": "/publish/radar/huanan.html"},
    "hourly-precipitation": {"name": "逐小时降水实况", "group": "天气实况", "path": "/publish/observations/hourly-precipitation.html"},
    "hourly-temperature": {"name": "逐小时气温实况", "group": "天气实况", "path": "/publish/observations/hourly-temperature.html"},
    "hourly-winds": {"name": "逐小时风实况", "group": "天气实况", "path": "/publish/observations/hourly-winds.html"},
    "visibility": {"name": "能见度", "group": "天气实况", "path": "/publish/sea/seaplatform1.html"},
    "lightning": {"name": "强对流/闪电观测", "group": "天气实况", "path": "/publish/observations/lighting.html"},
    "soil-moisture": {"name": "土壤水分", "group": "天气实况", "path": "/publish/soil-moisture/10cm.html"},
    "weather-bulletin": {"name": "天气公报", "group": "天气预报", "path": "/publish/weather-bulletin/index.htm"},
    "weather-tip": {"name": "每日天气提示", "group": "天气预报", "path": "/publish/weatherperday/index.htm"},
    "country-warning": {"name": "气象灾害预警", "group": "天气预报", "path": "/publish/country/warning/index.html"},
    "important-weather": {"name": "重要天气提示", "group": "天气预报", "path": "/publish/news/weather_new.html"},
    "weather-review": {"name": "重要天气盘点", "group": "天气预报", "path": "/publish/tianqiyubao/zhongyaotianqipandian/index.html"},
    "precipitation-1d": {"name": "24 小时降水量预报", "group": "天气预报", "path": "/publish/precipitation/1-day.html"},
    "temperature-24h": {"name": "24 小时气温预报", "group": "天气预报", "path": "/publish/temperature/hight/24hour.html"},
    "wind-24h": {"name": "24 小时大风预报", "group": "天气预报", "path": "/publish/wind/24h.html"},
    "severe-convection": {"name": "强对流天气预报", "group": "天气预报", "path": "/publish/bulletin/swpc.html"},
    "mid-range": {"name": "中期天气", "group": "天气预报", "path": "/publish/bulletin/mid-range.htm"},
    "global-weather": {"name": "全球天气预报", "group": "全球预报", "path": "/publish/bulletin/abroadweather.html"},
    "environment-bulletin": {"name": "环境气象公报", "group": "环境气象", "path": "/publish/observations/environmental.html"},
    "mountain-flood": {"name": "山洪灾害气象预警", "group": "天气预报", "path": "/publish/mountainflood.html"},
    "geohazard": {"name": "地质灾害气象风险预警", "group": "天气预报", "path": "/publish/geohazard.html"},
    "river-flood-risk": {"name": "中小河流洪水气象风险预警", "group": "天气预报", "path": "/publish/swdz/zxhlhsqxyj.html"},
    "waterlogging": {"name": "渍涝风险气象预警", "group": "天气预报", "path": "/publish/waterlogging.html"},
    "traffic": {"name": "交通气象预报", "group": "天气预报", "path": "/publish/traffic.html"},
    "forest-fire": {"name": "森林火险预报", "group": "天气预报", "path": "/publish/environment/forestfire-doc.html"},
    "grassland-fire": {"name": "草原火险预报", "group": "天气预报", "path": "/publish/environment/glassland-fire.html"},
    "typhoon-news": {"name": "台风快讯与报文", "group": "台风海洋", "path": "/publish/typhoon/typhoon_new.html"},
    "typhoon-path": {"name": "台风路径预报", "group": "台风海洋", "path": "/publish/typhoon/probability-img2.html"},
    "typhoon-bulletin": {"name": "台风公报", "group": "台风海洋", "path": "/publish/typhoon/warning.html"},
    "typhoon-warning": {"name": "台风预警", "group": "台风海洋", "path": "/publish/typhoon/warning_index.html"},
    "coastal-sea": {"name": "海区预报", "group": "台风海洋", "path": "/publish/marine/newcoastal.html"},
    "maritime": {"name": "海事公报", "group": "台风海洋", "path": "/publish/marine/maritime.html"},
    "marine-weather": {"name": "海洋天气预报", "group": "台风海洋", "path": "/publish/marine/forecast.htm"},
    "sea-fog": {"name": "近海海雾预报", "group": "台风海洋", "path": "/publish/taifenghaiyang/jinhaihaiwuyubao/index.html"},
    "sea-wind": {"name": "海区风力预报", "group": "台风海洋", "path": "/publish/taifenghaiyang/haiqufengliyubao/index.html"},
    "north-pacific": {"name": "北太平洋分析与预报", "group": "台风海洋", "path": "/publish/marine/h000.html"},
    "global-cyclone": {"name": "全球热带气旋监测公报", "group": "台风海洋", "path": "/publish/typhoon/totalcyclone.htm"},
    "global-disaster-monthly": {"name": "全球灾害性天气监测月报", "group": "全球预报", "path": "/publish/quanqiuyubao/quanqiuzaihaixingtianqijianceyuebao/index.html"},
    "global-rain-snow-asia": {"name": "亚洲全球雨雪落区预报", "group": "全球预报", "path": "/publish/quanqiuyubao/quanqiuyuxueluoquyubao/yazhou/24xiaoshi/index.html"},
    "fog": {"name": "雾预报", "group": "环境气象", "path": "/publish/fog.html"},
    "haze": {"name": "霾预报", "group": "环境气象", "path": "/publish/haze.html"},
    "dust": {"name": "沙尘天气预报", "group": "环境气象", "path": "/publish/severeweather/dust.html"},
    "air-pollution": {"name": "空气污染气象条件预报", "group": "环境气象", "path": "/publish/environment/air_pollution-24.html"},
    "agro-soil": {"name": "农业土壤水分监测", "group": "农业气象", "path": "/publish/agro/soil-moisture-monitoring-10cm.html"},
    "agro-drought": {"name": "农业干旱综合监测", "group": "农业气象", "path": "/publish/agro/disastersmonitoring/Agricultural_Drought_Monitoring.htm"},
    "agro-weekly": {"name": "农业气象周报", "group": "农业气象", "path": "/publish/agro/ten-week/index.html"},
    "agro-monthly": {"name": "农业气象月报", "group": "农业气象", "path": "/publish/agro/monthly/index.html"},
    "crop-stage": {"name": "作物发育期监测", "group": "农业气象", "path": "/publish/crop/index.htm"},
    "nwp-global": {"name": "中国气象局全球天气模式", "group": "数值预报", "path": "/publish/nwpc/grapes_gfs/nh/500hPa-hgt.htm"},
    "nwp-area": {"name": "中国气象局区域模式", "group": "数值预报", "path": "/publish/area/china/hws.html"},
    "nwp-typhoon": {"name": "中国气象局台风模式", "group": "数值预报", "path": "/publish/shuzhiyubao/GRAPES_TYMquyutaifengmoshi/taifenglujing/index.html"},
    "wave-model": {"name": "海浪模式", "group": "数值预报", "path": "/publish/nwp/ww3/globe/index.html"},
}

CMA_PAGE_CATALOG = {
    "home": {"name": "中国气象局天气首页", "group": "综合", "path": "/"},
    "city-map": {"name": "城市预报地图", "group": "城市预报", "path": "/web/weather/map.html"},
    "alarm-map": {"name": "气象预警地图", "group": "气象预警", "path": "/web/alarm/map.html"},
    "satellite-fy4b": {"name": "FY-4B 卫星云图", "group": "天气实况", "path": "/web/channel-2b0863600e144b13807e606f928b1266.html"},
    "daily-tip": {"name": "每日天气提示", "group": "气象公报", "path": "/web/channel-380.html"},
    "precipitation-24h": {"name": "24 小时降水量预报", "group": "天气预报", "path": "/web/channel-339.html"},
    "traffic": {"name": "交通气象预报", "group": "气象公报", "path": "/web/channel-423.html"},
}


class NmcError(Exception):
    """公开天气来源或查询失败。"""


class ChinaWeatherError(Exception):
    """中国天气网逐小时预报查询失败。"""


class CmaWeatherError(Exception):
    """中国气象局天气页面查询失败。"""

    def __init__(
        self,
        message: str,
        *,
        status_code: int | None = None,
        blocked: bool = False,
        url: str | None = None,
        details: dict[str, Any] | None = None,
    ) -> None:
        super().__init__(message)
        self.status_code = status_code
        self.blocked = blocked
        self.url = url
        self.details = details or {}


@dataclass(frozen=True)
class Station:
    code: str
    province: str
    city: str
    url: str | None = None


@dataclass(frozen=True)
class ChinaWeatherLocation:
    code: str
    province: str
    city: str
    parent_city: str | None = None


def now_cn() -> datetime:
    return datetime.now(timezone.utc).astimezone(CN_TZ)


def parse_cn_time(value: Any) -> datetime | None:
    if not isinstance(value, str) or not value.strip():
        return None
    for fmt in ("%Y-%m-%d %H:%M", "%Y/%m/%d %H:%M", "%Y-%m-%d %H:%M:%S"):
        try:
            return datetime.strptime(value.strip(), fmt).replace(tzinfo=CN_TZ)
        except ValueError:
            continue
    return None


def age_minutes(value: Any) -> float | None:
    parsed = parse_cn_time(value)
    if parsed is None:
        return None
    return max(0.0, (now_cn() - parsed).total_seconds() / 60)


def publish_age_minutes(value: Any) -> float | None:
    age = age_minutes(value)
    if age is None:
        return None
    return round(age, 1)


def is_missing(value: Any) -> bool:
    if value is None:
        return True
    if isinstance(value, str):
        return value.strip() in {"", "-", "9999", "9999.0", "null", "None"}
    if isinstance(value, (int, float)):
        return value == 9999 or value == 9999.0
    return False


def clean(value: Any) -> Any:
    if is_missing(value):
        return None
    if isinstance(value, list):
        return [clean(item) for item in value]
    if isinstance(value, dict):
        return {key: clean(item) for key, item in value.items()}
    return value


def cache_dir() -> Path:
    root = os.environ.get("LOCALAPPDATA")
    if root:
        path = Path(root) / "china-weather-skill"
    else:
        path = Path.home() / ".cache" / "china-weather-skill"
    path.mkdir(parents=True, exist_ok=True)
    return path


def configure_argparse_chinese() -> None:
    argparse._ = lambda text: ARGPARSE_TRANSLATIONS.get(text, text)


def http_json(path_or_url: str, timeout: int = DEFAULT_TIMEOUT_SECONDS) -> Any:
    url = path_or_url if path_or_url.startswith("http") else urljoin(BASE_URL, path_or_url)
    last_error: Exception | None = None
    for attempt in range(3):
        request = Request(url, headers=HEADERS)
        try:
            with urlopen(request, timeout=timeout) as response:
                charset = response.headers.get_content_charset() or "utf-8"
                text = response.read().decode(charset, errors="replace")
                return json.loads(text)
        except (HTTPError, URLError, TimeoutError, json.JSONDecodeError) as exc:
            last_error = exc
            if attempt < 2:
                time.sleep(0.4 * (attempt + 1))
    raise NmcError(f"failed to fetch JSON from {url}: {last_error}")


def http_text(
    url: str,
    headers: dict[str, str] | None = None,
    timeout: int = DEFAULT_TIMEOUT_SECONDS,
    error_cls: type[Exception] = NmcError,
) -> str:
    last_error: Exception | None = None
    for attempt in range(3):
        request = Request(url, headers=headers or HEADERS)
        try:
            with urlopen(request, timeout=timeout) as response:
                charset = response.headers.get_content_charset() or "utf-8"
                return response.read().decode(charset, errors="replace")
        except (HTTPError, URLError, TimeoutError) as exc:
            last_error = exc
            if attempt < 2:
                time.sleep(0.4 * (attempt + 1))
    raise error_cls(f"failed to fetch text from {url}: {last_error}")


def normalize_name(value: str) -> str:
    text = re.sub(r"\s+", "", value or "")
    replacements = [
        "维吾尔自治区",
        "壮族自治区",
        "回族自治区",
        "特别行政区",
        "自治区",
        "自治州",
        "地区",
        "盟",
        "省",
        "市",
        "县",
        "区",
    ]
    changed = True
    while changed:
        changed = False
        for suffix in replacements:
            if text.endswith(suffix) and len(text) > len(suffix):
                text = text[: -len(suffix)]
                changed = True
    return text


def load_stations(refresh: bool = False) -> list[Station]:
    cache_file = cache_dir() / "stations.json"
    if not refresh and cache_file.exists():
        try:
            payload = json.loads(cache_file.read_text(encoding="utf-8"))
            if time.time() - payload.get("created_at", 0) < STATION_CACHE_TTL_SECONDS:
                return [Station(**item) for item in payload["stations"]]
        except (OSError, json.JSONDecodeError, KeyError, TypeError):
            pass

    provinces = http_json("/rest/province/all")
    stations: list[Station] = []
    for province in provinces:
        province_code = province.get("code")
        if not province_code:
            continue
        cities = http_json(f"/rest/province/{province_code}")
        for city in cities:
            code = city.get("code")
            city_name = city.get("city")
            province_name = city.get("province") or province.get("name")
            if code and city_name and province_name:
                stations.append(
                    Station(
                        code=str(code),
                        province=str(province_name),
                        city=str(city_name),
                        url=city.get("url"),
                    )
                )

    cache_payload = {
        "created_at": time.time(),
        "source": BASE_URL,
        "stations": [station.__dict__ for station in stations],
    }
    cache_file.write_text(json.dumps(cache_payload, ensure_ascii=False, indent=2), encoding="utf-8")
    return stations


def resolve_station(city: str | None, province: str | None, station_id: str | None, refresh: bool) -> Station:
    if station_id:
        return Station(code=station_id, province="", city="", url=None)
    if not city:
        raise NmcError("city is required unless --station-id is provided")

    stations = load_stations(refresh=refresh)
    city_norm = normalize_name(city)
    province_norm = normalize_name(province or "")

    candidates = stations
    if province_norm:
        candidates = [
            station
            for station in candidates
            if normalize_name(station.province) == province_norm or province_norm in normalize_name(station.province)
        ]
        if not candidates:
            raise NmcError(f"no province match for {province!r}")

    exact = [station for station in candidates if normalize_name(station.city) == city_norm]
    if len(exact) == 1:
        return exact[0]
    if len(exact) > 1:
        raw_exact = [station for station in exact if station.city == city]
        if len(raw_exact) == 1:
            return raw_exact[0]
        raise_ambiguous(city, exact)

    fuzzy = [
        station
        for station in candidates
        if city_norm in normalize_name(station.city) or normalize_name(station.city) in city_norm
    ]
    if len(fuzzy) == 1:
        return fuzzy[0]
    if len(fuzzy) > 1:
        raise_ambiguous(city, fuzzy)

    nearby = [
        station
        for station in stations
        if city_norm and (city_norm in normalize_name(station.city) or normalize_name(station.city) in city_norm)
    ][:12]
    if nearby:
        raise NmcError(f"no exact city match for {city!r}; possible candidates: {format_candidates(nearby)}")
    raise NmcError(f"no city match for {city!r}")


def format_candidates(stations: list[Station]) -> str:
    return "; ".join(f"{station.province}/{station.city}({station.code})" for station in stations[:12])


def raise_ambiguous(city: str | None, stations: list[Station]) -> None:
    raise NmcError(f"ambiguous city {city!r}; rerun with --province. candidates: {format_candidates(stations)}")


def search_china_weather_location(city: str | None, province: str | None) -> ChinaWeatherLocation:
    if not city:
        raise ChinaWeatherError("city is required for hourly forecast lookup")

    url = (
        f"{CHINA_WEATHER_SEARCH_URL}?cityname={quote(city)}"
        f"&callback=success_jsonpCallback&_={int(time.time() * 1000)}"
    )
    text = http_text(url, headers=CHINA_WEATHER_HEADERS, error_cls=ChinaWeatherError)
    match = re.search(r"success_jsonpCallback\((.*)\)\s*$", text, re.S)
    if not match:
        raise ChinaWeatherError("China Weather search did not return JSONP")
    try:
        rows = json.loads(match.group(1))
    except json.JSONDecodeError as exc:
        raise ChinaWeatherError(f"China Weather search JSON parse failed: {exc}") from exc

    city_norm = normalize_name(city)
    province_norm = normalize_name(province or "")
    candidates: list[ChinaWeatherLocation] = []
    for row in rows:
        ref = str(row.get("ref", ""))
        parts = ref.split("~")
        if len(parts) < 10:
            continue
        code, name, parent, province_name = parts[0], parts[2], parts[4], parts[9]
        if not code.isdigit() or len(code) != 9:
            continue
        if province_norm and province_norm != normalize_name(province_name):
            continue
        candidates.append(
            ChinaWeatherLocation(
                code=code,
                province=province_name,
                city=name,
                parent_city=parent if parent != name else None,
            )
        )

    exact = [
        item
        for item in candidates
        if normalize_name(item.city) == city_norm or normalize_name(item.parent_city or "") == city_norm
    ]
    if len(exact) == 1:
        return exact[0]
    raw_exact = [item for item in exact if item.city == city or item.parent_city == city]
    if len(raw_exact) == 1:
        return raw_exact[0]
    if len(exact) > 1:
        formatted = "; ".join(f"{item.province}/{item.city}({item.code})" for item in exact[:12])
        raise ChinaWeatherError(f"ambiguous China Weather city {city!r}; rerun with --province. candidates: {formatted}")

    fuzzy = [
        item
        for item in candidates
        if city_norm in normalize_name(item.city)
        or normalize_name(item.city) in city_norm
        or city_norm in normalize_name(item.parent_city or "")
    ]
    if len(fuzzy) == 1:
        return fuzzy[0]
    if len(fuzzy) > 1:
        formatted = "; ".join(f"{item.province}/{item.city}({item.code})" for item in fuzzy[:12])
        raise ChinaWeatherError(f"ambiguous China Weather city {city!r}; rerun with --province. candidates: {formatted}")
    raise ChinaWeatherError(f"no China Weather city match for {city!r}")


def parse_weathercom_time(value: Any) -> str | None:
    if not isinstance(value, str) or not re.fullmatch(r"\d{10}", value):
        return None
    return f"{value[0:4]}-{value[4:6]}-{value[6:8]} {value[8:10]}:00"


def weathercom_time_relation(value: Any) -> str:
    parsed = parse_weathercom_time(value)
    if parsed is None:
        return "未知"
    return date_relation(parsed[:10])


def is_precipitation_weather(code: str | None, text: str | None) -> bool:
    value = f"{code or ''}{text or ''}"
    return any(keyword in value for keyword in ("03", "04", "05", "06", "07", "08", "09", "10", "11", "12", "19", "21", "22", "23", "24", "25", "雨", "雪", "冰雹"))


def parse_china_weather_hourly_page(text: str, limit: int) -> tuple[list[dict[str, Any]], str | None]:
    match = re.search(r"var hour3data=(.*?);var hour3week", text, re.S)
    if not match:
        raise ChinaWeatherError("China Weather hourly data not found")
    try:
        groups = json.loads(match.group(1))
    except json.JSONDecodeError as exc:
        raise ChinaWeatherError(f"China Weather hourly JSON parse failed: {exc}") from exc

    update_match = re.search(r'var uptime="([^"]+)"', text)
    update_text = update_match.group(1) if update_match else None
    rows = [item for group in groups for item in group]
    normalized = []
    for row in rows[: max(limit, 0)]:
        code = clean(row.get("ja"))
        weather_text = CHINA_WEATHER_TEXT.get(str(code), str(code) if code is not None else None)
        normalized.append(
            {
                "time": parse_weathercom_time(row.get("jf")),
                "date_relation": weathercom_time_relation(row.get("jf")),
                "weather_code": code,
                "weather": weather_text,
                "temperature_c": clean(row.get("jb")),
                "wind_code": clean(row.get("jd")),
                "humidity_percent": clean(row.get("je")),
                "precipitation_signal": is_precipitation_weather(str(code) if code is not None else None, weather_text),
            }
        )
    return normalized, update_text


def fetch_china_weather_hourly_forecast(city: str | None, province: str | None, limit: int) -> dict[str, Any]:
    location = search_china_weather_location(city, province)
    path = f"/weather1dn/{location.code}.shtml"
    url = urljoin(CHINA_WEATHER_BASE_URL, path)
    text = http_text(url, headers=CHINA_WEATHER_HEADERS, error_cls=ChinaWeatherError)
    hours, update_text = parse_china_weather_hourly_page(text, limit)
    return {
        "ok": True,
        "source": {
            "name": "中国天气网",
            "site": CHINA_WEATHER_BASE_URL,
            "endpoint": path,
            "retrieved_at": now_cn().strftime("%Y-%m-%d %H:%M:%S %Z"),
        },
        "note": "逐小时预报数据，不是实况；用于判断未来具体时段的降水、天气和温度趋势。",
        "weather_code": location.code,
        "province": location.province,
        "city": location.city,
        "parent_city": location.parent_city,
        "update_text": update_text,
        "hours": hours,
    }


def normalize_space(value: Any) -> str:
    text = html.unescape(str(value or "")).replace("\xa0", " ")
    return re.sub(r"\s+", " ", text).strip()


class PageExtractor(HTMLParser):
    def __init__(self, base_url: str) -> None:
        super().__init__(convert_charrefs=True)
        self.base_url = base_url
        self.title_parts: list[str] = []
        self.links: list[dict[str, str]] = []
        self.images: list[dict[str, str]] = []
        self._in_title = False
        self._anchor_stack: list[dict[str, Any]] = []

    @property
    def title(self) -> str | None:
        title = normalize_space("".join(self.title_parts))
        return title or None

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        attrs_dict = {key.lower(): value for key, value in attrs if value is not None}
        if tag.lower() == "title":
            self._in_title = True
        if tag.lower() == "a" and attrs_dict.get("href"):
            self._anchor_stack.append(
                {
                    "href": attrs_dict["href"],
                    "title": attrs_dict.get("title"),
                    "text": [],
                }
            )
        if tag.lower() == "img":
            src = attrs_dict.get("data-original") or attrs_dict.get("src")
            if src:
                self.images.append(
                    {
                        "url": absolute_url(src, self.base_url) or src,
                        "alt": normalize_space(attrs_dict.get("alt")),
                        "title": normalize_space(attrs_dict.get("title")),
                    }
                )

    def handle_data(self, data: str) -> None:
        if self._in_title:
            self.title_parts.append(data)
        if self._anchor_stack:
            self._anchor_stack[-1]["text"].append(data)

    def handle_endtag(self, tag: str) -> None:
        if tag.lower() == "title":
            self._in_title = False
        if tag.lower() == "a" and self._anchor_stack:
            item = self._anchor_stack.pop()
            href = normalize_space(item.get("href"))
            text = normalize_space("".join(item.get("text") or []) or item.get("title"))
            if not href or href.startswith(("javascript:", "#", "mailto:")):
                return
            self.links.append(
                {
                    "text": text,
                    "url": absolute_url(href, self.base_url) or href,
                    "title": normalize_space(item.get("title")),
                }
            )


def html_to_text_excerpt(text: str, limit: int) -> tuple[str, bool]:
    body = re.sub(r"(?is)<script.*?</script>", " ", text)
    body = re.sub(r"(?is)<style.*?</style>", " ", body)
    body = re.sub(r"(?is)<svg.*?</svg>", " ", body)
    body = re.sub(r"(?i)<br\s*/?>", "\n", body)
    body = re.sub(r"(?i)</(p|div|li|h[1-6]|tr|table|section|article)>", "\n", body)
    body = re.sub(r"(?s)<[^>]+>", " ", body)
    lines = [normalize_space(line) for line in html.unescape(body).splitlines()]
    lines = [line for line in lines if line]
    plain = "\n".join(lines)
    for marker in ("当前位置：", "当前位置:"):
        index = plain.find(marker)
        if index >= 0:
            plain = plain[index:]
            break
    for marker in ("推荐服务", "国家气象中心 版权所有", "中国气象报社 版权所有", "Copyright©"):
        index = plain.find(marker)
        if index > 0:
            plain = plain[:index]
            break
    truncated = len(plain) > limit
    if truncated:
        plain = plain[:limit].rstrip()
    return plain, truncated


def dedupe_by_url(items: list[dict[str, str]]) -> list[dict[str, str]]:
    seen: set[str] = set()
    deduped = []
    for item in items:
        url = item.get("url")
        if not url or url in seen:
            continue
        seen.add(url)
        deduped.append(item)
    return deduped


def useful_image(item: dict[str, str]) -> bool:
    url = item.get("url", "").lower()
    skip_fragments = (
        "/assets/img/default_loading",
        "/assets/img/w/",
        "/assets/favicon",
        "/assets/img/index/",
        "/assets/img/category-icon/",
        "/assets/img/typhoon_code",
        "/assets/img/qxkjcxfwpt",
        "/assets/img/nmc_dyh",
        "/static/img/sina",
        "/static/img/weixin",
        "gongan.png",
        "blue.png",
        "logo",
        "qrcode",
    )
    return bool(url) and not any(fragment in url for fragment in skip_fragments)


def useful_link(item: dict[str, str]) -> bool:
    text = normalize_space(item.get("text") or item.get("title"))
    url = item.get("url", "")
    if not text or len(text) <= 1:
        return False
    skip_text = {
        "首页",
        "天气实况",
        "城市预报",
        "天气预报",
        "台风海洋",
        "全球预报",
        "环境气象",
        "农业气象",
        "数值预报",
        "关于我们",
        "联系方式",
        "网站声明",
        "网站地图",
        "English",
    }
    if text in skip_text:
        return False
    if "/publish/forecast/" in url:
        return False
    if any(fragment in url for fragment in ("weibo.com", "qzone.qq.com", "connect.qq.com")):
        return False
    return True


def extract_page_generated_time(text: str) -> str | None:
    match = re.search(r'name=["\']?[^"\'>]*页面生成时间[^"\'>]*["\']?\s+value=["\']([^"\']+)["\']', text)
    if match:
        return normalize_space(match.group(1))
    return None


def resolve_product(product_id: str) -> tuple[str, dict[str, str]]:
    if product_id in PRODUCT_CATALOG:
        return product_id, PRODUCT_CATALOG[product_id]
    product_norm = normalize_name(product_id)
    matches = [
        (key, item)
        for key, item in PRODUCT_CATALOG.items()
        if product_norm
        and (
            product_norm == normalize_name(item["name"])
            or product_norm in normalize_name(item["name"])
            or product_norm in normalize_name(key)
        )
    ]
    if len(matches) == 1:
        return matches[0]
    if len(matches) > 1:
        candidates = "; ".join(f"{key}={item['name']}" for key, item in matches[:12])
        raise NmcError(f"product {product_id!r} is ambiguous; candidates: {candidates}")
    raise NmcError(f"unknown product {product_id!r}; run catalog to list supported product ids")


def fetch_product(product_id: str, link_limit: int, image_limit: int, text_limit: int) -> dict[str, Any]:
    resolved_id, item = resolve_product(product_id)
    url = absolute_url(item["path"], BASE_URL) or item["path"]
    text = http_text(url, headers=HEADERS)
    extractor = PageExtractor(url)
    extractor.feed(text)
    links = [link for link in dedupe_by_url(extractor.links) if useful_link(link)][:link_limit]
    images = [image for image in dedupe_by_url(extractor.images) if useful_image(image)][:image_limit]
    excerpt, truncated = html_to_text_excerpt(text, text_limit)
    return {
        "schema_version": SCHEMA_VERSION,
        "ok": True,
        "source": {
            "name": "国家气象中心/中央气象台",
            "site": BASE_URL,
            "endpoint": item["path"],
            "retrieved_at": now_cn().strftime("%Y-%m-%d %H:%M:%S %Z"),
        },
        "product": {
            "id": resolved_id,
            "name": item["name"],
            "group": item["group"],
            "url": url,
        },
        "page_title": extractor.title,
        "page_generated_time": extract_page_generated_time(text),
        "text": {
            "excerpt": excerpt,
            "truncated": truncated,
        },
        "links": links,
        "images": images,
        "notes": [
            "这是官方公开产品页解析结果，只提取文字、链接和图片地址，不下载图片文件。",
            "图像类产品应查看图片时间、页面生成时间和当前查询时间的距离。",
        ],
    }


def cma_absolute_url(path_or_url: str) -> str:
    url = path_or_url if path_or_url.startswith("http") else urljoin(CMA_WEATHER_BASE_URL, path_or_url)
    parsed = urlparse(url)
    if parsed.netloc != "weather.cma.cn":
        raise CmaWeatherError("中国气象局页面地址必须属于 weather.cma.cn", url=url)
    return url


def cma_block_details(text: str) -> dict[str, Any]:
    title_match = re.search(r"<title>(.*?)</title>", text, re.S | re.I)
    event_match = re.search(r"event_id:\s*([0-9a-fA-F]+)", text)
    message_match = re.search(r'<p class=desc>(.*?)</p>', text, re.S | re.I)
    return {
        "title": normalize_space(title_match.group(1)) if title_match else None,
        "message": normalize_space(message_match.group(1)) if message_match else None,
        "event_id": event_match.group(1) if event_match else None,
    }


def is_cma_blocked(text: str) -> bool:
    return "请求已被阻断" in text or "已被拦截" in text or "event_id:" in text


def request_cma_text(url: str, timeout: int = DEFAULT_TIMEOUT_SECONDS) -> tuple[str, int | None]:
    request = Request(url, headers=CMA_WEATHER_HEADERS)
    try:
        with urlopen(request, timeout=timeout) as response:
            charset = response.headers.get_content_charset() or "utf-8"
            text = response.read().decode(charset, errors="replace")
            status_code = getattr(response, "status", None)
    except HTTPError as exc:
        charset = exc.headers.get_content_charset() if exc.headers else None
        body = exc.read().decode(charset or "utf-8", errors="replace")
        if is_cma_blocked(body):
            raise CmaWeatherError(
                "weather.cma.cn 返回安全拦截页",
                status_code=exc.code,
                blocked=True,
                url=url,
                details=cma_block_details(body),
            ) from exc
        raise CmaWeatherError(
            f"weather.cma.cn 返回 HTTP {exc.code}",
            status_code=exc.code,
            url=url,
        ) from exc
    except (URLError, TimeoutError) as exc:
        raise CmaWeatherError(f"读取 weather.cma.cn 页面失败：{exc}", url=url) from exc
    if is_cma_blocked(text):
        raise CmaWeatherError(
            "weather.cma.cn 返回安全拦截页",
            status_code=status_code,
            blocked=True,
            url=url,
            details=cma_block_details(text),
        )
    return text, status_code


def cma_failure_payload(exc: CmaWeatherError, page: dict[str, Any] | None = None) -> dict[str, Any]:
    payload = {
        "schema_version": SCHEMA_VERSION,
        "ok": False,
        "source": {
            "name": "中国气象局天气页面",
            "site": CMA_WEATHER_BASE_URL,
            "retrieved_at": now_cn().strftime("%Y-%m-%d %H:%M:%S %Z"),
        },
        "blocked": exc.blocked,
        "status_code": exc.status_code,
        "url": exc.url,
        "error": str(exc),
        "details": exc.details,
        "notes": [
            "这是官方天气页面的访问结果；如果被安全策略拦截，不要绕过拦截，保留 ok:false、status_code、error 和 details 供智能体判断。",
        ],
    }
    if page:
        payload["page"] = page
    return payload


def resolve_cma_page(page_id: str) -> tuple[str, dict[str, str]]:
    if page_id in CMA_PAGE_CATALOG:
        return page_id, CMA_PAGE_CATALOG[page_id]
    page_norm = normalize_name(page_id)
    matches = [
        (key, item)
        for key, item in CMA_PAGE_CATALOG.items()
        if page_norm
        and (
            page_norm == normalize_name(item["name"])
            or page_norm in normalize_name(item["name"])
            or page_norm in normalize_name(key)
        )
    ]
    if len(matches) == 1:
        return matches[0]
    if len(matches) > 1:
        candidates = "; ".join(f"{key}={item['name']}" for key, item in matches)
        raise CmaWeatherError(f"中国气象局页面 {page_id!r} 不唯一；候选项：{candidates}")
    raise CmaWeatherError(f"未知中国气象局页面 {page_id!r}；运行 catalog 查看支持的页面标识")


def fetch_cma_page(
    page_id: str,
    link_limit: int,
    image_limit: int,
    text_limit: int,
    *,
    path_override: str | None = None,
    page_override: dict[str, str] | None = None,
) -> dict[str, Any]:
    if path_override is None:
        resolved_id, item = resolve_cma_page(page_id)
    else:
        resolved_id = page_id
        item = page_override or {"name": page_id, "group": "自定义", "path": path_override}
    url = cma_absolute_url(item["path"])
    page = {
        "id": resolved_id,
        "name": item["name"],
        "group": item["group"],
        "url": url,
    }
    try:
        text, status_code = request_cma_text(url)
    except CmaWeatherError as exc:
        if not exc.url:
            exc.url = url
        return cma_failure_payload(exc, page)

    extractor = PageExtractor(url)
    extractor.feed(text)
    links = [link for link in dedupe_by_url(extractor.links) if useful_link(link)][:link_limit]
    images = [image for image in dedupe_by_url(extractor.images) if useful_image(image)][:image_limit]
    excerpt, truncated = html_to_text_excerpt(text, text_limit)
    return {
        "schema_version": SCHEMA_VERSION,
        "ok": True,
        "source": {
            "name": "中国气象局天气页面",
            "site": CMA_WEATHER_BASE_URL,
            "retrieved_at": now_cn().strftime("%Y-%m-%d %H:%M:%S %Z"),
            "status_code": status_code,
        },
        "page": page,
        "page_title": extractor.title,
        "text": {
            "excerpt": excerpt,
            "truncated": truncated,
        },
        "links": links,
        "images": images,
        "notes": [
            "这是 weather.cma.cn 官方公开页面的解析结果，只提取文字、链接和图片地址。",
            "如果本机返回安全拦截页，脚本会返回 ok:false，不尝试绕过。",
        ],
    }


def normalize_real_map_row(row: list[Any]) -> dict[str, Any]:
    return {
        "station": clean(row[0] if len(row) > 0 else None),
        "station_level": clean(row[1] if len(row) > 1 else None),
        "latitude": clean(row[2] if len(row) > 2 else None),
        "longitude": clean(row[3] if len(row) > 3 else None),
        "province_code": clean(row[4] if len(row) > 4 else None),
        "station_code": clean(row[5] if len(row) > 5 else None),
        "url": absolute_url(row[6] if len(row) > 6 else None),
        "rain_1h_mm": clean(row[7] if len(row) > 7 else None),
        "temperature_c": clean(row[8] if len(row) > 8 else None),
        "humidity_percent": clean(row[9] if len(row) > 9 else None),
        "pressure_hpa": clean(row[10] if len(row) > 10 else None),
        "wind_direction_degree": clean(row[11] if len(row) > 11 else None),
        "wind_speed_mps": clean(row[12] if len(row) > 12 else None),
    }


def normalize_forecast_map_row(row: list[Any]) -> dict[str, Any]:
    return {
        "city": clean(row[0] if len(row) > 0 else None),
        "station_level": clean(row[1] if len(row) > 1 else None),
        "longitude": clean(row[2] if len(row) > 2 else None),
        "latitude": clean(row[3] if len(row) > 3 else None),
        "date": clean(row[4] if len(row) > 4 else None),
        "date_relation": date_relation(row[4] if len(row) > 4 else None),
        "publish_time": clean(row[5] if len(row) > 5 else None),
        "publish_age_minutes": publish_age_minutes(row[5] if len(row) > 5 else None),
        "day": {
            "weather": clean(row[6] if len(row) > 6 else None),
            "weather_code": clean(row[7] if len(row) > 7 else None),
            "temperature_c": clean(row[8] if len(row) > 8 else None),
            "wind_direction": clean(row[9] if len(row) > 9 else None),
            "wind_power": clean(row[10] if len(row) > 10 else None),
        },
        "night": {
            "weather": clean(row[11] if len(row) > 11 else None),
            "weather_code": clean(row[12] if len(row) > 12 else None),
            "temperature_c": clean(row[13] if len(row) > 13 else None),
            "wind_direction": clean(row[14] if len(row) > 14 else None),
            "wind_power": clean(row[15] if len(row) > 15 else None),
        },
        "province_code": clean(row[16] if len(row) > 16 else None),
        "station_code": clean(row[17] if len(row) > 17 else None),
        "url": absolute_url(row[18] if len(row) > 18 else None),
    }


def filtered_limited_rows(rows: list[dict[str, Any]], args: argparse.Namespace) -> list[dict[str, Any]]:
    province_code = normalize_space(args.province_code).upper()
    city = normalize_name(args.city or "")
    filtered = []
    for row in rows:
        if province_code and normalize_space(row.get("province_code")).upper() != province_code:
            continue
        row_city = normalize_name(str(row.get("city") or row.get("station") or ""))
        if city and city not in row_city and row_city not in city:
            continue
        filtered.append(row)
    if args.all:
        return filtered
    return filtered[: args.limit]


def resolve_nmc_province_code(province: str | None) -> str:
    province_text = normalize_space(province)
    if not province_text:
        return ""
    if re.fullmatch(r"[A-Z]{3}", province_text.upper()):
        return province_text.upper()
    province_norm = normalize_name(province_text)
    provinces = http_json("/rest/province/all")
    matches = []
    for item in provinces:
        name = normalize_name(str(item.get("name") or item.get("province") or ""))
        code = normalize_space(item.get("code")).upper()
        if province_norm and code and (province_norm == name or province_norm in name or name in province_norm):
            matches.append(code)
    if len(matches) == 1:
        return matches[0]
    if len(matches) > 1:
        raise NmcError(f"省份 {province!r} 不唯一；请使用国家气象中心省份代码，例如 ABJ")
    raise NmcError(f"没有找到 {province!r} 对应的省份代码")


def resolve_cma_station_from_real_map(city: str, province: str | None) -> dict[str, Any]:
    city_norm = normalize_name(city)
    if not city_norm:
        raise CmaWeatherError("cma-city 必须提供城市名")
    province_code = resolve_nmc_province_code(province)
    payload = http_json("/rest/real/map/latestHour.json")
    rows = [normalize_real_map_row(row) for row in (payload.get("data") or {}).get("list") or []]
    candidates = []
    for row in rows:
        if province_code and normalize_space(row.get("province_code")).upper() != province_code:
            continue
        row_city = normalize_name(str(row.get("station") or ""))
        if row_city and (row_city == city_norm or city_norm in row_city or row_city in city_norm):
            candidates.append(row)
    exact = [row for row in candidates if normalize_name(str(row.get("station") or "")) == city_norm]
    if len(exact) == 1:
        return exact[0]
    if len(exact) > 1:
        candidates = exact
    if len(candidates) == 1:
        return candidates[0]
    if len(candidates) > 1:
        formatted = "; ".join(
            f"{row.get('province_code')}/{row.get('station')}({row.get('station_code')})" for row in candidates[:12]
        )
        raise CmaWeatherError(f"中国气象局城市 {city!r} 不唯一；请加 --province 或 --province-code 后重试。候选项：{formatted}")
    raise CmaWeatherError(f"在国家气象中心实况地图中没有找到 {city!r} 对应的中国气象局站点")


def fetch_cma_city(city: str, province: str | None, link_limit: int, image_limit: int, text_limit: int) -> dict[str, Any]:
    try:
        station = resolve_cma_station_from_real_map(city, province)
    except (NmcError, CmaWeatherError) as exc:
        if isinstance(exc, CmaWeatherError):
            cma_exc = exc
        else:
            cma_exc = CmaWeatherError(str(exc))
        return cma_failure_payload(cma_exc, {"id": "city", "name": city, "group": "城市预报", "url": None})
    station_code = normalize_space(station.get("station_code"))
    page = {
        "name": f"{station.get('station')}城市预报",
        "group": "城市预报",
        "path": f"/web/weather/{station_code}",
    }
    result = fetch_cma_page(
        f"city-{station_code}",
        link_limit,
        image_limit,
        text_limit,
        path_override=page["path"],
        page_override=page,
    )
    result["station_resolution"] = {
        "method": "国家气象中心全国实况地图站点编码 -> weather.cma.cn 城市页",
        "city": station.get("station"),
        "province_code": station.get("province_code"),
        "station_code": station_code,
        "latitude": station.get("latitude"),
        "longitude": station.get("longitude"),
        "nmc_url": station.get("url"),
    }
    return result


def latest_rank_ymdh(rank_type: str, hours: int, period: str | None) -> str:
    text = http_text(BASE_URL + "/", headers=HEADERS)
    if hours in {1, 6}:
        match = re.search(rf'<select[^>]+id=["\']?{hours}h_list["\']?[^>]*>(.*?)</select>', text, re.S)
        if match:
            option = re.search(r'value=["\']?(\d{10})["\']?', match.group(1))
            if option:
                return option.group(1)
    if hours == 24:
        hidden_ids: list[str]
        if rank_type == "rain":
            hidden_ids = ["r20_js_ymdh", "r08_js_ymdh"] if period != "08" else ["r08_js_ymdh", "r20_js_ymdh"]
        elif rank_type == "maxtemp":
            hidden_ids = ["ht_qw_ymdh"]
        elif rank_type == "mintemp":
            hidden_ids = ["lt_qw_ymdh"]
        else:
            raise NmcError("24 小时排行只支持 rain、maxtemp、mintemp")
        values = []
        for hidden_id in hidden_ids:
            match = re.search(rf'id=["\']?{hidden_id}["\']?\s+value=["\']?(\d{{10}})["\']?', text)
            if match:
                values.append(match.group(1))
        if values:
            return max(values)
    raise NmcError("无法从国家气象中心首页解析最新排行时次；请显式传入 --ymdh")


def normalize_rank_type(value: str) -> str:
    mapping = {
        "rain": "rain",
        "降水": "rain",
        "降雨": "rain",
        "temperature": "maxtemp",
        "temp": "maxtemp",
        "气温": "maxtemp",
        "高温": "maxtemp",
        "maxtemp": "maxtemp",
        "最高气温": "maxtemp",
        "mintemp": "mintemp",
        "低温": "mintemp",
        "最低气温": "mintemp",
        "wind": "wind",
        "风": "wind",
        "风速": "wind",
    }
    key = normalize_space(value).lower()
    if key not in mapping:
        raise NmcError(f"不支持的排行类型 {value!r}；请使用 rain、maxtemp、mintemp 或 wind")
    return mapping[key]


def rank_unit(rank_type: str) -> str:
    return {"rain": "mm", "maxtemp": "℃", "mintemp": "℃", "wind": "m/s"}.get(rank_type, "")


def normalize_rank_rows(rows: list[dict[str, Any]], rank_type: str, limit: int) -> list[dict[str, Any]]:
    normalized = []
    for index, row in enumerate(rows[:limit], start=1):
        pcode = clean(row.get("pcode"))
        pinyin = clean(row.get("pinyin"))
        url = absolute_url(f"/publish/forecast/{pcode}/{pinyin}.html") if pcode and pinyin else None
        normalized.append(
            {
                "rank": index,
                "province": clean(row.get("pname")),
                "city": clean(row.get("name")),
                "station_code": clean(row.get("code")),
                "value": clean(row.get("value")),
                "unit": rank_unit(rank_type),
                "url": url,
            }
        )
    return normalized


def fetch_layer_images(kind: str, limit: int) -> dict[str, Any]:
    if kind not in {"radar", "satellite"}:
        raise NmcError("图层类型必须是 radar 或 satellite")
    if kind == "satellite":
        product = fetch_product("satellite-fy4b", link_limit=0, image_limit=limit, text_limit=1000)
        return {
            "schema_version": SCHEMA_VERSION,
            "ok": True,
            "source": product["source"],
            "kind": "卫星图层",
            "page_generated_time": product.get("page_generated_time"),
            "images": [
                {
                    "time": extract_image_time_code(image.get("url")),
                    "image": image.get("url"),
                }
                for image in product.get("images", [])
            ],
            "notes": [
                "卫星图层使用国家气象中心卫星云图产品页图片地址，time 为图片文件名中的产品时次代码。",
                "同时查看 page_generated_time、正文中的产品制作时间和当前查询时间。",
            ],
        }
    endpoint = f"{TYPHOON_BASE_URL}/publish/{kind}/latest.json"
    payload = http_json(endpoint)
    rows = payload.get("data") or []
    images = []
    for row in rows[:limit]:
        if not isinstance(row, list) or len(row) < 2:
            continue
        images.append(
            {
                "time": clean(row[0]),
                "image": absolute_url(f"/publish{row[1]}", TYPHOON_BASE_URL),
            }
        )
    return {
        "schema_version": SCHEMA_VERSION,
        "ok": payload.get("code") == 0,
        "source": {
            "name": "国家气象中心台风网图层",
            "site": TYPHOON_BASE_URL,
            "endpoint": f"/publish/{kind}/latest.json",
            "retrieved_at": now_cn().strftime("%Y-%m-%d %H:%M:%S %Z"),
        },
        "kind": "雷达图层" if kind == "radar" else "卫星图层",
        "images": images,
        "notes": ["图层序列只返回图片地址和图上时间；需要自行比较图上时间与当前查询时间。"],
    }


def extract_image_time_code(url: Any) -> str | None:
    if not isinstance(url, str):
        return None
    match = re.search(r"_(\d{14})\d{3}", url)
    if not match:
        match = re.search(r"(\d{14})", url)
    if not match:
        return None
    value = match.group(1)
    return f"{value[0:4]}-{value[4:6]}-{value[6:8]} {value[8:10]}:{value[10:12]}:{value[12:14]}"


def weather_payload(station_code: str) -> dict[str, Any]:
    payload = http_json(f"/rest/weather?stationid={station_code}")
    if payload.get("code") != 0:
        raise NmcError(f"国家气象中心返回非成功响应：{payload.get('msg') or payload.get('code')}")
    data = payload.get("data")
    if not isinstance(data, dict):
        raise NmcError("国家气象中心响应中没有 data 字段")
    return data


def absolute_url(value: Any, base_url: str = BASE_URL) -> str | None:
    if is_missing(value):
        return None
    text = str(value)
    if text.startswith("//"):
        if re.match(r"^//[^/]+\.[^/]+/", text):
            text = "https:" + text
        else:
            text = text[1:]
    return re.sub(r"^(https?://[^/]+)//+", r"\1/", urljoin(base_url, text))


def normalize_station(data: dict[str, Any], fallback: Station) -> dict[str, Any]:
    station = (data.get("real") or {}).get("station") or (data.get("predict") or {}).get("station") or {}
    return {
        "code": clean(station.get("code") or fallback.code),
        "province": clean(station.get("province") or fallback.province),
        "city": clean(station.get("city") or fallback.city),
        "url": absolute_url(station.get("url") or fallback.url),
    }


def normalize_warning(real: dict[str, Any]) -> dict[str, Any] | None:
    warn = real.get("warn") or {}
    if is_missing(warn.get("alert")) and is_missing(warn.get("issuecontent")):
        return None
    return {
        "alert": clean(warn.get("alert")),
        "province": clean(warn.get("province")),
        "city": clean(warn.get("city")),
        "signal_type": clean(warn.get("signaltype")),
        "signal_level": clean(warn.get("signallevel")),
        "issue_content": clean(warn.get("issuecontent")),
        "defense_guidance": clean(warn.get("fmeans")),
        "url": absolute_url(warn.get("url")),
    }


def normalize_realtime(real: dict[str, Any]) -> dict[str, Any]:
    weather = real.get("weather") or {}
    wind = real.get("wind") or {}
    publish_time = clean(real.get("publish_time"))
    return {
        "publish_time": publish_time,
        "publish_age_minutes": publish_age_minutes(publish_time),
        "weather": {
            "text": clean(weather.get("info")),
            "temperature_c": clean(weather.get("temperature")),
            "feels_like_c": clean(weather.get("feelst")),
            "temperature_diff_c": clean(weather.get("temperatureDiff")),
            "humidity_percent": clean(weather.get("humidity")),
            "rain_1h_mm": clean(weather.get("rain")),
            "pressure_hpa": clean(weather.get("airpressure")),
            "comfort_index": clean(weather.get("icomfort")),
            "comfort_text": clean(weather.get("rcomfort")),
        },
        "wind": {
            "direction": clean(wind.get("direct")),
            "degree": clean(wind.get("degree")),
            "power": clean(wind.get("power")),
            "speed_mps": clean(wind.get("speed")),
        },
        "sunrise_sunset": clean(real.get("sunriseSunset") or {}),
    }


def normalize_day_part(part: dict[str, Any]) -> dict[str, Any]:
    weather = part.get("weather") or {}
    wind = part.get("wind") or {}
    return {
        "weather": clean(weather.get("info")),
        "temperature_c": clean(weather.get("temperature")),
        "wind_direction": clean(wind.get("direct")),
        "wind_power": clean(wind.get("power")),
    }


def normalize_forecast(predict: dict[str, Any], max_days: int, warning: dict[str, Any] | None) -> dict[str, Any]:
    publish_time = clean(predict.get("publish_time"))
    days = []
    for item in (predict.get("detail") or [])[:max_days]:
        day = {
            "date": clean(item.get("date")),
            "date_relation": date_relation(item.get("date")),
            "publish_time": clean(item.get("pt") or publish_time),
            "day": normalize_day_part(item.get("day") or {}),
            "night": normalize_day_part(item.get("night") or {}),
            "precipitation_mm": clean(item.get("precipitation")),
        }
        day["risk"] = assess_day_risk(day, warning)
        days.append(day)
    return {
        "publish_time": publish_time,
        "publish_age_minutes": publish_age_minutes(publish_time),
        "days": days,
    }


def normalize_air(air: dict[str, Any] | None) -> dict[str, Any] | None:
    if not air:
        return None
    result = {
        "forecast_time": clean(air.get("forecasttime")),
        "aqi": clean(air.get("aqi")),
        "level": clean(air.get("aq")),
        "quality": clean(air.get("text")),
    }
    if all(value is None for value in result.values()):
        return None
    return result


def normalize_daily_temperature_chart(data: dict[str, Any], limit: int) -> list[dict[str, Any]]:
    if limit <= 0:
        return []
    rows = data.get("tempchart") or data.get("tempChart") or []
    normalized = []
    for row in rows[-limit:]:
        normalized.append(
            {
                "date": clean(row.get("time")),
                "date_relation": date_relation(row.get("time")),
                "max_temperature_c": clean(row.get("max_temp")),
                "min_temperature_c": clean(row.get("min_temp")),
                "day_weather": clean(row.get("day_text")),
                "night_weather": clean(row.get("night_text")),
            }
        )
    return normalized


def normalize_climate(data: dict[str, Any]) -> dict[str, Any] | None:
    climate = data.get("climate")
    if not isinstance(climate, dict):
        return None
    months = []
    for row in climate.get("month") or []:
        months.append(
            {
                "month": clean(row.get("month")),
                "avg_max_temperature_c": clean(row.get("maxTemp")),
                "avg_min_temperature_c": clean(row.get("minTemp")),
                "avg_precipitation_mm": clean(row.get("precipitation")),
            }
        )
    return {"normal_period": clean(climate.get("time")), "months": months}


def normalize_hourly(data: dict[str, Any], limit: int) -> list[dict[str, Any]]:
    if limit <= 0:
        return []
    rows = data.get("passedchart") or data.get("passedChart") or []
    normalized = []
    for row in rows[:limit]:
        normalized.append(
            {
                "time": clean(row.get("time")),
                "temperature_c": clean(row.get("temperature")),
                "humidity_percent": clean(row.get("humidity")),
                "pressure_hpa": clean(row.get("pressure")),
                "rain_1h_mm": clean(row.get("rain1h")),
                "rain_6h_mm": clean(row.get("rain6h")),
                "rain_12h_mm": clean(row.get("rain12h")),
                "rain_24h_mm": clean(row.get("rain24h")),
                "wind_direction_degree": clean(row.get("windDirection")),
                "wind_speed_mps": clean(row.get("windSpeed")),
            }
        )
    return normalized


def date_relation(value: Any) -> str:
    if not isinstance(value, str):
        return "未知"
    date_value = None
    for fmt in ("%Y-%m-%d", "%Y/%m/%d"):
        try:
            date_value = datetime.strptime(value, fmt).date()
            break
        except ValueError:
            continue
    if date_value is None:
        return "未知"
    today = now_cn().date()
    if date_value < today:
        return "过去"
    if date_value == today:
        return "今天"
    return "未来"


def wind_power_number(value: Any) -> int | None:
    if is_missing(value):
        return None
    numbers = [int(item) for item in re.findall(r"\d+", str(value))]
    return max(numbers) if numbers else None


def risk_level(score: int) -> str:
    if score >= 5:
        return "严重"
    if score >= 4:
        return "高"
    if score >= 2:
        return "中"
    return "低"


def warning_score(warning: dict[str, Any] | None) -> tuple[int, list[str]]:
    if not warning:
        return 0, []
    text = "".join(str(warning.get(key) or "") for key in ("alert", "signal_type", "signal_level", "issue_content"))
    if "红色" in text:
        return 5, ["存在红色预警信号"]
    if "橙色" in text:
        return 4, ["存在橙色预警信号"]
    if "黄色" in text:
        return 3, ["存在黄色预警信号"]
    if "蓝色" in text:
        return 2, ["存在蓝色预警信号"]
    return 2, ["存在预警信号"]


def assess_day_risk(day: dict[str, Any], warning: dict[str, Any] | None) -> dict[str, Any]:
    score, reasons = warning_score(warning)
    texts = " ".join(
        str(value or "")
        for value in (
            day.get("day", {}).get("weather"),
            day.get("night", {}).get("weather"),
            day.get("day", {}).get("wind_power"),
            day.get("night", {}).get("wind_power"),
        )
    )
    precipitation = day.get("precipitation_mm")
    try:
        precipitation_value = float(precipitation) if precipitation is not None else 0.0
    except (TypeError, ValueError):
        precipitation_value = 0.0

    if any(keyword in texts for keyword in ("特大暴雨", "大暴雨", "暴雪", "台风", "冰雹", "雷暴大风")):
        score = max(score, 5)
        reasons.append("预报包含强灾害性天气描述")
    elif any(keyword in texts for keyword in ("暴雨", "大雪", "冻雨", "道路结冰")):
        score = max(score, 4)
        reasons.append("预报包含高影响天气描述")
    elif any(keyword in texts for keyword in ("大雨", "雷阵雨", "中雪", "大风", "沙尘", "雾")):
        score = max(score, 3)
        reasons.append("预报包含中等影响天气描述")
    elif any(keyword in texts for keyword in ("小雨", "阵雨", "小雪")):
        score = max(score, 2)
        reasons.append("预报包含降水描述")

    if precipitation_value >= 50:
        score = max(score, 5)
        reasons.append(f"预报降水 {precipitation_value:g} mm")
    elif precipitation_value >= 25:
        score = max(score, 4)
        reasons.append(f"预报降水 {precipitation_value:g} mm")
    elif precipitation_value >= 10:
        score = max(score, 3)
        reasons.append(f"预报降水 {precipitation_value:g} mm")
    elif precipitation_value >= 1:
        score = max(score, 2)
        reasons.append(f"预报降水 {precipitation_value:g} mm")

    for part in ("day", "night"):
        power = wind_power_number(day.get(part, {}).get("wind_power"))
        if power and power >= 6:
            score = max(score, 4)
            reasons.append(f"{part} 风力 {power} 级")
        elif power and power >= 4:
            score = max(score, 3)
            reasons.append(f"{part} 风力 {power} 级")

    return {"level": risk_level(score), "score": score, "reasons": sorted(set(reasons))}


def assess_current_risk(realtime: dict[str, Any], hourly: list[dict[str, Any]], warning: dict[str, Any] | None) -> dict[str, Any]:
    score, reasons = warning_score(warning)
    text = str(realtime.get("weather", {}).get("text") or "")
    rain = realtime.get("weather", {}).get("rain_1h_mm")
    wind_speed = realtime.get("wind", {}).get("speed_mps")

    try:
        rain_value = float(rain) if rain is not None else 0.0
    except (TypeError, ValueError):
        rain_value = 0.0
    try:
        wind_value = float(wind_speed) if wind_speed is not None else 0.0
    except (TypeError, ValueError):
        wind_value = 0.0

    hourly_rain_values = []
    for row in hourly[:3]:
        value = row.get("rain_1h_mm")
        if value is not None:
            try:
                hourly_rain_values.append(float(value))
            except (TypeError, ValueError):
                pass
    max_recent_rain = max(hourly_rain_values) if hourly_rain_values else 0.0

    if any(keyword in text for keyword in ("暴雨", "雷暴", "冰雹", "暴雪", "台风")):
        score = max(score, 4)
        reasons.append("当前实况包含高影响天气描述")
    elif any(keyword in text for keyword in ("大雨", "雷阵雨", "大雪", "大风", "沙尘", "雾")):
        score = max(score, 3)
        reasons.append("当前实况包含中等影响天气描述")
    elif any(keyword in text for keyword in ("小雨", "阵雨", "小雪")):
        score = max(score, 2)
        reasons.append("当前实况包含降水描述")

    if rain_value >= 10 or max_recent_rain >= 10:
        score = max(score, 4)
        reasons.append("近小时雨量较强")
    elif rain_value >= 2.5 or max_recent_rain >= 2.5:
        score = max(score, 3)
        reasons.append("近小时有明显降水")
    elif rain_value > 0 or max_recent_rain > 0:
        score = max(score, 2)
        reasons.append("近小时有降水")

    if wind_value >= 10.8:
        score = max(score, 4)
        reasons.append("当前风速较大")
    elif wind_value >= 5.5:
        score = max(score, 3)
        reasons.append("当前风速偏大")

    return {"level": risk_level(score), "score": score, "reasons": sorted(set(reasons))}


def overall_risk(
    forecast: dict[str, Any],
    warning: dict[str, Any] | None,
    current_risk: dict[str, Any],
) -> dict[str, Any]:
    upcoming_days = [item for item in forecast.get("days", []) if item.get("date_relation") in {"今天", "未来"}]
    scores = [item.get("risk", {}).get("score", 0) for item in upcoming_days[:2]]
    warning_base, warning_reasons = warning_score(warning)
    score = max(scores + [warning_base, current_risk.get("score", 0), 0])
    reasons = list(warning_reasons)
    reasons.extend(current_risk.get("reasons", []))
    for item in upcoming_days[:2]:
        reasons.extend(item.get("risk", {}).get("reasons", []))
    return {
        "level": risk_level(score),
        "score": score,
        "reasons": sorted(set(reasons)),
        "inputs_considered": [
            "城市预警信号或 alerts",
            "数据发布时间与当前查询时间的距离",
            "今天和明天预报",
            "未来逐小时预报数据",
            "雷达、卫星、实况地图和实况排行",
            "近期小时观测中的降水、风力趋势",
            "后续 3-7 天预报和官方产品页",
        ],
    }


def build_result(args: argparse.Namespace) -> dict[str, Any]:
    station = resolve_station(args.city, args.province, args.station_id, args.refresh_stations)
    data = weather_payload(station.code)
    real = data.get("real") or {}
    predict = data.get("predict") or {}
    warning = normalize_warning(real)
    forecast = normalize_forecast(predict, args.days, warning)
    realtime = normalize_realtime(real)
    hourly = normalize_hourly(data, args.hourly)
    air = normalize_air(data.get("air"))
    current_risk = assess_current_risk(realtime, hourly, warning)
    result = {
        "schema_version": SCHEMA_VERSION,
        "ok": True,
        "source": {
            "name": "国家气象中心/中央气象台",
            "site": BASE_URL,
            "endpoint": "/rest/weather",
            "retrieved_at": now_cn().strftime("%Y-%m-%d %H:%M:%S %Z"),
        },
        "time_notice": "注意查看 publish_time 与当前查询时间 retrieved_at 的距离；脚本只提供 publish_age_minutes，不做时效等级判断。",
        "query": {
            "input_city": args.city,
            "input_province": args.province,
            "input_station_id": args.station_id,
        },
        "station": normalize_station(data, station),
        "warning": warning,
        "realtime": realtime,
        "forecast": forecast,
        "air": air,
        "recent_hourly": hourly,
        "daily_temperature_chart": normalize_daily_temperature_chart(data, args.daily_chart),
        "current_risk": current_risk,
        "overall_risk": overall_risk(forecast, warning, current_risk),
        "capabilities": {
            "city_resolution": "通过 /rest/province 接口解析省份和城市站点",
            "current_conditions": True,
            "seven_day_forecast": True,
            "city_warning_signal": warning is not None,
            "air_quality": air is not None,
            "recent_hourly_observations": bool(hourly),
            "hourly_forecast_data": bool(args.hourly_forecast),
            "cma_city_page_attempted": bool(getattr(args, "include_cma", False)),
            "cma_city_page_data": False,
            "daily_temperature_chart": args.daily_chart > 0,
            "climate_normals": bool(args.include_climate),
            "regional_radar_metadata": data.get("radar") is not None,
        },
        "notes": [
            "官方公开国家气象中心数据；预报是指导信息，不是确定承诺。",
            "9999 等占位值会输出为 null。",
            "行程风险判断需要同时看预警信号、普通预报、近小时观测和可用官方页面数据。",
        ],
    }
    radar = data.get("radar") or {}
    if radar:
        result["radar"] = {
            "title": clean(radar.get("title")),
            "image": absolute_url(radar.get("image")),
            "url": absolute_url(radar.get("url")),
            }
    if args.include_climate:
        result["climate"] = normalize_climate(data)
    if getattr(args, "include_cma", False):
        cma_city = args.city or result["station"].get("city")
        cma_province = args.province or result["station"].get("province")
        result["cma_city_page"] = fetch_cma_city(cma_city, cma_province, 10, 8, 4000)
        result["capabilities"]["cma_city_page_data"] = bool(result["cma_city_page"].get("ok"))
    if args.hourly_forecast:
        hourly_city = args.city or result["station"].get("city")
        hourly_province = args.province or result["station"].get("province")
        try:
            result["hourly_forecast"] = fetch_china_weather_hourly_forecast(
                hourly_city,
                hourly_province,
                args.hourly_forecast_limit,
            )
        except ChinaWeatherError as exc:
            result["hourly_forecast"] = {
                "ok": False,
                "source": {
                    "name": "中国天气网",
                    "site": CHINA_WEATHER_BASE_URL,
                    "retrieved_at": now_cn().strftime("%Y-%m-%d %H:%M:%S %Z"),
                },
                "error": str(exc),
            }
    return result


def cmd_query(args: argparse.Namespace) -> int:
    try:
        result = build_result(args)
    except NmcError as exc:
        print(json.dumps({"ok": False, "error": str(exc)}, ensure_ascii=False, indent=2), file=sys.stderr)
        return 2
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


def cmd_stations(args: argparse.Namespace) -> int:
    try:
        stations = load_stations(refresh=args.refresh_stations)
        query = normalize_name(args.city or "")
        province = normalize_name(args.province or "")
        matches = []
        for station in stations:
            if province and province not in normalize_name(station.province):
                continue
            if query and query not in normalize_name(station.city) and normalize_name(station.city) not in query:
                continue
            matches.append(station.__dict__)
        print(json.dumps({"source": BASE_URL, "count": len(matches), "stations": matches[: args.limit]}, ensure_ascii=False, indent=2))
        return 0
    except NmcError as exc:
        print(json.dumps({"ok": False, "error": str(exc)}, ensure_ascii=False, indent=2), file=sys.stderr)
        return 2


def cmd_catalog(args: argparse.Namespace) -> int:
    group_filter = normalize_space(args.group)
    products = []
    for product_id, item in PRODUCT_CATALOG.items():
        if group_filter and group_filter not in item["group"] and group_filter not in item["name"]:
            continue
        products.append(
            {
                "id": product_id,
                "name": item["name"],
                "group": item["group"],
                "url": absolute_url(item["path"], BASE_URL),
            }
        )
    cma_pages = []
    for page_id, item in CMA_PAGE_CATALOG.items():
        if group_filter and group_filter not in item["group"] and group_filter not in item["name"]:
            continue
        cma_pages.append(
            {
                "id": page_id,
                "name": item["name"],
                "group": item["group"],
                "url": cma_absolute_url(item["path"]),
            }
        )
    payload = {
        "schema_version": SCHEMA_VERSION,
        "ok": True,
        "source": BASE_URL,
        "retrieved_at": now_cn().strftime("%Y-%m-%d %H:%M:%S %Z"),
        "data_sources": {
            "nmc_cn": "国家气象中心/中央气象台 nmc.cn",
            "weather_com_cn_hourly": "中国天气网 weather.com.cn",
            "cma_weather_cn": "中国气象局天气页面 weather.cma.cn",
        },
        "commands": [
            {"command": "query", "use": "城市实况、7 天预报、预警、空气质量、近期小时观测；加 --hourly-forecast 查询未来逐小时数据，加 --include-cma 同时抓取中国气象局城市页"},
            {"command": "stations", "use": "查城市/站点候选，处理重名城市"},
            {"command": "map-weather", "use": "全国或指定省份代码的实况、今天、明天城市天气地图数据"},
            {"command": "rank", "use": "全国降水、气温、风速实况排行"},
            {"command": "alerts", "use": "全国公开预警信号列表，可按省份关键词过滤"},
            {"command": "layers", "use": "雷达或卫星图层序列图片地址"},
            {"command": "product", "use": "查询国家气象中心官方产品页、公报、图像产品、台风海洋、环境农业和数值预报页面"},
            {"command": "cma-healthcheck", "use": "检测 weather.cma.cn 是否可由本机脚本访问；常见结果是安全策略拦截"},
            {"command": "cma-page", "use": "读取 weather.cma.cn 官方页面摘要；如果被拦截则返回 ok:false"},
            {"command": "cma-city", "use": "用国家气象中心实况地图解析数值站号后尝试读取 weather.cma.cn 城市天气页"},
            {"command": "healthcheck", "use": "来源连通性和城市覆盖抽样检查"},
        ],
        "products": products,
        "cma_pages": cma_pages,
    }
    print(json.dumps(payload, ensure_ascii=False, indent=2))
    return 0


def cmd_product(args: argparse.Namespace) -> int:
    try:
        result = fetch_product(args.product_id, args.link_limit, args.image_limit, args.text_limit)
    except NmcError as exc:
        print(json.dumps({"ok": False, "error": str(exc)}, ensure_ascii=False, indent=2), file=sys.stderr)
        return 2
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


def cmd_cma_page(args: argparse.Namespace) -> int:
    try:
        result = fetch_cma_page(args.page_id, args.link_limit, args.image_limit, args.text_limit)
    except CmaWeatherError as exc:
        result = cma_failure_payload(exc)
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


def cmd_cma_city(args: argparse.Namespace) -> int:
    result = fetch_cma_city(args.city, args.province or args.province_code, args.link_limit, args.image_limit, args.text_limit)
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


def cmd_cma_healthcheck(args: argparse.Namespace) -> int:
    checks = []
    for page_id in args.pages:
        result = fetch_cma_page(page_id, link_limit=0, image_limit=0, text_limit=200)
        checks.append(
            {
                "page_id": page_id,
                "ok": result.get("ok"),
                "blocked": result.get("blocked", False),
                "status_code": result.get("status_code") or result.get("source", {}).get("status_code"),
                "url": result.get("url") or result.get("page", {}).get("url"),
                "error": result.get("error"),
                "details": result.get("details"),
            }
        )
    blocked = [item for item in checks if item.get("blocked")]
    failed = [item for item in checks if not item.get("ok")]
    payload = {
        "schema_version": SCHEMA_VERSION,
        "ok": not failed,
        "source": {
            "name": "中国气象局天气页面",
            "site": CMA_WEATHER_BASE_URL,
            "retrieved_at": now_cn().strftime("%Y-%m-%d %H:%M:%S %Z"),
        },
        "checked_count": len(checks),
        "success_count": len(checks) - len(failed),
        "failure_count": len(failed),
        "blocked_count": len(blocked),
        "results": checks,
        "notes": [
            "weather.cma.cn 是官方天气展示页面，但本地脚本环境可能被安全策略拦截。",
            "如果 blocked_count 大于 0，不要绕过拦截；保留失败结果，并继续查看其它已成功返回的数据。",
        ],
    }
    print(json.dumps(payload, ensure_ascii=False, indent=2))
    return 0


def cmd_map_weather(args: argparse.Namespace) -> int:
    try:
        if args.kind == "real":
            payload = http_json("/rest/real/map/latestHour.json")
            data = payload.get("data") or {}
            rows = [normalize_real_map_row(row) for row in data.get("list") or []]
            source_endpoint = "/rest/real/map/latestHour.json"
            result = {
                "schema_version": SCHEMA_VERSION,
                "ok": payload.get("code") == 0,
                "source": {
                    "name": "国家气象中心/中央气象台",
                    "site": BASE_URL,
                    "endpoint": source_endpoint,
                    "retrieved_at": now_cn().strftime("%Y-%m-%d %H:%M:%S %Z"),
                },
                "kind": "全国城市实况地图",
                "update_time": clean(data.get("update_time")),
                "headers": clean(data.get("header")),
                "count_total": len(rows),
                "rows": filtered_limited_rows(rows, args),
            }
        else:
            day = 1 if args.kind == "today" else 2
            source_endpoint = f"/dataservice/weather/map/ALL/day{day}.json"
            payload = http_json(source_endpoint)
            rows = [normalize_forecast_map_row(row) for row in payload.get("data") or []]
            result = {
                "schema_version": SCHEMA_VERSION,
                "ok": payload.get("code") == 0,
                "source": {
                    "name": "国家气象中心/中央气象台",
                    "site": BASE_URL,
                    "endpoint": source_endpoint,
                    "retrieved_at": now_cn().strftime("%Y-%m-%d %H:%M:%S %Z"),
                },
                "kind": "全国今天城市预报地图" if args.kind == "today" else "全国明天城市预报地图",
                "count_total": len(rows),
                "rows": filtered_limited_rows(rows, args),
            }
    except NmcError as exc:
        print(json.dumps({"ok": False, "error": str(exc)}, ensure_ascii=False, indent=2), file=sys.stderr)
        return 2
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


def cmd_rank(args: argparse.Namespace) -> int:
    try:
        rank_type = normalize_rank_type(args.type)
        if rank_type == "wind" and args.hours != 1:
            raise NmcError("风速排行只支持 --hours 1")
        ymdh = args.ymdh or latest_rank_ymdh(rank_type, args.hours, args.period)
        endpoint = f"/rest/realrank/{rank_type}/{args.hours}/{ymdh}"
        payload = http_json(endpoint)
        data = payload.get("data") or {}
        rows = normalize_rank_rows(data.get("data") or [], rank_type, args.limit)
        result = {
            "schema_version": SCHEMA_VERSION,
            "ok": payload.get("code") == 0,
            "source": {
                "name": "国家气象中心/中央气象台",
                "site": BASE_URL,
                "endpoint": endpoint,
                "retrieved_at": now_cn().strftime("%Y-%m-%d %H:%M:%S %Z"),
            },
            "rank_type": {"rain": "降水", "maxtemp": "最高气温", "mintemp": "最低气温", "wind": "风速"}[rank_type],
            "hours": args.hours,
            "ymdh": ymdh,
            "format_time": clean(data.get("format_time") or data.get("time")),
            "rows": rows,
        }
    except NmcError as exc:
        print(json.dumps({"ok": False, "error": str(exc)}, ensure_ascii=False, indent=2), file=sys.stderr)
        return 2
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


def cmd_alerts(args: argparse.Namespace) -> int:
    try:
        province = normalize_space(args.province)
        query = urlencode(
            {
                "pageNo": args.page,
                "pageSize": args.limit,
                "signaltype": args.signal_type,
                "signallevel": args.signal_level,
                "province": province,
            }
        )
        endpoint = f"/rest/findAlarm?{query}"
        payload = http_json(endpoint)
        data = payload.get("data") or {}
        page = data.get("page") or {}
        alerts = []
        for item in page.get("list") or []:
            alerts.append(
                {
                    "alert_id": clean(item.get("alertid")),
                    "issue_time": clean(item.get("issuetime")),
                    "title": clean(item.get("title")),
                    "url": absolute_url(item.get("url")),
                    "icon": absolute_url(item.get("pic")),
                }
            )
        province_alarms = []
        for item in data.get("provinceAlarms") or []:
            province_alarms.append(
                {
                    "alert_id": clean(item.get("alertid")),
                    "issue_time": clean(item.get("issuetime")),
                    "title": clean(item.get("title")),
                    "url": absolute_url(item.get("url")),
                    "icon": absolute_url(item.get("pic")),
                }
            )
        result = {
            "schema_version": SCHEMA_VERSION,
            "ok": payload.get("code") == 0,
            "source": {
                "name": "国家气象中心/中央气象台",
                "site": BASE_URL,
                "endpoint": endpoint,
                "retrieved_at": now_cn().strftime("%Y-%m-%d %H:%M:%S %Z"),
            },
            "province_filter": args.province,
            "signal_type_filter": args.signal_type,
            "signal_level_filter": args.signal_level,
            "page": {
                "page_no": clean(page.get("pageNo")),
                "page_size": clean(page.get("pageSize")),
                "total_count": clean(page.get("count")),
                "total_page": clean(page.get("totalPage")),
            },
            "alerts": alerts,
            "province_alarms": province_alarms,
            "notes": ["列表来自公开预警接口；单条预警详情可直接访问返回的 url。"],
        }
    except NmcError as exc:
        print(json.dumps({"ok": False, "error": str(exc)}, ensure_ascii=False, indent=2), file=sys.stderr)
        return 2
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


def cmd_layers(args: argparse.Namespace) -> int:
    try:
        result = fetch_layer_images(args.kind, args.limit)
    except NmcError as exc:
        print(json.dumps({"ok": False, "error": str(exc)}, ensure_ascii=False, indent=2), file=sys.stderr)
        return 2
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


def province_groups(stations: list[Station]) -> dict[str, list[Station]]:
    groups: dict[str, list[Station]] = {}
    for station in stations:
        groups.setdefault(station.province, []).append(station)
    return groups


def station_health(station: Station) -> dict[str, Any]:
    started = time.time()
    try:
        data = weather_payload(station.code)
        real = data.get("real") or {}
        predict = data.get("predict") or {}
        realtime_time = clean(real.get("publish_time"))
        forecast_time = clean(predict.get("publish_time"))
        forecast_days = len(predict.get("detail") or [])
        return {
            "ok": bool(realtime_time or forecast_time) and forecast_days > 0,
            "province": station.province,
            "city": station.city,
            "station_code": station.code,
            "realtime_publish_time": realtime_time,
            "forecast_publish_time": forecast_time,
            "forecast_days": forecast_days,
            "has_warning": normalize_warning(real) is not None,
            "has_air": data.get("air") is not None,
            "has_hourly": bool(data.get("passedchart") or data.get("passedChart")),
            "elapsed_ms": round((time.time() - started) * 1000),
        }
    except NmcError as exc:
        return {
            "ok": False,
            "province": station.province,
            "city": station.city,
            "station_code": station.code,
            "error": str(exc),
            "elapsed_ms": round((time.time() - started) * 1000),
        }


def cmd_healthcheck(args: argparse.Namespace) -> int:
    try:
        stations = load_stations(refresh=args.refresh_stations)
    except NmcError as exc:
        print(json.dumps({"ok": False, "error": str(exc)}, ensure_ascii=False, indent=2), file=sys.stderr)
        return 2

    groups = province_groups(stations)
    samples: list[Station] = []
    for province in sorted(groups):
        samples.extend(groups[province][: args.per_province])
    if args.limit:
        samples = samples[: args.limit]

    results = []
    for index, station in enumerate(samples):
        if index and args.delay > 0:
            time.sleep(args.delay)
        results.append(station_health(station))

    failed = [item for item in results if not item.get("ok")]
    payload = {
        "schema_version": SCHEMA_VERSION,
        "ok": not failed and bool(results),
        "source": BASE_URL,
        "retrieved_at": now_cn().strftime("%Y-%m-%d %H:%M:%S %Z"),
        "station_count": len(stations),
        "province_count": len(groups),
        "sample_count": len(results),
        "success_count": len(results) - len(failed),
        "failure_count": len(failed),
        "results": results,
    }
    print(json.dumps(payload, ensure_ascii=False, indent=2))
    return 0 if payload["ok"] else 1


def parser() -> argparse.ArgumentParser:
    configure_argparse_chinese()
    root = argparse.ArgumentParser(description="查询中国公开天气数据，并输出规范化 JSON。")
    subparsers = root.add_subparsers(dest="command", required=True)

    query = subparsers.add_parser("query", help="查询单个城市或站点。")
    query.add_argument("city", nargs="?", help="城市名，例如 北京、上海、朝阳。")
    query.add_argument("--province", help="用于区分重名城市的省份或直辖市，例如 北京、辽宁。")
    query.add_argument("--station-id", help="国家气象中心 /rest/province 返回的站点代码，例如 Wqsps。")
    query.add_argument("--days", type=int, default=7, choices=range(1, 8), metavar="1-7", help="返回的预报天数。")
    query.add_argument("--hourly", type=int, default=12, help="返回的近期逐小时观测条数；传 0 表示关闭。")
    query.add_argument("--hourly-forecast", action="store_true", help="同时返回中国天气网逐小时预报数据。")
    query.add_argument("--hourly-forecast-limit", type=int, default=96, help="最多返回的逐小时预报条数。")
    query.add_argument("--include-cma", action="store_true", help="可访问时同时返回 weather.cma.cn 城市页面数据。")
    query.add_argument("--daily-chart", type=int, default=0, help="返回的日温度图条数；传 0 表示关闭。")
    query.add_argument("--daily-history", dest="daily_chart", type=int, help=argparse.SUPPRESS)
    query.add_argument("--include-climate", action="store_true", help="可用时同时返回月度气候常年值。")
    query.add_argument("--refresh-stations", action="store_true", help="刷新本地缓存的省份、城市和站点列表。")
    query.set_defaults(func=cmd_query)

    stations = subparsers.add_parser("stations", help="搜索站点候选。")
    stations.add_argument("city", nargs="?", help="城市名片段。")
    stations.add_argument("--province", help="省份或直辖市过滤条件。")
    stations.add_argument("--limit", type=int, default=30)
    stations.add_argument("--refresh-stations", action="store_true", help="刷新本地缓存的省份、城市和站点列表。")
    stations.set_defaults(func=cmd_stations)

    catalog = subparsers.add_parser("catalog", help="列出本技能支持的查询能力和国家气象中心官方产品页。")
    catalog.add_argument("--group", default="", help="按产品组或产品名称过滤，例如 天气预报、台风海洋。")
    catalog.set_defaults(func=cmd_catalog)

    product = subparsers.add_parser("product", help="查询一个国家气象中心官方产品页、公报或图像产品。")
    product.add_argument("product_id", help="产品标识或中文产品名；运行 catalog 查看可用值。")
    product.add_argument("--link-limit", type=int, default=20, help="最多返回的页面链接数。")
    product.add_argument("--image-limit", type=int, default=12, help="最多返回的产品图片数。")
    product.add_argument("--text-limit", type=int, default=6000, help="最多返回的正文摘要字符数。")
    product.set_defaults(func=cmd_product)

    cma_healthcheck = subparsers.add_parser("cma-healthcheck", help="检测 weather.cma.cn 是否可由本机脚本访问。")
    cma_healthcheck.add_argument(
        "--pages",
        nargs="+",
        default=["home", "city-map", "alarm-map"],
        help="要检测的中国气象局页面标识；运行 catalog 查看 cma_pages。",
    )
    cma_healthcheck.set_defaults(func=cmd_cma_healthcheck)

    cma_page = subparsers.add_parser("cma-page", help="尝试读取一个 weather.cma.cn 官方页面摘要。")
    cma_page.add_argument("page_id", help="中国气象局页面标识或中文名；运行 catalog 查看 cma_pages。")
    cma_page.add_argument("--link-limit", type=int, default=20, help="最多返回的页面链接数。")
    cma_page.add_argument("--image-limit", type=int, default=12, help="最多返回的图片数。")
    cma_page.add_argument("--text-limit", type=int, default=6000, help="最多返回的正文摘要字符数。")
    cma_page.set_defaults(func=cmd_cma_page)

    cma_city = subparsers.add_parser("cma-city", help="尝试读取 weather.cma.cn 城市天气页。")
    cma_city.add_argument("city", help="城市名，例如 北京、上海。")
    cma_city.add_argument("--province", default="", help="省份名，例如 北京、上海。")
    cma_city.add_argument("--province-code", default="", help="国家气象中心省份代码，例如 ABJ=北京。")
    cma_city.add_argument("--link-limit", type=int, default=10, help="最多返回的页面链接数。")
    cma_city.add_argument("--image-limit", type=int, default=8, help="最多返回的图片数。")
    cma_city.add_argument("--text-limit", type=int, default=4000, help="最多返回的正文摘要字符数。")
    cma_city.set_defaults(func=cmd_cma_city)

    map_weather = subparsers.add_parser("map-weather", help="查询全国城市实况/今天/明天天气地图数据。")
    map_weather.add_argument("--kind", choices=("real", "today", "tomorrow"), default="real", help="real=实况，today=今天预报，tomorrow=明天预报。")
    map_weather.add_argument("--province-code", default="", help="国家气象中心省份代码过滤，例如 ABJ=北京。")
    map_weather.add_argument("--city", help="城市名过滤。")
    map_weather.add_argument("--limit", type=int, default=100, help="默认最多返回 100 条。")
    map_weather.add_argument("--all", action="store_true", help="返回过滤后的全部记录，谨慎使用。")
    map_weather.set_defaults(func=cmd_map_weather)

    rank = subparsers.add_parser("rank", help="查询全国实况排行：降水、最高/最低气温、风速。")
    rank.add_argument("--type", default="rain", help="rain/降水、maxtemp/最高气温、mintemp/最低气温、wind/风速。")
    rank.add_argument("--hours", type=int, choices=(1, 6, 24), default=1, help="统计时长。风速仅支持 1 小时。")
    rank.add_argument("--ymdh", help="指定时次，格式 YYYYMMDDHH；不指定时自动从国家气象中心首页取最新时次。")
    rank.add_argument("--period", choices=("08", "20"), help="24 小时降水可指定 08 或 20 时统计。")
    rank.add_argument("--limit", type=int, default=20, help="返回排行条数。")
    rank.set_defaults(func=cmd_rank)

    alerts = subparsers.add_parser("alerts", help="查询全国公开预警列表，可按省份关键词过滤。")
    alerts.add_argument("--province", default="", help="省份关键词，例如 北京。")
    alerts.add_argument("--signal-type", default="", help="预警类型过滤，例如 暴雨预警、雷电预警。")
    alerts.add_argument("--signal-level", default="", help="预警等级过滤，例如 蓝色、黄色、橙色、红色。")
    alerts.add_argument("--page", type=int, default=1, help="页码。")
    alerts.add_argument("--limit", type=int, default=30, help="返回预警条数。")
    alerts.set_defaults(func=cmd_alerts)

    layers = subparsers.add_parser("layers", help="查询雷达或卫星图层序列图片地址。")
    layers.add_argument("--kind", choices=("radar", "satellite"), default="radar", help="图层类型。")
    layers.add_argument("--limit", type=int, default=12, help="返回图片条数。")
    layers.set_defaults(func=cmd_layers)

    healthcheck = subparsers.add_parser("healthcheck", help="检查来源连通性，并抽样验证全国城市覆盖。")
    healthcheck.add_argument("--per-province", type=int, default=1, help="每个省级区域抽样的站点数量。")
    healthcheck.add_argument("--limit", type=int, help="最多抽样数量。")
    healthcheck.add_argument("--delay", type=float, default=0.2, help="站点检查之间的延迟秒数。")
    healthcheck.add_argument("--refresh-stations", action="store_true", help="刷新本地缓存的省份、城市和站点列表。")
    healthcheck.set_defaults(func=cmd_healthcheck)
    return root


def main(argv: list[str] | None = None) -> int:
    args = parser().parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
