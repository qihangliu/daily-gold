#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
金价抓取 + 趋势分析 + 绘图推送 (GitHub Actions 专用版)
优化：增强反爬虫策略，增加重试机制，完善请求头模拟
"""

import os
import sys
import time
import json
import random
import datetime
import base64
import io
from typing import Any, Dict, List, Optional
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

try:
    from dotenv import load_dotenv
    load_dotenv()
except Exception:
    pass

import requests

# 引入数据分析库
try:
    import pandas as pd
    import matplotlib
    # 设置无头模式，防止在 GitHub Actions 报错
    matplotlib.use('Agg')
    import matplotlib.pyplot as plt
    import matplotlib.dates as mdates
    HAS_ANALYSIS_LIBS = True
except ImportError:
    HAS_ANALYSIS_LIBS = False
    print("⚠️ 缺少 pandas 或 matplotlib，将跳过绘图和深度分析。")

# ---------- 配置 ----------
TOPIC = os.environ.get("PUSHPLUS_TOPIC", "20251206")
TOKEN = os.environ.get("PUSHPLUS_TOKEN")
PER_REQUEST_TIMEOUT = (5, 10) # 适当增加超时时间
MAX_RETRIES = 3 # 最大重试次数

# 扩展的 User-Agent 池，模拟不同设备
USER_AGENTS = [
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:109.0) Gecko/20100101 Firefox/121.0",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10.15; rv:109.0) Gecko/20100101 Firefox/121.0",
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/119.0.0.0 Safari/537.36",
]

def get_headers(referer: Optional[str] = None) -> Dict[str, str]:
    """
    生成伪装性更强的 Headers
    """
    h = {
        "User-Agent": random.choice(USER_AGENTS),
        "Connection": "keep-alive",
        "Accept": "application/json, text/javascript, */*; q=0.01",
        "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
        "Accept-Encoding": "gzip, deflate, br",
        "DNT": "1", # Do Not Track
        "Cache-Control": "no-cache",
        "Pragma": "no-cache",
        "Sec-Fetch-Dest": "empty",
        "Sec-Fetch-Mode": "cors",
        "Sec-Fetch-Site": "same-site",
    }
    if referer:
        h["Referer"] = referer
    return h

# ---------- 数据分析与绘图核心 ----------

def analyze_and_plot(klines: List[str]) -> Dict[str, Any]:
    """
    处理历史K线数据，计算指标，生成图片
    """
    if not HAS_ANALYSIS_LIBS or not klines:
        return {}
    
    # 1. 数据清洗
    data_list = []
    for k in klines:
        parts = k.split(',')
        if len(parts) > 3:
            data_list.append({
                "date": parts[0],
                "close": float(parts[2])
            })
    
    df = pd.DataFrame(data_list)
    df['date'] = pd.to_datetime(df['date'])
    df.set_index('date', inplace=True)
    
    # 2. 计算技术指标
    # MA (移动平均线)
    df['MA5'] = df['close'].rolling(window=5).mean()
    df['MA20'] = df['close'].rolling(window=20).mean()
    
    # RSI (相对强弱指数)
    delta = df['close'].diff()
    gain = (delta.where(delta > 0, 0)).rolling(window=14).mean()
    loss = (-delta.where(delta < 0, 0)).rolling(window=14).mean()
    rs = gain / loss
    df['RSI'] = 100 - (100 / (1 + rs))
    
    latest = df.iloc[-1]
    
    # 3. 生成“五金”购买建议
    rsi_val = latest['RSI']
    price = latest['close']
    ma20 = latest['MA20']
    
    trend_msg = "震荡"
    buy_score = 50 
    
    if price > ma20:
        trend_msg = "上升通道 (贵)"
        buy_score -= 10
    else:
        trend_msg = "下降/回调 (便宜)"
        buy_score += 10
        
    if rsi_val > 70:
        prediction = "严重超买，近期极大概率回调，千万别买！"
        buy_score = 10
        icon = "🛑"
    elif rsi_val > 60:
        prediction = "价格偏高，建议再等等"
        buy_score = 30
        icon = "✋"
    elif rsi_val < 30:
        prediction = "严重超卖，黄金坑出现，速去金店！"
        buy_score = 95
        icon = "🔥🔥"
    elif rsi_val < 45:
        prediction = "价格适中偏低，刚需可入"
        buy_score = 75
        icon = "🛒"
    else:
        prediction = "市场方向不明，按需购买"
        buy_score = 50
        icon = "⚖️"

    # 4. 绘图 (Matplotlib)
    img_base64 = None
    try:
        plt.style.use('ggplot') 
        fig, (ax1, ax2) = plt.subplots(2, 1, figsize=(8, 5), sharex=True, gridspec_kw={'height_ratios': [3, 1]})
        
        # 上图：价格 + 均线
        ax1.plot(df.index, df['close'], label='Price', color='#d4af37', linewidth=1.5)
        ax1.plot(df.index, df['MA5'], label='MA5', color='blue', alpha=0.3, linewidth=1)
        ax1.plot(df.index, df['MA20'], label='MA20', color='red', alpha=0.3, linewidth=1)
        ax1.set_title(f'Gold Price Trend (Last {len(df)} Days)', fontsize=10)
        ax1.legend(loc='upper left', fontsize='small')
        ax1.grid(True, alpha=0.3)
        
        # 下图：RSI
        ax2.plot(df.index, df['RSI'], label='RSI(14)', color='purple', linewidth=1)
        ax2.axhline(70, color='red', linestyle='--', alpha=0.5, linewidth=0.8)
        ax2.axhline(30, color='green', linestyle='--', alpha=0.5, linewidth=0.8)
        ax2.fill_between(df.index, df['RSI'], 70, where=(df['RSI'] >= 70), facecolor='red', alpha=0.3)
        ax2.fill_between(df.index, df['RSI'], 30, where=(df['RSI'] <= 30), facecolor='green', alpha=0.3)
        ax2.set_ylabel('RSI')
        ax2.grid(True, alpha=0.3)
        
        plt.gca().xaxis.set_major_formatter(mdates.DateFormatter('%m-%d'))
        plt.xticks(rotation=45)
        plt.tight_layout()
        
        buf = io.BytesIO()
        plt.savefig(buf, format='png', dpi=100)
        buf.seek(0)
        img_base64 = base64.b64encode(buf.read()).decode('utf-8')
        plt.close(fig)
    except Exception as e:
        print(f"绘图失败: {e}")

    return {
        "rsi": round(rsi_val, 2) if not pd.isna(rsi_val) else 50,
        "ma20": round(ma20, 2) if not pd.isna(ma20) else 0,
        "trend_msg": trend_msg,
        "prediction": prediction,
        "buy_score": buy_score,
        "icon": icon,
        "chart_img": img_base64
    }

# ---------- 数据源 ----------

def get_price_eastmoney_history(session: requests.Session) -> Optional[Dict[str, Any]]:
    """
    东方财富源 - 增强版
    """
    try:
        # lmt=120: 获取最近120天数据
        url = "https://push2his.eastmoney.com/api/qt/stock/kline/get?secid=119.Au9999&fields1=f1&fields2=f51,f52,f53,f54,f55&klt=101&fqt=1&lmt=120"
        
        # 发送请求，Retry 策略由 session 统一管理
        resp = session.get(url, headers=get_headers("https://quote.eastmoney.com/"), timeout=PER_REQUEST_TIMEOUT)
        resp.raise_for_status()
        data = resp.json()
        
        if data and data.get("data") and data["data"].get("klines"):
            klines = data["data"]["klines"]
            
            # 解析当期数据
            latest_k = klines[-1].split(',')
            current_price = float(latest_k[2])
            prev_k = klines[-2].split(',')
            prev_price = float(prev_k[2])
            
            change = current_price - prev_price
            change_pct = (change / prev_price) * 100
            
            # --- 进行高级分析 ---
            analysis = analyze_and_plot(klines)
            
            advice = analysis.get("prediction", "数据不足，建议观望")
            icon = analysis.get("icon", "🤔")
            pos_pct = analysis.get("buy_score", 50)
            
            return {
                "source": "东方财富 (含趋势分析)",
                "price": round(current_price, 2),
                "change": round(change, 2),
                "change_pct": round(change_pct, 2),
                "advice": advice,
                "advice_icon": icon,
                "pos_pct": pos_pct,
                "trend_analysis": analysis,
                "est_price": round(current_price + 25, 1),
                "bg_color": "#d9534f" if change > 0 else "#5cb85c"
            }
        else:
            print("⚠️ 东方财富接口返回数据结构异常或为空")
            
    except Exception as e:
        print(f"❌ 东方财富请求/分析失败: {e}")
    return None

# ---------- 推送函数 ----------
def send_pushplus(data: Dict[str, Any], token: Optional[str] = None, topic: Optional[str] = None):
    token = token or TOKEN
    topic = topic or TOPIC
    if not token:
        print("⚠️ 未配置 Token，仅打印结果：")
        print(json.dumps(data, ensure_ascii=False, indent=2))
        return

    date_str = datetime.datetime.now().strftime("%Y-%m-%d %H:%M")
    change_sign = "+" if data.get('change', 0) > 0 else ""
    
    # 构建分析部分的 HTML
    analysis_html = ""
    trend_data = data.get('trend_analysis', {})
    
    if trend_data:
        rsi_color = "red" if trend_data.get('rsi', 50) > 70 else "green" if trend_data.get('rsi', 50) < 30 else "#666"
        
        analysis_html = f"""
        <div style="background-color: #f0f8ff; margin-top: 15px; border-radius: 8px; padding: 12px; border: 1px solid #b8daff;">
            <div style="font-weight:bold; color:#004085; margin-bottom:8px;">📊 趋势智能分析</div>
            <div style="font-size:12px; color:#333; line-height:1.6;">
                当前趋势: <b>{trend_data.get('trend_msg')}</b><br>
                RSI 指标: <b style="color:{rsi_color}">{trend_data.get('rsi')}</b> (30以下适合买入)<br>
                20日均价: ¥{trend_data.get('ma20')}
            </div>
        </div>
        """
        
        if trend_data.get('chart_img'):
            analysis_html += f"""
            <div style="margin-top: 15px; text-align: center;">
                <img src="data:image/png;base64,{trend_data['chart_img']}" style="max-width: 100%; border-radius: 8px; border: 1px solid #ddd;" />
                <div style="font-size:10px; color:#999;">近120天金价走势与RSI指标</div>
            </div>
            """

    content = f"""
    <div style="font-family: -apple-system, sans-serif; max-width: 600px; margin: 0 auto;">
        <div style="background-color: {data.get('bg_color', '#333')}; border-radius: 12px; padding: 20px; color: #fff; text-align: center; box-shadow: 0 4px 6px rgba(0,0,0,0.1);">
            <div style="font-size: 14px; opacity: 0.9;">今日金价 (Au99.99)</div>
            <div style="font-size: 42px; font-weight: 800; margin: 10px 0;">{data['price']}</div>
            <div style="background: rgba(255,255,255,0.2); display: inline-block; padding: 4px 12px; border-radius: 20px; font-size: 14px;">
                {change_sign}{data['change']}元 ({change_sign}{data['change_pct']}%)
            </div>
        </div>

        <div style="margin-top: 15px; padding: 15px; background: #fff; border: 1px solid #eee; border-radius: 12px;">
            <div style="display: flex; align-items: center; justify-content: space-between; margin-bottom: 10px;">
                <span style="font-weight: bold; color: #333;">💡 购买建议</span>
                <span style="background: #eee; padding: 2px 8px; border-radius: 4px; font-size: 12px; color: #555;">五金备婚</span>
            </div>
            <div style="font-size: 16px; font-weight: bold; color: {data.get('bg_color', '#333')}; margin-bottom: 8px;">
                {data['advice_icon']} {data['advice']}
            </div>
            <div style="background: #e9ecef; height: 10px; border-radius: 5px; overflow: hidden; margin-top: 5px;">
                <div style="width: {data['pos_pct']}%; background: linear-gradient(90deg, #ffc107, #28a745); height: 100%;"></div>
            </div>
            <div style="text-align: right; font-size: 10px; color: #999; margin-top: 2px;">推荐入手指数: {data['pos_pct']}/100</div>

            {analysis_html}
            
            <div style="margin-top: 15px; padding-top: 10px; border-top: 1px dashed #eee; font-size: 13px; display: flex; justify-content: space-between;">
                <span style="color: #666;">预估实体店价(含工费)</span>
                <span style="font-weight: bold; color: #d39e00;">≈ ¥ {data['est_price']}</span>
            </div>
        </div>
        
        <div style="text-align: center; margin-top: 20px; color: #bbb; font-size: 12px;">
            更新时间: {date_str} <br> 数据来源: {data['source']}
        </div>
    </div>
    """

    payload = {
        "token": token,
        "title": f"{data.get('advice_icon','')} 金价: {data['price']} (推荐度:{data['pos_pct']})",
        "content": content,
        "template": "html",
        "topic": topic
    }

    try:
        # 推送接口也使用重试逻辑较好的 session
        requests.post("http://www.pushplus.plus/send", json=payload, headers=get_headers(), timeout=(3, 10))
        print("✅ 推送完成")
    except Exception as e:
        print("❌ 推送失败:", e)

# ---------- 主入口 ----------
def main():
    print("=== 金价趋势分析版启动 (Anti-Scraping Enhanced) ===")
    
    # 初始化 Session 并挂载重试策略
    # 这是规避网络不稳定和服务器临时限流（429/50x）的关键
    session = requests.Session()
    retry_strategy = Retry(
        total=MAX_RETRIES,
        backoff_factor=1,  # 重试等待时间: 1s, 2s, 4s...
        status_forcelist=[429, 500, 502, 503, 504],
        allowed_methods=["HEAD", "GET", "OPTIONS"]
    )
    adapter = HTTPAdapter(max_retries=retry_strategy)
    session.mount("https://", adapter)
    session.mount("http://", adapter)

    try:
        # 优先使用东方财富（因为有历史数据可做分析）
        result = get_price_eastmoney_history(session)
        
        if result:
            send_pushplus(result)
        else:
            print("❌ 获取数据失败，请检查日志。")
            
    except Exception as e:
        print(f"❌ 程序发生未捕获异常: {e}")
    finally:
        session.close()

if __name__ == "__main__":
    try:
        sys.stdout.reconfigure(encoding='utf-8')
    except Exception:
        pass
    main()
