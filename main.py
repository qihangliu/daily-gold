import requests
import re
import os
import datetime
import sys
import random
import time
import statistics

try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass

sys.stdout.reconfigure(encoding='utf-8')
TOKEN = os.environ.get("PUSHPLUS_TOKEN")
TOPIC = "20251206"

# 扩充 User-Agent 池 (模拟更多设备)
USER_AGENTS = [
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Mozilla/5.0 (iPhone; CPU iPhone OS 16_0 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/16.0 Mobile/15E148 Safari/604.1",
    "Mozilla/5.0 (Linux; Android 10; SM-G975F) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/96.0.4664.104 Mobile Safari/537.36"
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

# --- 接口1: 东方财富 K线历史 (最佳) ---
def get_price_eastmoney_history():
    print("--- [尝试 1] 东方财富 (K线趋势) ---")
    try:
        url = "https://push2his.eastmoney.com/api/qt/stock/kline/get?secid=119.Au9999&fields1=f1&fields2=f51,f52,f53,f54,f55&klt=101&fqt=1&lmt=6"
        resp = requests.get(url, headers=get_headers("https://quote.eastmoney.com/"), timeout=8)
        data = resp.json()

        if data and data.get("data") and data["data"].get("klines"):
            klines = data["data"]["klines"]
            parsed_history = [float(k.split(',')[2]) for k in klines]

            current_price = parsed_history[-1]
            prev_price = parsed_history[-2] if len(parsed_history) >= 2 else current_price

            change = current_price - prev_price
            pct = (change / prev_price) * 100

            # 如果接口返回 0 (有时候休市会这样)，则判定失败
            if current_price <= 0: return None

            advice, icon, pos_pct, w_low, w_high = calculate_technical_advice(current_price, parsed_history[:-1])

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
                "est_price": round(current_price + 25, 1)
            }
    except Exception as e:
        print(f"❌ 东方财富K线异常: {e}")
    return None

# --- 接口2: 东方财富 快照 (备用) ---
def get_price_eastmoney_snapshot():
    print("--- [尝试 2] 东方财富 (实时快照) ---")
    try:
        url = "https://push2.eastmoney.com/api/qt/stock/get?secid=119.Au9999&fields=f43,f169,f170"
        resp = requests.get(url, headers=get_headers("https://quote.eastmoney.com/"), timeout=8)
        d = resp.json().get("data")
        if d and d["f43"] != "-":
            price = float(d["f43"])
            if price <= 0: return None

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
                "week_low": price, "week_high": price, "history_trend": [],
                "bg_color": "#5cb85c" if change < 0 else "#d9534f",
                "est_price": price + 25
            }
    except Exception as e:
        print(f"❌ 东方财富快照异常: {e}")
    return None

# --- 接口3: 第一黄金网 (新增 - 垂直行业数据) ---
def get_price_jijinhao():
    print("--- [尝试 3] 第一黄金网 (集金号) ---")
    try:
        # JO_92233 是 Au9999 代码
        url = "https://api.jijinhao.com/sQuoteCenter/realTime.jsp?sCodes=JO_92233"
        resp = requests.get(url, headers=get_headers("https://www.dyhjw.com/"), timeout=10)

        if resp.status_code == 200:
            # 返回格式: var hq_json_JO_92233={"time":"...","last":"615.50","pre_close":"617.20",...}
            # 使用正则提取 JSON 部分
            match = re.search(r'=\s*({.*?})', resp.text)
            if match:
                # 他们的 JSON key 有时候不带引号，为了保险用正则直接取值
                json_str = match.group(1)

                last_match = re.search(r'"last":"([\d\.]+)"', json_str)
                pre_match = re.search(r'"pre_close":"([\d\.]+)"', json_str)

                if last_match and pre_match:
                    current = float(last_match.group(1))
                    prev = float(pre_match.group(1))

                    if current <= 0 or prev <= 0: return None

                    change = current - prev
                    pct = (change / prev) * 100

                    advice, icon, score = generate_basic_advice(current, pct)

                    return {
                        "source": "第一黄金网",
                        "price": current,
                        "change": round(change, 2),
                        "change_pct": round(pct, 2),
                        "advice": advice,
                        "advice_icon": icon,
                        "pos_pct": score,
                        "week_low": current, "week_high": current, "history_trend": [],
                        "bg_color": "#5cb85c" if change < 0 else "#d9534f",
                        "est_price": round(current + 25, 1)
                    }
    except Exception as e:
        print(f"❌ 第一黄金网异常: {e}")
    return None

# --- 接口4: 雅虎财经 (国际换算 - 最强备用) ---
def get_price_yahoo_calc():
    print("--- [尝试 4] 雅虎财经 (国际换算) ---")
    try:
        url_gold = "https://query1.finance.yahoo.com/v8/finance/chart/GC=F?interval=1d&range=1d"
        resp_gold = requests.get(url_gold, headers=get_headers(), timeout=15)
        data_gold = resp_gold.json()
        gold_usd_oz = data_gold['chart']['result'][0]['meta']['regularMarketPrice']
        prev_gold = data_gold['chart']['result'][0]['meta']['chartPreviousClose']

        url_cny = "https://query1.finance.yahoo.com/v8/finance/chart/CNY=X?interval=1d&range=1d"
        resp_cny = requests.get(url_cny, headers=get_headers(), timeout=15)
        cny_rate = resp_cny.json()['chart']['result'][0]['meta']['regularMarketPrice']

        print(f"国际金价: ${gold_usd_oz}, 汇率: {cny_rate}")

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
            "pos_pct": score,
            "week_low": round(price_cny, 2), "week_high": round(price_cny, 2), "history_trend": [],
            "bg_color": "#5cb85c" if change < 0 else "#d9534f",
            "est_price": round(price_cny + 25, 1)
        }
    except Exception as e:
        print(f"❌ 雅虎财经异常: {e}")
    return None

# --- 接口5: 腾讯财经 (Smart模式) ---
def get_price_tencent():
    print("--- [尝试 5] 腾讯财经 ---")
    try:
        # 腾讯 Au9999 代码是 shau9999
        url = "http://qt.gtimg.cn/q=s_shau9999"
        resp = requests.get(url, headers=get_headers("https://finance.qq.com/"), timeout=6)
        if resp.status_code == 200:
            # v_s_shau9999="1~黄金9999~shau9999~615.50~-2.10~-0.34~...";
            match = re.search(r'="([^"]+)"', resp.text)
            if match:
                data = match.group(1).split('~')
                if len(data) >= 6:
                    current = float(data[3])
                    change = float(data[4])
                    pct = float(data[5])

                    if current <= 0: return None

                    advice, icon, score = generate_basic_advice(current, pct)

                    return {
                        "source": "腾讯财经",
                        "price": current,
                        "change": change,
                        "change_pct": pct,
                        "advice": advice,
                        "advice_icon": icon,
                        "pos_pct": score,
                        "week_low": current, "week_high": current, "history_trend": [],
                        "bg_color": "#5cb85c" if change < 0 else "#d9534f",
                        "est_price": current + 25
                    }
    except Exception as e:
        print(f"❌ 腾讯财经异常: {e}")
    return None

def send_pushplus(data):
    print(f"--- 发起推送 ({data['source']}) ---")
    date_str = datetime.datetime.now().strftime("%Y-%m-%d %H:%M")
    change_sign = "+" if data['change'] > 0 else ""

    # 历史趋势HTML
    trend_html = ""
    if data['history_trend']:
        trend_items = "".join([f"<span style='background:#f3f3f3; padding:2px 5px; margin-right:4px; color:#555;'>{p}</span>" for p in data['history_trend']])
        trend_html = f"<div style='margin-top:10px; font-size:12px; color:#666;'>近3日: {trend_items} <span style='font-weight:bold;'>→ {data['price']}</span></div>"
    else:
        trend_html = "<div style='margin-top:10px; font-size:12px; color:#999;'>* 实时快照源，暂无历史数据</div>"

    content = f"""
    <div style="font-family: -apple-system, sans-serif; background-color: #ffffff; padding: 15px; border-radius: 10px; border: 1px solid #eee; color: #333333;">
        <div style="background-color: {data['bg_color']}; border-radius: 8px; padding: 20px; color: #ffffff; text-align: center;">
            <div style="font-size: 13px; opacity: 0.9; color: #ffffff;">水贝参考价 (Au99.99)</div>
            <div style="font-size: 40px; font-weight: 800; line-height: 1.1; margin: 5px 0; color: #ffffff;">{data['price']}</div>
            <div style="display: inline-block; font-size: 14px; background-color: rgba(0,0,0,0.15); padding: 4px 12px; border-radius: 12px; color: #ffffff;">
                {change_sign}{data['change']}元 ({change_sign}{data['change_pct']}%)
            </div>
        </div>
        <div style="background-color: #f8f9fa; margin-top: 15px; border-radius: 8px; padding: 15px; border: 1px solid #eeeeee;">
            <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 12px;">
                <span style="font-weight: bold; color: #333333;">决策建议</span>
                <span style="font-weight: bold; color: {data['bg_color']}">{data['advice_icon']} {data['advice']}</span>
            </div>
            <div style="margin-bottom: 6px; font-size: 12px; color: #666666; display: flex; justify-content: space-between;">
                <span>低 {data['week_low']}</span>
                <span>高 {data['week_high']}</span>
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
    print("=== 五重保险版启动 ===")

    strategies = [
        get_price_eastmoney_history,
        get_price_eastmoney_snapshot,
        get_price_jijinhao,
        get_price_yahoo_calc,
        get_price_tencent
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
    else:
        print("❌ 所有的金价接口都失败了，这网络太难了")