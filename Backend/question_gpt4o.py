import redis
import json
import numpy as np
# import ollama
from sentence_transformers import SentenceTransformer
import time
import threading
import itertools
from openai import OpenAI
from dotenv import load_dotenv
import os
import tiktoken
# import sys

# 初始化 Redis DB（單元向量資料庫）
unit_vector_db = redis.Redis(host='localhost', port=6379, db=1)

from enum import Enum
class QuestionType(Enum):
    CHOICE = "選擇題"
    DEFINITION = "定義題"
    CALCULATION = "計算題"
    SHORT_ANSWER = "簡答題"
    SITUATIONAL = "情境題"
    OPEN_ENDED = "開放式問題"
    COMPREHENSIVE = "綜合思考題"

# 載入 SentenceTransformer 模型
embedding_model = SentenceTransformer("sentence-transformers/paraphrase-multilingual-mpnet-base-v2")
load_dotenv()
API_KEY = os.getenv("OPENAI_API_KEY")
client = OpenAI(api_key=API_KEY)
tk = tiktoken.encoding_for_model("gpt-4o-mini")


# 載入所有子主題與向量
def load_all_vectors():
    keys = unit_vector_db.keys("subtopic:*")
    subtopics = []
    vectors = []
    for key in keys:
        topic = key.decode("utf-8").replace("subtopic:", "")
        data = unit_vector_db.hget(key, "embedding")
        if data:
            embedding = np.array(json.loads(data))
            subtopics.append(topic)
            vectors.append(embedding)
    return subtopics, np.vstack(vectors)

# 根據輸入文字搜尋相似子主題
def search_similar_subtopics(query, top_k=3):
    query_vec = embedding_model.encode([query], convert_to_numpy=True)
    subtopics, matrix = load_all_vectors()
    scores = np.dot(matrix, query_vec.T).reshape(-1)  # cosine 相似度
    top_indices = np.argsort(scores)[-top_k:][::-1]
    return [(subtopics[i], scores[i]) for i in top_indices]

# 動畫旗標
_loading = True

def _animate_loading(message):
    for dots in itertools.cycle(["", ".", "..", "..."]):
        if not _loading:
            break
        print(f"\r{message}{dots}   ", end="", flush=True)
        time.sleep(0.5)

def generate_random_questions_gpt4o(course_info, num_questions=3):
    global _loading
    _loading = True

    message = f"自動出題中"
    t = threading.Thread(target=_animate_loading, args=(message,))
    t.start()

    prompt = f"""你是一位資料結構課程的出題老師，請根據以下課程內容，**隨機生成{num_questions} 題觀念性問題**。這些問題需符合指定的出題類型與條件。
   ---

    ## 🧠【課程內容】：
    {course_info}

    ---

    ## 🧾【出題規範與限制】：

    1. 問題必須與上述課程內容有明確關聯，**不能出現任何程式碼問題**。
    2. 問題類型須從以下7種類型中產生，並隨機選擇：
    - 1. 選擇題（需附上解釋理由）
    - 2. 定義題（要求寫出概念定義並舉例）
    - 3. 計算題（計算時間複雜度、樹高、碰撞機率等）
    - 4. 簡答題（回答概念並輔以說明或比較）
    - 5. 情境題（假設特定情境，問學生會發生什麼，並說明原因）
    - 6. 開放式問題（學生可自由提出想法，不只一種答案）
    - 7. 綜合思考題（需結合兩個以上概念回答）

    3. 題目需為**非是非題**，並且**問題文字不超過兩句話**。
    4. 每題應強調**理解、解釋、比較、舉例、或推理計算**。
    5. 題目中**不提供提示或範例**，不附解答。
    6. 題目**不能只是知識回憶**，應引導學生思考其應用與理解。

    ---

    ## ✅【範例參考】：
    - 如何判定 min-max heap 任一節點 [x] 是在 min 或 max 層？
    - DEAP 和 min-max heap 的想法有何共通點？
    - 建立 binomial heap 的時間複雜度如何決定？
    - pairing heap 和 Fibonacci heap 有何異同？
    - 給定 m 種相異鍵值，如何推算 2-3 樹高的上限？
    - 以線性探索搜尋雜湊表不存在值的效率如何評估？請舉例解說。
    - 令 m = 雜湊表大小、n = 資料筆數，請從 m 和 n 推導發生碰撞的機率。
    - AVL 樹刪除葉節點後的檢查可否改從樹根開始由上而下？有何優缺點？

    ---

    請根據以上規則，只生成 {num_questions} 題問題。每題為繁體中文獨立問題，*不用編號*直接換行列出。

    ---
    ## 【輸出格式】：
    【問題類型(7種類型之一)】每題問題獨立一行，**不需要任何其他文字或說明**。
    【問題類型(7種類型之一)】每題問題獨立一行，**不需要任何其他文字或說明**。
    【問題類型(7種類型之一)】每題問題獨立一行，**不需要任何其他文字或說明**。

    """

    response = client.chat.completions.create(
        model="gpt-4o-mini",
        messages=[
            {"role": "system", "content": "你是一位專業的課程助理，能根據課程內容生成三個相關問題。請用中文詢問，遇到專有名詞後面括號英文名稱，如:Heap（堆積）。"},
            {"role": "user", "content": prompt}
        ]
    )

    _loading = False
    t.join()
    print("\r" + " " * (len(message) + 5), end="")  # 清空動畫行

    return [q.strip() for q in response.choices[0].message.content.split("\n") if q.strip()]

def evaluate_answer_gpt4o(question, user_answer):
    global _loading
    _loading = True
    message = f"📝檢查回答中，請耐心等待"
    t = threading.Thread(target=_animate_loading, args=(message,))
    t.start()

    prompt = f"""
你是一位專業的電腦科學助理，請根據以下標準評分使用者的回答：

### 評分標準
1. '若[使用者的回答] 與 [問題] 不相關，文不對題'總分零分。
2. '若 [問題] 要求舉例，而沒有舉例'總分零分。
3. '若 [問題] 要求解釋或理由，而未說明原因'總分零分。
4. '若 [問題] 要求寫出優缺點，而未寫出優缺點，或少其中一個'總分零分。
5. '若 [使用者的回答] 缺少答案關鍵詞'扣一分。
6. ' [使用者的回答] 若字數少於20字，代表答案過短'扣三分，回答很多不扣分。
7. '若 [使用者的回答] 不正確'最高分五分，若超過一個錯，再依錯誤數量，每發現一個錯誤就再扣一分，直到分數為零。
8. '總分不能超過十分'超過以仍十分統計。
9. '總分不能低於零分，也就是總分不能出現負數'低於零分以零分統計。
10. 扣分與加分必定是'整數'。
11. '評分時，若[使用者的回答]有錯誤，並在[扣分原因]依序點出錯誤的地方，給予正確的答案'**內容有錯誤，就一定會被扣分，不可能滿分十分**。

### 問題
{question}

### 使用者的回答
{user_answer}

請根據**評分標準**對[使用者的回答]打 1~10 分，1分是最低分、10分是最高分。
並且使用繁體中文，提供簡短(2、3句)的評語，剩下只需說明扣分原因(沒扣分，也就是回答滿分十分則寫'扣分原因:無')。
若學生的回答有錯或說明不足的部分，請在[扣分原因]後寫上'錯誤地方與正確的答案'或'針對說明不足的部分提供改善建議'，並在評語給予整體回答評價。

### 輸出格式為:
分數: (獲得分數)/10 分  
評語: (評語)  
扣分原因: (列點扣分原因，沒有扣分寫'無')
"""

    response = client.chat.completions.create(
        model="gpt-4o-mini",
        messages=[
            {"role": "system", "content": "你是一位 資料結構 評審，負責評分使用者的答案。"},
            {"role": "user", "content": prompt}
        ]
    )

    _loading = False
    t.join()
    print("\r" + " " * (len(message) + 5), end="")  # 清空動畫行

    return response.choices[0].message.content.strip()

# 用gpt-4o-mini判斷問題類型，用enum格式回答
# 後臺跑不用告訴使用者，直接回傳問題類型
# 前端與其他功能不用等待(平行處理)
def classify_question_type(question):
    global _loading
    _loading = True
    message = f"📝問題類型分類中，請耐心等待"
    t = threading.Thread(target=_animate_loading, args=(message,))
    t.start()

    prompt = f"""你是一位專業的資料結構課程助理，請根據以下問題內容，判斷其類型並回傳對應的枚舉值。
    問題內容：
    {question}
    請根據以下類型進行分類，並以枚舉格式回傳：
    - CHOICE: 選擇題
    - DEFINITION: 定義題
    - CALCULATION: 計算題
    - SHORT_ANSWER: 簡答題
    - SITUATIONAL: 情境題
    - OPEN_ENDED: 開放式問題
    - COMPREHENSIVE: 綜合思考題
    回傳格式為：
    qaType.XXX
    其中 XXX 為對應的枚舉值，不要包含其他文字或解釋。
    """
    response = client.chat.completions.create(
        model="gpt-4o-mini",
        messages=[
            {"role": "system", "content": "你是一位專業的資料結構課程助理，負責判斷問題類型。"},
            {"role": "user", "content": prompt}
        ]
    )

    _loading = False
    t.join()
    print("\r" + " " * (len(message) + 5), end="")  # 清空動畫行

    return response.choices[0].message.content.strip()


