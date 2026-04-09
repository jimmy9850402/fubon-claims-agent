from fastapi import FastAPI, Query
import psycopg2
import os
import requests
import json
import re
import uvicorn
from ddgs import DDGS  # 🌐 載入最新版免費網路爬蟲套件

app = FastAPI()

# ==========================================
# 🔑 環境變數設定
# ==========================================
DB_URL = os.environ.get("DATABASE_URL")
OPENROUTER_API_KEY = os.environ.get("OPENROUTER_API_KEY")

# ⚖️ 霍夫曼係數計算 (年息 5%)
def get_hoffmann_coefficient(years: int) -> float:
    if years <= 0: return 0.0
    return round(sum(1.0 / (1 + n * 0.05) for n in range(years)), 6)

# 🏢 主計處 113 年各縣市平均月消費支出
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
    return {"status": "Fubon Agent is Live", "version": "Web-Search-Enabled"}

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
    medical_fee: int = Query(0, description="醫療費用")
):
    # 1. 優先搜尋內部資料庫
    db_judgments = search_judgments(body_part, city)
    context_info = ""
    
    # 🌟 2. 智慧 Fallback：資料庫找不到，啟動 DuckDuckGo 網路爬蟲
    if db_judgments:
        context_info = f"【內部資料庫判例】：\n" + "\n".join(db_judgments)
    else:
        print(f"⚠️ 資料庫查無 {body_part} 紀錄，觸發聯網搜尋...")
        # 💡 精煉搜尋關鍵字：去掉冗言贅字，只留最核心的名詞
        clean_body_part = body_part.replace("併發", " ").replace("造成", " ")
        search_query = f"車禍 {clean_body_part} 精神慰撫金 判決"
        web_results = search_web_judgments(search_query)
        
        if web_results:
            context_info = f"【網路即時搜尋判例與法理見解】(內部資料庫無紀錄，啟動聯網輔助)：\n{web_results}"
        else:
            context_info = f"【⚠️ 提醒】：內部資料庫與網路搜尋皆無具體紀錄，請根據您對台灣地方法院歷年車禍損害賠償判決之專業知識進行法理模擬分析。"

    # 3. 客觀財務損失精算
    work_loss = salary * months
    
    labor_loss_comp = 0
    if labor_loss_ratio > 0:
        coef = get_hoffmann_coefficient(max(0, 65 - age))
        labor_loss_comp = int((salary * 12) * (labor_loss_ratio / 100) * coef)

    support_comp = 0
    if dependents > 0:
        monthly_exp = DGBAS_EXPENSES.get(city, DGBAS_EXPENSES["其他"])
        support_comp = int((monthly_exp * 12) * dependents * get_hoffmann_coefficient(10))

    # 4. 呼叫「多層級」AI 專家模擬慰撫金與報告
    ai_result = call_ai_with_fallback(age, job, body_part, liability, city, context_info)
    
    dynamic_consolation = ai_result.get("estimated_consolation", 98000)
    final_report = ai_result.get("report_text", "報告產出失敗。")

    # 5. 總理賠金額計算
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
# 🌐 免費網路爬蟲模組 (DuckDuckGo)
# ==========================================
def search_web_judgments(query):
    try:
        print(f"🌐 執行爬蟲: {query}")
        # 使用最新的 ddgs 套件進行搜尋
        results = DDGS().text(query, region='tw-tz', max_results=3)
        results_list = list(results)
        
        if not results_list: return ""
        
        # 將抓到的標題與內文摘要組合起來
        web_context = "\n".join([f"- {r.get('title', '無標題')}: {r.get('body', '')}" for r in results_list])
        return web_context
    except Exception as e:
        print(f"⚠️ 網路搜尋失敗: {e}")
        return ""

# ==========================================
# 🧠 AI 備援與調度中心
# ==========================================
def call_ai_with_fallback(age, job, body_part, liability, city, context_info):
    model_list = [
        "google/gemma-4-31b-it:free",
        "meta-llama/llama-3.3-70b-instruct:free",
        "openrouter/auto"
    ]
    
    prompt = f"""
    你現在是台灣富邦產險最資深的理賠法務專家。請產出專業法律建議書。
    地點：{city} | 傷者：{age}歲{job} | 傷勢：{body_part} | 肇責：{liability}%
    {context_info}
    
    格式：一、關鍵議題 二、適用法條(民法184,193,195) 三、構成要件 四、區域判例分析(請優先引述上方提供之判例或法理資訊) 五、結論與談判策略。
    必須回傳純 JSON：{{"estimated_consolation": 數字, "report_text": "Markdown 報告"}}
    """

    for model_id in model_list:
        try:
            print(f"⏳ 嘗試呼叫模型: {model_id}...")
            if not OPENROUTER_API_KEY: raise ValueError("未設定 API KEY")

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
                timeout=45
            )
            
            data = res.json()
            if 'choices' in data and len(data['choices']) > 0:
                print(f"✅ 模型 {model_id} 成功！")
                content = data['choices'][0]['message']['content']
                clean_json = re.sub(r'```json\n?|```', '', content).strip()
                return json.loads(clean_json)
        except:
            continue
            
    return {
        "estimated_consolation": 98000, 
        "report_text": "### ⚠️ AI 伺服器目前繁忙，請稍候再試。"
    }

# ==========================================
# 🔍 內部資料庫檢索
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
