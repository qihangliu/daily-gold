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

USER_AGENTS = [
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
]


def get_headers():
    return {
        "User-Agent": random.choice(USER_AGENTS),
        "Accept": "*/*",
        "Connection": "keep-alive",
        "Referer": "https://quote.eastmoney.com/",
    }


def calculate_technical_advice(price, history_prices):
    """
    根据历史数据生成决策建议
    history_prices: 最近几天的收盘价列表
    """
    if not history_prices:
        return "数据不足，按需购买", "☕", 50, price, price

    # 计算 5日均线 (MA5)
    all_prices = history_prices + [price]
    # 取最后5个点计算均线
    ma5 = statistics.mean(all_prices[-5:])

    # 计算本周(或近5日)高低点
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
            advice = "近5日极低位，建议入手"
            advice_icon = "🔥🔥"  # 火热推荐
        elif position_pct < 50:
            advice = "低于周均价，适合买入"
            advice_icon = "🛒"  # 购物车
        else:
            advice = "趋势回调中，可分批入"
            advice_icon = "📉"
    else:
        # 现价高于5日均线 -> 贵
        if position_pct > 80:
            advice = "近5日高位，切勿追高"
            advice_icon = "🛑"  # 停止
        else:
            advice = "高于周均价，建议观望"
            advice_icon = "✋"  # 等待

    return advice, advice_icon, position_pct, week_low, week_high


def get_price_eastmoney_history():
    """
    主力接口：东方财富 K线历史接口 (替代雅虎)
    获取最近 5 天的数据进行趋势分析
    """
    print("--- [尝试] 东方财富 (K线趋势) ---")
    try:
        # lmt=5: 获取最近5天
        # klt=101: 日K
        # secid=119.Au9999: 上海黄金交易所代码
        url = "https://push2his.eastmoney.com/api/qt/stock/kline/get?secid=119.Au9999&fields1=f1&fields2=f51,f52,f53,f54,f55&klt=101&fqt=1&lmt=6"

        resp = requests.get(url, headers=get_headers(), timeout=10)
        data = resp.json()

        if data and data.get("data") and data["data"].get("klines"):
            klines = data["data"]["klines"]
            # klines 格式: ["2023-10-20,460.5,462.1,459.8,461.0,...", ...]
            # 解析收盘价 (index 2 是收盘价)
            parsed_history = []
            for k in klines:
                # 东方财富K线数据是以逗号分隔的字符串
                # 日期,开盘,收盘,最高,最低...
                parts = k.split(",")
                close_price = float(parts[2])
                parsed_history.append(close_price)

            # 东方财富的历史数据包含今天(如果是交易时间)
            # 我们取最后一个作为当前价
            current_price = parsed_history[-1]
            # 昨天的价格
            prev_price = (
                parsed_history[-2] if len(parsed_history) >= 2 else current_price
            )

            # 历史列表 (不含今天，用于计算)
            history_for_calc = parsed_history[:-1]

            change = current_price - prev_price
            pct = (change / prev_price) * 100

            # 生成决策
            advice, icon, pos_pct, w_low, w_high = calculate_technical_advice(
                current_price, history_for_calc
            )

            # 格式化近3日走势 (取倒数第4到倒数第2个)
            history_str_list = []
            if len(parsed_history) >= 4:
                recent = parsed_history[-4:-1]
                history_str_list = [str(p) for p in recent]

            labor_fee = 25
            est_price = current_price + labor_fee
            bg_color = "#5cb85c" if change < 0 else "#d9534f"

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
                "bg_color": bg_color,
                "est_price": round(est_price, 1),
                "labor_fee": labor_fee,
            }
    except Exception as e:
        print(f"❌ 东方财富K线异常: {e}")
    return None


def get_price_sina_fallback():
    """
    备用接口：新浪财经 (老牌接口，最稳)
    """
    print("--- [备用] 新浪财经接口 ---")
    url = "http://hq.sinajs.cn/list=gds_Au99_99"
    try:
        resp = requests.get(url, headers=get_headers(), timeout=5)
        if resp.status_code == 200:
            # var hq_str_gds_Au99_99="黄金9999,476.50,475.10,478.00,474.00,...";
            match = re.search(r'"([^"]+)"', resp.text)
            if match:
                d = match.group(1).split(",")
                if len(d) > 8:
                    current = float(d[3])
                    prev = float(d[4])
                    low = float(d[5])
                    high = float(d[6])

                    if current == 0:
                        current = prev  # 休市处理

                    change = current - prev
                    pct = (change / prev) * 100

                    bg_color = "#5cb85c" if change < 0 else "#d9534f"

                    return {
                        "source": "新浪财经(快照)",
                        "price": current,
                        "change": round(change, 2),
                        "change_pct": round(pct, 2),
                        "advice": "价格回调中" if change < 0 else "价格上涨中",
                        "advice_icon": "ℹ️",
                        "pos_pct": 50,
                        "week_low": low if low > 0 else current,
                        "week_high": high if high > 0 else current,
                        "history_trend": [],
                        "bg_color": bg_color,
                        "est_price": current + 25,
                        "labor_fee": 25,
                    }
    except Exception as e:
        print(f"❌ 新浪财经异常: {e}")
    return None


def send_pushplus(data):
    print(f"--- 正在发起推送 ({data['source']}) ---")
    date_str = datetime.datetime.now().strftime("%Y-%m-%d %H:%M")

    change_sign = "+" if data["change"] > 0 else ""

    # 历史走势 HTML
    trend_html = ""
    if data["history_trend"]:
        trend_items = "".join(
            [
                f"<span style='background:#f3f3f3; padding:2px 5px; border-radius:4px; font-size:12px; margin-right:4px; color:#555; border:1px solid #eee;'>{p}</span>"
                for p in data["history_trend"]
            ]
        )
        trend_html = f"<div style='margin-top:10px; font-size:12px; color:#666;'>近3日走势: {trend_items} <span style='color:#333; font-weight:bold;'>→ {data['price']}</span></div>"

    # --- HTML 模板优化 (深色模式适配) ---
    # 1. 最外层 section 强制白色背景，确保在深色模式下变成“卡片”而不是反色成黑色
    # 2. 所有的文字颜色强制指定，防止反色后看不清
    content = f"""
    <div style="font-family: -apple-system, sans-serif; max-width: 100%; background-color: #ffffff; padding: 15px; border-radius: 10px; border: 1px solid #eee; color: #333333;">

        <!-- 1. 核心价格卡片 -->
        <div style="background-color: {data["bg_color"]}; border-radius: 8px; padding: 20px 15px; color: #ffffff; text-align: center; box-shadow: 0 2px 8px rgba(0,0,0,0.1);">
            <div style="font-size: 13px; opacity: 0.95; margin-bottom: 5px; color: #ffffff;">水贝模式参考价 (Au99.99)</div>
            <div style="font-size: 42px; font-weight: 800; line-height: 1; color: #ffffff;">{data["price"]}</div>
            <div style="margin-top: 10px;">
                <span style="font-size: 14px; background-color: rgba(255,255,255,0.2); padding: 4px 12px; border-radius: 20px; color: #ffffff;">
                    {change_sign}{data["change"]}元 ({change_sign}{data["change_pct"]}%)
                </span>
            </div>
        </div>

        <!-- 2. 决策辅助仪表盘 -->
        <div style="background-color: #fcfcfc; margin-top: 15px; border-radius: 8px; padding: 15px; border: 1px solid #f0f0f0;">
            <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 15px;">
                <span style="font-weight: bold; color: #333333; font-size: 16px;">决策分析</span>
                <span style="font-size: 14px; font-weight: bold; color: {data["bg_color"]}">{data["advice_icon"]} {data["advice"]}</span>
            </div>

            <!-- 价格区间条 -->
            <div style="margin-bottom: 5px; font-size: 12px; color: #666666; display: flex; justify-content: space-between;">
                <span>周低 {data["week_low"]}</span>
                <span>周高 {data["week_high"]}</span>
            </div>
            <!-- 进度条背景强制灰色，防止深色模式下消失 -->
            <div style="position: relative; height: 10px; background: linear-gradient(90deg, #5cb85c 0%, #ffc107 50%, #d9534f 100%); border-radius: 5px; margin-bottom: 15px;">
                <div style="position: absolute; left: {data["pos_pct"]}%; top: -3px; width: 6px; height: 16px; background-color: #333333; border: 2px solid #ffffff; border-radius: 4px; box-shadow: 0 2px 4px rgba(0,0,0,0.2); transform: translateX(-50%);"></div>
            </div>

            {trend_html}
        </div>

        <!-- 3. 落地成本 -->
        <div style="background-color: #f9f9f9; margin-top: 15px; border-radius: 8px; padding: 12px; border: 1px solid #eeeeee; display: flex; align-items: center; justify-content: space-between;">
            <div style="font-size: 14px; color: #555555;">预估到手 (含工费)</div>
            <div style="font-size: 20px; font-weight: bold; color: #f0ad4e;">
                ¥ {data["est_price"]}
            </div>
        </div>

        <div style="margin-top: 15px; text-align: center; color: #cccccc; font-size: 12px;">
            更新: {date_str} | 源: {data["source"]}
        </div>
    </div>
    """

    url = "http://www.pushplus.plus/send"
    payload = {
        "token": TOKEN,
        "title": f"{data['advice_icon']} {data['price']} ({change_sign}{data['change']})",
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
    print("=== 决策辅助版 (V3) 启动 ===")

    # 1. 尝试 东方财富 K线 (历史趋势)
    data = get_price_eastmoney_history()

    # 2. 失败则尝试 新浪财经 (快照)
    if not data:
        data = get_price_sina_fallback()

    if data:
        print(f"✅ 获取成功: {data['source']} | 现价: {data['price']} | 建议: {data['advice']}")
        if TOKEN:
            send_pushplus(data)
        else:
            print("📢 [模拟推送] Token未配置，跳过发送")
    else:
        print("❌ 所有接口均失败，请检查网络或IP限制")