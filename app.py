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

# 🌟 啟動 Google Gemini 模型大腦
if GEMINI_API_KEY:
    genai.configure(api_key=GEMINI_API_KEY)

# ==========================================
# ⚖️ 法院認證：正確版霍夫曼計算法模組 (第一年不扣除利息)
# ==========================================
def get_hoffmann_coefficient(years: int) -> float:
    if years <= 0:
        return 0.0
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
    return {"status": "Fubon Claims AI Agent is Online! (Dynamic Gemini Pricing)", "message": "Ready to evaluate."}


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
    print(f"--- 🚀 收到請求 ---")
    print(f"📍 部位: {body_part} | 職業: {job} | 年齡: {age} | 薪資: {salary} | 休養: {months}月")
    
    # ==========================================
    # 1. 執行 Supabase 資料庫搜尋 (RAG)
    # ==========================================
    judgments = search_supabase(body_part)
    data_source = "Hybrid (Supabase + Google Web Search)"
    
    # 2. 備援邏輯
    if not judgments:
        print("⚠️ 資料庫查無結果，將完全依賴 Gemini 聯網搜尋...")

    # ==========================================
    # 3. 理賠邏輯精算大腦 (明確計算得出的客觀損失)
    # ==========================================
    work_loss = salary * months
    
    labor_loss_compensation = 0
    labor_loss_reason = "經初步評估，傷勢未達永久勞動力減損標準，無須額外提列補償現值。"
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
        support_coef = get_hoffmann_coefficient(10)
        dependent_support_compensation = int((monthly_expense * 12) * dependents * support_coef)
        dependent_reason = f"依主計處標準與霍夫曼係數 {support_coef} 精算現值為 {dependent_support_compensation:,} 元。"

    # ==========================================
    # 🌟 4. 呼叫 Gemini 進行「動態定價」與報告生成
    # ==========================================
    gemini_result = generate_report_with_gemini(
        age=age, job=job, body_part=body_part, liability=liability, 
        work_loss=work_loss, labor_loss=labor_loss_compensation, 
        dependent_support=dependent_support_compensation, 
        judgments=judgments
    )
    
    # 解析 Gemini 吐出來的 JSON 結果 (取代寫死的 80000)
    dynamic_consolation = gemini_result.get("estimated_consolation", 80000)
    tailexi_report = gemini_result.get("report_text", "報告生成失敗。")

    # ==========================================
    # 5. 總金額計算與肇責拆算
    # ==========================================
    total_estimated = work_loss + dynamic_consolation + labor_loss_compensation + dependent_support_compensation
    final_amount = int(total_estimated * (liability / 100))

    print(f"✅ 運算完成！Gemini 動態慰撫金: {dynamic_consolation} | 最終總建議金額: {final_amount}")

    # ==========================================
    # 6. 回傳 JSON 資料包給 Copilot Studio
    # ==========================================
    return {
        "status": "success",
        "data_source": data_source,
        "results": {
            "input_job": job,
            "input_age": age,
            "input_body_part": body_part,
            "calculated_work_loss": work_loss,
            "calculated_labor_loss": labor_loss_compensation,
            "calculated_dependent_support": dependent_support_compensation,
            "dynamic_consolation": dynamic_consolation, # ✅ 把 Gemini 算出的慰撫金傳給前端
            "labor_loss_reason": labor_loss_reason,
            "dependent_reason": dependent_reason,
            "suggested_total_before_liability": total_estimated,
            "final_suggested_amount": final_amount,
            "tailexi_style_report": tailexi_report # ✅ 包含完整 Markdown 報告
        }
    }


def search_supabase(keyword):
    """連線到 Supabase 並執行『多關鍵字』模糊檢索，加入車禍防呆"""
    try:
        conn = psycopg2.connect(DB_URL)
        cursor = conn.cursor()
        
        keywords = keyword.split()
        if not keywords: return []
            
        base_conditions = '("JFULL" ilike \'%車禍%\' OR "JFULL" ilike \'%交通事故%\')'
        keyword_conditions = " AND ".join(['"JFULL" ilike %s' for _ in keywords])
        params = tuple(f"%{k}%" for k in keywords)
        
        sql_query = f"""
            SELECT "JFULL" 
            FROM car_judgments 
            WHERE {base_conditions} AND ({keyword_conditions})
            ORDER BY "JDATE" desc LIMIT 3
        """
        
        cursor.execute(sql_query, params)
        rows = cursor.fetchall()
        cursor.close()
        conn.close()
        
        if rows:
            print(f"✨ 成功從資料庫撈到 {len(rows)} 筆判例！")
            return [row[0][:3000].replace("\n", " ") for row in rows]
        return []
            
    except Exception as e:
        print(f"❌ 資料庫搜尋出錯: {str(e)}")
        return []

# ==========================================
# 🤖 Gemini 報告生成模組 (JSON 結構化輸出)
# ==========================================
def generate_report_with_gemini(age, job, body_part, liability, work_loss, labor_loss, dependent_support, judgments):
    """交由 Gemini 綜合推理、查網頁與排版，並嚴格輸出 JSON"""
    if not GEMINI_API_KEY:
        return {"estimated_consolation": 80000, "report_text": "⚠️ 未設定 GEMINI_API_KEY。"}
        
    judgments_text = "\n\n".join(judgments) if judgments else "⚠️ 內部資料庫無完全吻合之判例，請連上 Google 搜尋最新實務見解。"
    other_comp = labor_loss + dependent_support
    
    prompt = f"""
    你現在是一位台灣資深車禍理賠法務。請綜合【本案資訊】、【內部判例】，並「自動連上網路搜尋」最新實務行情，來精確評估「精神慰撫金」的合理金額，並撰寫專業的理賠和解建議書。

    🚨【AI 慰撫金估價守則】(非常重要)：
    請務必依據傷勢（{body_part}）的嚴重程度、復原期，以及傷者職業（{job}）動態估算精神慰撫金。
    參考基準：小擦傷約 1~3 萬；一般骨折約 5~15 萬；嚴重粉碎性骨折或重傷應給予 15 萬~50 萬以上。
    請綜合你查到的網路判決新聞與內部判例，給出一個你認為最精準的「單一整數金額」。

    請務必回傳純 JSON 格式（不要加上 ```json 標籤），必須包含以下兩個 Key：
    {{
        "estimated_consolation": 120000,  // 請填入你評估的最合理精神慰撫金「整數金額」
        "report_text": "一、工作損失... 二、慰撫金數額之酌定因素... 六、最終建議理賠金額..." // 這是 Markdown 格式的完整報告。報告內的「精神慰撫金」請填寫你剛剛評估的金額；「最終建議理賠金額」請務必將工作損失、勞動力減損、扶養費與精神慰撫金加總後，再乘以肇責比例({liability}%)來精確計算。
    }}

    【本案資訊】
    - 傷者年齡：{age} 歲
    - 職業：{job}
    - 受傷部位：{body_part}
    - 肇責比例：我方 {liability}%
    - 系統已確定之工作損失：{work_loss} 元
    - 系統已確定之勞動力/扶養費現值：{other_comp} 元

    【內部過往判例】
    {judgments_text}
    """
    
    try:
        print("🧠 正在呼叫 Gemini 生成動態定價與分析報告...")
        model = genai.GenerativeModel(
            model_name='gemini-1.5-pro',
            tools=[{"google_search_retrieval": {}}]
        )
        
        # 溫度設為 0.4 提供推理彈性，使其估價更貼近真實行情
        response = model.generate_content(
            prompt,
            generation_config=genai.types.GenerationConfig(temperature=0.4)
        )
        
        # 清洗可能出現的 Markdown JSON 標籤
        clean_text = re.sub(r'```json\n?', '', response.text)
        clean_text = re.sub(r'```\n?', '', clean_text)
        
        result_dict = json.loads(clean_text)
        return result_dict
        
    except Exception as e:
        print(f"❌ Gemini JSON 解析錯誤: {str(e)}")
        return {
            "estimated_consolation": 80000, 
            "report_text": f"報告生成或格式解析失敗。請確認 Gemini 回傳了正確的 JSON 格式。錯誤訊息：{str(e)}"
        }

if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=8000)
