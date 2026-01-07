#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
金价抓取 + 趋势分析 + 绘图推送 (GitHub Actions 增强版)
功能：双源备份（东方财富 + Yahoo Finance），支持 RSI/MA 分析及 HTML 图文推送
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

import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

# 核心分析库
try:
    import pandas as pd
    import matplotlib
    matplotlib.use('Agg') # 必须在无头环境下运行
    import matplotlib.pyplot as plt
    import matplotlib.dates as mdates
    import yfinance as yf
    HAS_LIBS = True
except ImportError as e:
    print(f"❌ 缺少必要库: {e}")
    HAS_LIBS = False

# ---------- 配置 ----------
TOPIC = os.environ.get("PUSHPLUS_TOPIC", "20251206")
TOKEN = os.environ.get("PUSHPLUS_TOKEN")
PER_REQUEST_TIMEOUT = (10, 30)

USER_AGENTS = [
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
]

def get_headers(referer: Optional[str] = None) -> Dict[str, str]:
    h = {"User-Agent": random.choice(USER_AGENTS), "Accept": "*/*"}
    if referer: h["Referer"] = referer
    return h

# ---------- 趋势分析与绘图 ----------

def analyze_and_plot(df: pd.DataFrame) -> Dict[str, Any]:
    """
    计算指标并绘图。输入 df 必须包含 'close' 列，索引为 DatetimeIndex
    """
    if df.empty: return {}
    
    # 计算指标
    df['MA5'] = df['close'].rolling(window=5).mean()
    df['MA20'] = df['close'].rolling(window=20).mean()
    
    delta = df['close'].diff()
    gain = (delta.where(delta > 0, 0)).rolling(window=14).mean()
    loss = (-delta.where(delta < 0, 0)).rolling(window=14).mean()
    rs = gain / loss
    df['RSI'] = 100 - (100 / (1 + rs))
    
    latest = df.iloc[-1]
    rsi_val = latest['RSI']
    price = latest['close']
    ma20 = latest['MA20']
    
    # 策略判断
    buy_score = 50
    if price < ma20: buy_score += 15
    else: buy_score -= 10
    
    if rsi_val > 70:
        prediction, icon, buy_score = "超买严重，谨防回调", "🛑", 10
    elif rsi_val < 35:
        prediction, icon, buy_score = "进入低位，建议分批入场", "🔥", 90
    elif rsi_val < 45:
        prediction, icon, buy_score = "价格适中，按需选购", "🛒", 70
    else:
        prediction, icon, buy_score = "波动区间，建议观望", "⚖️", 50

    # 绘图 (英文 Label 避免 Actions 环境下中文乱码)
    img_base64 = None
    try:
        plt.style.use('ggplot')
        fig, (ax1, ax2) = plt.subplots(2, 1, figsize=(9, 6), sharex=True, gridspec_kw={'height_ratios': [3, 1]})
        
        ax1.plot(df.index, df['close'], label='Price(CNY/g)', color='#d4af37', linewidth=2)
        ax1.plot(df.index, df['MA20'], label='MA20', color='red', linestyle='--', alpha=0.6)
        ax1.set_title('Gold Price Trend (Recent 120 Days)')
        ax1.legend()
        
        ax2.plot(df.index, df['RSI'], label='RSI(14)', color='purple')
        ax2.axhline(70, color='red', alpha=0.3)
        ax2.axhline(30, color='green', alpha=0.3)
        ax2.set_ylim(0, 100)
        
        plt.gca().xaxis.set_major_formatter(mdates.DateFormatter('%m-%d'))
        plt.xticks(rotation=45)
        plt.tight_layout()
        
        buf = io.BytesIO()
        plt.savefig(buf, format='png', dpi=120)
        img_base64 = base64.b64encode(buf.getvalue()).decode('utf-8')
        plt.close(fig)
    except Exception as e:
        print(f"⚠️ 绘图异常: {e}")

    return {
        "rsi": round(rsi_val, 2) if not pd.isna(rsi_val) else 50,
        "ma20": round(ma20, 2),
        "prediction": prediction,
        "buy_score": buy_score,
        "icon": icon,
        "chart_img": img_base64
    }

# ---------- 数据源 1: 东方财富 ----------

def get_price_eastmoney(session: requests.Session) -> Optional[Dict[str, Any]]:
    try:
        url = "https://push2his.eastmoney.com/api/qt/stock/kline/get?secid=119.Au9999&fields1=f1&fields2=f51,f52,f53,f54,f55&klt=101&fqt=1&lmt=120"
        resp = session.get(url, headers=get_headers("https://quote.eastmoney.com/"), timeout=PER_REQUEST_TIMEOUT)
        data = resp.json()
        klines = data.get("data", {}).get("klines", [])
        if not klines: return None
        
        data_list = []
        for k in klines:
            p = k.split(',')
            data_list.append({"date": p[0], "close": float(p[2])})
        
        df = pd.DataFrame(data_list)
        df['date'] = pd.to_datetime(df['date'])
        df.set_index('date', inplace=True)
        
        analysis = analyze_and_plot(df)
        curr = df.iloc[-1]['close']
        prev = df.iloc[-2]['close']
        
        return {
            "source": "东方财富",
            "price": round(curr, 2),
            "change": round(curr - prev, 2),
            "change_pct": round((curr - prev) / prev * 100, 2),
            "analysis": analysis
        }
    except Exception as e:
        print(f"⚠️ 东方财富解析失败: {e}")
        return None

# ---------- 数据源 2: Yahoo Finance (海外环境最稳) ----------

def get_price_yahoo_intl() -> Optional[Dict[str, Any]]:
    try:
        print("🌐 正在连接 Yahoo Finance 国际源...")
        # 抓取伦敦金 (XAU/USD)
        gold = yf.Ticker("XAUUSD=X")
        g_hist = gold.history(period="125d")
        
        # 抓取汇率 (USD/CNY)
        rate_ticker = yf.Ticker("USDCNY=X")
        r_hist = rate_ticker.history(period="1d")
        usd_cny = r_hist['Close'].iloc[-1]
        
        if g_hist.empty: return None
        
        # 换算: (美金/盎司) / 31.1035 * 汇率 = 人民币/克
        df = pd.DataFrame()
        df['close'] = (g_hist['Close'] / 31.1034768) * usd_cny
        df.index = g_hist.index
        
        analysis = analyze_and_plot(df)
        curr = df['close'].iloc[-1]
        prev = df['close'].iloc[-2]
        
        return {
            "source": f"Yahoo Finance (汇率:{round(usd_cny, 2)})",
            "price": round(curr, 2),
            "change": round(curr - prev, 2),
            "change_pct": round((curr - prev) / prev * 100, 2),
            "analysis": analysis
        }
    except Exception as e:
        print(f"❌ Yahoo Finance 获取失败: {e}")
        return None

# ---------- 推送与主逻辑 ----------

def send_pushplus(data: Dict[str, Any]):
    if not TOKEN:
        print("💡 结果：", data['price'], data['analysis']['prediction'])
        return

    ana = data['analysis']
    bg_color = "#d9534f" if data['change'] > 0 else "#5cb85c"
    
    img_html = f'<div style="text-align:center;"><img src="data:image/png;base64,{ana["chart_img"]}" style="max-width:100%; border-radius:8px;"/></div>' if ana.get("chart_img") else ""

    content = f"""
    <div style="font-family:sans-serif; max-width:500px; border:1px solid #eee; border-radius:12px; overflow:hidden;">
        <div style="background:{bg_color}; color:white; padding:20px; text-align:center;">
            <div style="font-size:14px; opacity:0.8;">Au99.99 实时估价</div>
            <div style="font-size:40px; font-weight:bold;">¥{data['price']}</div>
            <div>{data['change']} ({data['change_pct']}%)</div>
        </div>
        <div style="padding:15px;">
            <div style="font-size:18px; font-weight:bold; color:#333;">{ana['icon']} {ana['prediction']}</div>
            <div style="margin:10px 0; background:#eee; height:8px; border-radius:4px;">
                <div style="width:{ana['buy_score']}%; background:linear-gradient(90deg, #ffc107, #28a745); height:100%; border-radius:4px;"></div>
            </div>
            <div style="font-size:12px; color:#666;">
                RSI: {ana['rsi']} | 20日均价: {ana['ma20']} <br>
                建议入手指数: {ana['buy_score']}/100
            </div>
            {img_html}
            <div style="margin-top:10px; font-size:11px; color:#bbb; text-align:center;">
                来源: {data['source']} | 时间: {datetime.datetime.now().strftime('%Y-%m-%d %H:%M')}
            </div>
        </div>
    </div>
    """
    
    payload = {
        "token": TOKEN,
        "title": f"{ana['icon']} 金价:{data['price']} ({ana['prediction']})",
        "content": content,
        "template": "html",
        "topic": TOPIC
    }
    requests.post("http://www.pushplus.plus/send", json=payload, timeout=20)
    print("✅ 推送已尝试发送")

def main():
    if not HAS_LIBS: return
    
    session = requests.Session()
    adapter = HTTPAdapter(max_retries=Retry(total=3, backoff_factor=1))
    session.mount("https://", adapter)
    
    # 策略：GitHub Actions 下优先尝试 Yahoo Finance
    # 或者先试国内源，不行立刻切国际源
    print("--- 启动金价监控 (GitHub Actions 优化版) ---")
    result = get_price_eastmoney(session)
    
    if not result:
        print("⚠️ 国内源失效，正在切换国际源备份...")
        result = get_price_yahoo_intl()
        
    if result:
        send_pushplus(result)
    else:
        print("❌ 抓取失败：所有数据源均无法访问")
                                        
if __name__ == "__main__":
    main()
