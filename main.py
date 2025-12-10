#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
优化后的金价抓取并通过 PushPlus 推送
特点：
- 并行请求多个数据源，遇到第一个可用源即返回
- 每个请求均指定 connect/read timeout，避免长时间挂起
- 使用 requests.Session 复用连接
- 可在 GitHub Actions 上稳定执行
"""

import os
import re
import sys
import time
import json
import random
import datetime
import statistics
from pathlib import Path
from typing import Any, Dict, List, Optional
from concurrent.futures import ThreadPoolExecutor, as_completed

try:
    from dotenv import load_dotenv
    load_dotenv()
except Exception:
    pass

import requests

# ---------- 配置 ----------
TOPIC = os.environ.get("PUSHPLUS_TOPIC", "20251206")
TOKEN = os.environ.get("PUSHPLUS_TOKEN")
# 每个requests的 (connect_timeout, read_timeout)
PER_REQUEST_TIMEOUT = (3, 6)  # 3s 建连，6s 读取
# 尝试所有数据源的整体超时（秒）
OVERALL_TIMEOUT = 18
# 并发线程数（数据源个数）
MAX_WORKERS = 4

# ---------- User-Agent 池 ----------
USER_AGENTS = [
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Mozilla/5.0 (iPhone; CPU iPhone OS 16_0 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/16.0 Mobile/15E148 Safari/604.1",
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/119.0.0.0 Safari/537.36",
]

def get_headers(referer: Optional[str] = None) -> Dict[str, str]:
    h = {
        "User-Agent": random.choice(USER_AGENTS),
        "Accept": "*/*",
        "Connection": "keep-alive",
    }
    if referer:
        h["Referer"] = referer
    return h

# ---------- 建议计算函数（保留你的逻辑） ----------
def generate_basic_advice(price: float, change_pct: float):
    if change_pct < -1.2:
        return "今日大跌，黄金坑！", "🔥🔥", 10
    elif change_pct < -0.3:
        return "回调中，适合入手", "🛒", 30
    elif change_pct > 1.2:
        return "今日暴涨，切勿追高", "🛑", 90
    elif change_pct > 0.3:
        return "小幅上涨，建议观望", "✋", 70
    else:
        return "价格横盘，按需购买", "☕", 50

def calculate_technical_advice(price: float, history_prices: List[float]):
    if not history_prices or len(history_prices) < 3:
        return "数据源波动，建议分批", "⚖️", 50, price, price

    all_prices = history_prices + [price]
    ma5 = statistics.mean(all_prices[-5:]) if len(all_prices) >= 5 else statistics.mean(all_prices)

    week_low = min(all_prices)
    week_high = max(all_prices)

    if week_high - week_low == 0:
        position_pct = 50
    else:
        position_pct = ((price - week_low) / (week_high - week_low)) * 100

    if price < ma5:
        if position_pct < 20:
            advice = "近5日极低位，建议入手"
            advice_icon = "🔥🔥"
        elif position_pct < 50:
            advice = "低于周均价，适合买入"
            advice_icon = "🛒"
        else:
            advice = "跌破均线，可尝试建仓"
            advice_icon = "📉"
    else:
        if position_pct > 80:
            advice = "近5日高位，谨防回调"
            advice_icon = "🛑"
        else:
            advice = "高于周均价，建议观望"
            advice_icon = "✋"

    return advice, advice_icon, position_pct, week_low, week_high

# ---------- 数据源实现（都使用 session） ----------
def get_price_goldpriceorg(session: requests.Session) -> Optional[Dict[str, Any]]:
    """
    GoldPrice.org 返回 CNY 的盎司价格 -> 换算为 元/克
    该源通常稳定，不易被墙
    """
    try:
        url = "https://data-asg.goldprice.org/dbXRates/CNY"
        resp = session.get(url, headers=get_headers(), timeout=PER_REQUEST_TIMEOUT)
        resp.raise_for_status()
        data = resp.json()
        if data and "items" in data and len(data["items"]) > 0:
            price_oz_cny = float(data["items"][0].get("xauPrice", 0))
            if price_oz_cny <= 0:
                return None
            price_g_cny = price_oz_cny / 31.1035
            return {
                "source": "GoldPrice.org",
                "price": round(price_g_cny, 2),
                "change": 0,
                "change_pct": 0,
                "advice": "国际源数据，参考现价",
                "advice_icon": "🌐",
                "pos_pct": 50,
                "week_low": round(price_g_cny, 2),
                "week_high": round(price_g_cny, 2),
                "history_trend": [],
                "bg_color": "#333333",
                "est_price": round(price_g_cny + 25, 1)
            }
    except Exception as e:
        print(f"❌ GoldPrice.org 异常: {e}")
    return None

def get_price_binance(session: requests.Session) -> Optional[Dict[str, Any]]:
    """
    通过 Binance PAXGUSDT 以及外汇换算到 CNY，并转为 元/克
    """
    try:
        url_gold = "https://api.binance.com/api/v3/ticker/price?symbol=PAXGUSDT"
        url_rate = "https://api.exchangerate-api.com/v4/latest/USD"
        resp_gold = session.get(url_gold, headers=get_headers(), timeout=PER_REQUEST_TIMEOUT)
        resp_gold.raise_for_status()
        gold_price_usd = float(resp_gold.json()["price"])

        resp_rate = session.get(url_rate, headers=get_headers(), timeout=PER_REQUEST_TIMEOUT)
        resp_rate.raise_for_status()
        cny_rate = float(resp_rate.json()["rates"].get("CNY", 0))
        if cny_rate <= 0:
            return None

        price_cny = (gold_price_usd * cny_rate) / 31.1035

        url_24h = "https://api.binance.com/api/v3/ticker/24hr?symbol=PAXGUSDT"
        resp_24h = session.get(url_24h, headers=get_headers(), timeout=PER_REQUEST_TIMEOUT)
        resp_24h.raise_for_status()
        data_24h = resp_24h.json()
        price_change_percent = float(data_24h.get("priceChangePercent", 0.0))
        price_change_amount = float(data_24h.get("priceChange", 0.0))

        change_cny = (price_change_amount * cny_rate) / 31.1035

        advice, icon, score = generate_basic_advice(price_cny, price_change_percent)

        return {
            "source": "Binance(国际)",
            "price": round(price_cny, 2),
            "change": round(change_cny, 2),
            "change_pct": round(price_change_percent, 2),
            "advice": advice,
            "advice_icon": icon,
            "pos_pct": score,
            "week_low": round(price_cny, 2),
            "week_high": round(price_cny, 2),
            "history_trend": [],
            "bg_color": "#5cb85c" if price_change_percent < 0 else "#d9534f",
            "est_price": round(price_cny + 25, 1)
        }
    except Exception as e:
        print(f"❌ Binance 异常: {e}")
    return None

def get_price_eastmoney_history(session: requests.Session) -> Optional[Dict[str, Any]]:
    """
    东方财富历史 K 线（secid=119.Au9999）
    """
    try:
        url = "https://push2his.eastmoney.com/api/qt/stock/kline/get?secid=119.Au9999&fields1=f1&fields2=f51,f52,f53,f54,f55&klt=101&fqt=1&lmt=6"
        resp = session.get(url, headers=get_headers("https://quote.eastmoney.com/"), timeout=PER_REQUEST_TIMEOUT)
        resp.raise_for_status()
        data = resp.json()
        if data and data.get("data") and data["data"].get("klines"):
            klines = data["data"]["klines"]
            parsed_history = [float(k.split(',')[2]) for k in klines]
            current = parsed_history[-1]
            if current <= 0:
                return None
            prev = parsed_history[-2] if len(parsed_history) >= 2 else current
            change = current - prev
            pct = (change / prev) * 100 if prev != 0 else 0
            advice, icon, pos_pct, w_low, w_high = calculate_technical_advice(current, parsed_history[:-1])
            history_str = [str(p) for p in parsed_history[-4:-1]] if len(parsed_history) >= 4 else []
            return {
                "source": "东方财富",
                "price": round(current, 2),
                "change": round(change, 2),
                "change_pct": round(pct, 2),
                "advice": advice,
                "advice_icon": icon,
                "pos_pct": pos_pct,
                "week_low": w_low,
                "week_high": w_high,
                "history_trend": history_str,
                "bg_color": "#5cb85c" if change < 0 else "#d9534f",
                "est_price": round(current + 25, 1)
            }
    except Exception as e:
        print(f"❌ 东方财富 异常: {e}")
    return None

def get_price_jijinhao(session: requests.Session) -> Optional[Dict[str, Any]]:
    """
    第一黄金网（示例解析）
    """
    try:
        url = "https://api.jijinhao.com/sQuoteCenter/realTime.jsp?sCodes=JO_92233"
        resp = session.get(url, headers=get_headers("https://www.dyhjw.com/"), timeout=PER_REQUEST_TIMEOUT)
        resp.raise_for_status()
        text = resp.text
        match = re.search(r'=\s*({.*?})', text)
        if match:
            json_str = match.group(1)
            last = re.search(r'"last":"([\d\.]+)"', json_str)
            pre = re.search(r'"pre_close":"([\d\.]+)"', json_str)
            if last and pre:
                current = float(last.group(1))
                prev = float(pre.group(1))
                if current <= 0:
                    return None
                change = current - prev
                pct = (change / prev) * 100 if prev != 0 else 0
                advice, icon, score = generate_basic_advice(current, pct)
                return {
                    "source": "第一黄金网",
                    "price": current,
                    "change": round(change, 2),
                    "change_pct": round(pct, 2),
                    "advice": advice,
                    "advice_icon": icon,
                    "pos_pct": score,
                    "week_low": current,
                    "week_high": current,
                    "history_trend": [],
                    "bg_color": "#5cb85c" if change < 0 else "#d9534f",
                    "est_price": round(current + 25, 1)
                }
    except Exception as e:
        print(f"❌ 第一黄金网 异常: {e}")
    return None

# ---------- 推送函数 ----------
def send_pushplus(data: Dict[str, Any], token: Optional[str] = None, topic: Optional[str] = None):
    token = token or TOKEN
    topic = topic or TOPIC
    if not token:
        print("⚠️ PUSHPLUS_TOKEN 未配置，跳过推送（仅打印）")
        print(json.dumps(data, ensure_ascii=False, indent=2))
        return

    date_str = datetime.datetime.now().strftime("%Y-%m-%d %H:%M")
    change_sign = "+" if data.get('change', 0) > 0 else ""
    trend_html = ""
    if data.get('history_trend'):
        trend_items = "".join([f"<span style='background:#f3f3f3; padding:2px 5px; margin-right:4px; color:#555;'>{p}</span>"
                               for p in data['history_trend']])
        trend_html = f"<div style='margin-top:10px; font-size:12px; color:#666;'>近3日: {trend_items} <span style='font-weight:bold;'>→ {data['price']}</span></div>"

    bg_color = data.get('bg_color', '#333333')

    content = f"""
    <div style="font-family: -apple-system, sans-serif; background-color: #ffffff; padding: 15px; border-radius: 10px; border: 1px solid #eee; color: #333333;">
        <div style="background-color: {bg_color}; border-radius: 8px; padding: 20px; color: #ffffff; text-align: center;">
            <div style="font-size: 13px; opacity: 0.9; color: #ffffff;">参考金价 (Au99.99)</div>
            <div style="font-size: 40px; font-weight: 800; line-height: 1.1; margin: 5px 0; color: #ffffff;">{data['price']}</div>
            <div style="display: inline-block; font-size: 14px; background-color: rgba(0,0,0,0.15); padding: 4px 12px; border-radius: 12px; color: #ffffff;">
                {change_sign}{data['change']}元 ({change_sign}{data['change_pct']}%)
            </div>
        </div>
        <div style="background-color: #f8f9fa; margin-top: 15px; border-radius: 8px; padding: 15px; border: 1px solid #eeeeee;">
            <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 12px;">
                <span style="font-weight: bold; color: #333333;">决策建议</span>
                <span style="font-weight: bold; color: {bg_color}">{data['advice_icon']} {data['advice']}</span>
            </div>
            <div style="position: relative; height: 8px; background: linear-gradient(90deg, #5cb85c 0%, #ffc107 50%, #d9534f 100%); border-radius: 4px; margin-bottom: 10px;">
                <div style="position: absolute; left: {data['pos_pct']}%; top: -3px; width: 6px; height: 14px; background-color: #333333; border: 2px solid #ffffff; border-radius: 3px; transform: translateX(-50%);"></div>
            </div>
            {trend_html}
        </div>
        <div style="background-color: #fff8e1; margin-top: 15px; border-radius: 8px; padding: 12px; display: flex; justify-content: space-between; align-items: center; border: 1px solid #ffeeba;">
            <div style="font-size: 13px; color: #856404;">预估到手 (含工费)</div>
            <div style="font-size: 22px; font-weight: bold; color: #d39e00;">¥ {data['est_price']}</div>
        </div>
        <div style="margin-top: 15px; text-align: center; color: #bbbbbb; font-size: 12px;">
            更新: {date_str} | 源: {data['source']}
        </div>
    </div>
    """

    payload = {
        "token": token,
        "title": f"{data.get('advice_icon','')} 金价: {data.get('price')} ({change_sign}{data.get('change')})",
        "content": content,
        "template": "html",
        "topic": topic
    }

    try:
        resp = requests.post("http://www.pushplus.plus/send", json=payload, headers=get_headers(), timeout=(3, 10))
        print("✅ PushPlus 响应:", resp.status_code, resp.text[:200])
    except Exception as e:
        print("❌ PushPlus 推送异常:", e)
        print("📢 推送内容预览：")
        print(json.dumps(payload, ensure_ascii=False)[:1000])

# ---------- 主流程（并行尝试多个源） ----------
def main():
    print("=== 优化版金价推送启动 ===")
    start_time = time.time()

    sources = [
        get_price_goldpriceorg,
        get_price_binance,
        get_price_eastmoney_history,
        get_price_jijinhao,
    ]

    result = None
    with requests.Session() as session:
        # 保持 session 的 headers（可以被单次覆盖）
        session.headers.update({"Accept": "*/*"})
        with ThreadPoolExecutor(max_workers=MAX_WORKERS) as ex:
            futures = {ex.submit(src, session): src.__name__ for src in sources}
            try:
                # as_completed 返回迭代器，按完成顺序产出
                for future in as_completed(futures, timeout=OVERALL_TIMEOUT):
                    src_name = futures.get(future)
                    try:
                        data = future.result(timeout=0.1)
                    except Exception as e:
                        print(f"⚠ 源 {src_name} 执行失败: {e}")
                        continue

                    if data:
                        print(f"✅ 成功从 [{data['source']}] 获取数据（来自 {src_name}）")
                        result = data
                        break
                    else:
                        print(f"⚠ 源 {src_name} 返回空结果，继续等待其它源...")
            except Exception as e:
                print("⚠ 并行等待超时或异常:", e)

            # 如果拿到了 result，尝试取消其它还没完成的 future（不强制，但会释放资源）
            if result is not None:
                for f in futures:
                    if not f.done():
                        try:
                            f.cancel()
                        except Exception:
                            pass

    elapsed = time.time() - start_time
    print(f"--- 总耗时: {elapsed:.2f}s ---")

    if result:
        if TOKEN:
            send_pushplus(result)
        else:
            print("📢 Token 未配置，打印结果：")
            print(json.dumps(result, ensure_ascii=False, indent=2))
    else:
        print("❌ 所有接口均失败，未获取到金价。")
        # 这里可以选择降级策略：比如只推送“今日任务失败”或重试一次（可视情况开启）
        # 为了避免无限重试，默认不重试

if __name__ == "__main__":
    # 保证输出 utf-8
    try:
        sys.stdout.reconfigure(encoding='utf-8')
    except Exception:
        pass
    main()
