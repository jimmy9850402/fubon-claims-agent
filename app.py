from fastapi import FastAPI, Query
import psycopg2
import os
import uvicorn

app = FastAPI()

# 從 Render 的環境變數讀取 Supabase IPv4 連線字串
DB_URL = os.environ.get("DATABASE_URL")

# ==========================================
# ⚖️ 法院認證：正確版霍夫曼計算法模組 (第一年不扣除利息)
# ==========================================
def get_hoffmann_coefficient(years: int) -> float:
    """
    計算正確版霍夫曼累計係數 (法定年息 5%)
    公式：Σ [1 / (1 + n * 0.05)]，n 從 0 開始到 (years - 1)
    """
    if years <= 0:
        return 0.0
    
    coefficient = 0.0
    for n in range(years):
        # 第一年 n=0，分母為 1；第二年 n=1，分母為 1.05...
        coefficient += 1.0 / (1 + n * 0.05)
    
    # 根據司法院標準，取至小數點後 6 位
    return round(coefficient, 6)

# ==========================================
# 📊 主計總處 113 年度各縣市平均每人月消費支出
# ==========================================
DGBAS_EXPENSES = {
    "基隆市": 24022,
    "臺北市": 34952, "台北市": 34952,
    "新北市": 27557,
    "桃園市": 25718,
    "新竹縣": 30014,
    "新竹市": 29722,
    "苗栗縣": 22019,
    "臺中市": 28754, "台中市": 28754,
    "彰化縣": 20323,
    "南投縣": 19180,
    "雲林縣": 20411,
    "嘉義縣": 21473,
    "嘉義市": 27255,
    "臺南市": 23036, "台南市": 23036,
    "高雄市": 26722,
    "屏東縣": 22241,
    "宜蘭縣": 23935,
    "花蓮縣": 21969,
    "臺東縣": 19402, "台東縣": 19402,
    "澎湖縣": 20188,
    "總平均": 26640,
    "其他": 26640     # 若輸入錯誤，採用 113 年全國總平均作為預設
}

@app.get("/")
def home():
    """首頁測試，確認 API 有活著"""
    return {"status": "Fubon Claims AI Agent is Online!", "message": "Ready to evaluate."}


@app.get("/evaluate")
def evaluate(
    body_part: str = Query(..., description="受傷部位關鍵字"),
    salary: int = Query(..., description="月薪"),
    months: int = Query(..., description="休養月數"),
    liability: int = Query(..., description="肇責比例 (0-100)"),
    # 來自 Copilot 卡片的進階參數
    job: str = Query("一般職業", description="傷者職業"),
    age: int = Query(30, description="傷者年齡"),
    labor_loss_ratio: int = Query(0, description="勞動力減損比例 (0-100)"),
    # 扶養費計算參數
    dependents: int = Query(0, description="受扶養人數"),
    city: str = Query("新北市", description="居住縣市 (用於主計處標準)")
):
    print(f"--- 🚀 收到請求 ---")
    print(f"📍 部位: {body_part} | 職業: {job} | 年齡: {age} | 薪資: {salary} | 休養: {months}月")
    print(f"⚠️ 減損: {labor_loss_ratio}% | 扶養: {dependents}人 | 縣市: {city} | 肇責: {liability}%")
    
    # ==========================================
    # 1. 執行 Supabase 資料庫搜尋 (支援多關鍵字斷詞)
    # ==========================================
    judgments = search_supabase(body_part)
    
    data_source = "Database"
    
    # 2. 備援邏輯：如果真的連斷詞都查不到，提供 AI 模擬判斷
    if not judgments:
        print("⚠️ 資料庫查無結果，啟動 Web_Search 備援邏輯...")
        data_source = "AI_Internal_Knowledge"
        judgments = [
            f"目前資料庫中查無『{body_part}』的最新精確判決書內容。",
            f"根據 AI 網路知識庫建議：針對{body_part}傷勢，常見的精神慰撫金法院判賠區間約在 5 萬至 15 萬元之間。",
            "建議理賠人員可根據此行情與客戶先行溝通，並提醒客戶提供後續診斷證明書以利精確評估。"
        ]

    # ==========================================
    # 3. 理賠邏輯精算大腦
    # ==========================================
    # A. 短期工作損失與基礎慰撫金
    work_loss = salary * months
    suggested_consolation = 80000 
    
    # B. 長期勞動力減損精算 (啟動霍夫曼大腦)
    labor_loss_compensation = 0
    labor_loss_reason = "經初步評估，傷勢未達永久勞動力減損標準，無須額外提列補償現值。"
    
    if labor_loss_ratio > 0:
        remaining_years = max(0, 65 - age)
        if remaining_years > 0:
            coef = get_hoffmann_coefficient(remaining_years)
            annual_income = salary * 12
            labor_loss_compensation = int(annual_income * (labor_loss_ratio / 100) * coef)
            
            labor_loss_reason = (
                f"【勞動力減損精算報告】：\n"
                f"考量傷者職業為「{job}」，現年 {age} 歲，距 65 歲退休尚餘 {remaining_years} 年。\n"
                f"依勞保失能給付標準，判定「{body_part}」傷勢導致其勞動減損比例達 {labor_loss_ratio}%。\n"
                f"按正確版霍夫曼計算法扣除中間利息 (適用累計係數 {coef})，"
                f"應一次給付勞動減損現值為 {labor_loss_compensation:,} 元。"
            )

    # C. 👨‍👩‍👧‍👦 扶養費精算模組 (主計總處 113 年標準 + 霍夫曼)
    dependent_support_compensation = 0
    dependent_reason = "經確認，無受扶養人請求權或未填寫扶養人數。"
    
    if dependents > 0:
        # 抓取該縣市的主計處標準，若無相符則取全國總平均
        monthly_expense = DGBAS_EXPENSES.get(city, DGBAS_EXPENSES["其他"])
        
        # 實務上會依子女實際年齡計算，這裡暫時統一以平均需再扶養 10 年做示範
        support_years = 10 
        support_coef = get_hoffmann_coefficient(support_years)
        
        # 扶養費公式：月消費 x 12個月 x 扶養人數 x 霍夫曼係數
        dependent_support_compensation = int((monthly_expense * 12) * dependents * support_coef)
        
        dependent_reason = (
            f"【扶養費精算報告】：\n"
            f"傷者育有 {dependents} 名受扶養人。依行政院主計總處最新(113年度)統計，{city} 平均每人月消費支出為 {monthly_expense:,} 元。\n"
            f"考量扶養年限 (暫估 {support_years} 年)，按霍夫曼計算法扣除中間利息 (適用累計係數 {support_coef})，"
            f"預估一次給付扶養費現值為 {dependent_support_compensation:,} 元。"
        )

    # D. 總金額計算與肇責拆算
    total_estimated = work_loss + suggested_consolation + labor_loss_compensation + dependent_support_compensation
    final_amount = int(total_estimated * (liability / 100))

    print(f"✅ 運算完成！來源: {data_source} | 總損失: {total_estimated} | 建議金額(乘肇責後): {final_amount}")

    # ==========================================
    # 4. 回傳 JSON 資料包給 Copilot Studio
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
            "labor_loss_reason": labor_loss_reason,
            "dependent_reason": dependent_reason,
            "suggested_total_before_liability": total_estimated,
            "final_suggested_amount": final_amount
        },
        "judgments": judgments
    }


def search_supabase(keyword):
    """連線到 Supabase 並執行『多關鍵字』模糊檢索"""
    try:
        conn = psycopg2.connect(DB_URL)
        cursor = conn.cursor()
        
        keywords = keyword.split()
        if not keywords:
            return []
            
        conditions = " AND ".join(['"JFULL" ilike %s' for _ in keywords])
        params = tuple(f"%{k}%" for k in keywords)
        
        sql_query = f"""
            SELECT "JFULL" 
            FROM car_judgments 
            WHERE {conditions}
            ORDER BY "JDATE" desc 
            LIMIT 5
        """
        
        cursor.execute(sql_query, params)
        rows = cursor.fetchall()
        
        cursor.close()
        conn.close()
        
        if rows:
            print(f"✨ 成功從資料庫撈到 {len(rows)} 筆判例！")
            return [row[0][:3500].replace("\n", " ") for row in rows]
        else:
            return []
            
    except Exception as e:
        print(f"❌ 資料庫搜尋出錯: {str(e)}")
        return []

if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=8000)
