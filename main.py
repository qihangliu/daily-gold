#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
金价抓取 + 趋势分析 + 绘图推送 (GitHub Actions 深度优化版)
融合优点：增强反爬、精美 HTML 模板、多源容灾、趋势智能判断
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

# 环境配置加载
try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass

import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

# 数据分析库
try:
    import pandas as pd
    import matplotlib
    matplotlib.use('Agg')  
    import matplotlib.pyplot as plt
    import matplotlib.dates as mdates
    HAS_ANALYSIS_LIBS = True
except ImportError:
    HAS_ANALYSIS_LIBS = False

# ---------- 全局配置 ----------
PUSHPLUS_TOKEN = os.environ.get("PUSHPLUS_TOKEN")
PUSHPLUS_TOPIC = os.environ.get("PUSHPLUS_TOPIC", "daily_gold")
MAX_RETRIES = 3
TIMEOUT = (5, 15)

USER_AGENTS = [
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/119.0.0.0 Safari/537.36"
]

class GoldAnalytics:
    """深度趋势分析与绘图引擎"""
    
    @staticmethod
    def get_analysis(df: pd.DataFrame) -> Dict[str, Any]:
        """计算技术指标并生成购买建议"""
        # 计算 MA 和 RSI
        df['MA5'] = df['close'].rolling(window=5).mean()
        df['MA20'] = df['close'].rolling(window=20).mean()
        
        delta = df['close'].diff()
        gain = (delta.where(delta > 0, 0)).rolling(window=14).mean()
        loss = (-delta.where(delta < 0, 0)).rolling(window=14).mean()
        rs = gain / (loss + 1e-9)
        df['RSI'] = 100 - (100 / (1 + rs))

        latest = df.iloc[-1]
        rsi_val = round(latest['RSI'], 2)
        price = latest['close']
        ma20 = latest['MA20']

        # 智能决策逻辑 (参考了你的建议)
        buy_score = 50
        if price < ma20: buy_score += 15
        else: buy_score -= 10
        
        if rsi_val < 30:
            advice, icon, buy_score = "严重超卖，黄金坑出现，速去金店！", "🔥🔥", 95
        elif rsi_val < 45:
            advice, icon, buy_score = "价格适中偏低，刚需可入手", "🛒", 75
        elif rsi_val > 70:
            advice, icon, buy_score = "严重超买，近期概率回调，别买！", "🛑", 10
        elif rsi_val > 60:
            advice, icon, buy_score = "价格偏高，建议再等一等", "✋", 30
        else:
            advice, icon, buy_score = "市场方向不明，按需购买", "⚖️", 50

        # 绘图 Base64
        img_base64 = GoldAnalytics._generate_chart(df)
        
        return {
            "rsi": rsi_val,
            "ma20": round(ma20, 2),
            "advice": advice,
            "icon": icon,
            "buy_score": buy_score,
            "chart_img": img_base64,
            "trend_msg": "上升通道" if price > ma20 else "回调区间"
        }

    @staticmethod
    def _generate_chart(df: pd.DataFrame) -> Optional[str]:
        try:
            plt.style.use('ggplot')
            fig, (ax1, ax2) = plt.subplots(2, 1, figsize=(9, 6), sharex=True, gridspec_kw={'height_ratios': [3, 1]})
            
            # 价格图
            ax1.plot(df.index, df['close'], label='Price', color='#d4af37', linewidth=2)
            ax1.plot(df.index, df['MA20'], label='MA20', color='#e74c3c', linestyle='--', alpha=0.6)
            ax1.set_title(f"Gold Price Trend (Last {len(df)} Days)", fontsize=12, fontweight='bold')
            ax1.legend(loc='upper left')
            ax1.grid(True, alpha=0.3)

            # RSI 图
            ax2.plot(df.index, df['RSI'], label='RSI(14)', color='#9b59b6', linewidth=1)
            ax2.axhline(70, color='#e74c3c', linestyle=':', alpha=0.5)
            ax2.axhline(30, color='#2ecc71', linestyle=':', alpha=0.5)
            ax2.fill_between(df.index, df['RSI'], 70, where=(df['RSI'] >= 70), facecolor='#e74c3c', alpha=0.2)
            ax2.fill_between(df.index, df['RSI'], 30, where=(df['RSI'] <= 30), facecolor='#2ecc71', alpha=0.2)
            ax2.set_ylabel('RSI')
            
            plt.gca().xaxis.set_major_formatter(mdates.DateFormatter('%m-%d'))
            plt.xticks(rotation=45)
            plt.tight_layout()

            buf = io.BytesIO()
            plt.savefig(buf, format='png', dpi=100)
            return base64.b64encode(buf.getvalue()).decode('utf-8')
        except Exception as e:
            print(f"⚠️ 绘图失败: {e}")
            return None

class GoldTracker:
    def __init__(self):
        self.session = self._init_session()

    def _init_session(self):
        s = requests.Session()
        retries = Retry(total=MAX_RETRIES, backoff_factor=1, status_forcelist=[429, 500, 502, 503, 504])
        s.mount("https://", HTTPAdapter(max_retries=retries))
        return s

    def _get_headers(self, referer: str) -> Dict[str, str]:
        """融合参考脚本的深度伪装头部"""
        return {
            "User-Agent": random.choice(USER_AGENTS),
            "Accept": "application/json, text/javascript, */*; q=0.01",
            "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
            "Referer": referer,
            "DNT": "1",
            "Sec-Fetch-Dest": "empty",
            "Sec-Fetch-Mode": "cors",
            "Sec-Fetch-Site": "same-site",
            "Cache-Control": "no-cache"
        }

    def fetch_data(self) -> Optional[Dict]:
        """多源容灾抓取"""
        # 源1：东方财富 (国内实物金首选)
        print("🚀 尝试抓取东方财富源...")
        try:
            url = "https://push2his.eastmoney.com/api/qt/stock/kline/get?secid=119.Au9999&fields1=f1&fields2=f51,f52,f53,f54,f55&klt=101&fqt=1&lmt=100"
            resp = self.session.get(url, headers=self._get_headers("https://quote.eastmoney.com/"), timeout=TIMEOUT)
            data = resp.json()
            if data and data.get("data"):
                klines = []
                for k in data['data']['klines']:
                    p = k.split(',')
                    klines.append({"date": p[0], "close": float(p[2])})
                
                df = pd.DataFrame(klines).set_index(pd.to_datetime([x['date'] for x in klines]))
                analysis = GoldAnalytics.get_analysis(df)
                
                curr = klines[-1]['close']
                prev = klines[-2]['close']
                return {
                    "price": curr,
                    "change": round(curr - prev, 2),
                    "change_pct": round((curr - prev) / prev * 100, 2),
                    "est_price": round(curr + 25, 1), # 预估实体店价
                    "source": "东方财富 (Au9999)",
                    "analysis": analysis
                }
        except Exception as e:
            print(f"⚠️ 东方财富解析失败: {e}")

        # 源2：Yahoo Finance (作为备份)
        print("🚀 尝试抓取国际源备份 (Yahoo)...")
        try:
            import yfinance as yf
            ticker = yf.Ticker("GC=F")
            hist = ticker.history(period="100d")
            if not hist.empty:
                df = hist[['Close']].rename(columns={'Close': 'close'})
                analysis = GoldAnalytics.get_analysis(df)
                curr = round(df['close'].iloc[-1], 2)
                prev = round(df['close'].iloc[-2], 2)
                return {
                    "price": curr,
                    "change": round(curr - prev, 2),
                    "change_pct": round((curr - prev) / prev * 100, 2),
                    "est_price": round(curr * 7.2 + 30, 1), # 粗略估算国内价
                    "source": "Yahoo Finance (GC=F)",
                    "analysis": analysis
                }
        except Exception as e:
            print(f"❌ 所有数据源均失效: {e}")
        return None

    def push(self, data: Dict):
        """融合参考脚本的精美 HTML 模板"""
        if not PUSHPLUS_TOKEN:
            print(f"📢 结果: {data['price']} ({data['analysis']['advice']})")
            return

        an = data['analysis']
        bg_color = "#d9534f" if data['change'] > 0 else "#5cb85c"
        rsi_color = "#e74c3c" if an['rsi'] > 70 else "#2ecc71" if an['rsi'] < 30 else "#3498db"
        
        content = f"""
        <div style="font-family: -apple-system, sans-serif; max-width: 600px; margin: 0 auto; background-color: #f9f9f9; padding: 15px; border-radius: 16px;">
            <!-- 头部卡片 -->
            <div style="background: linear-gradient(135deg, {bg_color}, #333); border-radius: 12px; padding: 25px; color: #fff; text-align: center; box-shadow: 0 4px 15px rgba(0,0,0,0.1);">
                <div style="font-size: 14px; opacity: 0.9;">今日金价 ({data['source']})</div>
                <div style="font-size: 48px; font-weight: 800; margin: 10px 0;">{data['price']}</div>
                <div style="background: rgba(255,255,255,0.2); display: inline-block; padding: 4px 15px; border-radius: 20px; font-size: 15px;">
                    {"📈" if data['change'] > 0 else "📉"} {data['change']}元 ({data['change_pct']}%)
                </div>
            </div>

            <!-- 分析卡片 -->
            <div style="margin-top: 20px; padding: 20px; background: #fff; border-radius: 12px; box-shadow: 0 2px 10px rgba(0,0,0,0.05);">
                <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 15px;">
                    <span style="font-weight: bold; color: #333; font-size: 16px;">💡 智能购买建议</span>
                    <span style="background: #fff3cd; color: #856404; padding: 2px 10px; border-radius: 6px; font-size: 12px;">五金备婚参考</span>
                </div>
                
                <div style="font-size: 18px; font-weight: bold; color: {bg_color}; margin-bottom: 12px;">
                    {an['icon']} {an['advice']}
                </div>

                <!-- 进度条 -->
                <div style="background: #eee; height: 12px; border-radius: 6px; overflow: hidden; margin: 15px 0 5px 0;">
                    <div style="width: {an['buy_score']}%; background: linear-gradient(90deg, #f1c40f, #2ecc71); height: 100%;"></div>
                </div>
                <div style="text-align: right; font-size: 11px; color: #999;">推荐入手指数: {an['buy_score']}/100</div>

                <!-- 指标详情 -->
                <div style="margin-top: 15px; background: #f0f7ff; padding: 12px; border-radius: 8px; border: 1px solid #d1e7ff; font-size: 13px; color: #444; line-height: 1.6;">
                    • 当前趋势: <b>{an['trend_msg']}</b><br>
                    • RSI 指标: <b style="color:{rsi_color}">{an['rsi']}</b> (30以下适合买入)<br>
                    • 20日均价: <b>¥{an['ma20']}</b>
                </div>

                {f'<div style="margin-top:15px;"><img src="data:image/png;base64,{an["chart_img"]}" style="width:100%; border-radius:8px; border:1px solid #eee;"/></div>' if an['chart_img'] else ''}

                <div style="margin-top: 15px; padding-top: 12px; border-top: 1px dashed #eee; font-size: 14px; display: flex; justify-content: space-between;">
                    <span style="color: #666;">预估实体店价 (含工费)</span>
                    <span style="font-weight: bold; color: #d39e00;">≈ ¥ {data['est_price']}</span>
                </div>
            </div>

            <div style="text-align: center; margin-top: 20px; color: #bbb; font-size: 11px;">
                Update: {datetime.datetime.now().strftime('%Y-%m-%d %H:%M')} <br>
                Powered by UV & GitHub Actions
            </div>
        </div>
        """
        
        payload = {
            "token": PUSHPLUS_TOKEN,
            "title": f"{an['icon']} 金价分析: {data['price']} (得分:{an['buy_score']})",
            "content": content,
            "template": "html",
            "topic": PUSHPLUS_TOPIC
        }
        
        try:
            self.session.post("http://www.pushplus.plus/send", json=payload, timeout=TIMEOUT)
            print("✅ 精美推送已发出")
        except Exception as e:
            print(f"❌ 推送失败: {e}")

    def run(self):
        print("=== Gold Tracker Pro 启动 ===")
        data = self.fetch_data()
        if data:
            self.push(data)
        else:
            print("🚨 任务失败：无法获取任何有效金价数据")

if __name__ == "__main__":
    GoldTracker().run()