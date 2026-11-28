#!/usr/bin/env python3
"""
台指期當沖：用「日內位階」決定多空（使用者想法）
  位階＝(現價 − 當天最低) ÷ (當天最高 − 當天最低)；09:15 規則判 BO 日：位階穿越 ≥ 門檻做多、≤ 1−門檻做空；MR 日相反
  停損 0.3×ATR20、停利 0.6×ATR20、一次一口（同 research_tx_scalp.py）；和原本「開盤區間」訊號比較
結果（2026/11）：位階版 7 年中 3～4 年虧（原本開盤區間版 0 年）；合併也沒有加分 → 不採用
用法：python scripts/research_tx_pos.py
"""
import sys,json,statistics as st,random
from collections import defaultdict
sys.path.insert(0, __import__('os').path.dirname(__file__))
import research_tx_scalp as sc, research_tx_regime as rr, tx_regime_review as trv
day=rr.load_dir(rr.DATA/'futures'/'day');reg={r['date']:r for r in json.load(open('data/futures/regime_rows.json'))}
p=trv.params()['current'];dates=sorted(d for d,b in day.items() if len(b)>=250)
rng={d:max(x[1] for x in day[d].values())-min(x[2] for x in day[d].values()) for d in dates}
A={};PL={}
for i,d in enumerate(dates):
    if i<20 or d not in reg: continue
    A[d]=st.mean(rng[x] for x in dates[i-20:i]);PL[d]=trv.decide(reg[d],p)[1]
def pos_sig(bars,plan,th,atr,minr):
    """位階穿越門檻才觸發（進入高位階區或低位階區那一分鐘）"""
    out={};hi=lo=None;prev=None
    for m in sorted(bars):
        if m>sc.LAST_ENTRY: break
        o,h,l,c=bars[m][:4]
        hi=h if hi is None else max(hi,h);lo=l if lo is None else min(lo,l)
        if m<sc.OR_M or hi-lo<minr*atr: prev=None if hi==lo else (c-lo)/(hi-lo);continue
        ps=(c-lo)/(hi-lo)
        if prev is not None:
            d=0
            if ps>=th and prev<th: d=1
            elif ps<=1-th and prev>1-th: d=-1
            if d:
                if plan=='BO': out[m]=d
                elif plan=='MR': out[m]=-d
                elif plan=='ALLBO': out[m]=d
                elif plan=='ALLMR': out[m]=-d
        prev=ps
    return out
P=(('2020-22','2020','2023'),('2023-24','2023','2025'),('2025+','2025','2100'))
def run(name,mk,sl):
    yr=defaultdict(list);tr=[]
    for d in A:
        s=mk(d);t=sc.run_day(day[d],s,sl*A[d]);yr[d[:4]].append(sum(t));tr+=t
    neg=sum(st.mean(v)<0 for v in yr.values())
    print(f"{name} 停損 {sl}×ATR：勝率 {sum(x>0 for x in tr)/max(1,len(tr))*100:.0f}%、{len(tr)/len(A):.1f} 筆/天｜"+'、'.join(f"{y} {st.mean(v):+.1f}" for y,v in sorted(yr.items()))+f"｜虧錢年份 {neg}/7")
rnd=random.Random(7)
reg_sig={d:(sc.signals(day[d],'REGIME_BO',A[d],PL[d],0,rnd) if PL[d]=='BO' else sc.signals(day[d],'REGIME_MR',A[d],PL[d],0,rnd) if PL[d]=='MR' else {}) for d in A}
run('原本：09:15 規則（開盤區間）',lambda d:reg_sig[d],0.3)
for th in (0.7,0.8,0.9):
    for minr in (0.2,0.4):
        run(f'位階 ≥{th}／≤{1-th:.1f}（規則決定順逆，當天振幅 ≥{minr}ATR）',lambda d,th=th,minr=minr:pos_sig(day[d],PL[d],th,A[d],minr),0.3)
run('對照：不管規則，一律位階高做多',lambda d:pos_sig(day[d],'ALLBO',0.8,A[d],0.2),0.3)
run('對照：不管規則，一律位階高做空',lambda d:pos_sig(day[d],'ALLMR',0.8,A[d],0.2),0.3)
# 合併：規則訊號 + 位階訊號（任一觸發）
run('規則訊號＋位階 0.8 合併',lambda d:{**pos_sig(day[d],PL[d],0.8,A[d],0.2),**reg_sig[d]},0.3)
