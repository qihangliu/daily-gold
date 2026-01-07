#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
金价抓取 + 趋势分析 + 绘图推送 (GitHub Actions 深度优化版)
版本优化：修正 API 地址、增加非空校验、强化反爬、多源路由
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
MAX_RETRIES = 5
TIMEOUT = (10, 25)

USER_AGENTS = [
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/121.0.0.0 Safari/537.36",
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/119.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:122.0) Gecko/20100101 Firefox/122.0"
]

class GoldAnalytics:
    """深度趋势分析与绘图引擎"""
    
    @staticmethod
    def get_analysis(df: pd.DataFrame) -> Dict[str, Any]:
        """计算技术指标并生成购买建议"""
        if df.empty or len(df) < 20:
            return {"advice": "数据不足", "icon": "❓", "buy_score": 50, "chart_img": None, "trend_msg": "未知", "rsi": 50, "ma20": 0}

        # 计算 MA 和 RSI
        df['MA5'] = df['close'].rolling(window=5).mean()
        df['MA20'] = df['close'].rolling(window=20).mean()
        
        delta = df['close'].diff()
        gain = (delta.where(delta > 0, 0)).rolling(window=14).mean()
        loss = (-delta.where(delta < 0, 0)).rolling(window=14).mean()
        rs = gain / (loss + 1e-9)
        df['RSI'] = 100 - (100 / (1 + rs))

        latest = df.iloc[-1]
        rsi_val = round(float(latest['RSI']), 2) if not pd.isna(latest['RSI']) else 50
        price = float(latest['close'])
        ma20 = round(float(latest['MA20']), 2) if not pd.isna(latest['MA20']) else price

        # 智能决策逻辑
        buy_score = 50
        if price < ma20: buy_score += 15
        else: buy_score -= 10
        
        if rsi_val < 30:
            advice, icon, buy_score = "严重超卖，黄金坑出现，建议分批入场！", "🔥🔥", 95
        elif rsi_val < 45:
            advice, icon, buy_score = "价格适中偏低，刚需可轻仓关注", "🛒", 75
        elif rsi_val > 75:
            advice, icon, buy_score = "严重超买，近期风险极大，切勿追高！", "🛑", 10
        elif rsi_val > 65:
            advice, icon, buy_score = "价格处于高位，建议持金观望", "✋", 30
        else:
            advice, icon, buy_score = "震荡区间，建议按需小量操作", "⚖️", 50

        img_base64 = GoldAnalytics._generate_chart(df)
        
        return {
            "rsi": rsi_val,
            "ma20": ma20,
            "advice": advice,
            "icon": icon,
            "buy_score": buy_score,
            "chart_img": img_base64,
            "trend_msg": "多头排列" if price > ma20 else "空头回调"
        }

    @staticmethod
    def _generate_chart(df: pd.DataFrame) -> Optional[str]:
        if not HAS_ANALYSIS_LIBS: return None
        try:
            plt.style.use('bmh')
            fig, (ax1, ax2) = plt.subplots(2, 1, figsize=(10, 7), sharex=True, gridspec_kw={'height_ratios': [3, 1]})
            
            # 价格图
            ax1.plot(df.index, df['close'], label='Price', color='#d4af37', linewidth=2.5)
            ax1.plot(df.index, df['MA20'], label='MA20', color='#3498db', linestyle='--', alpha=0.8)
            ax1.set_title(f"Gold Price Trend Analysis (Last {len(df)} Days)", fontsize=14, fontweight='bold')
            ax1.legend(loc='upper left')
            ax1.grid(True, alpha=0.2)

            # RSI 图
            ax2.plot(df.index, df['RSI'], label='RSI(14)', color='#9b59b6', linewidth=1.5)
            ax2.axhline(70, color='#e74c3c', linestyle=':', alpha=0.6)
            ax2.axhline(30, color='#2ecc71', linestyle=':', alpha=0.6)
            ax2.fill_between(df.index, 30, 70, color='#9b59b6', alpha=0.05)
            ax2.set_ylabel('RSI')
            ax2.set_ylim(0, 100)
            
            plt.gca().xaxis.set_major_formatter(mdates.DateFormatter('%m-%d'))
            plt.xticks(rotation=45)
            plt.tight_layout()

            buf = io.BytesIO()
            plt.savefig(buf, format='png', dpi=110)
            return base64.b64encode(buf.getvalue()).decode('utf-8')
        except Exception as e:
            print(f"⚠️ 绘图失败: {e}")
            return None

class GoldTracker:
    def __init__(self):
        self.session = self._init_session()

    def _init_session(self):
        s = requests.Session()
        # 增加重试次数和 backoff 因子，应对 GitHub Actions IP 限制
        retries = Retry(total=MAX_RETRIES, backoff_factor=2, status_forcelist=[403, 429, 500, 502, 503, 504])
        s.mount("https://", HTTPAdapter(max_retries=retries))
        return s

    def _get_headers(self, referer: str) -> Dict[str, str]:
        """深度伪装 Headers"""
        return {
            "User-Agent": random.choice(USER_AGENTS),
            "Accept": "application/json, text/javascript, */*; q=0.01",
            "Accept-Language": "zh-CN,zh;q=0.9,en-GB;q=0.8,en;q=0.7",
            "Referer": referer,
            "DNT": "1",
            "Sec-Fetch-Dest": "empty",
            "Sec-Fetch-Mode": "cors",
            "Sec-Fetch-Site": "same-site",
            "Connection": "keep-alive"
        }

    def fetch_eastmoney(self) -> Optional[Dict]:
        """源1：东方财富修正版 API"""
        print("🚀 尝试连接东方财富 (Au9999)...")
        try:
            # 修正后的字段和 secid
            url = "https://push2his.eastmoney.com/api/qt/stock/kline/get?secid=119.Au9999&fields1=f1,f2,f3,f4,f5,f6&fields2=f51,f52,f53,f54,f55&klt=101&fqt=1&lmt=100"
            resp = self.session.get(url, headers=self._get_headers("https://quote.eastmoney.com/shau9999.html"), timeout=TIMEOUT)
            res_json = resp.json()
            
            # 增加严密的非空校验，防止 'NoneType' 报错
            if not res_json or 'data' not in res_json or res_json['data'] is None:
                print("⚠️ 东方财富接口返回空数据或被限流")
                return None
            
            klines_raw = res_json['data'].get('klines', [])
            if not klines_raw:
                return None

            klines = []
            for k in klines_raw:
                p = k.split(',')
                klines.append({"date": p[0], "close": float(p[2])})
            
            df = pd.DataFrame(klines)
            df['date'] = pd.to_datetime(df['date'])
            df.set_index('date', inplace=True)
            
            analysis = GoldAnalytics.get_analysis(df)
            curr = klines[-1]['close']
            prev = klines[-2]['close']
            
            return {
                "price": curr,
                "change": round(curr - prev, 2),
                "change_pct": round((curr - prev) / prev * 100, 2),
                "est_price": round(curr + 22, 1), # 国内工费预估
                "source": "东方财富 (Au9999)",
                "analysis": analysis
            }
        except Exception as e:
            print(f"⚠️ 东方财富请求失败: {e}")
        return None

    def fetch_yahoo(self) -> Optional[Dict]:
        """源2：Yahoo Finance 替代方案 (GC=F 期货)"""
        print("🚀 尝试连接 Yahoo Finance (GC=F)...")
        try:
            import yfinance as yf
            # XAUUSD=X 经常 404，改用 GC=F (黄金期货)
            ticker = yf.Ticker("GC=F")
            hist = ticker.history(period="100d", interval="1d")
            
            if hist.empty:
                print("⚠️ Yahoo Finance 返回空历史记录")
                return None
            
            df = hist[['Close']].rename(columns={'Close': 'close'})
            analysis = GoldAnalytics.get_analysis(df)
            
            curr = round(float(df['close'].iloc[-1]), 2)
            prev = round(float(df['close'].iloc[-2]), 2)
            
            return {
                "price": curr,
                "change": round(curr - prev, 2),
                "change_pct": round((curr - prev) / prev * 100, 2),
                "est_price": round(curr * 7.15 + 25, 1), # 国际转国内预估价
                "source": "Yahoo (Gold Futures)",
                "analysis": analysis
            }
        except Exception as e:
            print(f"⚠️ Yahoo 源请求失败: {e}")
        return None

    def push(self, data: Dict):
        """高级 HTML 推送模板"""
        if not PUSHPLUS_TOKEN:
            print(f"💰 结果: {data['price']} | 建议: {data['analysis']['advice']}")
            return

        an = data['analysis']
        # 颜色动态判断
        main_color = "#e74c3c" if data['change'] > 0 else "#2ecc71"
        score_color = "#f39c12" if an['buy_score'] > 70 else "#95a5a6"
        
        content = f"""
        <div style="font-family: 'Helvetica Neue', Arial, sans-serif; max-width: 550px; margin: 0 auto; background: #fdfdfd; padding: 10px;">
            <div style="background: linear-gradient(135deg, {main_color} 0%, #2c3e50 100%); border-radius: 15px; padding: 25px; color: white; text-align: center; box-shadow: 0 10px 20px rgba(0,0,0,0.15);">
                <div style="font-size: 13px; text-transform: uppercase; letter-spacing: 2px; opacity: 0.8;">{data['source']}</div>
                <div style="font-size: 52px; font-weight: 900; margin: 10px 0;">{data['price']}</div>
                <div style="background: rgba(255,255,255,0.15); display: inline-block; padding: 5px 15px; border-radius: 30px; font-size: 16px;">
                    {"+" if data['change'] > 0 else ""}{data['change']} ({data['change_pct']}%)
                </div>
            </div>

            <div style="margin-top: -20px; background: white; border-radius: 15px; padding: 20px; box-shadow: 0 5px 15px rgba(0,0,0,0.05); border: 1px solid #eee;">
                <div style="display: flex; justify-content: space-between; align-items: center; border-bottom: 1px solid #f5f5f5; padding-bottom: 10px; margin-bottom: 15px;">
                    <span style="font-weight: bold; color: #333;">📊 深度行情研判</span>
                    <span style="font-size: 11px; color: #999; background: #f5f5f5; padding: 2px 8px; border-radius: 5px;">AI 智能分析</span>
                </div>
                
                <div style="font-size: 20px; font-weight: bold; color: {main_color}; margin-bottom: 15px; text-align: center;">
                    {an['icon']} {an['advice']}
                </div>

                <div style="background: #f8f9fa; border-radius: 10px; padding: 15px; margin-bottom: 15px;">
                    <div style="display: flex; justify-content: space-between; margin-bottom: 8px; font-size: 13px;">
                        <span>买入推荐指数</span>
                        <span style="font-weight: bold; color: {score_color};">{an['buy_score']}/100</span>
                    </div>
                    <div style="background: #e9ecef; height: 10px; border-radius: 5px; overflow: hidden;">
                        <div style="width: {an['buy_score']}%; background: linear-gradient(90deg, #f1c40f, #2ecc71); height: 100%;"></div>
                    </div>
                </div>

                <div style="display: grid; grid-template-columns: 1fr 1fr; gap: 10px; margin-bottom: 15px;">
                    <div style="border: 1px solid #edf2f7; padding: 10px; border-radius: 8px; text-align: center;">
                        <div style="font-size: 11px; color: #718096; margin-bottom: 4px;">RSI (14)</div>
                        <div style="font-weight: bold; color: #2d3748;">{an['rsi']}</div>
                    </div>
                    <div style="border: 1px solid #edf2f7; padding: 10px; border-radius: 8px; text-align: center;">
                        <div style="font-size: 11px; color: #718096; margin-bottom: 4px;">MA20 支撑</div>
                        <div style="font-weight: bold; color: #2d3748;">{an['ma20']}</div>
                    </div>
                </div>

                {f'<div style="text-align: center;"><img src="data:image/png;base64,{an["chart_img"]}" style="width:100%; border-radius:10px; box-shadow: 0 4px 8px rgba(0,0,0,0.05);"/></div>' if an['chart_img'] else ''}

                <div style="margin-top: 20px; padding-top: 15px; border-top: 1px dashed #e2e8f0; display: flex; justify-content: space-between; align-items: center;">
                    <div style="font-size: 13px; color: #4a5568;">🛍️ 预估门店金价 (含工费)</div>
                    <div style="font-size: 18px; font-weight: bold; color: #b7791f;">¥ {data['est_price']}</div>
                </div>
            </div>

            <div style="text-align: center; margin-top: 15px; color: #cbd5e0; font-size: 10px; letter-spacing: 1px;">
                UPDATE: {datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')}
            </div>
        </div>
        """

        payload = {
            "token": PUSHPLUS_TOKEN,
            "title": f"{an['icon']} 金价预警: {data['price']} ({an['trend_msg']})",
            "content": content,
            "template": "html",
            "topic": PUSHPLUS_TOPIC
        }
        
        try:
            r = self.session.post("http://www.pushplus.plus/send", json=payload, timeout=TIMEOUT)
            print(f"✅ 推送结果: {r.status_code}")
        except Exception as e:
            print(f"❌ 推送失败: {e}")

    def run(self):
        print("--- Gold Tracker Enhanced Starting ---")
        # 尝试国内源
        result = self.fetch_eastmoney()
        
        # 国内源失败则尝试国际源
        if not result:
            print("🔄 切换至备份源...")
            result = self.fetch_yahoo()
            
        if result:
            self.push(result)
        else:
            print("🚨 致命错误：所有数据源均无法访问，任务终止")

if __name__ == "__main__":
    GoldTracker().run()