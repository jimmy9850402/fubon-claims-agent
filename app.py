from fastapi import FastAPI, Query
import psycopg2
import os
import requests
import json
import re
import uvicorn

app = FastAPI()

# ==========================================
# 🔑 環境變數設定 (請在Render後台設定)
# ==========================================
DB_URL = os.environ.get("DATABASE_URL")
OPENROUTER_API_KEY = os.environ.get("OPENROUTER_API_KEY")

# ⚖️ 法院認證：霍夫曼累計係數計算法 (法定年息 5%)
def get_hoffmann_coefficient(years: int) -> float:
    if years <= 0: return 0.0
    coefficient = 0.0
    for n in range(years):
        coefficient += 1.0 / (1 + n * 0.05)
    return round(coefficient, 6)

# 🏢 行政院主計總處 113 年各縣市平均月消費支出 (扶養費基準)
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
    return {"status": "Fubon Claims AI Agent is Online!", "engine": "OpenRouter-Gemini-2.0-Free"}

# ==========================================
# 🚀 理賠估算核心引擎 (已移除案號問項)
# ==========================================
@app.get("/evaluate")
def evaluate(
    body_part: str = Query(..., description="受傷部位"),
    salary: int = Query(..., description="月薪"),
    months: int = Query(..., description="休養月數"),
    liability: int = Query(..., description="肇責比例 (0-100)"),
    job: str = Query("一般職業", description="傷者職業"),
    age: int = Query(35, description="傷者年齡"),
    labor_loss_ratio: int = Query(0, description="勞動力減損比例"),
    dependents: int = Query(0, description="受扶養人數"),
    city: str = Query("台北市", description="居住縣市")
):
    print(f"--- ⚖️ 啟動自動化理賠評估：{city} {job} ({body_part}) ---")
    
    # 1. 檢索資料庫判例 (RAG)
    judgments = search_judgments_in_supabase(body_part, city)

    # 2. 客觀財產損失計算 (霍夫曼精算大腦)
    work_loss = salary * months
    
    labor_loss_comp = 0
    if labor_loss_ratio > 0:
        rem_years = max(0, 65 - age)
        coef = get_hoffmann_coefficient(rem_years)
        labor_loss_comp = int((salary * 12) * (labor_loss_ratio / 100) * coef)

    support_comp = 0
    if dependents > 0:
        monthly_exp = DGBAS_EXPENSES.get(city, DGBAS_EXPENSES["其他"])
        support_coef = get_hoffmann_coefficient(10) # 預設扶養 10 年
        support_comp = int((monthly_exp * 12) * dependents * support_coef)

    # 🌟 3. 呼叫 OpenRouter 進行「精神慰撫金」智慧估價與報告生成
    gemini_result = call_openrouter(
        age=age, job=job, body_part=body_part, liability=liability, 
        work_loss=work_loss, labor_loss=labor_loss_comp, 
        dependent_support=support_comp, judgments=judgments, 
        dependents_count=dependents, city=city
    )
    
    dynamic_consolation = gemini_result.get("estimated_consolation", 85000)
    tailexi_report = gemini_result.get("report_text", "報告解析失敗，請手動校核。")

    # 4. 最終金額加總與肇責相抵
    total_before_liability = work_loss + dynamic_consolation + labor_loss_comp + support_comp
    final_amount = int(total_before_liability * (liability / 100))

    return {
        "status": "success",
        "results": {
            "input_job": job,
            "input_city": city,
            "dynamic_consolation": dynamic_consolation,
            "suggested_total_before_liability": total_before_liability,
            "final_suggested_amount": final_amount,
            "tailexi_style_report": tailexi_report 
        }
    }

# ==========================================
# 🔍 判例檢索模組 (Supabase)
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
# 🧠 OpenRouter 專家大腦模組 (100% 免費版)
# ==========================================
def call_openrouter(age, job, body_part, liability, work_loss, labor_loss, dependent_support, judgments, dependents_count, city):
    if not OPENROUTER_API_KEY:
        return {"estimated_consolation": 80000, "report_text": "OpenRouter API Key 未設定"}

    judgments_text = "\n\n".join(judgments) if judgments else f"參考 {city} 地區最新實務行情。"
    other_total = labor_loss + dependent_support

    prompt = f"""
    你現在是台灣富邦產險的資深理賠主管。請針對傷勢「{body_part}」，參考內部判例與實務行情，產出一份專業的理賠建議書。
    
    【評估核心原則】：
    1. 在地化定價：考量「{city}」之生活水準。
    2. 身分加權：傷者為「{job}」，現年 {age} 歲。若有專業身分或扶養重擔({dependents_count}人)，應大幅調升慰撫金。
    3. 拒絕定額：嚴禁固定使用 8 萬。必須有零有整。
    
    必須回傳「純 JSON」格式（無任何標籤或註解），包含以下 Key：
    {{
        "estimated_consolation": 225000,
        "report_text": "一、工作損失分析... 二、慰撫金酌定因素 (考量職業 {job} 與扶養 {dependents_count} 人影響)... 三、理賠建議彙整..." 
    }}

    【個案數據】
    - 年齡：{age} | 職業：{job} | 傷勢：{body_part} | 縣市：{city}
    - 肇責：{liability}% | 受扶養：{dependents_count} 人
    - 系統精算財產損害：{work_loss + other_total} 元
    
    【過往判例參考】
    {judgments_text}
    """

    try:
        response = requests.post(
            url="https://openrouter.ai/api/v1/chat/completions",
            headers={
                "Authorization": f"Bearer {OPENROUTER_API_KEY}",
                "Content-Type": "application/json"
            },
            data=json.dumps({
                "model": "google/gemini-2.0-flash-001:free", # 💡 這裡加上 :free 確保永遠不花錢
                "messages": [{"role": "user", "content": prompt}]
            }),
            timeout=15
        )
        
        res_json = response.json()
        raw_content = res_json['choices'][0]['message']['content']
        
        # 結構化清理 JSON
        clean_json = re.sub(r'```json\n?|```', '', raw_content).strip()
        return json.loads(clean_json)
        
    except Exception as e:
        return {
            "estimated_consolation": 92000, 
            "report_text": f"自動生成中斷，請手動校核。原因：{str(e)}"
        }

if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=8000)
