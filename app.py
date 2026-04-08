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
# 請確保在 Render 的 Environment Variables 設定了這兩個變數
DB_URL = os.environ.get("DATABASE_URL")
GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY")

# 🌟 啟動 Google Gemini 模型
if GEMINI_API_KEY:
    genai.configure(api_key=GEMINI_API_KEY)

# ==========================================
# ⚖️ 法院認證：正確版霍夫曼計算法模組
# ==========================================
def get_hoffmann_coefficient(years: int) -> float:
    """正確版霍夫曼累計係數 (法定年息 5%，第一年不扣除利息)"""
    if years <= 0:
        return 0.0
    coefficient = 0.0
    for n in range(years):
        coefficient += 1.0 / (1 + n * 0.05)
    return round(coefficient, 6)

# 行政院主計總處最新每人月消費支出
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
    return {"status": "Fubon Claims AI Agent is Online!", "engine": "Gemini 1.5 Pro Latest"}


@app.get("/evaluate")
def evaluate(
    body_part: str = Query(..., description="受傷部位關鍵字"),
    salary: int = Query(..., description="月薪"),
    months: int = Query(..., description="休養月數"),
    liability: int = Query(..., description="肇責比例 (0-100)"),
    job: str = Query("一般職業", description="傷者職業"),
    age: int = Query(30, description="傷者年齡"),
    labor_loss_ratio: int = Query(0, description="勞動力減損比例 (0-100)"),
    dependents: int = Query(0, description="受扶養人數"),
    city: str = Query("新北市", description="居住縣市")
):
    print(f"--- 🚀 啟動理賠評估：{body_part} ---")
    
    # 1. 檢索資料庫判例
    judgments = search_judgments_in_supabase(body_part)
    laws = search_laws_in_supabase("慰撫金") 
    
    if not laws:
         laws = ["民法第184條：侵權行為損害賠償責任。", "民法第195條：非財產上損害賠償(慰撫金)。"]

    # 2. 客觀損失計算
    work_loss = salary * months
    
    labor_loss_compensation = 0
    labor_loss_reason = "無"
    if labor_loss_ratio > 0:
        remaining_years = max(0, 65 - age)
        if remaining_years > 0:
            coef = get_hoffmann_coefficient(remaining_years)
            labor_loss_compensation = int((salary * 12) * (labor_loss_ratio / 100) * coef)
            labor_loss_reason = f"依霍夫曼係數 {coef} 精算現值為 {labor_loss_compensation:,} 元。"

    dependent_support_compensation = 0
    dependent_reason = "無"
    if dependents > 0:
        monthly_expense = DGBAS_EXPENSES.get(city, DGBAS_EXPENSES["其他"])
        support_coef = get_hoffmann_coefficient(10) # 預設扶養10年
        dependent_support_compensation = int((monthly_expense * 12) * dependents * support_coef)
        dependent_reason = f"依 {city} 標準與霍夫曼係數 {support_coef} 精算現值為 {dependent_support_compensation:,} 元。"

    # 🌟 3. 呼叫 Gemini 進行動態定價與報告生成
    gemini_result = generate_dynamic_report(
        age=age, job=job, body_part=body_part, liability=liability, 
        work_loss=work_loss, labor_loss=labor_loss_compensation, 
        dependent_support=dependent_support_compensation, 
        judgments=judgments, laws=laws
    )
    
    # 從 Gemini 回傳的 JSON 提取數據
    dynamic_consolation = gemini_result.get("estimated_consolation", 80000)
    tailexi_report = gemini_result.get("report_text", "無法生成報告。")

    # 4. 最終金額加總與肇責折減
    total_before_liability = work_loss + dynamic_consolation + labor_loss_compensation + dependent_support_compensation
    final_amount = int(total_before_liability * (liability / 100))

    return {
        "status": "success",
        "results": {
            "input_job": job,
            "input_body_part": body_part,
            "calculated_work_loss": work_loss,
            "calculated_labor_loss": labor_loss_compensation,
            "calculated_dependent_support": dependent_support_compensation,
            "dynamic_consolation": dynamic_consolation,
            "labor_loss_reason": labor_loss_reason,
            "dependent_reason": dependent_reason,
            "suggested_total_before_liability": total_before_liability,
            "final_suggested_amount": final_amount,
            "tailexi_style_report": tailexi_report 
        }
    }

# ==========================================
# 🔍 檢索與生成核心
# ==========================================
def search_judgments_in_supabase(keyword):
    try:
        conn = psycopg2.connect(DB_URL)
        cursor = conn.cursor()
        keywords = keyword.split()
        base_filter = '("JFULL" ilike \'%車禍%\' OR "JFULL" ilike \'%交通事故%\')'
        keyword_filter = " AND ".join(['"JFULL" ilike %s' for _ in keywords])
        sql = f'SELECT "JFULL" FROM car_judgments WHERE {base_filter} AND ({keyword_filter}) ORDER BY "JDATE" desc LIMIT 3'
        cursor.execute(sql, tuple(f"%{k}%" for k in keywords))
        rows = cursor.fetchall()
        cursor.close()
        conn.close()
        return [row[0][:2500].replace("\n", " ") for row in rows] if rows else []
    except:
        return []

def search_laws_in_supabase(keyword):
    try:
        conn = psycopg2.connect(DB_URL)
        cursor = conn.cursor()
        cursor.execute("SELECT article_number, article_content FROM laws WHERE article_content ilike %s LIMIT 5", (f"%{keyword}%",))
        rows = cursor.fetchall()
        cursor.close()
        conn.close()
        return [f"{r[0]}：{r[1]}" for r in rows] if rows else []
    except:
        return []

def generate_dynamic_report(age, job, body_part, liability, work_loss, labor_loss, dependent_support, judgments, laws):
    """呼叫最新版 Gemini 進行精確估價與連網分析"""
    if not GEMINI_API_KEY:
        return {"estimated_consolation": 80000, "report_text": "API Key 缺失"}
        
    judgments_text = "\n\n".join(judgments) if judgments else "參考網路實務行情。"
    laws_text = "\n\n".join(laws)
    other_total = labor_loss + dependent_support
    
    prompt = f"""
    你現在是台灣資深車禍理賠專家。請針對傷勢「{body_part}」，參考內部判例與 Google 搜尋最新行情，評估最合理的「精神慰撫金」。
    
    🚨 指令：
    1. 嚴禁固定使用 8 萬元。請根據傷勢嚴重度精確估價（如：45,000 或 125,000）。
    2. 必須回傳「純 JSON」格式（無 Markdown 標籤），包含：
       - "estimated_consolation": 整數金額
       - "report_text": 專業分析報告 (Markdown 格式)
    3. 報告中的最終金額計算必須包含你給出的慰撫金，並乘以肇責比例 {liability}%。

    【案情概要】
    - 年齡：{age} | 職業：{job} | 部位：{body_part}
    - 工作損失：{work_loss} | 勞力減損與扶養費：{other_total}
    
    【法規與判例】
    {laws_text}
    {judgments_text}
    """
    
    try:
        # 🌟 使用最新版本模型名稱
        model = genai.GenerativeModel(
            model_name='gemini-1.5-pro-latest',
            tools=[{"google_search_retrieval": {}}]
        )
        response = model.generate_content(prompt, generation_config=genai.types.GenerationConfig(temperature=0.4))
        
        # 移除 JSON 可能夾帶的 Markdown 符號
        clean_json = re.sub(r'```json\n?|```', '', response.text).strip()
        return json.loads(clean_json)
    except Exception as e:
        print(f"Gemini 呼叫失敗: {e}")
        return {"estimated_consolation": 85000, "report_text": "報告產出異常，請手動校核。"}

if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=8000)
