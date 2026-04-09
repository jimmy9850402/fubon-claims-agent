from fastapi import FastAPI, Query
import psycopg2
import os
import uvicorn
import google.generativeai as genai
import json
import re

app = FastAPI()

# ==========================================
# 🔑 環境變數設定 
# ==========================================
DB_URL = os.environ.get("DATABASE_URL")
GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY")

if GEMINI_API_KEY:
    genai.configure(api_key=GEMINI_API_KEY.strip())

# ⚖️ 正確版霍夫曼累計係數
def get_hoffmann_coefficient(years: int) -> float:
    if years <= 0: return 0.0
    coefficient = sum(1.0 / (1 + n * 0.05) for n in range(years))
    return round(coefficient, 6)

@app.get("/evaluate")
def evaluate(
    # 🚨 已刪除 caseId，讓理賠員少填一欄
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
    print(f"--- 🚀 啟動極速評估：{city} {job} ({body_part}) ---")
    
    # 1. 檢索資料庫
    judgments = search_supabase(body_part, city)

    # 2. 客觀損失計算
    work_loss = salary * months
    labor_loss_comp = 0
    if labor_loss_ratio > 0:
        rem_years = max(0, 65 - age)
        coef = get_hoffmann_coefficient(rem_years)
        labor_loss_comp = int((salary * 12) * (labor_loss_ratio / 100) * coef)

    # 🌟 3. 呼叫 Gemini 3.1 Flash Lite (高額度版)
    gemini_result = generate_dynamic_report(
        age=age, job=job, body_part=body_part, liability=liability, 
        work_loss=work_loss, labor_loss=labor_loss_comp, 
        judgments=judgments, city=city
    )
    
    dynamic_consolation = gemini_result.get("estimated_consolation", 80000)
    tailexi_report = gemini_result.get("report_text", "報告生成異常，請檢查 API。")

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

def generate_dynamic_report(age, job, body_part, liability, work_loss, labor_loss, judgments, city):
    if not GEMINI_API_KEY: return {"estimated_consolation": 80000, "report_text": "Key 缺失"}
    
    prompt = f"""
    你現在是台灣富邦產險的資深法務，請針對「{city}」的案件進行專業評估。
    受傷部位：{body_part} | 職業：{job} | 年齡：{age} | 肇責：{liability}%
    
    指令：
    1. 根據職業「{job}」的身分地位動態調整慰撫金。
    2. 參考資料：{judgments}
    3. 嚴禁使用 // 註解。
    回傳純 JSON：{{"estimated_consolation": 數字, "report_text": "Markdown內容"}}
    """
    
    try:
        # 🌟 改用 Flash Lite 預覽版，確保 500 次/天 的額度
        model = genai.GenerativeModel(
            model_name='gemini-3.1-flash-lite-preview',
            tools=[{"google_search_retrieval": {}}]
        )
        response = model.generate_content(prompt, generation_config=genai.types.GenerationConfig(temperature=0.3))
        clean_json = re.sub(r'```json\n?|```', '', response.text).strip()
        return json.loads(clean_json)
    except Exception as e:
        return {"estimated_consolation": 88000, "report_text": f"API 暫時繁忙，請稍後。錯誤：{str(e)}"}

def search_supabase(keyword, city):
    try:
        conn = psycopg2.connect(DB_URL)
        cur = conn.cursor()
        cur.execute('SELECT "JFULL" FROM car_judgments WHERE "JFULL" ilike %s AND "JFULL" ilike %s LIMIT 2', (f"%{keyword}%", f"%{city}%"))
        rows = cur.fetchall()
        cur.close()
        conn.close()
        return [r[0][:1500] for r in rows]
    except: return []

if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=8000)
