import requests
import re
import os
import datetime
import sys
import random
import time
import json
import statistics

try:
    from dotenv import load_dotenv

    load_dotenv()
except ImportError:
    pass

sys.stdout.reconfigure(encoding="utf-8")
TOKEN = os.environ.get("PUSHPLUS_TOKEN")
TOPIC = "20251206"

# 扩充 User-Agent 池
USER_AGENTS = [
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Mozilla/5.0 (iPhone; CPU iPhone OS 16_0 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/16.0 Mobile/15E148 Safari/604.1",
]


def get_headers(referer=None):
    headers = {
        "User-Agent": random.choice(USER_AGENTS),
        "Accept": "*/*",
        "Connection": "keep-alive",
    }
    if referer:
        headers["Referer"] = referer
    return headers


def generate_basic_advice(price, change_pct):
    """
    当没有历史数据时，根据当日涨跌幅生成基础建议
    """
    # 简单的涨跌判断逻辑
    if change_pct < -1.0:
        return "今日大跌，黄金坑！", "🔥🔥", 10  # 极低位
    elif change_pct < -0.3:
        return "回调中，适合入手", "🛒", 30  # 适合买
    elif change_pct > 1.0:
        return "今日暴涨，切勿追高", "🛑", 90  # 极高位
    elif change_pct > 0.3:
        return "小幅上涨，建议观望", "✋", 70  # 观望
    else:
        return "价格横盘，按需购买", "☕", 50  # 中性


def calculate_technical_advice(price, history_prices):
    """
    根据历史数据生成高级决策建议
    """
    if not history_prices or len(history_prices) < 3:
        # 数据不足，降级处理
        return "数据源波动，建议分批", "⚖️", 50, price, price

    all_prices = history_prices + [price]
    ma5 = (
        statistics.mean(all_prices[-5:])
        if len(all_prices) >= 5
        else statistics.mean(all_prices)
    )

    week_low = min(all_prices)
    week_high = max(all_prices)

    if week_high - week_low == 0:
        position_pct = 50
    else:
        position_pct = ((price - week_low) / (week_high - week_low)) * 100

    # 均线策略
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


# --- 接口1: 东方财富 K线历史 (最佳数据) ---
def get_price_eastmoney_history():
    print("--- [尝试 1] 东方财富 (K线趋势) ---")
    try:
        url = "https://push2his.eastmoney.com/api/qt/stock/kline/get?secid=119.Au9999&fields1=f1&fields2=f51,f52,f53,f54,f55&klt=101&fqt=1&lmt=6"
        resp = requests.get(
            url, headers=get_headers("https://quote.eastmoney.com/"), timeout=8
        )
        data = resp.json()

        if data and data.get("data") and data["data"].get("klines"):
            klines = data["data"]["klines"]
            parsed_history = [float(k.split(",")[2]) for k in klines]

            current_price = parsed_history[-1]
            prev_price = (
                parsed_history[-2] if len(parsed_history) >= 2 else current_price
            )

            change = current_price - prev_price
            pct = (change / prev_price) * 100

            advice, icon, pos_pct, w_low, w_high = calculate_technical_advice(
                current_price, parsed_history[:-1]
            )

            history_str_list = []
            if len(parsed_history) >= 4:
                history_str_list = [str(p) for p in parsed_history[-4:-1]]

            return {
                "source": "东方财富(趋势)",
                "price": round(current_price, 2),
                "change": round(change, 2),
                "change_pct": round(pct, 2),
                "advice": advice,
                "advice_icon": icon,
                "pos_pct": pos_pct,
                "week_low": round(w_low, 1),
                "week_high": round(w_high, 1),
                "history_trend": history_str_list,
                "bg_color": "#5cb85c" if change < 0 else "#d9534f",
                "est_price": round(current_price + 25, 1),
            }
        else:
            print(f"❌ 东方财富K线返回数据为空: {str(data)[:100]}")
    except Exception as e:
        print(f"❌ 东方财富K线异常: {e}")
    return None


# --- 接口2: 东方财富 快照 (备用) ---
def get_price_eastmoney_snapshot():
    print("--- [尝试 2] 东方财富 (实时快照) ---")
    try:
        url = "https://push2.eastmoney.com/api/qt/stock/get?secid=119.Au9999&fields=f43,f169,f170"
        resp = requests.get(
            url, headers=get_headers("https://quote.eastmoney.com/"), timeout=8
        )
        d = resp.json().get("data")
        if d and d["f43"] != "-":
            price = float(d["f43"])
            change = float(d["f169"])
            pct = float(d["f170"])

            advice, icon, score = generate_basic_advice(price, pct)

            return {
                "source": "东方财富(快照)",
                "price": price,
                "change": change,
                "change_pct": pct,
                "advice": advice,
                "advice_icon": icon,
                "pos_pct": score,
                "week_low": price,
                "week_high": price,
                "history_trend": [],
                "bg_color": "#5cb85c" if change < 0 else "#d9534f",
                "est_price": price + 25,
            }
    except Exception as e:
        print(f"❌ 东方财富快照异常: {e}")
    return None


# --- 接口3: 雅虎财经 (国际换算 - 以前成功过，最强底兜) ---
def get_price_yahoo_calc():
    print("--- [尝试 3] 雅虎财经 (国际换算) ---")
    try:
        # 只取1天数据，成功率极高
        url_gold = "https://query1.finance.yahoo.com/v8/finance/chart/GC=F?interval=1d&range=1d"
        resp_gold = requests.get(url_gold, headers=get_headers(), timeout=15)
        data_gold = resp_gold.json()
        gold_usd_oz = data_gold["chart"]["result"][0]["meta"]["regularMarketPrice"]
        prev_gold = data_gold["chart"]["result"][0]["meta"]["chartPreviousClose"]

        url_cny = "https://query1.finance.yahoo.com/v8/finance/chart/CNY=X?interval=1d&range=1d"
        resp_cny = requests.get(url_cny, headers=get_headers(), timeout=15)
        cny_rate = resp_cny.json()["chart"]["result"][0]["meta"]["regularMarketPrice"]

        print(f"国际金价: ${gold_usd_oz}, 汇率: {cny_rate}")

        # 换算：1盎司 = 31.1035克
        price_cny = (gold_usd_oz * cny_rate) / 31.1035
        prev_price_cny = (prev_gold * cny_rate) / 31.1035

        change = price_cny - prev_price_cny
        pct = (change / prev_price_cny) * 100

        advice, icon, score = generate_basic_advice(price_cny, pct)

        return {
            "source": "雅虎财经(换算)",
            "price": round(price_cny, 2),
            "change": round(change, 2),
            "change_pct": round(pct, 2),
            "advice": advice,
            "advice_icon": icon,
            "pos_pct": score,  # 估算的仪表盘位置
            "week_low": round(price_cny, 2),
            "week_high": round(price_cny, 2),
            "history_trend": [],
            "bg_color": "#5cb85c" if change < 0 else "#d9534f",
            "est_price": round(price_cny + 25, 1),
        }
    except Exception as e:
        print(f"❌ 雅虎财经异常: {e}")
    return None


# --- 接口4: 新浪财经 (最后防线) ---
def get_price_sina():
    print("--- [尝试 4] 新浪财经 ---")
    try:
        url = "http://hq.sinajs.cn/list=gds_Au99_99"
        resp = requests.get(
            url, headers=get_headers("http://finance.sina.com.cn/"), timeout=5
        )
        if resp.status_code == 200:
            match = re.search(r'"([^"]+)"', resp.text)
            if match:
                d = match.group(1).split(",")
                if len(d) > 8:
                    current = float(d[3])
                    prev = float(d[4])
                    if current == 0:
                        current = prev

                    change = current - prev
                    pct = (change / prev) * 100
                    advice, icon, score = generate_basic_advice(current, pct)

                    return {
                        "source": "新浪财经",
                        "price": current,
                        "change": round(change, 2),
                        "change_pct": round(pct, 2),
                        "advice": advice,
                        "advice_icon": icon,
                        "pos_pct": score,
                        "week_low": float(d[5]),
                        "week_high": float(d[6]),
                        "history_trend": [],
                        "bg_color": "#5cb85c" if change < 0 else "#d9534f",
                        "est_price": current + 25,
                    }
    except Exception as e:
        print(f"❌ 新浪异常: {e}")
    return None


def send_pushplus(data):
    print(f"--- 发起推送 ({data['source']}) ---")
    date_str = datetime.datetime.now().strftime("%Y-%m-%d %H:%M")

    change_sign = "+" if data["change"] > 0 else ""

    # 历史趋势HTML (如果有)
    trend_html = ""
    if data["history_trend"]:
        trend_items = "".join(
            [
                f"<span style='background:#f3f3f3; padding:2px 5px; margin-right:4px; color:#555;'>{p}</span>"
                for p in data["history_trend"]
            ]
        )
        trend_html = f"<div style='margin-top:10px; font-size:12px; color:#666;'>近3日: {trend_items} <span style='font-weight:bold;'>→ {data['price']}</span></div>"
    else:
        trend_html = "<div style='margin-top:10px; font-size:12px; color:#999;'>* 当前源暂无历史K线数据，仅展示实时快照</div>"

    # HTML 模板 (深色模式适配增强)
    # 所有颜色强制指定，背景强制白色/灰色
    content = f"""
    <div style="font-family: -apple-system, sans-serif; background-color: #ffffff; padding: 15px; border-radius: 10px; border: 1px solid #eee; color: #333333;">

        <!-- 1. 价格卡片 -->
        <div style="background-color: {data["bg_color"]}; border-radius: 8px; padding: 20px; color: #ffffff; text-align: center;">
            <div style="font-size: 13px; opacity: 0.9; color: #ffffff;">水贝参考价 (Au99.99)</div>
            <div style="font-size: 40px; font-weight: 800; line-height: 1.1; margin: 5px 0; color: #ffffff;">{data["price"]}</div>
            <div style="display: inline-block; font-size: 14px; background-color: rgba(0,0,0,0.15); padding: 4px 12px; border-radius: 12px; color: #ffffff;">
                {change_sign}{data["change"]}元 ({change_sign}{data["change_pct"]}%)
            </div>
        </div>

        <!-- 2. 决策分析 -->
        <div style="background-color: #f8f9fa; margin-top: 15px; border-radius: 8px; padding: 15px; border: 1px solid #eeeeee;">
            <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 12px;">
                <span style="font-weight: bold; color: #333333;">决策建议</span>
                <span style="font-weight: bold; color: {data["bg_color"]}">{data["advice_icon"]} {data["advice"]}</span>
            </div>

            <!-- 可视化条 -->
            <div style="margin-bottom: 6px; font-size: 12px; color: #666666; display: flex; justify-content: space-between;">
                <span>低 {data["week_low"]}</span>
                <span>高 {data["week_high"]}</span>
            </div>
            <div style="position: relative; height: 8px; background: linear-gradient(90deg, #5cb85c 0%, #ffc107 50%, #d9534f 100%); border-radius: 4px; margin-bottom: 10px;">
                <div style="position: absolute; left: {data["pos_pct"]}%; top: -3px; width: 6px; height: 14px; background-color: #333333; border: 2px solid #ffffff; border-radius: 3px; transform: translateX(-50%);"></div>
            </div>
            {trend_html}
        </div>

        <!-- 3. 到手成本 -->
        <div style="background-color: #fff8e1; margin-top: 15px; border-radius: 8px; padding: 12px; display: flex; justify-content: space-between; align-items: center; border: 1px solid #ffeeba;">
            <div style="font-size: 13px; color: #856404;">预估到手 (含工费)</div>
            <div style="font-size: 22px; font-weight: bold; color: #d39e00;">
                ¥ {data["est_price"]}
            </div>
        </div>

        <div style="margin-top: 15px; text-align: center; color: #bbbbbb; font-size: 12px;">
            更新: {date_str} | 源: {data["source"]}
        </div>
    </div>
    """

    url = "http://www.pushplus.plus/send"
    payload = {
        "token": TOKEN,
        "title": f"{data['advice_icon']} 金价: {data['price']} ({change_sign}{data['change']})",
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
    print("=== 全能抗造版启动 ===")

    # 按优先级尝试
    # 1. 东方财富K线 (数据最全)
    # 2. 东方财富快照 (数据较新)
    # 3. 雅虎换算 (最稳定，IP通过率高)
    # 4. 新浪财经 (备用)
    strategies = [
        get_price_eastmoney_history,
        get_price_eastmoney_snapshot,
        get_price_yahoo_calc,
        get_price_sina,
    ]

    data = None
    for strategy in strategies:
        data = strategy()
        if data:
            print(f"✅ 成功从 [{data['source']}] 获取数据")
            break
        else:
            print("⚠️ 失败，切换下一个源...")
            time.sleep(1)

    if data:
        if TOKEN:
            send_pushplus(data)
        else:
            print("📢 [模拟推送] Token未配置")
    else:
        print("❌ 所有接口均失败，网络环境可能被严重限制")