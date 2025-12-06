import requests
import re
import os
import datetime

# 环境变量获取 Token
PUSHPLUS_TOKEN = os.environ.get("PUSHPLUS_TOKEN")

def get_shuibei_strategy():
    """
    获取国内大盘金价 (Au99.99)，并计算水贝模式落地价
    """
    # 新浪财经接口：gds_Au99_99 (上海黄金交易所黄金9999)
    url = "http://hq.sinajs.cn/list=gds_Au99_99"
    headers = {"Referer": "http://finance.sina.com.cn/"}
    
    try:
        response = requests.get(url, headers=headers)
        if response.status_code == 200:
            # 数据格式：
            # "380.00,380.00,380.00,380.00,380.00,0.00,0.00,0.00,..."
            # 字段含义（按顺序）：
            # 0: 开盘价, 1: 最高价, 2: 最低价, 3: 当前价, 4: 昨收价 ...
            text = response.text
            match = re.search(r'"([^"]+)"', text)
            
            if match:
                data = match.group(1).split(',')
                
                # 关键指标
                current_price = float(data[3]) # 当前大盘价
                yesterday_close = float(data[4]) # 昨收价
                open_price = float(data[0])    # 今开价
                
                # 如果当前休市（非交易时间价格可能是0或不更新），做个简单兜底
                if current_price == 0:
                    current_price = yesterday_close

                # --- 趋势分析 ---
                change = current_price - yesterday_close
                change_pct = (change / yesterday_close) * 100
                
                # 简单趋势判断逻辑
                if change > 0:
                    trend_symbol = "🔴 涨" # 红色代表涨
                    advice = "今日在大盘高位，建议观望，除非刚需。"
                elif change < 0:
                    trend_symbol = "🟢 跌" # 绿色代表跌
                    advice = "大盘回调中，适合去展厅选款！"
                else:
                    trend_symbol = "⚪ 平"
                    advice = "价格横盘，可按需购买。"

                # --- 水贝模式落地价试算 ---
                # 假设工费范围：10元(简单款) - 35元(古法/精工)
                price_low_labor = current_price + 10
                price_high_labor = current_price + 35
                
                return {
                    "price": current_price,
                    "change": round(change, 2),
                    "change_pct": round(change_pct, 2),
                    "trend": trend_symbol,
                    "advice": advice,
                    "calc_low": round(price_low_labor, 1),
                    "calc_high": round(price_high_labor, 1),
                    "time": datetime.datetime.now().strftime("%H:%M")
                }
    except Exception as e:
        print(f"Error: {e}")
    return None

def send_pushplus(data):
    if not data:
        return

    date_str = datetime.datetime.now().strftime("%Y-%m-%d")
    
    # 构造针对买首饰的 HTML 报告
    content = (
        f"<h3>✨ 结婚五金备战日报 ({date_str})</h3>"
        f"<p style='font-size:16px'><b>当前大盘：<span style='color:{'red' if data['change']>0 else 'green'}'>{data['price']}</span> 元/克</b></p>"
        f"<p>较昨日：{data['trend']} {data['change']}元 ({data['change_pct']}%)</p>"
        f"<hr>"
        f"<h4>🛒 水贝模式预算 (含工费)</h4>"
        f"<ul>"
        f"<li>普通工艺(光圈等)：约 <b>{data['calc_low']}</b> 元/克</li>"
        f"<li>古法/精工(手镯等)：约 <b>{data['calc_high']}</b> 元/克</li>"
        f"</ul>"
        f"<div style='background-color:#f4f4f5; padding:10px; border-radius:5px;'>"
        f"<b>🤖 机器人建议：</b><br>{data['advice']}"
        f"</div>"
        f"<p style='font-size:12px;color:gray;margin-top:20px'>*去展厅记得只要'按克重'，不要'一口价'！</p>"
    )

    url = 'http://www.pushplus.plus/send'
    payload = {
        "token": PUSHPLUS_TOKEN,
        "title": f"今日金价{data['price']} - {data['trend']}",
        "content": content,
        "template": "html"
    }
    
    requests.post(url, json=payload)
    print("推送完成")

if __name__ == "__main__":
    if not PUSHPLUS_TOKEN:
        print("请设置 PUSHPLUS_TOKEN")
    else:
        data = get_shuibei_strategy()
        send_pushplus(data)
