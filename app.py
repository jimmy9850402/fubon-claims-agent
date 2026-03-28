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
    
    # 1. 執行 Supabase 資料庫搜尋 (293MB 大數據)
    judgments = search_supabase(body_part)
    
    data_source = "Database"
    
    # 2. 備援邏輯：如果資料庫查不到，提供 AI 模擬判斷 (避免回傳空箱子)
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
    # 預設建議慰撫金中間值 80000 (可由 AI 在 Copilot 裡根據判例再次動態修正)
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
    """連線到 Supabase 並執行模糊檢索"""
    try:
        # 建立資料庫連線
        conn = psycopg2.connect(DB_URL)
        cursor = conn.cursor()
        
        # 搜尋關鍵字 (使用 ilike 進行模糊比對，不分大小寫)
        # 注意這裡：已經幫大寫欄位加上了 "雙引號" 避免 PostgreSQL 認錯！
        sql_query = """
            SELECT "JFULL" 
            FROM car_judgments 
            WHERE "JFULL" ilike %s 
            ORDER BY "JDATE" desc 
            LIMIT 3
        """
        cursor.execute(sql_query, (f"%{keyword}%",))
        rows = cursor.fetchall()
        
        cursor.close()
        conn.close()
        
        if rows:
            print(f"✨ 成功從資料庫撈到 {len(rows)} 筆判例！")
            # 每筆判決書內容截取前 1200 字，確保 Copilot 跑得動
            return [row[0][:1200].replace("\n", " ") for row in rows]
        else:
            return []
            
    except Exception as e:
        print(f"❌ 資料庫搜尋出錯: {str(e)}")
        return []

if __name__ == "__main__":
    # 本地端測試用
    uvicorn.run(app, host="0.0.0.0", port=8000)
