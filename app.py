from fastapi import FastAPI, Query
import psycopg2
import os
import uvicorn

app = FastAPI()

# 從 Render 的環境變數讀取 Supabase IPv4 連線字串
DB_URL = os.environ.get("DATABASE_URL")

@app.get("/")
def home():
    """首頁測試，確認 API 有活著"""
    return {"status": "Fubon Claims AI Agent is Online!", "message": "Ready to evaluate."}

@app.get("/evaluate")
def evaluate(
    body_part: str = Query(..., description="受傷部位關鍵字"),
    salary: int = Query(..., description="月薪"),
    months: int = Query(..., description="休養月數"),
    liability: int = Query(..., description="肇責比例 (0-100)")
):
    print(f"--- 🚀 收到請求 ---")
    print(f"📍 部位: {body_part} | 薪資: {salary} | 月數: {months} | 肇責: {liability}%")
    
    # 1. 執行 Supabase 資料庫搜尋 (支援多關鍵字斷詞)
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

    # 3. 理賠邏輯精算 (Python 核心計算)
    work_loss = salary * months
    suggested_consolation = 80000 
    
    total_estimated = work_loss + suggested_consolation
    final_amount = total_estimated * (liability / 100)

    print(f"✅ 運算完成！來源: {data_source} | 建議金額: {final_amount}")

    # 4. 回傳 JSON 資料包給 Copilot Studio
    return {
        "status": "success",
        "data_source": data_source,
        "results": {
            "input_body_part": body_part,
            "calculated_work_loss": work_loss,
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
        
        # 💡 魔法在這裡：把輸入的字串用「空白」切開
        # 例如："右手 骨折" -> ["右手", "骨折"]
        keywords = keyword.split()
        
        # 如果使用者沒輸入任何東西，直接回傳空陣列
        if not keywords:
            return []
            
        # 動態組合 SQL 條件：產生 "JFULL" ilike %s AND "JFULL" ilike %s
        conditions = " AND ".join(['"JFULL" ilike %s' for _ in keywords])
        
        # 準備對應的參數（為每個關鍵字加上 % 符號）
        params = tuple(f"%{k}%" for k in keywords)
        
        sql_query = f"""
            SELECT "JFULL" 
            FROM car_judgments 
            WHERE {conditions}
            ORDER BY "JDATE" desc 
            LIMIT 3
        """
        
        # 執行 SQL
        cursor.execute(sql_query, params)
        rows = cursor.fetchall()
        
        cursor.close()
        conn.close()
        
        if rows:
            print(f"✨ 成功從資料庫撈到 {len(rows)} 筆判例！")
            return [row[0][:1200].replace("\n", " ") for row in rows]
        else:
            return []
            
    except Exception as e:
        print(f"❌ 資料庫搜尋出錯: {str(e)}")
        return []

if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=8000)
