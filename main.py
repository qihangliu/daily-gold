import requests
import re
import os
import datetime
import sys
import random
import time
import json
import statistics  # 用于计算平均值

try:
    from dotenv import load_dotenv

    load_dotenv()
except ImportError:
    pass

sys.stdout.reconfigure(encoding="utf-8")
TOKEN = os.environ.get("PUSHPLUS_TOKEN")
TOPIC = "20251206"

USER_AGENTS = [
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
]


def get_headers():
    return {
        "User-Agent": random.choice(USER_AGENTS),
        "Accept": "*/*",
        "Connection": "keep-alive",
    }


def calculate_technical_advice(price, history_prices):
    """
    根据历史数据生成决策建议
    history_prices: 最近5天的价格列表 (不含今日，或者含今日)
    """
    advice = "按需购买"
    advice_icon = "☕"
    signal_score = 50  # 0-100, 越高越不建议买，越低越建议买

    if not history_prices:
        return advice, advice_icon, 50, None, None

    # 计算 5日均线 (MA5)
    # 如果历史数据不足5天，就用现有的
    all_prices = history_prices + [price]
    ma5 = statistics.mean(all_prices[-5:])

    # 计算本周高低点
    week_low = min(all_prices)
    week_high = max(all_prices)

    # 价格位置 (0 = 最低, 100 = 最高)
    if week_high - week_low == 0:
        position_pct = 50
    else:
        position_pct = ((price - week_low) / (week_high - week_low)) * 100

    # 决策逻辑
    if price < ma5:
        # 现价低于5日均线 -> 便宜
        if position_pct < 20:
            advice = "本周极低位，强烈建议买入"
            advice_icon = "🔥🔥"
            signal_score = 10
        elif position_pct < 50:
            advice = "低于周均价，适合入手"
            advice_icon = "🛒"
            signal_score = 30
        else:
            advice = "趋势回调中，可以分批入"
            advice_icon = "📉"
            signal_score = 45
    else:
        # 现价高于5日均线 -> 贵
        if position_pct > 80:
            advice = "本周极高位，千万别追高"
            advice_icon = "🛑"
            signal_score = 90
        else:
            advice = "高于周均价，建议等待回调"
            advice_icon = "✋"
            signal_score = 70

    return advice, advice_icon, position_pct, week_low, week_high


def get_price_yahoo_rich():
    """
    增强版雅虎接口：获取最近 5 天的数据进行趋势分析
    """
    print("--- [尝试] 雅虎财经 (获取5日趋势) ---")
    try:
        # 获取 黄金期货 (GC=F) - 请求过去 5 天 (range=5d)
        url_gold = "https://query1.finance.yahoo.com/v8/finance/chart/GC=F?interval=1d&range=5d"
        resp_gold = requests.get(url_gold, headers=get_headers(), timeout=15)
        data_gold = resp_gold.json()

        # 获取 汇率 (CNY=X)
        url_cny = "https://query1.finance.yahoo.com/v8/finance/chart/CNY=X?interval=1d&range=1d"
        resp_cny = requests.get(url_cny, headers=get_headers(), timeout=10)
        cny_rate = resp_cny.json()["chart"]["result"][0]["meta"]["regularMarketPrice"]

        # 解析黄金历史数据
        chart_result = data_gold["chart"]["result"][0]
        timestamps = chart_result["timestamp"]
        closes = chart_result["indicators"]["quote"][0]["close"]

        # 过滤掉空值 (有时候休市会有 None)
        valid_history = []
        for ts, close in zip(timestamps, closes):
            if close:
                price_cny = (close * cny_rate) / 31.1035
                valid_history.append(price_cny)

        if not valid_history:
            return None

        current_price = valid_history[-1]  # 最新的
        prev_price = valid_history[-2] if len(valid_history) >= 2 else current_price

        change = current_price - prev_price
        pct = (change / prev_price) * 100

        # 生成决策数据
        advice, icon, pos_pct, w_low, w_high = calculate_technical_advice(
            current_price, valid_history[:-1]
        )

        # 格式化历史趋势字符串 (用于展示)
        history_str_list = []
        # 取最近3天 (不含今天)
        recent_days = valid_history[-4:-1]
        for p in recent_days:
            history_str_list.append(str(round(p, 1)))

        labor_fee = 25
        est_price = current_price + labor_fee

        # 决定大背景颜色
        bg_color = "#5cb85c" if change < 0 else "#d9534f"
        if -0.5 < change < 0.5:
            bg_color = "#6c757d"  # 震荡用灰色

        return {
            "source": "雅虎财经(5日趋势)",
            "price": round(current_price, 2),
            "change": round(change, 2),
            "change_pct": round(pct, 2),
            "advice": advice,
            "advice_icon": icon,
            "pos_pct": pos_pct,  # 价格在区间的位置 0-100
            "week_low": round(w_low, 1),
            "week_high": round(w_high, 1),
            "history_trend": history_str_list,  # 历史价格列表
            "bg_color": bg_color,
            "est_price": round(est_price, 1),
            "labor_fee": labor_fee,
        }

    except Exception as e:
        print(f"❌ 雅虎高级接口异常: {e}")
    return None


def get_price_eastmoney_fallback():
    """
    备用接口：东方财富 (仅当前快照，无历史分析)
    """
    print("--- [备用] 东方财富接口 ---")
    url = "https://push2.eastmoney.com/api/qt/stock/get?secid=119.Au9999&fields=f43,f169,f170"
    try:
        resp = requests.get(url, headers=get_headers(), timeout=10)
        d = resp.json().get("data")
        if d and d["f43"] != "-":
            price = float(d["f43"])
            change = float(d["f169"])
            pct = float(d["f170"])

            # 备用模式下的简单建议
            advice = "数据源仅含现价，建议观望"
            bg_color = "#d9534f" if change > 0 else "#5cb85c"

            return {
                "source": "东方财富(快照)",
                "price": price,
                "change": change,
                "change_pct": pct,
                "advice": "价格回调中" if change < 0 else "价格上涨中",
                "advice_icon": "ℹ️",
                "pos_pct": 50,  # 没数据，放中间
                "week_low": price,  # 没数据，暂为现价
                "week_high": price,
                "history_trend": [],
                "bg_color": bg_color,
                "est_price": price + 25,
                "labor_fee": 25,
            }
    except Exception as e:
        print(f"❌ 东方财富异常: {e}")
    return None


def send_pushplus(data):
    print(f"--- 正在发起推送 ({data['source']}) ---")
    date_str = datetime.datetime.now().strftime("%Y-%m-%d %H:%M")

    change_sign = "+" if data["change"] > 0 else ""
    change_str = f"{change_sign}{data['change']}"

    # --- 构建可视化进度条 ---
    # 根据 pos_pct (0-100) 计算小球的位置
    # 左边是低(绿)，右边是高(红)
    # 我们用一个 CSS 渐变条

    # 历史走势 HTML
    trend_html = ""
    if data["history_trend"]:
        trend_items = "".join(
            [
                f"<span style='background:#f1f3f5; padding:2px 6px; border-radius:4px; font-size:12px; margin-right:4px; color:#666;'>{p}</span>"
                for p in data["history_trend"]
            ]
        )
        trend_html = f"<div style='margin-top:8px; font-size:12px; color:#888;'>近3日走势: {trend_items} <span style='color:#333; font-weight:bold;'>→ {data['price']}</span></div>"

    content = f"""
    <div style="font-family: sans-serif; max-width: 100%; background-color: #f8f9fa; padding: 12px; border-radius: 8px;">

        <!-- 1. 核心价格卡片 -->
        <div style="background: {data["bg_color"]}; border-radius: 12px; padding: 20px 15px; color: white; text-align: center; box-shadow: 0 4px 12px rgba(0,0,0,0.15);">
            <div style="font-size: 13px; opacity: 0.9; margin-bottom: 4px;">水贝模式参考价 (Au99.99)</div>
            <div style="font-size: 46px; font-weight: 800; line-height: 1;">{int(data["price"])}<span style="font-size: 18px;">.{str(data["price"]).split(".")[1]}</span></div>
            <div style="margin-top: 10px; font-size: 15px; background: rgba(0,0,0,0.15); display: inline-block; padding: 4px 12px; border-radius: 20px;">
                {change_str}元 ({change_sign}{data["change_pct"]}%)
            </div>
        </div>

        <!-- 2. 决策辅助仪表盘 (核心功能) -->
        <div style="background: white; margin-top: 15px; border-radius: 12px; padding: 15px; border: 1px solid #e9ecef;">
            <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 15px;">
                <span style="font-weight: bold; color: #333; font-size: 16px;">决策分析</span>
                <span style="font-size: 14px; font-weight: bold; color: {data["bg_color"]}">{data["advice_icon"]} {data["advice"]}</span>
            </div>

            <!-- 价格区间条 -->
            <div style="margin-bottom: 5px; font-size: 12px; color: #666; display: flex; justify-content: space-between;">
                <span>周低 {data["week_low"]}</span>
                <span>周高 {data["week_high"]}</span>
            </div>
            <div style="position: relative; height: 12px; background: linear-gradient(90deg, #5cb85c 0%, #ffc107 50%, #d9534f 100%); border-radius: 6px; margin-bottom: 20px;">
                <!-- 定位小球 -->
                <div style="position: absolute; left: {data["pos_pct"]}%; top: -4px; width: 4px; height: 20px; background: #333; border: 2px solid white; border-radius: 2px; box-shadow: 0 2px 4px rgba(0,0,0,0.2); transform: translateX(-50%);"></div>
                <div style="position: absolute; left: {data["pos_pct"]}%; top: -22px; transform: translateX(-50%); font-size: 12px; font-weight: bold; color: #333;">Current</div>
            </div>

            {trend_html}
        </div>

        <!-- 3. 落地成本计算 -->
        <div style="background: white; margin-top: 15px; border-radius: 12px; padding: 15px; border: 1px solid #e9ecef;">
            <div style="font-size: 14px; color: #555; margin-bottom: 8px;">预估到手成本 (含{data["labor_fee"]}元工费)</div>
            <div style="font-size: 24px; font-weight: bold; color: #f0ad4e;">
                ¥ {data["est_price"]} <span style="font-size:14px; color:#999; font-weight:normal;">/克</span>
            </div>
        </div>

        <div style="margin-top: 20px; text-align: center; color: #adb5bd; font-size: 12px;">
            更新于: {date_str} | 源: {data["source"]}
        </div>
    </div>
    """

    url = "http://www.pushplus.plus/send"
    payload = {
        "token": TOKEN,
        "title": f"{data['advice_icon']} 金价决策: {data['price']} ({change_sign}{data['change_pct']}%)",
        "content": content,
        "template": "html",
        "topic": TOPIC,
    }

    try:
        resp = requests.post(url, json=payload, headers=get_headers(), timeout=15)
        print(f"✅ 推送响应: {resp.status_code}")
    except Exception as e:
        print(f"❌ 推送失败: {e}")


if __name__ == "__main__":
    print("=== 决策辅助版启动 ===")

    if not TOKEN:
        print("🔍 提示: 本地无Token模式")

    # 1. 优先尝试雅虎 (Rich Data)
    data = get_price_yahoo_rich()

    # 2. 失败则降级到东方财富 (Snapshot Data)
    if not data:
        data = get_price_eastmoney_fallback()

    if data:
        print(f"✅ 获取成功: {data['source']} | 现价: {data['price']} | 建议: {data['advice']}")
        if TOKEN:
            send_pushplus(data)
        else:
            print("📢 [模拟推送] 内容已生成，请配置Token后查看效果")
    else:
        print("❌ 所有接口失败")