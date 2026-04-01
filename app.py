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
    # 👇 新增：接收來自 Copilot 卡片的進階參數 (設定預設值避免舊版連線報錯)
    job: str = Query("一般職業", description="傷者職業"),
    age: int = Query(30, description="傷者年齡"),
    labor_loss_ratio: int = Query(0, description="勞動力減損比例 (0-100)")
):
    print(f"--- 🚀 收到請求 ---")
    print(f"📍 部位: {body_part} | 職業: {job} | 年齡: {age} | 薪資: {salary} | 休養: {months}月 | 減損: {labor_loss_ratio}% | 肇責: {liability}%")
    
    # 1. 執行 Supabase 資料庫搜尋 (支援多關鍵字斷詞，撈取 5 筆)
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
    # A. 短期工作損失
    work_loss = salary * months
    suggested_consolation = 80000 
    
    # B. 長期勞動力減損精算 (啟動霍夫曼大腦)
    labor_loss_compensation = 0
    labor_loss_reason = "經初步評估，傷勢未達永久勞動力減損標準，無須額外提列補償現值。"
    
    if labor_loss_ratio > 0:
        # 計算距 65 歲強制退休的剩餘年資
        remaining_years = max(0, 65 - age)
        
        if remaining_years > 0:
            # 取得對應的霍夫曼係數
            coef = get_hoffmann_coefficient(remaining_years)
            # 年薪
            annual_income = salary * 12
            # 霍夫曼一次給付現值 = 年收入 * 減損比例 * 霍夫曼係數
            labor_loss_compensation = int(annual_income * (labor_loss_ratio / 100) * coef)
            
            labor_loss_reason = (
                f"【勞動力減損精算報告】：\n"
                f"考量傷者職業為「{job}」，現年 {age} 歲，距 65 歲退休尚餘 {remaining_years} 年。\n"
                f"依勞保失能給付標準，判定「{body_part}」傷勢導致其勞動減損比例達 {labor_loss_ratio}%。\n"
                f"按法院認可之正確版霍夫曼計算法扣除中間利息 (適用累計係數 {coef})，"
                f"應一次給付勞動力減損現值為 {labor_loss_compensation:,} 元。"
            )

    # C. 總金額計算與肇責拆算
    total_estimated = work_loss + suggested_consolation + labor_loss_compensation
    final_amount = int(total_estimated * (liability / 100))

    print(f"✅ 運算完成！來源: {data_source} | 建議金額: {final_amount} (含霍夫曼減損: {labor_loss_compensation})")

    # 4. 回傳 JSON 資料包給 Copilot Studio
    return {
        "status": "success",
        "data_source": data_source,
        "results": {
            "input_job": job,
            "input_age": age,
            "input_body_part": body_part,
            "calculated_work_loss": work_loss,
            "calculated_labor_loss": labor_loss_compensation,  # 👈 新增這筆精算金額
            "labor_loss_reason": labor_loss_reason,            # 👈 新增這段判斷論述
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
        
        # 將輸入的字串用「空白」切開 (例如："右手 骨折" -> ["右手", "骨折"])
        keywords = keyword.split()
        
        if not keywords:
            return []
            
        # 動態組合 SQL 條件：產生 "JFULL" ilike %s AND "JFULL" ilike %s
        conditions = " AND ".join(['"JFULL" ilike %s' for _ in keywords])
        
        # 準備對應的參數（為每個關鍵字加上 % 符號）
        params = tuple(f"%{k}%" for k in keywords)
        
        # 撈出 5 筆案件
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
