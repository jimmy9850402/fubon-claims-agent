from fastapi import FastAPI, Query
import psycopg2
import os
import requests
import json
import re
import uvicorn
from ddgs import DDGS  # 🌐 聯網搜尋套件

app = FastAPI()

# ==========================================
# 🔑 環境變數與設定
# ==========================================
DB_URL = os.environ.get("DATABASE_URL")
OPENROUTER_API_KEY = os.environ.get("OPENROUTER_API_KEY")

# 市場行情調整係數 (將多年前的參考表基數調升至現行水準)
MARKET_ADJUSTMENT_FACTOR = 1.3 

# ⚖️ 霍夫曼係數計算
def get_hoffmann_coefficient(years: int) -> float:
    if years <= 0: return 0.0
    return round(sum(1.0 / (1 + n * 0.05) for n in range(years)), 6)

@app.get("/")
def home():
    return {"status": "Fubon AI Agent Live", "standard": "2026-Advanced-Logic"}

@app.get("/evaluate")
def evaluate(
    body_part: str = Query(..., description="受傷部位"),
    salary: int = Query(..., description="月薪"),
    months: int = Query(..., description="休養月數"),
    liability: int = Query(..., description="肇責比例"),
    job: str = Query("一般職業", description="職業"),
    age: int = Query(35, description="年齡"),
    labor_loss_ratio: int = Query(0, description="勞力減損比"),
    dependents: int = Query(0, description="受扶養人數"),
    city: str = Query("台北市", description="居住縣市"),
    medical_fee: int = Query(0, description="醫療費用")
):
    # 1. 判例檢索 (優先資料庫，備援聯網)
    db_judgments = search_judgments(body_part, city)
    context_info = ""
    
    if db_judgments:
        context_info = f"【內部資料庫判例摘要】：\n" + "\n".join(db_judgments)
    else:
        # 智慧聯網搜尋關鍵字
        clean_keyword = body_part.replace("粉碎性", " ").replace("骨折", " ")
        web_results = search_web_judgments(f"車禍 {clean_keyword} 精神慰撫金 判決 台灣")
        context_info = f"【網路即時法理參考】：\n{web_results}" if web_results else "查無特定判例，依專業法理推估。"

    # 2. 客觀財務損失計算 (不變)
    work_loss = salary * months
    labor_loss_comp = int((salary * 12) * (labor_loss_ratio / 100) * get_hoffmann_coefficient(max(0, 65 - age))) if labor_loss_ratio > 0 else 0

    # 3. 呼叫 AI 生成報告 (注入「參考表」邏輯)
    ai_result = call_ai_logic(age, job, body_part, liability, city, context_info)
    
    dynamic_consolation = ai_result.get("estimated_consolation", 100000)
    final_report = ai_result.get("report_text", "報告產出失敗。")

    # 4. 總額計算與肇責分擔
    total_before = medical_fee + work_loss + labor_loss_comp + dynamic_consolation
    final_amount = int(total_before * (liability / 100))

    return {
        "status": "success",
        "results": {
            "dynamic_consolation": dynamic_consolation,
            "final_suggested_amount": final_amount,
            "tailexi_style_report": final_report 
        }
    }

# ==========================================
# 🧠 AI 核心邏輯 (內建富邦參考表矩陣)
# ==========================================
def call_ai_logic(age, job, body_part, liability, city, context_info):
    # 這裡將圖片中的參考表邏輯寫入 Prompt
    prompt = f"""
    你現在是台灣富邦產險最資深的理賠法務專家。請針對以下案例產出專業建議書。
    地點：{city} | 傷者：{age}歲{job} | 傷勢：{body_part} | 肇責：{liability}%
    {context_info}
    
    【📋 富邦內部精神補償參考矩陣 (數位化歷史標準)】：
    1. 皮肉損傷 (擦挫傷/撕裂傷)：0~2萬
    2. 輕微骨折 (鎖骨/手掌/肋骨)：0~7萬
    3. 一般上肢骨折 (橈骨/尺骨/肱骨)：0~11萬 (骨幹部基數)
    4. 嚴重骨折 (粉碎性/開放性/下肢股骨/椎骨)：15萬~26萬
    5. 重大傷情 (顱內出血/截肢/神經病變)：30萬~150萬以上
    
    【⚖️ 2026年現行核定加權規則】：
    - 市場修正：上述為多年前基準，請自動乘以 {MARKET_ADJUSTMENT_FACTOR} 倍作為現行底薪與通膨校正。
    - 職業加權：傷者為「{job}」，需考慮其對精密勞作之依賴及社會地位，應加成 20%~40%。
    - 傷情加權：若為粉碎性且需復健超過半年，應取級距高標。

    請依據此邏輯精算出最符合實務(如協理建議之26萬左右)的慰撫金 (estimated_consolation)。

    格式：一、關鍵議題 二、適用法條 三、構成要件 四、內部參考表對照與加權理由 五、結論與談判策略。
    必須回傳純 JSON：{{"estimated_consolation": 數字, "report_text": "Markdown 報告"}}
    """

    model_list = ["google/gemma-4-31b-it:free", "meta-llama/llama-3.3-70b-instruct:free", "openrouter/auto"]
    
    for model_id in model_list:
        try:
            res = requests.post(
                url="https://openrouter.ai/api/v1/chat/completions",
                headers={"Authorization": f"Bearer {OPENROUTER_API_KEY.strip()}", "Content-Type": "application/json"},
                data=json.dumps({"model": model_id, "messages": [{"role": "user", "content": prompt}], "temperature": 0.3}),
                timeout=45
            )
            data = res.json()
            if 'choices' in data:
                content = data['choices'][0]['message']['content']
                clean_json = re.sub(r'```json\n?|```', '', content).strip()
                return json.loads(clean_json)
        except: continue
    return {"estimated_consolation": 150000, "report_text": "AI 繁忙中。"}

# ==========================================
# 🌐 聯網搜尋與資料庫功能 (不變)
# ==========================================
def search_web_judgments(query):
    try:
        results = DDGS().text(query, region='tw-tz', max_results=3)
        return "\n".join([f"- {r.get('title')}: {r.get('body')}" for r in list(results)])
    except: return ""

def search_judgments(keyword, city):
    try:
        conn = psycopg2.connect(DB_URL)
        cur = conn.cursor()
        cur.execute('SELECT "JFULL" FROM car_judgments WHERE "JFULL" ilike %s AND "JFULL" ilike %s LIMIT 1', (f"%車禍%", f"%{keyword}%"))
        rows = cur.fetchall()
        cur.close(); conn.close()
        return [r[0][:1000] for r in rows]
    except: return []

if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=8000)
