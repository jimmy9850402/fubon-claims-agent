import os
import uuid
import json
import re
import requests
import psycopg2
from datetime import datetime
from fastapi import FastAPI, Query, Body, BackgroundTasks
from fastapi.responses import FileResponse
from pydantic import BaseModel
from docxtpl import DocxTemplate  # 🚀 核心：Word 套表工具
from ddgs import DDGS
import uvicorn

app = FastAPI()

# ==========================================
# 🔑 環境變數與設定
# ==========================================
DB_URL = os.environ.get("DATABASE_URL")
OPENROUTER_API_KEY = os.environ.get("OPENROUTER_API_KEY")
MARKET_ADJUSTMENT_FACTOR = 1.3  # 市場行情通膨修正係數

class ClaimData(BaseModel):
    caseId: str
    job: str
    body_part: str
    salary: int
    months: int
    liability: int
    age: int = 35
    medical_fee: int = 0
    city: str = "台北市"

# 刪除暫存檔的輔助函數
def remove_file(path: str):
    if os.path.exists(path):
        os.remove(path)

@app.get("/")
def home():
    return {"status": "Fubon AI Agent Live", "version": "2026.04.10-Final"}

# ==========================================
# 🧠 AI 專家邏輯 (內建富邦參考表基準)
# ==========================================
def call_ai_logic(age, job, body_part, liability, city, context_info, work_loss, medical_fee):
    prompt = f"""
    你現在是台灣富邦產險最資深的理賠法務專家。請產出專業建議書。
    傷者：{age}歲{job} | 傷勢：{body_part} | 肇責：{liability}% | 地點：{city}
    
    【📋 富邦內部精神補償參考矩陣 (數位化標準)】：
    1. 皮肉損傷 (擦挫傷/撕裂傷)：0~2萬
    2. 輕微骨折 (鎖骨/手掌/肋骨)：0~7萬
    3. 一般上肢骨折 (橈骨/尺骨/肱骨)：0~11萬 (基數)
    4. 嚴重骨折 (粉碎性/開放性/下肢股骨/椎骨)：15萬~26萬
    5. 重大傷情 (顱內出血/截肢)：30萬~150萬以上
    
    【🚀 現行核定加權邏輯】：
    - 市場修正：基準需自動乘以 {MARKET_ADJUSTMENT_FACTOR} 倍進行通膨校正。
    - 職業加權：傷者為「{job}」，考慮精密勞作需求及社經地位，應額外加成 20%~40%。
    - 實務目標：對於律師或嚴重手部骨折，最終金額應參考協理建議之 26 萬左右水準。

    請回傳純 JSON：{{"estimated_consolation": 數字, "report_text": "Markdown格式報告"}}
    """
    
    # 這裡實作 OpenRouter 呼叫 (簡略示範)
    try:
        res = requests.post(
            url="https://openrouter.ai/api/v1/chat/completions",
            headers={"Authorization": f"Bearer {OPENROUTER_API_KEY.strip()}"},
            data=json.dumps({"model": "openrouter/auto", "messages": [{"role": "user", "content": prompt}]})
        )
        data = res.json()
        content = data['choices'][0]['message']['content']
        clean_json = re.sub(r'```json\n?|```', '', content).strip()
        return json.loads(clean_json)
    except:
        return {"estimated_consolation": 150000, "report_text": "AI 繁忙中，請手動調整。"}

# ==========================================
# 📄 Word 生成與下載 (免 OneDrive 權限)
# ==========================================
@app.post("/generate_fubon_report")
def generate_fubon_report(data: ClaimData, background_tasks: BackgroundTasks):
    # 1. 執行 AI 精算
    work_loss = data.salary * data.months
    ai_result = call_ai_logic(data.age, data.job, data.body_part, data.liability, data.city, "", work_loss, data.medical_fee)
    
    consolation = ai_result.get("estimated_consolation", 0)
    report_text = ai_result.get("report_text", "")

    # 2. 讀取伺服器本地範本 (需與 app.py 放在同個 GitHub 目錄)
    template_path = "Fubon_Template.docx"
    if not os.path.exists(template_path):
        return {"error": "找不到 Word 範本檔，請確認 Fubon_Template.docx 已上傳至 GitHub"}

    doc = DocxTemplate(template_path)

    # 3. 準備套表變數
    context = {
        'CaseID': data.caseId,
        'Job': data.job,
        'BodyPart': data.body_part,
        'WorkLoss': f"{work_loss:,}",
        'Consolation': f"{consolation:,}",
        'Medical': f"{data.medical_fee:,}",
        'FinalAmount': f"{int((work_loss + consolation + data.medical_fee) * (data.liability/100)):,}",
        'AI_Report': report_text
    }

    # 4. 渲染並儲存暫存檔
    doc.render(context)
    temp_id = uuid.uuid4().hex[:6]
    server_filename = f"temp_{temp_id}.docx"
    doc.save(server_filename)

    # 5. 設定下載檔名 (日期命名)
    today_str = datetime.now().strftime("%Y%m%d")
    download_name = f"{today_str}_理賠計畫建議書.docx"

    # 6. 回傳檔案並排程刪除暫存檔
    background_tasks.add_task(remove_file, server_filename)

    return FileResponse(
        path=server_filename,
        filename=download_name,
        media_type='application/vnd.openxmlformats-officedocument.wordprocessingml.document'
    )

if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=8000)
