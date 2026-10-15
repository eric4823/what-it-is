#!/usr/bin/env python3
"""GitHub Actions EOD research feed. Does NOT publish intraday buy advice.
Secret: MASSIVE_API_KEY. Uses grouped daily US equity aggregates; includes quality gates.
"""
import os,sys,json,time,datetime as dt,urllib.request,urllib.parse,urllib.error,gzip
from pathlib import Path
from collections import defaultdict
from statistics import median
from zoneinfo import ZoneInfo

ROOT=Path(__file__).parent
OUT=ROOT/"data/latest.json"
KEY=os.getenv("MASSIVE_API_KEY","").strip()
BASE="https://api.massive.com"
MIN_UNIVERSE=300
CACHE=ROOT/".cache"
BARS_CACHE=CACHE/"bars.json.gz"
COMMON_CACHE=CACHE/"common.json"
REQUEST_INTERVAL=max(0.2,float(os.getenv("MASSIVE_REQUEST_INTERVAL_SECONDS","13.5")))
_last_request=0.0

def paced():
    global _last_request
    since=time.monotonic()-_last_request
    if _last_request and since<REQUEST_INTERVAL:
        time.sleep(REQUEST_INTERVAL-since)
    _last_request=time.monotonic()

def save_history(grouped):
    CACHE.mkdir(parents=True,exist_ok=True)
    obj={sym:rows[-125:] for sym,rows in grouped.items() if rows}
    tmp=BARS_CACHE.with_suffix(".tmp")
    with gzip.open(tmp,"wt",encoding="utf-8") as f:
        json.dump(obj,f,separators=(",",":"))
    tmp.replace(BARS_CACHE)

def load_history():
    try:
        with gzip.open(BARS_CACHE,"rt",encoding="utf-8") as f:
            obj=json.load(f)
        if not isinstance(obj,dict):raise ValueError("Invalid cache")
        return defaultdict(list,{k:v for k,v in obj.items() if isinstance(v,list)})
    except (OSError,ValueError,TypeError) as e:
        print("Historical cache unavailable:",str(e)[:80])
        return defaultdict(list)
def write(status,message,items=(),session=None,scanned=0,total=0):
    OUT.parent.mkdir(parents=True,exist_ok=True)
    obj={"schema_version":1,"status":status,"generated_at":dt.datetime.now(dt.timezone.utc).isoformat(),
         "session_date":session,"message":message,"coverage":{"scanned":scanned,"total":total},"candidates":list(items)}
    OUT.write_text(json.dumps(obj,ensure_ascii=False,indent=2)+"\n")
    print("feed",status,message)
def get(path,params):
    params=dict(params,apiKey=KEY)
    url=BASE+path+"?"+urllib.parse.urlencode(params)
    for attempt in range(7):
        paced()
        try:
            req=urllib.request.Request(url,headers={"User-Agent":"runner-research-dashboard/1.1"})
            with urllib.request.urlopen(req,timeout=40) as resp:
                return json.load(resp)
        except urllib.error.HTTPError as e:
            if e.code in (401,402,403):
                raise RuntimeError(f"API plan/permission denied (HTTP {e.code}).") from e
            if e.code==429:
                header=e.headers.get("Retry-After") if e.headers else None
                try:
                    wait=max(65.0,min(240.0,float(header))) if header else 65.0
                except (ValueError,TypeError):
                    wait=65.0
                if attempt==6:
                    raise RuntimeError("Massive API 429 after 7 paced retries; retry later.") from e
                print(f"HTTP 429, waiting {wait:.0f}s; retry {attempt+1}/7")
                time.sleep(wait)
            elif 500<=e.code<600:
                if attempt==6:raise
                time.sleep(min(40,2**attempt+3))
            else:
                raise
        except (TimeoutError,urllib.error.URLError):
            if attempt==6:raise
            time.sleep(min(40,2**attempt+3))
    raise RuntimeError("Repeated API errors")

def history_dates(n=115):
    ny=dt.datetime.now(ZoneInfo("America/New_York"))
    # Only request fully closed trading days, never the current unclosed session.
    today=ny.date() if ny.time()>=dt.time(18,0) else ny.date()-dt.timedelta(days=1)
    dates=[]
    for lag in range(185):
        d=today-dt.timedelta(days=lag)
        if d.weekday()<5:dates.append(d.isoformat())
        if len(dates)>=n:break
    return dates[::-1]
def find_common():
    try:
        cached=json.loads(COMMON_CACHE.read_text())
        if time.time()-float(cached["updated"])<7*86400 and len(cached["tickers"])>=MIN_UNIVERSE:
            return set(cached["tickers"])
    except (OSError,ValueError,KeyError,TypeError):
        pass
    out=set()
    payload=get("/v3/reference/tickers",{"market":"stocks","type":"CS","active":"true","limit":"1000"})
    for page in range(35):
        for item in payload.get("results",[]):
            if item.get("ticker"):out.add(item["ticker"].upper())
        next_url=payload.get("next_url")
        if not next_url:break
        parsed=urllib.parse.urlparse(next_url)
        if parsed.hostname not in ("api.massive.com","api.polygon.io"):
            raise RuntimeError("Unexpected ticker pagination URL")
        payload=get(parsed.path,dict(urllib.parse.parse_qsl(parsed.query)))
    else:
        raise RuntimeError("Incomplete ticker pagination")
    if len(out)<MIN_UNIVERSE:
        raise RuntimeError("Too few common shares returned")
    CACHE.mkdir(parents=True,exist_ok=True)
    COMMON_CACHE.write_text(json.dumps({"updated":time.time(),"tickers":sorted(out)}))
    return out

def score(ticker,rows):
    rows=sorted(rows,key=lambda x:x["date"])
    if len(rows)<85:return None
    cur=rows[-1]; prev=rows[-6:-1]
    if cur["volume"]<=0 or cur["close"]<0.3 or cur["close"]>25:return None
    dollar=cur["close"]*cur["volume"]
    if dollar<500000:return None
    def clv(r):
        ran=r["high"]-r["low"]
        return (2*r["close"]-r["high"]-r["low"])/ran if ran>0 else 0
    def cmf(n):
        chunk=rows[-n:]; den=sum(r["volume"] for r in chunk)
        return sum(clv(r)*r["volume"] for r in chunk)/den if den else 0
    c5=cmf(5);c20=cmf(20)
    rvol=cur["volume"]/median([r["volume"] for r in prev]) if median([r["volume"] for r in prev])>0 else 0
    closepos=clv(cur)
    first=not any(rows[i]["high"]/rows[i-1]["close"]>=1.5 for i in range(max(1,len(rows)-10),len(rows)-1))
    kind="FIRST_MOVE" if first else "CONTINUATION"
    score=0; reasons=[];risk=[]
    if c5>=.15:score+=2;reasons.append("CMF(5) 강세")
    if c5-c20>=.12:score+=1;reasons.append("단기 CMF 우위")
    if rvol>=1.6:score+=2;reasons.append("중앙값 RVOL 상승")
    elif rvol>=1.15:score+=1
    if closepos>=.5:score+=1;reasons.append("종가가 당일 고가 근처")
    if cur["close"]>max(r["high"] for r in rows[-21:-1]):score+=1;reasons.append("20일 신고가")
    recent_ret=cur["close"]/rows[-6]["close"]-1
    if recent_ret>0.8:risk.append("5거래일 상승률 +80% 초과")
    if dollar<2000000:risk.append("거래대금이 낮아 실제 체결 어려울 수 있음")
    if not first and rvol>=3:score+=2;reasons.append("연속형 거래량 확대")
    if score<5:return None
    return {"ticker":ticker,"kind":kind,"score":score,"close":round(cur["close"],4),
            "dollar_volume":round(dollar),"cmf5":round(c5,4),"rvol_med5":round(rvol,3),
            "reasons":reasons,"risks":risk}
def main():
    if not KEY:
        write("unconfigured","MASSIVE_API_KEY 미설정. 실제 데이터 없이 매수 후보를 만들지 않습니다.")
        return
    try: common=find_common()
    except Exception as e:
        write("error","보통주 목록 API 오류. 유효한 API 접근권한을 확인하세요: "+str(e)[:160]);return
    if len(common)<MIN_UNIVERSE:
        write("error",f"보통주 종목 커버리지 부족 ({len(common)}개).");return
    grouped=load_history()
    target_dates=history_dates(115)
    latest_cached=max((row["date"] for rows in grouped.values() for row in rows[-1:]),default="")
    missing=[date for date in target_dates if date>latest_cached]
    print(f"Cached through {latest_cached}; fetching {len(missing)} daily aggregates")
    for i,date in enumerate(missing,1):
        try:
            dat=get(f"/v2/aggs/grouped/locale/us/market/stocks/{date}",{"adjusted":"false"})
        except Exception as e:
            save_history(grouped)
            write("error","Grouped aggregates unavailable: "+str(e)[:160],session=latest_cached,total=len(common))
            return
        result=dat.get("results",[])
        if not result:continue
        for bar in result:
            sym=bar.get("T","")
            if sym not in common:continue
            try:
                op,hi,lo,cl,vol=map(float,(bar["o"],bar["h"],bar["l"],bar["c"],bar["v"]))
                if not(0<lo<=min(op,cl) and hi>=max(op,cl) and vol>=0):continue
                grouped[sym].append({"date":date,"open":op,"high":hi,"low":lo,"close":cl,"volume":vol})
            except (KeyError,ValueError,TypeError):
                continue
        if i%10==0:
            save_history(grouped)
    save_history(grouped)
    dates_with_bars=set(row["date"] for rows in grouped.values() for row in rows)
    valid_sessions=len(dates_with_bars.intersection(target_dates))
    last=max(dates_with_bars,default=None)
    if valid_sessions<85:
        write("error",f"유효 일봉 {valid_sessions}일만 확보됨. 최소 85일 필요.",session=last,total=len(common));return
    if not last or (dt.date.today()-dt.date.fromisoformat(last)).days>5:
        write("error","데이터 업데이트 지연. 최신 거래일을 확인할 수 없습니다.",session=last,total=len(common));return
    result=[]
    for sym,rows in grouped.items():
        if not rows or rows[-1]["date"]!=last:continue
        item=score(sym,rows)
        if item:result.append(item)
    scanned=sum(len(rows)>=85 for rows in grouped.values())
    if scanned<MIN_UNIVERSE:
        write("error",f"충분한 이력 종목 부족 ({scanned}개). 후보를 공개하지 않습니다.",session=last,scanned=scanned,total=len(common));return
    result.sort(key=lambda x:(-x["score"],-x["dollar_volume"]))
    write("research_only",f"일봉 {valid_sessions}거래일 분석 · 연구 후보 {len(result)}개 · 오늘 기준 보통주 스냅샷 · 15:45 매수 신호가 아님",result[:50],last,scanned,len(common))
if __name__=="__main__":main()
