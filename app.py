from fastapi import FastAPI, Query
import psycopg2
import os
import requests
import json
import re
import uvicorn

app = FastAPI()

# ==========================================
# 🔑 環境變數
# ==========================================
DB_URL = os.environ.get("DATABASE_URL")
OPENROUTER_API_KEY = os.environ.get("OPENROUTER_API_KEY")

def get_hoffmann_coefficient(years: int) -> float:
    if years <= 0: return 0.0
    return round(sum(1.0 / (1 + n * 0.05) for n in range(years)), 6)

DGBAS_EXPENSES = {
    "臺北市": 34952, "台北市": 34952, "新北市": 27557, "桃園市": 25718, 
    "臺中市": 28754, "台中市": 28754, "臺南市": 23036, "高雄市": 26722, "其他": 26640     
}

@app.get("/")
def home():
    return {"status": "TaiLexi-Level Fubon AI Online!", "v": "2026.04.09"}

@app.get("/evaluate")
def evaluate(
    body_part: str = Query(..., description="受傷部位"),
    salary: int = Query(..., description="月薪"),
    months: int = Query(..., description="休養月數"),
    liability: int = Query(..., description="肇責比例"),
    job: str = Query("一般職業", description="職業"),
    age: int = Query(35, description="年齡"),
    labor_loss_ratio: int = Query(0, description="勞力減損比"),
    dependents: int = Query(0, description="扶養人數"),
    city: str = Query("台北市", description="居住縣市")
):
    judgments = search_judgments(body_part, city)
    work_loss = salary * months
    labor_loss_comp = 0
    if labor_loss_ratio > 0:
        coef = get_hoffmann_coefficient(max(0, 65 - age))
        labor_loss_comp = int((salary * 12) * (labor_loss_ratio / 100) * coef)

    support_comp = 0
    if dependents > 0:
        monthly_exp = DGBAS_EXPENSES.get(city, DGBAS_EXPENSES["其他"])
        support_comp = int((monthly_exp * 12) * dependents * get_hoffmann_coefficient(10))

    # 🌟 呼叫 AI
    ai_result = call_ai_expert(
        age=age, job=job, body_part=body_part, liability=liability, 
        work_loss=work_loss, labor_loss=labor_loss_comp, 
        support_comp=support_comp, judgments=judgments, city=city
    )
    
    dynamic_consolation = ai_result.get("estimated_consolation", 92000)
    final_report = ai_result.get("report_text", "分析生成失敗")

    total_before = work_loss + dynamic_consolation + labor_loss_comp + support_comp
    final_amount = int(total_before * (liability / 100))

    return {
        "status": "success",
        "results": {
            "dynamic_consolation": dynamic_consolation,
            "final_suggested_amount": final_amount,
            "tailexi_style_report": final_report 
        }
    }

def call_ai_expert(age, job, body_part, liability, work_loss, labor_loss, support_comp, judgments, city):
    if not OPENROUTER_API_KEY: return {"estimated_consolation": 80000, "report_text": "Key Error"}

    prompt = f"""
    你現在是台灣富邦產險最資深的法律理賠專家，請比照 TaiLexi AI 格式產出「理賠分析建議書」。
    地點：{city} | 傷者：{age}歲{job} | 傷勢：{body_part} | 肇責：{liability}%
    
    必須包含：一、關鍵議題 二、適用法條(民184,193,195) 三、構成要件 四、區域判例({city})與數額酌定 五、結論。
    必須回傳純 JSON：{{"estimated_consolation": 數字, "report_text": "Markdown 報告"}}
    """

    try:
        # 💡 嘗試使用 OpenRouter 2026 最穩定的免費代號
        # 如果這個不行，可以換成 "meta-llama/llama-3.1-405b-instruct:free" 測試
        model_id = "google/gemini-2.0-flash-001:free" 
        
        res = requests.post(
            url="https://openrouter.ai/api/v1/chat/completions",
            headers={
                "Authorization": f"Bearer {OPENROUTER_API_KEY.strip()}",
                "Content-Type": "application/json",
                "HTTP-Referer": "https://fubon-ai.render.com", # OpenRouter 有時需要這個
            },
            data=json.dumps({
                "model": model_id,
                "messages": [{"role": "user", "content": prompt}],
                "temperature": 0.3
            }),
            timeout=25
        )
        
        data = res.json()
        
        # 🔍 診斷邏輯：如果沒有 choices，就印出錯誤訊息
        if 'choices' not in data:
            error_detail = data.get('error', {}).get('message', '未知錯誤')
            return {
                "estimated_consolation": 91111,
                "report_text": f"❌ OpenRouter 拒絕請求：{error_detail}\n模型代號：{model_id}"
            }

        content = data['choices'][0]['message']['content']
        clean_json = re.sub(r'```json\n?|```', '', content).strip()
        return json.loads(clean_json)
    except Exception as e:
        return {"estimated_consolation": 92222, "report_text": f"💥 程式執行出錯：{str(e)}"}

def search_judgments(keyword, city):
    try:
        conn = psycopg2.connect(DB_URL)
        cursor = conn.cursor()
        sql = """SELECT "JFULL" FROM car_judgments WHERE "JFULL" ilike %s AND "JFULL" ilike %s LIMIT 2"""
        cursor.execute(sql, (f"%車禍%", f"%{keyword}%", f"%{city}%"))
        rows = cursor.fetchall()
        cursor.close()
        conn.close()
        return [row[0][:1000] for row in rows]
    except: return []

if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=8000)
