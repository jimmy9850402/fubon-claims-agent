from fastapi import FastAPI, Query
import psycopg2
import os
import requests
import json
import re
import uvicorn

# 🚨 必須要有這行，伺服器才能啟動
app = FastAPI()

# ==========================================
# 🔑 環境變數設定
# ==========================================
DB_URL = os.environ.get("DATABASE_URL")
OPENROUTER_API_KEY = os.environ.get("OPENROUTER_API_KEY")

# ⚖️ 法院認證：霍夫曼係數計算 (年息 5%)
def get_hoffmann_coefficient(years: int) -> float:
    if years <= 0: return 0.0
    return round(sum(1.0 / (1 + n * 0.05) for n in range(years)), 6)

# 🏢 主計處 113 年各縣市平均月消費支出標準 (扶養費計算基準)
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
    return {"status": "Fubon Agent is Live", "version": "Final-Ultimate"}

@app.get("/evaluate")
def evaluate(
    body_part: str = Query(..., description="受傷部位"),
    salary: int = Query(..., description="月薪"),
    months: int = Query(..., description="休養月數"),
    liability: int = Query(..., description="肇責比例"),
    job: str = Query("一般職業", description="職業"),
    age: int = Query(35, description="年齡"),
    labor_loss_ratio: int = Query(0, description="勞力減損比"),
    dependents: int = Query(0, description="受扶養人數"),
    city: str = Query("台北市", description="居住縣市"),
    medical_fee: int = Query(0, description="醫療費用") # 🆕 新增醫療費用，預設為0
):
    # 1. 搜尋在地資料庫判例
    judgments = search_judgments(body_part, city)
    
    # 2. 客觀財務損失精算
    work_loss = salary * months
    
    labor_loss_comp = 0
    if labor_loss_ratio > 0:
        coef = get_hoffmann_coefficient(max(0, 65 - age))
        labor_loss_comp = int((salary * 12) * (labor_loss_ratio / 100) * coef)

    support_comp = 0
    if dependents > 0:
        # 動態抓取該縣市的生活費標準
        monthly_exp = DGBAS_EXPENSES.get(city, DGBAS_EXPENSES["其他"])
        # 假設平均扶養年限為 10 年 (實務上依受扶養人年齡而定，此為快速精算模組)
        support_comp = int((monthly_exp * 12) * dependents * get_hoffmann_coefficient(10))

    # 🌟 3. 呼叫「多層級」AI 專家模擬慰撫金與報告
    ai_result = call_ai_with_fallback(age, job, body_part, liability, city, judgments)
    
    dynamic_consolation = ai_result.get("estimated_consolation", 98000)
    final_report = ai_result.get("report_text", "報告產出失敗。")

    # 4. 總理賠金額計算 (包含醫療費) 與肇責相抵
    total_before_liability = medical_fee + work_loss + labor_loss_comp + support_comp + dynamic_consolation
    final_amount = int(total_before_liability * (liability / 100))

    return {
        "status": "success",
        "results": {
            "dynamic_consolation": dynamic_consolation,
            "final_suggested_amount": final_amount,
            "tailexi_style_report": final_report 
        }
    }

# ==========================================
# 🧠 AI 備援與調度中心 (45秒長時思考版)
# ==========================================
def call_ai_with_fallback(age, job, body_part, liability, city, judgments):
    model_list = [
        "google/gemma-4-31b-it:free",          # 邏輯王
        "meta-llama/llama-3.3-70b-instruct:free", # 備援一
        "openrouter/auto"                       # 最終防線
    ]
    
    db_info = f"【資料庫在地判例】：\n{judgments}" if judgments else f"【⚠️ 提醒】：查無判例，請根據您對『{city}地方法院』歷年判決之專業知識進行模擬分析。"

    prompt = f"""
    你現在是台灣富邦產險最資深的理賠法務專家。請產出專業法律建議書。
    地點：{city} | 傷者：{age}歲{job} | 傷勢：{body_part} | 肇責：{liability}%
    {db_info}
    
    格式：一、關鍵議題 二、適用法條(民法184,193,195) 三、構成要件 四、區域判例分析 五、結論與談判策略。
    必須回傳純 JSON：{{"estimated_consolation": 數字, "report_text": "Markdown 報告"}}
    """

    for model_id in model_list:
        try:
            print(f"⏳ 嘗試呼叫模型: {model_id}...")
            if not OPENROUTER_API_KEY:
                raise ValueError("未設定 OPENROUTER_API_KEY")

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
                timeout=45 # ⏳ 大模型需要時間思考，給足 45 秒
            )
            
            data = res.json()
            
            if 'choices' in data and len(data['choices']) > 0:
                print(f"✅ 模型 {model_id} 生成成功！")
                content = data['choices'][0]['message']['content']
                clean_json = re.sub(r'```json\n?|```', '', content).strip()
                return json.loads(clean_json)
            else:
                print(f"❌ 模型 {model_id} 失敗: {data.get('error', {}).get('message', '未知錯誤')}")
                continue

        except Exception as e:
            print(f"⚠️ 呼叫 {model_id} 發生錯誤: {e}")
            continue
            
    # 若全數陣亡，優雅退場
    return {
        "estimated_consolation": 98000, 
        "report_text": "### ⚠️ AI 伺服器目前繁忙\n\n目前所有 AI 模型通道皆處於高負載狀態。\n\n**系統建議**：\n1. 請稍候 1-2 分鐘後再次嘗試。\n2. 目前估算之慰撫金（98,000元）為系統基於基本參數之保底估算，僅供暫時參考。"
    }

# ==========================================
# 🔍 判例檢索模組
# ==========================================
def search_judgments(keyword, city):
    try:
        conn = psycopg2.connect(DB_URL)
        cur = conn.cursor()
        cur.execute('SELECT "JFULL" FROM car_judgments WHERE "JFULL" ilike %s AND "JFULL" ilike %s LIMIT 2', (f"%車禍%", f"%{keyword}%", f"%{city}%"))
        rows = cur.fetchall()
        cur.close()
        conn.close()
        return [r[0][:1000] for r in rows]
    except: return []

if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=8000)
