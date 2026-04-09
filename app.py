from fastapi import FastAPI, Query
import psycopg2
import os
import requests
import json
import re

app = FastAPI()

# ==========================================
# 🔑 環境變數設定 (OpenRouter 版)
# ==========================================
DB_URL = os.environ.get("DATABASE_URL")
OPENROUTER_API_KEY = os.environ.get("OPENROUTER_API_KEY")

# ⚖️ 法院認證：霍夫曼係數計算
def get_hoffmann_coefficient(years: int) -> float:
    if years <= 0: return 0.0
    coefficient = sum(1.0 / (1 + n * 0.05) for n in range(years))
    return round(coefficient, 6)

@app.get("/")
def home():
    return {"status": "Fubon AI Agent is Online!", "provider": "OpenRouter"}

@app.get("/evaluate")
def evaluate(
    body_part: str = Query(..., description="受傷部位"),
    salary: int = Query(..., description="月薪"),
    months: int = Query(..., description="休養月數"),
    liability: int = Query(..., description="肇責比例"),
    job: str = Query("一般職業", description="職業"),
    age: int = Query(35, description="年齡"),
    labor_loss_ratio: int = Query(0, description="勞動力減損比例"),
    dependents: int = Query(0, description="受扶養人數"),
    city: str = Query("台北市", description="居住縣市")
):
    # 1. 檢索資料 (RAG)
    judgments = search_supabase(body_part, city)

    # 2. 客觀計算
    work_loss = salary * months
    labor_loss_comp = 0
    if labor_loss_ratio > 0:
        rem_years = max(0, 65 - age)
        coef = get_hoffmann_coefficient(rem_years)
        labor_loss_comp = int((salary * 12) * (labor_loss_ratio / 100) * coef)

    # 🌟 3. 呼叫 OpenRouter 進行智慧估價
    gemini_result = call_openrouter(
        age=age, job=job, body_part=body_part, liability=liability, 
        work_loss=work_loss, judgments=judgments, city=city
    )
    
    dynamic_consolation = gemini_result.get("estimated_consolation", 85000)
    tailexi_report = gemini_result.get("report_text", "報告解析失敗。")

    # 4. 最終計算
    total = work_loss + dynamic_consolation + labor_loss_comp
    final_amount = int(total * (liability / 100))

    return {
        "status": "success",
        "results": {
            "input_job": job,
            "dynamic_consolation": dynamic_consolation,
            "final_suggested_amount": final_amount,
            "tailexi_style_report": tailexi_report 
        }
    }

# ==========================================
# 🧠 OpenRouter 呼叫模組
# ==========================================
def call_openrouter(age, job, body_part, liability, work_loss, judgments, city):
    if not OPENROUTER_API_KEY:
        return {"estimated_consolation": 80000, "report_text": "API Key 缺失"}

    prompt = f"""
    你現在是台灣富邦產險理賠主管。請針對傷勢「{body_part}」，參考以下判例進行慰撫金估價。
    傷者：{age}歲{job} | 地點：{city} | 肇責：{liability}%
    判例參考：{judgments}

    必須回傳純 JSON，不可有註解：
    {{
        "estimated_consolation": 200000,
        "report_text": "依據職業{job}之社會地位，調升慰撫金至20萬..."
    }}
    """

    try:
        response = requests.post(
            url="https://openrouter.ai/api/v1/chat/completions",
            headers={
                "Authorization": f"Bearer {OPENROUTER_API_KEY}",
                "Content-Type": "application/json"
            },
            data=json.dumps({
                "model": "google/gemini-2.0-flash-001", # 這是目前最穩定的免費模型
                "messages": [{"role": "user", "content": prompt}]
            })
        )
        
        res_json = response.json()
        raw_content = res_json['choices'][0]['message']['content']
        
        # 清理並解析 JSON
        clean_json = re.sub(r'```json\n?|```', '', raw_content).strip()
        return json.loads(clean_json)
        
    except Exception as e:
        return {"estimated_consolation": 88000, "report_text": f"服務繁忙：{str(e)}"}

def search_supabase(keyword, city):
    try:
        conn = psycopg2.connect(DB_URL)
        cur = conn.cursor()
        cur.execute('SELECT "JFULL" FROM car_judgments WHERE "JFULL" ilike %s AND "JFULL" ilike %s LIMIT 2', (f"%{keyword}%", f"%{city}%"))
        rows = cur.fetchall()
        cur.close()
        conn.close()
        return [r[0][:1000] for r in rows]
    except: return []
