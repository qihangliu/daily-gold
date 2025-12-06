import requests
import re
import os
import datetime
import sys
import random
import time
import json

# 强制刷新输出缓存
sys.stdout.reconfigure(encoding="utf-8")

TOKEN = os.environ.get("PUSHPLUS_TOKEN")
TOPIC = "20251206"

# --- 模拟浏览器的 User-Agent 列表 ---
USER_AGENTS = [
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
]


def get_headers():
    return {
        "User-Agent": random.choice(USER_AGENTS),
        "Accept": "*/*",
        "Accept-Language": "en-US,en;q=0.9",
        "Connection": "keep-alive",
    }


def format_output(source_name, price, change, change_pct):
    """统一格式化输出"""
    try:
        price = float(price)
        change = float(change)
        change_pct = float(change_pct)
    except:
        return None

    if change > 0:
        trend = "🔴 涨"
        advice = "今日在大盘高位，除非急需，建议暂缓。"
        color = "#d9534f"
    elif change < 0:
        trend = "🟢 跌"
        advice = "机会来了！大盘回调，适合去展厅看款！"
        color = "#5cb85c"
    else:
        trend = "⚪ 平"
        advice = "价格平稳，按需购买。"
        color = "#333333"

    est_price = price + 25  # 估算工费

    return {
        "source": source_name,
        "price": round(price, 2),
        "change": round(change, 2),
        "change_pct": round(change_pct, 2),
        "trend": trend,
        "advice": advice,
        "color": color,
        "est_price": round(est_price, 1),
    }


# --- 接口 1: 东方财富 (国内权威，通常比新浪稳) ---
def get_price_eastmoney():
    print("--- [尝试] 东方财富接口 ---")
    # secid=119.Au99.99 是上海黄金交易所的 Au99.99 代码
    # f43: 最新价, f44: 最高, f45: 最低, f46: 今开, f60: 昨收, f169: 涨跌, f170: 涨跌幅
    url = "https://push2.eastmoney.com/api/qt/stock/get?secid=119.Au9999&fields=f43,f60,f169,f170"

    try:
        resp = requests.get(url, headers=get_headers(), timeout=10)
        if resp.status_code == 200:
            data = resp.json()
            if data and data.get("data"):
                d = data["data"]
                current = d["f43"]
                change = d["f169"]
                pct = d["f170"]

                # 东方财富有时候休市返回 -
                if current == "-":
                    return None

                # 东方财富的数据已经是数字了，直接用
                return format_output("东方财富", current, change, pct)
    except Exception as e:
        print(f"❌ 东方财富异常: {e}")
    return None


# --- 接口 2: 雅虎财经 (美国本土，GitHub Actions 绝对不封) ---
def get_price_yahoo_calc():
    print("--- [尝试] 雅虎财经 (国际换算) ---")
    # 逻辑：获取国际金价(美元/盎司) * 汇率 / 31.1035 = 人民币/克
    try:
        # 1. 获取 黄金期货 (GC=F)
        url_gold = "https://query1.finance.yahoo.com/v8/finance/chart/GC=F?interval=1d&range=1d"
        resp_gold = requests.get(url_gold, headers=get_headers(), timeout=10)
        data_gold = resp_gold.json()
        gold_usd_oz = data_gold["chart"]["result"][0]["meta"]["regularMarketPrice"]
        prev_close_gold = data_gold["chart"]["result"][0]["meta"]["chartPreviousClose"]

        # 2. 获取 美元兑人民币汇率 (CNY=X)
        url_cny = "https://query1.finance.yahoo.com/v8/finance/chart/CNY=X?interval=1d&range=1d"
        resp_cny = requests.get(url_cny, headers=get_headers(), timeout=10)
        cny_rate = resp_cny.json()["chart"]["result"][0]["meta"]["regularMarketPrice"]

        print(f"国际金价: ${gold_usd_oz}/oz, 汇率: {cny_rate}")

        # 3. 换算
        # 1 金衡盎司 = 31.1034768 克
        price_cny_g = (gold_usd_oz * cny_rate) / 31.1035
        prev_price_cny_g = (prev_close_gold * cny_rate) / 31.1035

        change = price_cny_g - prev_price_cny_g
        pct = (change / prev_price_cny_g) * 100

        return format_output("雅虎财经(换算)", price_cny_g, change, pct)

    except Exception as e:
        print(f"❌ 雅虎财经异常: {e}")
    return None


# --- 原有接口 (新浪/腾讯) 也可以保留作为备选 ---
def get_price_sina():
    print("--- [尝试] 新浪财经 ---")
    url = "http://hq.sinajs.cn/list=gds_Au99_99"
    try:
        resp = requests.get(url, headers=get_headers(), timeout=5)
        if resp.status_code == 200 and '=""' not in resp.text:
            match = re.search(r'"([^"]+)"', resp.text)
            if match:
                d = match.group(1).split(",")
                if len(d) > 4:
                    return format_output(
                        "新浪财经",
                        d[3],
                        float(d[3]) - float(d[4]),
                        (float(d[3]) - float(d[4])) / float(d[4]) * 100,
                    )
    except:
        pass
    return None


def send_pushplus(data):
    if not data:
        return
    print(f"--- 发送推送 ({data['source']}) ---")

    date_str = datetime.datetime.now().strftime("%Y-%m-%d")
    content = (
        f"<h3>💍 2025 夺金计划日报 ({date_str})</h3>"
        f"<div style='font-size:16px; margin-bottom:10px;'>"
        f"今日大盘：<b style='color:{data['color']}; font-size:20px;'>{data['price']}</b> 元/克"
        f"</div>"
        f"<p>相比昨日：{data['trend']} {data['change']}元 ({data['change_pct']}%)</p>"
        f"<hr style='border:1px dashed #ccc;'>"
        f"<h4>🛒 预估落地价 (含工费)：</h4>"
        f"<p style='font-size:18px; font-weight:bold; color:#f0ad4e;'>¥ {data['est_price']} /克</p>"
        f"<p style='font-size:12px; color:gray;'>*数据来源: {data['source']}</p>"
        f"<br>"
        f"<div style='background:#f9f9f9; padding:15px; border-left:5px solid {data['color']}; border-radius:5px;'>"
        f"<b>🤖 机器人建议：</b><br>{data['advice']}"
        f"</div>"
    )

    url = "http://www.pushplus.plus/send"
    payload = {
        "token": TOKEN,
        "title": f"{data['trend']} 金价: {data['price']}",
        "content": content,
        "template": "html",
        "topic": TOPIC,
    }
    try:
        requests.post(url, json=payload, timeout=10)
        print("✅ 推送请求已发送")
    except Exception as e:
        print(f"❌ 推送失败: {e}")


if __name__ == "__main__":
    if not TOKEN:
        print("❌ 错误: PUSHPLUS_TOKEN 未设置")
        sys.exit(1)

    # 策略：优先用东方财富（国内准），不行用新浪，再不行用雅虎（国外稳）
    # 雅虎是最后一道防线，因为它在美国绝对不会被封
    strategies = [get_price_eastmoney, get_price_sina, get_price_yahoo_calc]

    gold_data = None
    for strategy in strategies:
        gold_data = strategy()
        if gold_data:
            print(f"✅ 成功从 [{gold_data['source']}] 获取数据")
            send_pushplus(gold_data)
            break
        else:
            print("⚠️ 获取失败，切换下一个源...")
            time.sleep(1)

    if not gold_data:
        print("❌ 所有接口全军覆没，请检查网络或Token")