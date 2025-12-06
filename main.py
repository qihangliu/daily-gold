import requests
import re
import os
import datetime
import sys
import random
import time

# 强制刷新输出缓存
sys.stdout.reconfigure(encoding="utf-8")

TOKEN = os.environ.get("PUSHPLUS_TOKEN")
TOPIC = "20251206"

# --- 模拟浏览器的 User-Agent 列表 ---
USER_AGENTS = [
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36 Edg/120.0.0.0",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:109.0) Gecko/20100101 Firefox/121.0",
]


def get_random_headers(referer=""):
    """生成随机的浏览器请求头"""
    headers = {
        "User-Agent": random.choice(USER_AGENTS),
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,image/apng,*/*;q=0.8,application/signed-exchange;v=b3;q=0.7",
        "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
        "Connection": "keep-alive",
        "Upgrade-Insecure-Requests": "1",
    }
    if referer:
        headers["Referer"] = referer
    return headers


def parse_gold_data(source_name, price, change, change_pct):
    """
    统一处理金价数据，生成文案和颜色
    """
    try:
        price = float(price)
        change = float(change)
        change_pct = float(change_pct)
    except (ValueError, TypeError):
        print(f"❌ 数据转换失败: {price}, {change}")
        return None

    if change > 0:
        trend = "🔴 涨"
        advice = "今日在大盘高位，除非急需，建议暂缓。"
        color = "#d9534f"  # 红
    elif change < 0:
        trend = "🟢 跌"
        advice = "机会来了！大盘回调，适合去展厅看款！"
        color = "#5cb85c"  # 绿
    else:
        trend = "⚪ 平"
        advice = "价格平稳，按需购买。"
        color = "#333333"  # 黑

    # 估算到手价 (大盘 + 25元工费)
    est_price = price + 25

    return {
        "source": source_name,
        "price": price,
        "change": round(change, 2),
        "change_pct": round(change_pct, 2),
        "trend": trend,
        "advice": advice,
        "color": color,
        "est_price": round(est_price, 1),
    }


def get_price_from_sina():
    """来源1：新浪财经"""
    print("--- [尝试 1] 连接新浪财经接口 ---")
    url = "http://hq.sinajs.cn/list=gds_Au99_99"
    # 新浪有时候校验 Referer
    headers = get_random_headers("http://finance.sina.com.cn/")

    try:
        response = requests.get(url, headers=headers, timeout=5)
        if response.status_code == 200:
            text = response.text
            # 检查空响应
            if '=""' in text or '=","' in text:
                print("❌ 新浪接口返回空数据")
                return None

            match = re.search(r'"([^"]+)"', text)
            if match:
                data = match.group(1).split(",")
                if len(data) >= 5:
                    current = float(data[3])
                    yesterday = float(data[4])
                    # 避免除以0错误
                    if yesterday == 0:
                        return None

                    return parse_gold_data(
                        "新浪财经",
                        current,
                        current - yesterday,
                        (current - yesterday) / yesterday * 100,
                    )
    except Exception as e:
        print(f"❌ 新浪接口异常: {e}")
    return None


def get_price_from_tencent():
    """来源2：腾讯财经 (IP限制较少)"""
    print("--- [尝试 2] 连接腾讯财经接口 ---")
    url = "http://qt.gtimg.cn/q=s_shau9999"
    headers = get_random_headers("https://finance.qq.com/")

    try:
        response = requests.get(url, headers=headers, timeout=5)
        if response.status_code == 200:
            text = response.text
            match = re.search(r'"([^"]+)"', text)
            if match:
                data = match.group(1).split("~")
                if len(data) >= 6:
                    return parse_gold_data("腾讯财经", data[3], data[4], data[5])
    except Exception as e:
        print(f"❌ 腾讯接口异常: {e}")
    return None


def get_price_from_jijinhao():
    """来源3：第一黄金网/集金号 (专业接口)"""
    print("--- [尝试 3] 连接第一黄金网接口 ---")
    # JO_92233 是 Au99.99 的代码
    url = "https://api.jijinhao.com/sQuoteCenter/realTime.jsp?sCodes=JO_92233"
    headers = get_random_headers("https://www.dyhjw.com/")

    try:
        response = requests.get(url, headers=headers, timeout=8)
        if response.status_code == 200:
            text = response.text
            # 返回的是 JS 对象: var hq_json_JO_92233={"time"..., "last": "476.50", "pre_close": "475.00", ...}
            # 我们用正则提取 json 部分
            match = re.search(r"=\s*({.*?})", text)
            if match:
                import json

                # 处理一下非标准的 JSON key (有时候 key 没有引号)
                json_str = match.group(1)

                # 简单正则提取数值，不依赖复杂的 JSON 解析库以防格式错误
                last_match = re.search(r'"last":"([\d\.]+)"', json_str)
                prev_match = re.search(r'"pre_close":"([\d\.]+)"', json_str)

                if last_match and prev_match:
                    current = float(last_match.group(1))
                    yesterday = float(prev_match.group(1))

                    if yesterday > 0:
                        change = current - yesterday
                        pct = (change / yesterday) * 100
                        return parse_gold_data("第一黄金网", current, change, pct)
    except Exception as e:
        print(f"❌ 第一黄金网接口异常: {e}")
    return None


def send_pushplus(data):
    if not data:
        return

    print(f"--- 正在通过 PushPlus 推送 ({data['source']}) ---")
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
        f"<p style='font-size:12px; color:gray;'>*数据来源: {data['source']} / 水贝模式</p>"
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
        # 推送也加上伪装头
        headers = get_random_headers()
        resp = requests.post(url, json=payload, headers=headers, timeout=10)
        print(f"推送结果: {resp.text}")
    except Exception as e:
        print(f"❌ 推送失败: {e}")


if __name__ == "__main__":
    print("=== 脚本启动 ===")
    if not TOKEN:
        print("❌ 错误: PUSHPLUS_TOKEN 未设置")
    else:
        gold_data = None

        # 按顺序尝试 3 个接口
        sources = [get_price_from_sina, get_price_from_tencent, get_price_from_jijinhao]

        for get_price_func in sources:
            gold_data = get_price_func()
            if gold_data:
                print("✅ 获取数据成功！")
                break
            else:
                print("⚠️ 当前接口获取失败，1秒后尝试下一个...")
                time.sleep(1) # 休息一下，模拟人类操作间隔

        # 结果处理
        if gold_data:
            send_pushplus(gold_data)
        else:
            print("❌ 所有 3 个接口均获取失败，今日无法推送")

    print("=== 脚本结束 ===")