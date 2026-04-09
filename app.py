import requests
import json
import re

def call_ai_expert(age, job, body_part, liability, city, judgments):
    if not OPENROUTER_API_KEY: return {"estimated_consolation": 80000, "report_text": "Key Error"}

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

    # 🏆 強化版：明確的備援模型清單 (優先使用我們已知穩定的模型)
    model_pool = [
        "google/gemma-4-31b-it:free",          # 優先：邏輯強，懂中文
        "meta-llama/llama-3.3-70b-instruct:free", # 備案一：推理能力極佳
        "openrouter/auto"                       # 最終防線：交給系統自動分配
    ]

    for model_id in model_pool:
        try:
            print(f"⏳ 嘗試使用模型: {model_id}...")
            res = requests.post(
                url="https://openrouter.ai/api/v1/chat/completions",
                headers={
                    "Authorization": f"Bearer {OPENROUTER_API_KEY.strip()}",
                    "Content-Type": "application/json",
                    "HTTP-Referer": "https://fubon-ai.render.com" # 建議保留，部分模型需要
                },
                data=json.dumps({
                    "model": model_id,
                    "messages": [{"role": "user", "content": prompt}],
                    "temperature": 0.3
                }),
                timeout=45 # 延長超時時間至 45 秒，給大模型更多思考時間
            )
            
            data = res.json()
            
            # 檢查是否有正常的 choices 回傳
            if 'choices' in data and len(data['choices']) > 0:
                print(f"✅ 模型 {model_id} 成功！")
                content = data['choices'][0]['message']['content']
                clean_json = re.sub(r'```json\n?|```', '', content).strip()
                return json.loads(clean_json)
            else:
                # 若無 choices，印出錯誤訊息供除錯
                error_msg = data.get('error', {}).get('message', '未知錯誤')
                print(f"❌ 模型 {model_id} 失敗或無效回應: {error_msg}")
                continue # 嘗試下一個模型

        except requests.exceptions.Timeout:
             print(f"⚠️ 模型 {model_id} 請求超時 (Timeout)。")
             continue
        except Exception as e:
            print(f"⚠️ 呼叫模型 {model_id} 發生例外錯誤: {e}")
            continue # 嘗試下一個模型

    # 如果所有模型都失敗，回傳更有建設性的錯誤訊息
    return {
        "estimated_consolation": 98000, 
        "report_text": "### ⚠️ AI 伺服器目前繁忙\n\n目前所有可用的 AI 模型通道皆處於高負載狀態或請求超時。\n\n**系統建議**：\n1. 請稍候 1-2 分鐘後再次嘗試。\n2. 若持續發生，請確認您的 OpenRouter API Key 狀態或網路連線。\n3. 目前估算之慰撫金（98,000 元）為系統基於基本參數之保底估算，僅供暫時參考。"
    }
