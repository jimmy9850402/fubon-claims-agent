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
    genai.configure(api_key=GEMINI_API_KEY)

# ==========================================
# ⚖️ 法院認證：正確版霍夫曼計算法模組
# ==========================================
def get_hoffmann_coefficient(years: int) -> float:
    if years <= 0: return 0.0
    coefficient = 0.0
    for n in range(years):
        coefficient += 1.0 / (1 + n * 0.05)
    return round(coefficient, 6)

DGBAS_EXPENSES = {
    "基隆市": 24022, "臺北市": 34952, "台北市": 34952, "新北市": 27557,
    "桃園市": 25718, "新竹縣": 30014, "新竹市": 29722, "苗栗縣": 22019,
    "臺中市": 28754, "台中市": 28754, "彰化縣": 20323, "南投縣": 19180,
    "雲林縣": 20411, "嘉義縣": 21473, "嘉義市": 27255, "臺南市": 23036, "台南市": 23036,
    "高雄市": 26722, "屏東縣": 22241, "宜蘭縣": 23935, "花蓮縣": 21969,
    "臺東縣": 19402, "台東縣": 19402, "澎湖縣": 20188,
    "總平均": 26640, "其他": 26640     
}

@app.get("/")
def home():
    return {"status": "Fubon Claims AI Agent is Online!", "engine": "Gemini 1.5 Pro (Precision Logic)"}


@app.get("/evaluate")
def evaluate(
    body_part: str = Query(..., description="受傷部位關鍵字"),
    salary: int = Query(..., description="月薪"),
    months: int = Query(..., description="休養月數"),
    liability: int = Query(..., description="肇責比例 (0-100)"),
    job: str = Query("一般職業", description="傷者職業"),
    age: int = Query(35, description="傷者年齡"),
    labor_loss_ratio: int = Query(0, description="勞動力減損比例 (0-100)"),
    dependents: int = Query(0, description="受扶養人數"),
    city: str = Query("新北市", description="居住縣市")
):
    print(f"--- 🚀 啟動深度評估：{body_part} ({job}) ---")
    
    # 1. 檢索資料
    judgments = search_judgments_in_supabase(body_part)
    laws = ["民法第184條", "民法第191-2條", "民法第193條", "民法第195條"]

    # 2. 確定性損失計算
    work_loss = salary * months
    
    labor_loss_compensation = 0
    if labor_loss_ratio > 0:
        remaining_years = max(0, 65 - age)
        if remaining_years > 0:
            coef = get_hoffmann_coefficient(remaining_years)
            labor_loss_compensation = int((salary * 12) * (labor_loss_ratio / 100) * coef)

    dependent_support_compensation = 0
    if dependents > 0:
        monthly_expense = DGBAS_EXPENSES.get(city, DGBAS_EXPENSES["其他"])
        support_coef = get_hoffmann_coefficient(10) # 預設扶養10年
        dependent_support_compensation = int((monthly_expense * 12) * dependents * support_coef)

    # 🌟 3. 呼叫 Gemini 進行「高階法律人格權」估價與報告
    gemini_result = generate_expert_report(
        age=age, job=job, body_part=body_part, liability=liability, 
        work_loss=work_loss, labor_loss=labor_loss_compensation, 
        dependent_support=dependent_support_compensation, 
        judgments=judgments, dependents_count=dependents
    )
    
    # 提取動態金額
    dynamic_consolation = gemini_result.get("estimated_consolation", 85000)
    tailexi_report = gemini_result.get("report_text", "報告解析失敗。")

    # 4. 最終計算
    total_before_liability = work_loss + dynamic_consolation + labor_loss_compensation + dependent_support_compensation
    final_amount = int(total_before_liability * (liability / 100))

    return {
        "status": "success",
        "results": {
            "input_job": job,
            "dynamic_consolation": dynamic_consolation,
            "suggested_total_before_liability": total_before_liability,
            "final_suggested_amount": final_amount,
            "tailexi_style_report": tailexi_report 
        }
    }

# ==========================================
# 🔍 搜尋模組
# ==========================================
def search_judgments_in_supabase(keyword):
    try:
        conn = psycopg2.connect(DB_URL)
        cursor = conn.cursor()
        keywords = keyword.split()
        sql = f'SELECT "JFULL" FROM car_judgments WHERE "JFULL" ilike %s AND "JFULL" ilike %s ORDER BY "JDATE" desc LIMIT 3'
        cursor.execute(sql, (f"%車禍%", f"%{keywords[0]}%"))
        rows = cursor.fetchall()
        cursor.close()
        conn.close()
        return [row[0][:2000].replace("\n", " ") for row in rows] if rows else []
    except:
        return []

# ==========================================
# 🤖 Gemini 專家思維模組
# ==========================================
def generate_expert_report(age, job, body_part, liability, work_loss, labor_loss, dependent_support, judgments, dependents_count):
    if not GEMINI_API_KEY:
        return {"estimated_consolation": 80000, "report_text": "API Key 缺失"}
        
    judgments_text = "\n\n".join(judgments) if judgments else "參考最新實務行情。"
    other_total = labor_loss + dependent_support
    
    prompt = f"""
    你現在是台灣產險業資深理賠主管。請針對傷勢「{body_part}」，參考內部判例與 Google 搜尋最新行情，精確評估「精神慰撫金」。
    
    🚨【理賠評估最高原則】：
    1. 拒絕定額主義：嚴禁固定使用 8 萬。必須依據傷勢痛苦程度與身分加權。
    2. 身分加權：本案傷者職業為「{job}」，現年 {age} 歲。
       - 律師/醫師/專業人士：精神痛苦之社會評價較高，應大幅調升慰撫金。
       - 扶養重擔：傷者須扶養 {dependents_count} 人，受傷期間之心理焦慮極大，應加權計算。
    3. 傷勢分級：粉碎性骨折屬重傷，起跳行情應在 15 萬以上。
    
    必須回傳「純 JSON」格式（無任何標籤），包含：
    {{
        "estimated_consolation": 180000,  // 請依據 {job} 身分與重傷情形給予精確估價
        "report_text": "一、工作損失... 二、慰撫金酌定因素 (請明確分析 {job} 職業性質與 {dependents_count} 名扶養人的加權影響)..." 
    }}

    【個案數據】
    - 年齡：{age} | 職業：{job} | 傷勢：{body_part} | 扶養人數：{dependents_count}
    - 肇責：{liability}%
    - 其他財產損害：{work_loss + other_total} 元
    
    【參考資料】
    {judgments_text}
    """
    
    try:
        # 使用最新版本並開啟連網搜尋
        model = genai.GenerativeModel(
            model_name='gemini-1.5-pro-latest',
            tools=[{"google_search_retrieval": {}}]
        )
        response = model.generate_content(prompt, generation_config=genai.types.GenerationConfig(temperature=0.4))
        
        # 結構化清理 JSON
        clean_json = re.sub(r'```json\n?|```', '', response.text).strip()
        return json.loads(clean_json)
    except Exception as e:
        print(f"Gemini 故障：{e}")
        return {"estimated_consolation": 88000, "report_text": "報告生成出錯，請手動校核。"}

if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=8000)
