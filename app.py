from fastapi import FastAPI, Query
import psycopg2
import os
import requests
import json
import re
import uvicorn

app = FastAPI()

# ==========================================
# 🔑 環境變數 (Render Settings)
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
    return {"status": "Fubon Hybrid-Search AI Online", "v": "2026.04.09.v2"}

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
    # 1. 優先從 Supabase 搜尋判例
    judgments = search_judgments(body_part, city)
    
    # 判斷是否搜尋到結果
    has_db_record = "YES" if judgments else "NO"
    print(f"--- 🔍 縣市：{city} | 資料庫是否有資料：{has_db_record} ---")

    # 2. 客觀計算
    work_loss = salary * months
    labor_loss_comp = 0
    if labor_loss_ratio > 0:
        coef = get_hoffmann_coefficient(max(0, 65 - age))
        labor_loss_comp = int((salary * 12) * (labor_loss_ratio / 100) * coef)

    support_comp = 0
    if dependents > 0:
        monthly_exp = DGBAS_EXPENSES.get(city, DGBAS_EXPENSES["其他"])
        support_comp = int((monthly_exp * 12) * dependents * get_hoffmann_coefficient(10))

    # 🌟 3. 呼叫 AI (若資料庫無資料，Prompt 會要求 AI 自行檢索)
    ai_result = call_ai_expert_hybrid(
        age=age, job=job, body_part=body_part, liability=liability, 
        work_loss=work_loss, labor_loss=labor_loss_comp, 
        support_comp=support_comp, judgments=judgments, city=city
    )
    
    dynamic_consolation = ai_result.get("estimated_consolation", 99000)
    final_report = ai_result.get("report_text", "報告生成失敗")

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

def call_ai_expert_hybrid(age, job, body_part, liability, work_loss, labor_loss, support_comp, judgments, city):
    if not OPENROUTER_API_KEY: return {"estimated_consolation": 80000, "report_text": "Key 未設定"}

    # 根據資料庫是否有結果，動態調整指令
    db_context = f"【資料庫判例參考】：\n{judgments}" if judgments else "【資料庫查無紀錄】：請根據你內建的台灣法院大數據知識，檢索「{city}」地區針對「{body_part}」的近年判賠行情進行分析。"

    prompt = f"""
    你現在是台灣產險界最資深的法律理賠專家，請比照 TaiLexi 專業法律機器人格式產出報告。
    
    【個案背景】
    - 地點：{city} | 傷者：{age}歲{job} | 傷勢：{body_part} | 肇責：{liability}%
    
    {db_context}
    
    【格式要求】：
    一、關鍵議題：列出侵權行為損害賠償(民184)與爭點。
    二、適用法條：包含民法184、193、195條之法律依據。
    三、構成要件：分析本案是否符合加害、因果、損害之要件。
    四、區域判例與數額酌定：
       - 若上方有資料庫判例，請深入解析。
       - 若無，請根據你對「{city}」地區法院(如{city}地院)之歷史判決見解，推估「{body_part}」之慰撫金合理區間。
       - 需考慮職業「{job}」之身分地位。
    五、結論與建議金額。

    請回傳「純 JSON」格式（嚴禁 Markdown 標籤或註解）：
    {{
        "estimated_consolation": 250000,
        "report_text": "Markdown 格式的長篇法律建議書"
    }}
    """

    try:
        # 使用 2026 最穩定的免費模型通道
        model_id = "google/gemini-2.0-flash-001:free"
        
        res = requests.post(
            url="https://openrouter.ai/api/v1/chat/completions",
            headers={
                "Authorization": f"Bearer {OPENROUTER_API_KEY.strip()}",
                "Content-Type": "application/json",
                "HTTP-Referer": "https://fubon-ai.render.com"
            },
            data=json.dumps({
                "model": model_id,
                "messages": [{"role": "user", "content": prompt}],
                "temperature": 0.3
            }),
            timeout=30
        )
        
        data = res.json()
        
        # 🛡️ 診斷：如果 choices 不在 JSON 裡，抓取錯誤原因
        if 'choices' not in data:
            error_msg = data.get('error', {}).get('message', 'OpenRouter 伺服器繁忙 (Free Quota Exceeded)')
            return {
                "estimated_consolation": 94444,
                "report_text": f"### ⚠️ AI 生成暫時中斷\n**原因**：{error_msg}\n\n**理賠建議**：因免費 API 額度限制，請稍候 60 秒再試。初步建議暫依本案財產損失與{city}平均行情進行核算。"
            }

        content = data['choices'][0]['message']['content']
        clean_json = re.sub(r'```json\n?|```', '', content).strip()
        return json.loads(clean_json)
    except Exception as e:
        return {"estimated_consolation": 95555, "report_text": f"💥 系統連線異常：{str(e)}"}

def search_judgments(keyword, city):
    try:
        conn = psycopg2.connect(DB_URL)
        cursor = conn.cursor()
        # 增加搜尋寬度：只要包含受傷部位或關鍵字即可
        sql = """SELECT "JFULL" FROM car_judgments WHERE "JFULL" ilike %s AND "JFULL" ilike %s LIMIT 2"""
        cursor.execute(sql, (f"%車禍%", f"%{keyword}%", f"%{city}%"))
        rows = cursor.fetchall()
        cursor.close()
        conn.close()
        return [row[0][:1200] for row in rows]
    except: return []

if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=8000)
