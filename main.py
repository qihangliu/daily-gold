import requests
import re
import os
import datetime

# 1. Token 依然从环境变量取 (安全第一)
TOKEN = os.environ.get("PUSHPLUS_TOKEN")

# 2. 这里填你的群组 ID
TOPIC = "20251206"

def get_shuibei_gold_price():
    """
    获取水贝模式金价策略 (Au99.99)
    """
    url = "http://hq.sinajs.cn/list=gds_Au99_99"
    headers = {"Referer": "http://finance.sina.com.cn/"}
    
    try:
        response = requests.get(url, headers=headers)
        if response.status_code == 200:
            text = response.text
            match = re.search(r'"([^"]+)"', text)
            if match:
                data = match.group(1).split(',')
                current_price = float(data[3]) # 当前价
                yesterday_close = float(data[4]) # 昨收价
                
                if current_price == 0:
                    current_price = yesterday_close

                # 趋势计算
                change = current_price - yesterday_close
                change_pct = (change / yesterday_close) * 100
                
                if change > 0:
                    trend = "🔴 涨"
                    advice = "今日在大盘高位，除非急需，建议暂缓。"
                    color = "#d9534f" # 红色
                elif change < 0:
                    trend = "🟢 跌"
                    advice = "机会来了！大盘回调，适合去展厅看款！"
                    color = "#5cb85c" # 绿色
                else:
                    trend = "⚪ 平"
                    advice = "价格平稳，按需购买。"
                    color = "#333333" # 黑色

                # 估算到手价 (大盘 + 25元工费)
                est_price = current_price + 25
                
                return {
                    "price": current_price,
                    "change": round(change, 2),
                    "change_pct": round(change_pct, 2),
                    "trend": trend,
                    "advice": advice,
                    "color": color,
                    "est_price": round(est_price, 1)
                }
    except Exception as e:
        print(f"获取金价失败: {e}")
    return None

def send_pushplus(data):
    if not data: return

    date_str = datetime.datetime.now().strftime("%Y-%m-%d")
    
    # --- 这里是推送内容的 HTML 模板 ---
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

    url = 'http://www.pushplus.plus/send'
    
    # 构造发送请求
    payload = {
        "token": TOKEN,
        "title": f"{data['trend']} 金价提醒：{data['price']}元", # 标题简洁一点，列表页好看
        "content": content,
        "template": "html",
        "topic": TOPIC  # <--- 这里就是你指定的群组
    }
    
    resp = requests.post(url, json=payload)
    print("推送响应:", resp.text)

if __name__ == "__main__":
    if not TOKEN:
        print("❌ 错误: 请在 GitHub Secrets 配置 PUSHPLUS_TOKEN")
    else:
        gold_data = get_shuibei_gold_price()
        send_pushplus(gold_data)
