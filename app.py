from fastapi import FastAPI, Query
import psycopg2
import os
import uvicorn
import google.generativeai as genai
import json
import re

app = FastAPI()

# ==========================================
# 🔑 系統核心設定 (API 與資料庫)
# ==========================================
DB_URL = os.environ.get("DATABASE_URL")
GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY")

if GEMINI_API_KEY:
    # 使用 .strip() 確保 Key 前後無空白
    genai.configure(api_key=GEMINI_API_KEY.strip())

# ⚖️ 法院認證：霍夫曼係數計算 (法定年息 5%)
def get_hoffmann_coefficient(years: int) -> float:
    if years <= 0: return 0.0
    coefficient = sum(1.0 / (1 + n * 0.05) for n in range(years))
    return round(coefficient, 6)

# 🏢 主計處 113 年各縣市平均月消費支出標準
DGBAS_EXPENSES = {
    "基隆市": 24022, "臺北市": 34952, "台北市": 34952, "新北市": 27557,
    "桃園市": 25718, "新竹縣": 30014, "新竹市": 29722, "苗栗縣": 22019,
    "臺中市": 28754, "台中市": 28754, "彰化縣": 20323, "南投縣": 19180,
    "雲林縣": 20411, "嘉義縣": 21473, "嘉義市": 27255, "臺南市": 23036, "台南市": 23036,
    "高雄市": 26722, "屏東縣": 22241, "宜蘭縣": 23935, "花蓮縣": 21969,
    "臺東縣": 19402, "台東縣": 19402, "澎湖縣": 20188, "總平均": 26640, "其他": 26640     
}

@app.get("/")
def home():
    return {"status": "Fubon Claims AI Agent is Online!", "model": "Gemini 3.1 Flash Lite (500 RPD)"}

# ==========================================
# 🚀 理賠估算核心引擎 (已移除案號問項)
# ==========================================
@app.get("/evaluate")
def evaluate(
    body_part: str = Query(..., description="受傷部位"),
    salary: int = Query(..., description="月薪"),
    months: int = Query(..., description="休養月數"),
    liability: int = Query(..., description="肇責比例 (0-100)"),
    job: str = Query("一般職業", description="職業"),
    age: int = Query(35, description="年齡"),
    labor_loss_ratio: int = Query(0, description="勞動力減損比例"),
    dependents: int = Query(0, description="受扶養人數"),
    city: str = Query("台北市", description="居住縣市")
):
    print(f"--- ⚖️ 啟動自動化理賠評估：{city} {job} ---")
    
    # 1. 檢索 Supabase 判例資料 (RAG)
    judgments = search_judgments_in_supabase(body_part, city)

    # 2. 客觀財產損失計算
    work_loss = salary * months
    
    # 勞動力減損 (霍夫曼精算)
    labor_loss_comp = 0
    if labor_loss_ratio > 0:
        rem_years = max(0, 65 - age)
        if rem_years > 0:
            coef = get_hoffmann_coefficient(rem_years)
            labor_loss_comp = int((salary * 12) * (labor_loss_ratio / 100) * coef)

    # 扶養費 (主計處標準 + 霍夫曼)
    support_comp = 0
    if dependents > 0:
        monthly_exp = DGBAS_EXPENSES.get(city, DGBAS_EXPENSES["其他"])
        support_coef = get_hoffmann_coefficient(10) # 預設計算 10 年
        support_comp = int((monthly_exp * 12) * dependents * support_coef)

    # 🌟 3. 呼叫 Gemini 3.1 Flash Lite 進行智慧估價
    gemini_result = generate_expert_report(
        age=age, job=job, body_part=body_part, liability=liability, 
        work_loss=work_loss, labor_loss=labor_loss_comp, 
        dependent_support=support_comp, judgments=judgments, 
        dependents_count=dependents, city=city
    )
    
    dynamic_consolation = gemini_result.get("estimated_consolation", 80000)
    tailexi_report = gemini_result.get("report_text", "報告解析失敗，請重新嘗試。")

    # 4. 總額彙整與肇責相抵
    total_estimated = work_loss + dynamic_consolation + labor_loss_comp + support_comp
    final_amount = int(total_estimated * (liability / 100))

    return {
        "status": "success",
        "results": {
            "input_job": job,
            "input_city": city,
            "dynamic_consolation": dynamic_consolation,
            "suggested_total_before_liability": total_estimated,
            "final_suggested_amount": final_amount,
            "tailexi_style_report": tailexi_report 
        }
    }

# ==========================================
# 🔍 判例檢索模組
# ==========================================
def search_judgments_in_supabase(keyword, city):
    try:
        conn = psycopg2.connect(DB_URL)
        cursor = conn.cursor()
        sql = """
            SELECT "JFULL" FROM car_judgments 
            WHERE "JFULL" ilike %s AND "JFULL" ilike %s 
            ORDER BY CASE WHEN "JFULL" ilike %s THEN 0 ELSE 1 END, "JDATE" desc 
            LIMIT 2
        """
        cursor.execute(sql, (f"%車禍%", f"%{keyword}%", f"%{city}%"))
        rows = cursor.fetchall()
        cursor.close()
        conn.close()
        return [row[0][:1500].replace("\n", " ") for row in rows] if rows else []
    except:
        return []

# ==========================================
# 🤖 Gemini 3.1 專家報告生成模組
# ==========================================
def generate_expert_report(age, job, body_part, liability, work_loss, labor_loss, dependent_support, judgments, dependents_count, city):
    if not GEMINI_API_KEY:
        return {"estimated_consolation": 80000, "report_text": "⚠️ 系統未設定 API_KEY。"}
        
    judgments_text = "\n\n".join(judgments) if judgments else f"參考 {city} 地區最新實務行情。"
    other_total = labor_loss + dependent_support
    
    # 🚨 注意：Prompt 已嚴格過濾 JSON 註解
    prompt = f"""
    你現在是台灣產險業資深理賠主管。請針對傷勢「{body_part}」，參考內部判例與聯網搜尋，評估「精神慰撫金」。
    
    【核心原則】：
    1. 在地化定價：考量「{city}」之生活水準。
    2. 身分加權：傷者為「{job}」，現年 {age} 歲。專業人士或扶養人數({dependents_count})多者，應調升慰撫金。
    3. 拒絕定額：嚴禁使用 8 萬元。需產出動態、精確的理賠計畫書。
    
    必須以「純 JSON」格式回傳，且絕對不可包含 // 註解文字：
    {{
        "estimated_consolation": 220000,
        "report_text": "一、工作損失分析... 二、慰撫金酌定因素 (考量職業 {job} 與地區 {city})... 三、總結理賠建議..." 
    }}

    【案件數據】
    - 年齡：{age} | 職業：{job} | 傷勢：{body_part} | 縣市：{city}
    - 肇責：{liability}% | 扶養：{dependents_count} 人
    - 系統精算財產損失：{work_loss + other_total} 元
    
    【參考資料】
    {judgments_text}
    """
    
    try:
        # 🌟 使用 500 次/天 的高額度模型
        model = genai.GenerativeModel(
            model_name='gemini-3.1-flash-lite-preview',
            tools=[{"google_search_retrieval": {}}]
        )
        response = model.generate_content(prompt, generation_config=genai.types.GenerationConfig(temperature=0.3))
        
        # 清理 Markdown 標記
        clean_json = re.sub(r'```json\n?|```', '', response.text).strip()
        return json.loads(clean_json)
        
    except Exception as e:
        print(f"Gemini 錯誤：{e}")
        return {
            "estimated_consolation": 95000, 
            "report_text": f"自動報告生成中斷，請手動校核。原因：{str(e)}"
        }

if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=8000)
