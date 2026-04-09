from fastapi import FastAPI, Query
import psycopg2
import os
import uvicorn
import google.generativeai as genai
import json
import re

app = FastAPI()

# ==========================================
# 🔑 環境變數與 Gemini 3 啟動
# ==========================================
DB_URL = os.environ.get("DATABASE_URL")
GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY")

if GEMINI_API_KEY:
    # 這裡使用剛剛測試成功的 .strip() 清洗邏輯
    genai.configure(api_key=GEMINI_API_KEY.strip())

# ==========================================
# ⚖️ 法院認證：正確版霍夫曼與主計處標準
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
    return {"status": "Fubon Claims AI Agent is Online!", "engine": "Gemini 3 Flash Preview"}

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
    print(f"--- 🚀 啟動評估：{city} {job} ({body_part}) ---")
    
    # 1. 檢索資料 (RAG)
    judgments = search_judgments_in_supabase(body_part, city)

    # 2. 客觀損失計算
    work_loss = salary * months
    labor_loss_comp = 0
    if labor_loss_ratio > 0:
        rem_years = max(0, 65 - age)
        coef = get_hoffmann_coefficient(rem_years)
        labor_loss_comp = int((salary * 12) * (labor_loss_ratio / 100) * coef)

    support_comp = 0
    if dependents > 0:
        monthly_exp = DGBAS_EXPENSES.get(city, DGBAS_EXPENSES["其他"])
        support_coef = get_hoffmann_coefficient(10)
        support_comp = int((monthly_exp * 12) * dependents * support_coef)

    # 🌟 3. 呼叫 Gemini 3 進行深度估價
    gemini_result = generate_expert_report(
        age=age, job=job, body_part=body_part, liability=liability, 
        work_loss=work_loss, labor_loss=labor_loss_comp, 
        dependent_support=support_comp, judgments=judgments, 
        dependents_count=dependents, city=city
    )
    
    dynamic_consolation = gemini_result.get("estimated_consolation", 80000)
    tailexi_report = gemini_result.get("report_text", "報告生成異常。")

    # 4. 總金額計算
    total_estimated = work_loss + dynamic_consolation + labor_loss_comp + support_comp
    final_suggested = int(total_estimated * (liability / 100))

    return {
        "status": "success",
        "results": {
            "input_job": job,
            "input_city": city,
            "dynamic_consolation": dynamic_consolation,
            "suggested_total_before_liability": total_estimated,
            "final_suggested_amount": final_suggested,
            "tailexi_style_report": tailexi_report 
        }
    }

# ==========================================
# 🔍 搜尋模組 (優化：加入縣市過濾)
# ==========================================
def search_judgments_in_supabase(keyword, city):
    try:
        conn = psycopg2.connect(DB_URL)
        cursor = conn.cursor()
        # 優先搜尋該地區的法院判決
        sql = f"""
            SELECT "JFULL" FROM car_judgments 
            WHERE "JFULL" ilike %s AND "JFULL" ilike %s 
            ORDER BY CASE WHEN "JFULL" ilike %s THEN 0 ELSE 1 END, "JDATE" desc 
            LIMIT 3
        """
        cursor.execute(sql, (f"%車禍%", f"%{keyword}%", f"%{city}%"))
        rows = cursor.fetchall()
        cursor.close()
        conn.close()
        return [row[0][:2000].replace("\n", " ") for row in rows] if rows else []
    except:
        return []

# ==========================================
# 🤖 Gemini 3 專家決策模組 (2026 最新版)
# ==========================================
def generate_expert_report(age, job, body_part, liability, work_loss, labor_loss, dependent_support, judgments, dependents_count, city):
    if not GEMINI_API_KEY: return {"estimated_consolation": 80000, "report_text": "API Key 缺失"}
    
    judgments_text = "\n\n".join(judgments) if judgments else f"參考{city}地區最新行情。"
    other_total = labor_loss + dependent_support
    
    prompt = f"""
    你現在是台灣富邦產險的資深理賠主管，正在評估「{city}」地區的車禍理賠案。
    請針對傷勢「{body_part}」，結合傷者職業「{job}」與扶養壓力，進行「非定額」的精神慰撫金估價。
    
    🚨【理賠決策指令】：
    1. 在地化評估：請考量「{city}」的生活水準。台北地區通常較高，中南部則依實務調整。
    2. 身分與家庭加權：傷者為「{job}」，須扶養「{dependents_count}」人。律師、醫護等社經地位較高者，精神痛苦應加重補償。
    3. 嚴禁固定金額：根據傷勢(粉碎性骨折屬重傷)給予動態、有零有整的估價。
    
    必須回傳「純 JSON」格式（嚴禁包含任何 // 註解或 Markdown 標籤），包含：
    {{
        "estimated_consolation": 225000,
        "report_text": "一、地區行情與判例分析 ({city}地區)... 二、傷者身分與家庭加權 (職業 {job} 與 {dependents_count} 名家屬)... 四、總計建議理賠(含肇責{liability}%計算)..."
    }}

    【案件參數】
    - 地點：{city} | 年齡：{age} | 職業：{job} | 部位：{body_part} | 扶養：{dependents_count}人
    - 系統已知財產損失：{work_loss + other_total} 元
    - 肇責比例：我方 {liability}%
    
    【過往判例參考】
    {judgments_text}
    """
    
    try:
        # 使用剛才測試成功的模型代號
        model = genai.GenerativeModel(
            model_name='gemini-3-flash-preview',
            tools=[{"google_search_retrieval": {}}] # 開啟聯網搜尋功能
        )
        response = model.generate_content(prompt, generation_config=genai.types.GenerationConfig(temperature=0.4))
        
        # 結構化清理，防止 JSON 損毀
        clean_json = re.sub(r'```json\n?|```', '', response.text).strip()
        return json.loads(clean_json)
    except Exception as e:
        return {
            "estimated_consolation": 95000, 
            "report_text": f"自動生成報告暫時失效，請根據{city}行情手動校核。錯誤：{str(e)}"
        }

if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=8000)
