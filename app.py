from fastapi import FastAPI
import psycopg2
import os
import requests

app = FastAPI()

# Supabase 連線資訊 (從 Render 環境變數讀取)
DB_URL = os.environ.get("DATABASE_URL")

@app.get("/evaluate_claim")
def evaluate_claim(body_part: str, salary: int, months: int, liability: int):
    # 步驟 1: 先去 Supabase 撈資料
    judgments = search_supabase(body_part)
    source = "Database"

    # 步驟 2: 如果資料庫沒資料，啟動網路搜尋備援
    if not judgments:
        judgments = search_web_backup(body_part)
        source = "Web Search"

    # 步驟 3: 格式化回傳給 Copilot
    return {
        "status": "success",
        "source": source,
        "body_part": body_part,
        "salary": salary,
        "months": months,
        "liability": liability,
        "judgment_data": judgments
    }

def search_supabase(keyword):
    try:
        conn = psycopg2.connect(DB_URL)
        cursor = conn.cursor()
        # 使用 ilike 進行模糊搜尋，確保繁體中文不漏掉
        query = f"SELECT JID, JFULL FROM car_judgments WHERE JFULL ilike '%{keyword}%' ORDER BY JDATE desc LIMIT 3;"
        cursor.execute(query)
        rows = cursor.fetchall()
        cursor.close()
        conn.close()
        return [row[1][:1000] for row in rows] # 截取前 1000 字避免超過 Token 限制
    except:
        return []

def search_web_backup(keyword):
    # 這裡未來可以對接 Tavily 或 Google Search API
    # 目前先提供一個模擬回傳，確保 AI 能進行後續動作
    return [f"網路搜尋結果：關於{keyword}的相關法院賠償趨勢..."]