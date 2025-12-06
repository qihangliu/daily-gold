import requests
import re
import os
import datetime
import sys

# 强制刷新输出缓存，确保日志能实时显示
sys.stdout.reconfigure(encoding="utf-8")

TOKEN = os.environ.get("PUSHPLUS_TOKEN")
TOPIC = "20251206"


def get_shuibei_gold_price():
    print("--- 正在连接新浪财经接口 ---")
    url = "http://hq.sinajs.cn/list=gds_Au99_99"
    headers = {
        "Referer": "http://finance.sina.com.cn/",
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    }

    try:
        response = requests.get(url, headers=headers, timeout=10)
        print(f"接口状态码: {response.status_code}")

        if response.status_code == 200:
            text = response.text
            print(f"接口返回原始内容: {text[:50]}...")  # 打印前50个字符看看

            match = re.search(r'"([^"]+)"', text)
            if match:
                data = match.group(1).split(",")
                # 打印解析出来的数据，看看是不是格式变了
                print(f"解析后的数据列表: {data}")

                if len(data) < 5:
                    print("❌ 数据字段不足，无法读取价格")
                    return None

                current_price = float(data[3])  # 当前价
                yesterday_close = float(data[4])  # 昨收价

                print(f"当前价: {current_price}, 昨收: {yesterday_close}")

                if current_price == 0:
                    current_price = yesterday_close

                # 趋势计算
                change = current_price - yesterday_close
                change_pct = (
                    (change / yesterday_close) * 100 if yesterday_close != 0 else 0
                )

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

                est_price = current_price + 25

                return {
                    "price": current_price,
                    "change": round(change, 2),
                    "change_pct": round(change_pct, 2),
                    "trend": trend,
                    "advice": advice,
                    "color": color,
                    "est_price": round(est_price, 1),
                }
            else:
                print("❌ 正则匹配失败：未找到引号内的内容")
        else:
            print("❌ 接口请求失败，状态码不是 200")

    except Exception as e:
        print(f"❌ 获取金价发生异常: {e}")

    return None


def send_pushplus(data):
    if not data:
        print("⚠️ 没有数据，取消推送")
        return

    print("--- 正在发送 PushPlus 推送 ---")
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
        f"<p style='font-size:12px; color:gray;'>*参考西安展厅/水贝模式</p>"
        f"<br>"
        f"<div style='background:#f9f9f9; padding:15px; border-left:5px solid {data['color']}; border-radius:5px;'>"
        f"<b>🤖 机器人建议：</b><br>{data['advice']}"
        f"</div>"
    )

    url = "http://www.pushplus.plus/send"

    payload = {
        "token": TOKEN,
        "title": f"{data['trend']} 金价提醒：{data['price']}元",
        "content": content,
        "template": "html",
        "topic": TOPIC,
    }

    try:
        resp = requests.post(url, json=payload, timeout=10)
        print(f"推送响应状态码: {resp.status_code}")
        print(f"推送响应内容: {resp.text}")
    except Exception as e:
        print(f"❌ 推送发生异常: {e}")


if __name__ == "__main__":
    print("=== 脚本开始执行 ===")
    if not TOKEN:
        print("❌ 错误: 环境变量 PUSHPLUS_TOKEN 未设置或为空")
    else:
        print("✅ 检测到 Token，开始获取数据...")
        gold_data = get_shuibei_gold_price()
        if gold_data:
            send_pushplus(gold_data)
        else:
            print("❌ 获取到的金价数据为空，无法推送")
    print("=== 脚本执行结束 ===")