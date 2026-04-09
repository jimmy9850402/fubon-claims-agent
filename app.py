from fastapi import FastAPI, Query
import psycopg2
import os
import requests
import json
import re
import uvicorn

app = FastAPI()

# ==========================================
# 🔑 環境變數設定 (Render Settings)
# ==========================================
DB_URL = os.environ.get("DATABASE_URL")
OPENROUTER_API_KEY = os.environ.get("OPENROUTER_API_KEY")

# ⚖️ 專業精算：霍夫曼係數 (年息 5%)
def get_hoffmann_coefficient(years: int) -> float:
    if years <= 0: return 0.0
    return round(sum(1.0 / (1 + n * 0.05) for n in range(years)), 6)

@app.get("/")
def home():
    return {"status": "TaiLexi-Fubon AI is Live!", "engine": "OpenRouter-Auto-Fallback"}

@app.get("/evaluate")
def evaluate(
    body_part: str = Query(..., description="受傷部位"),
    salary: int = Query(..., description="月薪"),
    months: int = Query(..., description="休養月數"),
    liability: int = Query(..., description="肇責比例 (0-100)"),
    job: str = Query("一般職業", description="職業"),
    age: int = Query(35, description="年齡"),
    labor_loss_ratio: int = Query(0, description="勞動力減損比"),
    city: str = Query("台北市", description="居住縣市")
):
    # 1. 檢索資料庫判例 (RAG)
    judgments = search_judgments(body_part, city)
    
    # 2. 客觀損失精算
    work_loss = salary * months
    labor_loss_comp = 0
    if labor_loss_ratio > 0:
        coef = get_hoffmann_coefficient(max(0, 65 - age))
        labor_loss_comp = int((salary * 12) * (labor_loss_ratio / 100) * coef)

    # 🌟 3. 呼叫 AI (使用 openrouter/auto 自動尋找最穩模型)
    ai_result = call_ai_expert(age, job, body_part, liability, city, judgments)
    
    dynamic_consolation = ai_result.get("estimated_consolation", 100000)
    tailexi_report = ai_result.get("report_text", "報告解析中斷。")

    # 4. 總額彙整與肇責計算
    total_estimated = work_loss + labor_loss_comp + dynamic_consolation
    final_amount = int(total_estimated * (liability / 100))

    return {
        "status": "success",
        "results": {
            "input_city": city,
            "dynamic_consolation": dynamic_consolation,
            "final_suggested_amount": final_amount,
            "tailexi_style_report": tailexi_report 
        }
    }

def call_ai_expert(age, job, body_part, liability, city, judgments):
    if not OPENROUTER_API_KEY: return {"estimated_consolation": 80000, "report_text": "Key Error"}

    # 核心邏輯：若資料庫為空，改由 AI 模擬區域法院見解
    db_context = f"【參考資料庫判例】：\n{judgments}" if judgments else f"【⚠️ 資料庫查無紀錄】：請根據您對『{city}地方法院』歷年車禍判決之大數據知識，模擬分析『{body_part}』之數額酌定。"

    prompt = f"""
    你現在是台灣富邦產險最資深的理賠法務專家。請產出專業法律建議書。
    地點：{city} | 傷者：{age}歲{job} | 傷勢：{body_part} | 肇責：{liability}%
    {db_context}
    
    【格式要求 - 比照 TaiLexi 專業格式】：
    一、關鍵議題：分析本案請求權基礎與爭點。
    二、適用法條：詳述《民法》第 184 條、193 條及 195 條之適用。
    三、構成要件：分析是否符合加害行為、權利侵害、因果關係。
    四、區域判例與數額酌定：
       - 請針對『{city}地方法院』之判賠行情進行深度分析。
       - 考量職業『{job}』之社經地位進行慰撫金加權計算。
    五、結論：建議最終總理賠金額(全損與肇責相抵後)與溝通策略。

    必須回傳純 JSON 格式：
    {{ "estimated_consolation": 數字, "report_text": "Markdown 報告內容" }}
    """

    try:
        res = requests.post(
            url="https://openrouter.ai/api/v1/chat/completions",
            headers={
                "Authorization": f"Bearer {OPENROUTER_API_KEY.strip()}",
                "Content-Type": "application/json",
                "HTTP-Referer": "https://fubon-ai.render.com"
            },
            data=json.dumps({
                "model": "openrouter/auto", 
                "messages": [{"role": "user", "content": prompt}],
                "temperature": 0.3
            }),
            timeout=40
        )
        data = res.json()
        content = data['choices'][0]['message']['content']
        clean_json = re.sub(r'```json\n?|```', '', content).strip()
        return json.loads(clean_json)
    except:
        return {"estimated_consolation": 98000, "report_text": "AI 繁忙，請稍後再試。"}

def search_judgments(keyword, city):
    try:
        conn = psycopg2.connect(DB_URL)
        cur = conn.cursor()
        sql = """SELECT "JFULL" FROM car_judgments WHERE "JFULL" ilike %s AND "JFULL" ilike %s LIMIT 2"""
        cur.execute(sql, (f"%車禍%", f"%{keyword}%", f"%{city}%"))
        rows = cur.fetchall()
        cur.close()
        conn.close()
        return [row[0][:1200] for row in rows]
    except: return []

if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=8000)
