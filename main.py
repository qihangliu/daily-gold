import requests
import re
import os
import datetime

# 从环境变量获取 Token，这样代码里不暴露敏感信息
PUSHPLUS_TOKEN = os.environ.get("PUSHPLUS_TOKEN")

def get_gold_price():
    """
    获取国际金价（伦敦金 XAU）并估算国内金价
    数据源：新浪财经
    """
    url = "http://hq.sinajs.cn/list=hf_XAU"
    headers = {"Referer": "http://finance.sina.com.cn/"}
    
    try:
        response = requests.get(url, headers=headers)
        if response.status_code == 200:
            # 数据格式：var hq_str_hf_XAU="183.00,2648.33,..."
            text = response.text
            match = re.search(r'"([^"]+)"', text)
            if match:
                data = match.group(1).split(',')
                # data[0] 是当前价格 (美元/盎司)
                price_usd = float(data[0]) 
                # 昨收价 data[1]
                yesterday = float(data[1])
                
                # 简单估算人民币价格 (汇率约 7.28，1盎司=31.1035克)
                # 你也可以调用汇率接口获取实时汇率，这里为简单起见写死或取个近似值
                exchange_rate = 7.28 
                price_cny = price_usd * exchange_rate / 31.1035
                
                # 计算涨跌幅
                diff = price_usd - yesterday
                trend_icon = "📈 涨" if diff > 0 else "📉 跌"
                diff_str = f"{diff:.2f}"
                
                return {
                    "usd": price_usd,
                    "cny": round(price_cny, 2),
                    "trend": trend_icon,
                    "diff": diff_str
                }
    except Exception as e:
        print(f"Error: {e}")
    return None

def send_pushplus(data):
    if not data:
        print("未获取到数据，不发送")
        return

    date_str = datetime.datetime.now().strftime("%Y-%m-%d")
    
    # 构造 HTML 内容，PushPlus 支持 HTML 渲染
    content = (
        f"<h3>📅 日期：{date_str}</h3>"
        f"<p><b>国际金价：</b>${data['usd']} /盎司</p>"
        f"<p><b>国内估算：</b>¥{data['cny']} /克</p>"
        f"<p><b>今日走势：</b>{data['trend']} ({data['diff']})</p>"
        f"<hr>"
        f"<p style='font-size:12px;color:gray;'>数据来源：新浪财经 | 自动推送</p>"
    )

    url = 'http://www.pushplus.plus/send'
    payload = {
        "token": PUSHPLUS_TOKEN,
        "title": f"今日金价提醒 {data['usd']}",
        "content": content,
        "template": "html" 
    }
    
    resp = requests.post(url, json=payload)
    print("推送结果:", resp.text)

if __name__ == "__main__":
    if not PUSHPLUS_TOKEN:
        print("请设置 PUSHPLUS_TOKEN 环境变量")
    else:
        gold_data = get_gold_price()
        send_pushplus(gold_data)
