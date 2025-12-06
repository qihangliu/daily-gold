import requests
import re
import os
import datetime
import sys
import random
import time
import json

# 尝试导入 dotenv，用于本地加载 .env 文件
# 如果在 GitHub Actions 环境运行，通常没有这个库，直接跳过即可
try:
    from dotenv import load_dotenv

    load_dotenv()
except ImportError:
    pass

# 强制刷新输出缓存，确保 GitHub Actions 日志实时显示
sys.stdout.reconfigure(encoding="utf-8")

# 获取 Token
TOKEN = os.environ.get("PUSHPLUS_TOKEN")
# 推送群组编码 (如有)
TOPIC = "20251206"

# --- 模拟浏览器的 User-Agent 列表 (反爬虫伪装) ---
USER_AGENTS = [
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36 Edg/120.0.0.0",
]


def get_headers():
    """生成随机请求头"""
    return {
        "User-Agent": random.choice(USER_AGENTS),
        "Accept": "*/*",
        "Accept-Language": "en-US,en;q=0.9,zh-CN;q=0.8",
        "Connection": "keep-alive",
    }


def format_output(source_name, price, change, change_pct):
    """统一格式化输出数据"""
    try:
        price = float(price)
        change = float(change)
        change_pct = float(change_pct)
    except:
        return None

    # 根据涨跌设置颜色和建议
    if change > 0:
        trend = "🔴 涨"
        advice = "今日在大盘高位，除非急需，建议暂缓。"
        color = "#d9534f"  # 红色
    elif change < 0:
        trend = "🟢 跌"
        advice = "机会来了！大盘回调，适合去展厅看款！"
        color = "#5cb85c"  # 绿色
    else:
        trend = "⚪ 平"
        advice = "价格平稳，按需购买。"
        color = "#333333"  # 灰色

    # 估算到手价 (大盘 + 25元工费)
    est_price = price + 25

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


# --- 策略 1: 东方财富 (国内权威，接口稳定) ---
def get_price_eastmoney():
    print("--- [尝试] 东方财富接口 ---")
    # secid=119.Au99.99 是上海黄金交易所代码
    url = "https://push2.eastmoney.com/api/qt/stock/get?secid=119.Au9999&fields=f43,f60,f169,f170"
    try:
        resp = requests.get(url, headers=get_headers(), timeout=10)
        if resp.status_code == 200:
            data = resp.json()
            if data and data.get("data"):
                d = data["data"]
                # f43:最新价, f169:涨跌额, f170:涨跌幅
                if d["f43"] != "-":
                    return format_output("东方财富", d["f43"], d["f169"], d["f170"])
    except Exception as e:
        print(f"❌ 东方财富异常: {e}")
    return None


# --- 策略 2: 雅虎财经 (国际换算，国外IP绝对不封) ---
def get_price_yahoo_calc():
    print("--- [尝试] 雅虎财经 (国际换算) ---")
    try:
        # 1. 获取 黄金期货 (GC=F) 美元/盎司
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

        # 3. 换算公式: (美元金价 * 汇率) / 31.1035 = 人民币克价
        price_cny_g = (gold_usd_oz * cny_rate) / 31.1035
        prev_price_cny_g = (prev_close_gold * cny_rate) / 31.1035

        change = price_cny_g - prev_price_cny_g
        pct = (change / prev_price_cny_g) * 100

        return format_output("雅虎财经(换算)", price_cny_g, change, pct)
    except Exception as e:
        print(f"❌ 雅虎财经异常: {e}")
    return None


# --- 策略 3: 新浪财经 (备用) ---
def get_price_sina():
    print("--- [尝试] 新浪财经 ---")
    url = "http://hq.sinajs.cn/list=gds_Au99_99"
    try:
        resp = requests.get(url, headers=get_headers(), timeout=5)
        # 检查是否被反爬返回空字符串
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
    """发送推送消息"""
    print(f"--- 正在发起推送 ({data['source']}) ---")
    date_str = datetime.datetime.now().strftime("%Y-%m-%d")

    # HTML 内容模板
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
        # 使用随机请求头，防止 PushPlus 屏蔽 GitHub IP
        headers = get_headers()
        resp = requests.post(url, json=payload, headers=headers, timeout=15)
        print(f"✅ 推送响应状态码: {resp.status_code}")
        print(f"✅ 推送响应内容: {resp.text}")
    except Exception as e:
        print(f"❌ 推送请求失败: {e}")


if __name__ == "__main__":
    print("=== 脚本启动 ===")

    # --- Token 诊断信息 ---
    if TOKEN:
        # 隐藏 Token 中间部分，仅显示首尾，用于日志确认
        mask_token = TOKEN[:4] + "*" * (len(TOKEN) - 4)
        print(f"🔍 环境变量检查: 检测到 TOKEN (长度={len(TOKEN)}, 开头={TOKEN[:4]}...)")
    else:
        print("🔍 环境变量检查: ❌ 未检测到 TOKEN！(将在获取数据后进入本地调试模式)")
    # ---------------------

    # 按顺序尝试策略：东方财富 -> 雅虎 -> 新浪
    strategies = [get_price_eastmoney, get_price_yahoo_calc, get_price_sina]
    gold_data = None

    for strategy in strategies:
        gold_data = strategy()
        if gold_data:
            print(f"✅ 成功从 [{gold_data['source']}] 获取数据")
            break
        else:
            print("⚠️ 获取失败，切换下一个源...")
            time.sleep(1)

    if gold_data:
        if TOKEN:
            send_pushplus(gold_data)
        else:
            # 如果没有 Token，打印在控制台供调试
            print("\n" + "=" * 40)
            print("📢 [本地/无Token模式] 模拟推送内容：")
            print(json.dumps(gold_data, indent=4, ensure_ascii=False))
            print("="*40 + "\n")
    else:
        print("❌ 所有接口全军覆没，请检查网络连接")

    print("=== 脚本结束 ===")