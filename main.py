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

sys.stdout.reconfigure(encoding='utf-8')
TOKEN = os.environ.get("PUSHPLUS_TOKEN")
TOPIC = "20251206"

# 扩充 User-Agent 池
USER_AGENTS = [
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Mozilla/5.0 (iPhone; CPU iPhone OS 16_0 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/16.0 Mobile/15E148 Safari/604.1"
]

def get_headers(referer=None):
    headers = {
        "User-Agent": random.choice(USER_AGENTS),
        "Accept": "*/*",
        "Connection": "keep-alive"
    }
    if referer:
        headers["Referer"] = referer
    return headers

def generate_basic_advice(price, change_pct):
    """
    当没有历史数据时，根据当日涨跌幅生成基础建议
    """
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

def calculate_technical_advice(price, history_prices):
    """
    根据历史数据生成高级决策建议
    """
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

# --- 接口1 (新): GoldPrice.org (全球数据源，通常不封) ---
def get_price_goldpriceorg():
    print("--- [尝试 1] GoldPrice.org (全球源) ---")
    try:
        # 这个接口直接返回人民币计价的黄金价格，非常方便
        # 很多黄金插件都用这个
        url = "https://data-asg.goldprice.org/dbXRates/CNY"
        resp = requests.get(url, headers=get_headers(), timeout=10)

        if resp.status_code == 200:
            data = resp.json()
            # 格式: {"items":[{"curr":"CNY","xauPrice":17158.45,"xagPrice":...}]}
            # xauPrice 是 1盎司黄金的人民币价格
            if data and "items" in data and len(data["items"]) > 0:
                price_oz_cny = data["items"][0]["xauPrice"]

                # 换算: 1金衡盎司 = 31.1034768 克
                price_g_cny = price_oz_cny / 31.1035

                # GoldPrice.org 很难获取昨日收盘，我们用一个模拟的涨跌幅逻辑
                # 或者如果有 history 接口更好，这里为了稳定性，我们假设它只提供现价
                # 为了不报错，我们假设昨日价格是 (现价 / 1.001) 模拟 0.1% 波动，或者不显示涨跌

                # 尝试获取涨跌幅 (GoldPrice首页一般有)
                # 这里为了稳健，我们暂时给一个 mock 的涨跌，重点是拿到现价
                change = 0
                change_pct = 0

                return {
                    "source": "GoldPrice.org",
                    "price": round(price_g_cny, 2),
                    "change": 0, # 数据源限制，暂无涨跌额
                    "change_pct": 0,
                    "advice": "国际源数据，参考现价",
                    "advice_icon": "🌐",
                    "pos_pct": 50,
                    "week_low": round(price_g_cny, 2),
                    "week_high": round(price_g_cny, 2),
                    "history_trend": [],
                    "bg_color": "#333333", # 中性色
                    "est_price": round(price_g_cny + 25, 1)
                }
    except Exception as e:
        print(f"❌ GoldPrice.org异常: {e}")
    return None

# --- 接口2 (新): Binance (币安 API - 极稳) ---
def get_price_binance():
    print("--- [尝试 2] Binance (PAXG实物金代币) ---")
    try:
        # 1. 获取 PAXG/USDT (锚定1盎司黄金)
        url_gold = "https://api.binance.com/api/v3/ticker/price?symbol=PAXGUSDT"
        resp_gold = requests.get(url_gold, headers=get_headers(), timeout=10)
        gold_price_usd = float(resp_gold.json()["price"])

        # 2. 获取 汇率 (这里用一个免费的汇率API，或者直接给个固定值做保底)
        # 免费汇率API: https://api.exchangerate-api.com/v4/latest/USD
        url_rate = "https://api.exchangerate-api.com/v4/latest/USD"
        resp_rate = requests.get(url_rate, headers=get_headers(), timeout=10)
        cny_rate = resp_rate.json()["rates"]["CNY"]

        print(f"PAXG(USD): {gold_price_usd}, 汇率: {cny_rate}")

        # 计算
        price_cny = (gold_price_usd * cny_rate) / 31.1035

        # 币安有24小时涨跌幅接口
        url_24h = "https://api.binance.com/api/v3/ticker/24hr?symbol=PAXGUSDT"
        resp_24h = requests.get(url_24h, headers=get_headers(), timeout=10)
        data_24h = resp_24h.json()
        price_change_percent = float(data_24h["priceChangePercent"])
        price_change_amount = float(data_24h["priceChange"])

        # 换算涨跌额 (大概)
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
        print(f"❌ Binance异常: {e}")
    return None

# --- 接口3: 东方财富 K线 (历史最佳) ---
def get_price_eastmoney_history():
    print("--- [尝试 3] 东方财富 (K线趋势) ---")
    try:
        url = "https://push2his.eastmoney.com/api/qt/stock/kline/get?secid=119.Au9999&fields1=f1&fields2=f51,f52,f53,f54,f55&klt=101&fqt=1&lmt=6"
        resp = requests.get(url, headers=get_headers("https://quote.eastmoney.com/"), timeout=8)
        data = resp.json()
        if data and data.get("data") and data["data"].get("klines"):
            klines = data["data"]["klines"]
            parsed_history = [float(k.split(',')[2]) for k in klines]
            current = parsed_history[-1]
            if current <= 0: return None

            prev = parsed_history[-2] if len(parsed_history) >= 2 else current
            change = current - prev
            pct = (change / prev) * 100

            advice, icon, pos_pct, w_low, w_high = calculate_technical_advice(current, parsed_history[:-1])

            history_str = []
            if len(parsed_history) >= 4:
                history_str = [str(p) for p in parsed_history[-4:-1]]

            return {
                "source": "东方财富",
                "price": round(current, 2),
                "change": round(change, 2),
                "change_pct": round(pct, 2),
                "advice": advice, "advice_icon": icon, "pos_pct": pos_pct,
                "week_low": w_low, "week_high": w_high, "history_trend": history_str,
                "bg_color": "#5cb85c" if change < 0 else "#d9534f",
                "est_price": round(current + 25, 1)
            }
    except Exception as e:
        print(f"❌ 东方财富K线异常: {e}")
    return None

# --- 接口4: 第一黄金网 (国内垂直) ---
def get_price_jijinhao():
    print("--- [尝试 4] 第一黄金网 ---")
    try:
        url = "https://api.jijinhao.com/sQuoteCenter/realTime.jsp?sCodes=JO_92233"
        resp = requests.get(url, headers=get_headers("https://www.dyhjw.com/"), timeout=10)
        if resp.status_code == 200:
            match = re.search(r'=\s*({.*?})', resp.text)
            if match:
                json_str = match.group(1)
                last = re.search(r'"last":"([\d\.]+)"', json_str)
                pre = re.search(r'"pre_close":"([\d\.]+)"', json_str)
                if last and pre:
                    current = float(last.group(1))
                    prev = float(pre.group(1))
                    if current <= 0: return None

                    change = current - prev
                    pct = (change / prev) * 100
                    advice, icon, score = generate_basic_advice(current, pct)
                    return {
                        "source": "第一黄金网",
                        "price": current, "change": round(change, 2), "change_pct": round(pct, 2),
                        "advice": advice, "advice_icon": icon, "pos_pct": score,
                        "week_low": current, "week_high": current, "history_trend": [],
                        "bg_color": "#5cb85c" if change < 0 else "#d9534f",
                        "est_price": round(current + 25, 1)
                    }
    except Exception as e:
        print(f"❌ 第一黄金网异常: {e}")
    return None

def send_pushplus(data):
    print(f"--- 发起推送 ({data['source']}) ---")
    date_str = datetime.datetime.now().strftime("%Y-%m-%d %H:%M")
    change_sign = "+" if data['change'] > 0 else ""

    trend_html = ""
    if data['history_trend']:
        trend_items = "".join([f"<span style='background:#f3f3f3; padding:2px 5px; margin-right:4px; color:#555;'>{p}</span>" for p in data['history_trend']])
        trend_html = f"<div style='margin-top:10px; font-size:12px; color:#666;'>近3日: {trend_items} <span style='font-weight:bold;'>→ {data['price']}</span></div>"

    # 颜色处理
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

    url = 'http://www.pushplus.plus/send'
    payload = {
        "token": TOKEN,
        "title": f"{data['advice_icon']} 金价: {data['price']} ({change_sign}{data['change']})",
        "content": content,
        "template": "html",
        "topic": TOPIC
    }

    try:
        resp = requests.post(url, json=payload, headers=get_headers(), timeout=15)
        print(f"✅ 推送响应: {resp.status_code}")
    except Exception as e:
        print(f"❌ 推送失败: {e}")

if __name__ == "__main__":
    print("=== 六重保险版 (最终奥义) 启动 ===")

    # 策略顺序：
    # 1. GoldPrice.org: 专用数据源，最不容易被封
    # 2. Binance: 币安API，高频交易级稳定，海外必通
    # 3. 东方财富: 国内数据
    # 4. 第一黄金网: 垂直数据
    strategies = [
        get_price_goldpriceorg,
        get_price_binance,
        get_price_eastmoney_history,
        get_price_jijinhao
    ]

    data = None
    for strategy in strategies:
        data = strategy()
        if data:
            print(f"✅ 成功从 [{data['source']}] 获取数据")
            break
        else:
            print("⚠️ 失败，切换下一个源...")
            time.sleep(1.5)

    if data:
        if TOKEN:
            send_pushplus(data)
        else:
            print("📢 [模拟推送] Token未配置")
            print(json.dumps(data, indent=4, ensure_ascii=False))
    else:
        print("❌ 所有接口全军覆没")