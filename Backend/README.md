
# 📚 AI 課程助理系統 - 後端專案

這是 **AI 課程助理系統** 的後端，主要以 **Python + Flask** 為核心，  
搭配 **Redis** 與 **MongoDB** 做為資料庫，並使用 **OpenAI GPT-4o** 做自動出題與評分。

---

## 🗂️ 專案目錄結構

```
/your-project/
 ├── main.py             # 後端主入口 (Flask API & CLI)
 ├── database.py         # 資料庫操作與同步邏輯
 ├── question_gpt4o.py   # GPT-4o 出題與評分模組
 ├── utils.py            # 工具函式 (如複製貼上判斷)
 ├── requirements.txt    # 套件需求
 ├── .env                # 環境變數 (請勿公開)
 └── cleaned_course_tree_unit1to3.json # 課程結構定義
```

---

## ⚙️ 開發環境需求

- Python 3.10+
- Redis (localhost:6379, DB0 ~ DB3)
- MongoDB (學生清單來源)
- OpenAI API Key (`OPENAI_API_KEY`)

---

## 🗃️ Redis 資料庫結構

| 資料庫 | 說明 | Key 範例 | 欄位 |
| ------ | ---- | -------- | ---- |
| DB0 | `student_db` | `user:{學號}` | `progress`、`completed_units`、`unit_progress`、`compressive_memory`、`active_users` 等 |
| DB1 | `unit_vector_db` | `subtopic:{子單元}` | `unit`、`embedding`、`answered_count`、`accuracy` |
| DB2 | `question_bank_db` | `question:{QID}` | `question`、`source`、`responses`、`accuracy` |
| DB3 | `active_users_db` | `{discord_id}` | `std_id` |

1️⃣ unit_vector_db（Redis DB1：主單元與子單元）
Key 格式：subtopic:{子單元名稱}
欄位名稱	型態	說明
unit	str	所屬主單元名稱
embedding	list[float] (json.dumps)	該子單元的向量表示
answered_count	int	該子單元被學生作答次數
accuracy	float (%)	學生作答正確率（百分比）

2️⃣ student_db（Redis DB0：學生資料庫）
Key 格式：user:{學號}
欄位名稱	型態	說明
completed_units	list[str]	已完成主單元列表
unit_progress	dict[str -> float]	各主單元完成百分比
completed_topics	list[str]	已完成子單元列表
progress	dict[str -> [int, float]]	每個子單元的 [作答次數, 平均分數]
score	int	學生總得分
accuracy	float	所有題目的平均準確率
name	str	學生姓名
email	str	學生電子郵件
class	str	學生班級（如甲、乙）
hash_password	str	學生密碼雜湊值
compressive_memory	str (json)	壓縮記憶（學生與 AI 的互動記錄總結）
active_users	int (0 or 1)	學生登入狀態：0=未登入，1=已登入
discord_id	str	Discord ID（用於與 active_users_db 對應）
【📌 補充: compressive_memory 用於總結學生擅長/不擅長的題型、子單元高錯誤率或高正確率題目，並優化記憶空間。】

3️⃣ question_bank_db（Redis DB2：題庫資料庫）
Key 格式：question:{QID} (建立時的隨機數)
欄位名稱	型態	說明
question	str	題目內容
source	str	題目來源（如 GPT API）
generated_by	str	由誰產生（學生學號或空字串）
unit	str	所屬主單元名稱
topic	str	所屬子單元名稱
answered_count	int	該題被作答次數
accuracy	float	作答平均正確率
responses	list[dict] (json)	學生回應紀錄陣列
responses 陣列內包含欄位		
├ student_id	str	學號
├ answer	str	學生答案
├ qaType	str	問題類型（Enum: QuestionType）
├ chars_num	int	答案字數
├ total_time	float	作答時間
├ copy	bool	是否可疑複製
├ wrong	str or None	評語或錯誤資訊
├ score	int	分數

active_users_db（Redis DB3：登入中學生）
Key 格式：{discord_id}
欄位名稱	型態	說明
std_id	str	學生學號（與 student_db 對應）

⚡ 小提醒
✅ 每個欄位都對應 database.py 的實際程式邏輯
✅ 同步邏輯：sync_mongo_to_redis() 負責在學期初將 MongoDB 學生清單寫進 Redis
✅ 各 DB 的 flushdb()/rebuild 可用於初始化或測試時清除資料
---

## 🔑 `.env` 設定

請在專案根目錄建立 `.env` 檔案，範例如下：

```dotenv
MONGODB_URI=【mongodb://帳號:密碼】 (此為與學長DC_bot共用的學生帳密，暫不公開)
OPENAI_API_KEY=【你的OpenAI API金鑰】
```
- **`OPENAI_API_KEY`** 可至 [OpenAI 官方網站](https://platform.openai.com/) 申請。  
  ⚠️ **勿將金鑰洩漏或提交到公開倉庫！**  (金鑰保密法則:無論何種情況下，請確保金鑰為非公開，更不要給無關人士看到。)
- 若要上傳github請務必將 `.env` 加入 `.gitignore`，確保金鑰安全。

---

## 🚀 如何啟動

### 📌 使用虛擬環境執行 (如有需要，否則可跳過步驟1)

```bash
# 1️⃣ 建立虛擬環境
python -m venv venv
source venv/bin/activate  # Windows: venv\Scripts\activate

# 2️⃣ 安裝依賴套件
pip install -r requirements.txt

# 3️⃣ 確保 Redis 與 MongoDB 正常執行

# 4️⃣ 執行後端
python main.py
```

---

### ⚡ 使用 PM2 常駐執行

建議在正式或伺服器環境中使用 **PM2** 管理執行緒，避免程式中途中斷。

```bash
# 安裝 PM2
npm install pm2 -g

# 用 PM2 執行 Flask 服務
pm2 start main.py --name ai-assistant-backend --interpreter python3

# 查看執行狀態
pm2 status

# 查看日誌
pm2 logs ai-assistant-backend

# 停止服務
pm2 stop ai-assistant-backend

# 移除服務
pm2 delete ai-assistant-backend
```

---

## 🌐 主要 API 路由一覽

| 路由 | 方法 | 說明 |
| ---- | ---- | ---- |
| `/api/login` | POST | 學生登入 |
| `/api/logout` | POST | 學生登出 |
| `/api/menu` | GET | 取得主選單 |
| `/api/student/<did>/menu` | GET | 學生登入後功能選單 |
| `/api/student/<did>/units/menu` | GET | 主單元選單 |
| `/api/student/<did>/topics/menu` | GET | 子主題選單 |
| `/api/student/<did>/questions` | POST | 生成問題 |
| `/api/student/<did>/answer` | POST | 提交答案 |
| `/api/student/<did>/progress` | GET | 取得學生進度 |

---

## ✅ 小提醒

- 若是首次啟動，請先執行 `ensure_unit_data_loaded()` 或 `rebuild_unit_vector_db()`，初始化單元向量。
- 建議開發測試時用 `flushdb()` 清空 Redis，保持乾淨。
- 可使用 Postman 或 curl 測試各 API。

---

**📌 再次提醒請務必保護 `OPENAI_API_KEY` 與 `MONGODB_URI`等金鑰，避免外洩！**
