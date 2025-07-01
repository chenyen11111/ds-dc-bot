# Redis DB 分配說明： 
# DB 0：student_db - 學生資料庫
# DB 1：unit_vector_db - 主單元與子主題
# DB 2：question_bank_db - 題庫資料庫
# DB 3：登入中學生資料庫（active_users）

import redis
import json
from sentence_transformers import SentenceTransformer
import numpy as np
from pymongo import MongoClient
import os
from flask import Flask, request, jsonify
import bcrypt
from dotenv import load_dotenv
load_dotenv()
"""
問題類型須從以下7種類型中產生，並隨機選擇：
    - 1. 選擇題（需附上解釋理由）
    - 2. 定義題（要求寫出概念定義並舉例）
    - 3. 計算題（計算時間複雜度、樹高、碰撞機率等）
    - 4. 簡答題（回答概念並輔以說明或比較）
    - 5. 情境題（假設特定情境，問學生會發生什麼，並說明原因）
    - 6. 開放式問題（學生可自由提出想法，不只一種答案）
    - 7. 綜合思考題（需結合兩個以上概念回答）
"""
from enum import Enum
class QuestionType(Enum):
    CHOICE = "選擇題"
    DEFINITION = "定義題"
    CALCULATION = "計算題"
    SHORT_ANSWER = "簡答題"
    SITUATIONAL = "情境題"
    OPEN_ENDED = "開放式問題"
    COMPREHENSIVE = "綜合思考題"

# 初始化 Flask 應用程式
app = Flask(__name__)

# 連接 MongoDB
# MongoDB 初始化
# print("✅ MONGODB_URI =", os.getenv("MONGODB_URI"))
mongo_client = MongoClient(os.getenv("MONGODB_URI"))
mongo_db = mongo_client['DAL_Discord']

student_list = mongo_db['student_list']

# 初始化 Redis 資料庫連線
student_db = redis.Redis(host='localhost', port=6379, db=0)
unit_vector_db = redis.Redis(host='localhost', port=6379, db=1)
question_bank_db = redis.Redis(host='localhost', port=6379, db=2)
active_users_db = redis.Redis(host='localhost', port=6379, db=3)

with open("/home/dc-qa-bot/discord_model/cleaned_course_tree_unit1to3.json", "r", encoding="utf-8") as f:
    _course_data = json.load(f)
unit_order = [unit['name'] for unit in _course_data]

model = SentenceTransformer('paraphrase-MiniLM-L6-v2')

topic_unit_map = {}
unit_topic_list = {}
subtopics = []
default_progress = {}

def ensure_unit_data_loaded():
    global topic_unit_map, unit_topic_list, subtopics, default_progress, unit_order

    # Redis DB1 初始化狀態檢查
    existing_keys = unit_vector_db.keys("subtopic:*")
    if not existing_keys:
        print("🔄 Redis DB1 尚未初始化，執行 rebuild_unit_vector_db()...")
        rebuild_unit_vector_db()
    else:
        print(f"✅ Redis DB1 已載入 {len(existing_keys)} 個子單元，略過初始化")

    sync_mongo_to_redis() # 初始化 MongoDB 資料到 Redis

    # 初始化記憶中結構
    topic_unit_map = {}
    unit_topic_list = {}

    for key in unit_vector_db.keys("subtopic:*"):
        topic = key.decode().split("subtopic:")[1]
        unit = unit_vector_db.hget(key, "unit").decode("utf-8")
        topic_unit_map[topic] = unit
        if unit not in unit_topic_list:
            unit_topic_list[unit] = []
        unit_topic_list[unit].append(topic)

    unit_order = sorted(unit_topic_list.keys())
    subtopics = list(topic_unit_map.keys())

def sync_mongo_to_redis(): # 將 MongoDB 學生資料同步到 Redis，學期初建立學生資料庫時使用
    ensure_unit_data_loaded()  # 確保單元資料已載入

    for student in student_list.find():
        student_id = str(student["student_id"])
        student_db.hset(f"user:{student_id}", mapping={
            "name": student["name"],
            "email": student["email"],
            "class": student["class"],
            "hash_password": student["hashed_password"],
            "completed_units": json.dumps([]),
            "unit_progress": json.dumps({}),
            "completed_topics": json.dumps([]),
            "progress": json.dumps({}),
            # 初始化壓縮記憶一開始放入"還未做過測驗"，作答後會被更新
            "compressive_memory": json.dumps(["第一單元還未做過測驗", "第二單元還未做過測驗", "第三單元還未做過測驗"]),
            # active_users: 學生登入狀態 (bool) [True or False]
            "active_users": int(False),  # 寫入 0 表示未登入，登入時改為 1
            "discord_id": "00000000",  # 新增 discord_id 欄位，初始化"00000000"
            "score": 0,
            "accuracy": 0.0
        })
    print("✅ 已將 MongoDB 學生資料寫入 Redis")

# 學期末刪除redis學生資料庫資料
def clear_student_data():
    ensure_unit_data_loaded()  # 確保單元資料已載入
    student_db.flushdb()
    print("✅ 已清除 Redis 學生資料庫資料")

# 主單元與子單元資料庫（unit_vector_db，Redis DB1）
# Key: subtopic:{子單元名稱}
# 欄位:
#   - unit: 主單元名稱（str）
#   - embedding: 該子單元的向量（list[float]，經 json.dumps）
#   - answered_count: 被學生作答次數（int）
#   - accuracy: 學生作答正確率（float，百分比）
def rebuild_unit_vector_db():
    unit_vector_db.flushdb()
    with open("/home/dc-qa-bot/discord_model/cleaned_course_tree_unit1to3.json", "r", encoding="utf-8") as f:
        course_data = json.load(f)

    global topic_unit_map, unit_topic_list, subtopics, default_progress, unit_order
    topic_unit_map = {}
    unit_topic_list = {}
    subtopics = []
    default_progress = {}
    unit_order = [unit['name'] for unit in course_data]

    for unit in course_data:
        unit_name = unit['name']
        unit_topic_list[unit_name] = [child['name'] for child in unit['children']]
        if unit['children']:
            default_progress[unit_name] = unit['children'][0]['name']
        for child in unit['children']:
            name = child['name']
            topic_unit_map[name] = unit_name
            subtopics.append(name)

    embeddings = model.encode(subtopics)
    for i, topic in enumerate(subtopics):
        key = f"subtopic:{topic}"
        unit_vector_db.hset(key, mapping={
            "unit": topic_unit_map[topic],
            "embedding": json.dumps(embeddings[i].tolist()),
            "answered_count": 0,
            "accuracy": 0.0
        })

def reset_student_db():
    student_db.flushdb()

def reset_question_bank_db():
    question_bank_db.flushdb()

# 清空主單元與子單元
def clear_unit_vector_db():
    ensure_unit_data_loaded()  # 確保單元資料已載入
    unit_vector_db.flushdb()
    print("✅ 已清除 Redis 主單元與子單元資料庫資料")


# 學生資料庫（student_db，Redis DB0）
# Key: user:{學號}
# 欄位:
#   - completed_units: 已完成主單元列表（list[str]）
#   - unit_progress: 每個主單元的完成百分比（dict[str -> float]）
#   - completed_topics: 已完成子單元列表（list[str]）
#   - progress: 每個子單元的 [次數, 平均分]（dict[str -> [int, float]]）
#   - score: 學生總得分（int）
#   - accuracy: 全部題目的平均準確率（float）
#   - name: 學生姓名（str）
#   - active_users: 學生登入狀態 0 或 1（int，0 表示未登入，1 表示登入中）
#   - email: 學生電子郵件（str）
#   - class: 學生班級（str）[甲 or 乙]
#   - hash_password: 學生密碼雜湊值（str）
#   - compressive memory : 壓縮記憶(將學生與bot的互動記錄壓縮存儲，避免過多資料佔用Redis空間。
#                          在問完問題後根據問題單元更新記憶內容，總結學生在該單元與子單元的互動)(str)
#                          特別關注學生擅長/不擅長的題目類型、哪些子單元的準確率/錯誤率高

def init_student(student_id):
    if not student_db.exists(f"user:{student_id}"):
        student_db.hset(f"user:{student_id}", mapping={
            "completed_units": json.dumps([]),
            "unit_progress": json.dumps({}),
            "completed_topics": json.dumps([]),
            "progress": json.dumps({}),
            "score": 0,
            "accuracy": 0.0,
            "name": "",
            "email": "",
            "class": "",
            "hash_password": "",
            "compressive_memory": json.dumps({})  # 初始化壓縮記憶
            
        })

# def register_student(student_id):
    # if not student_id.isdigit() or len(student_id) != 8:
        # return "學號格式錯誤，請輸入 8 位數字"
    # if student_db.exists(f"user:{student_id}"):
        # return "學號已存在"
    # init_student(student_id)
    # return "註冊成功"

# 題庫資料庫（question_bank_db，Redis DB2）
# Key: question:{qid}
# 欄位:
#   - question: 題目內容（str）
#   - source: 題目來源（str）
#   - generated_by: 學生學號 or ""（str）
#   - unit: 所屬主單元名稱（str）
#   - topic: 所屬子單元名稱（str）
#   - answered_count: 被作答次數（int）
#   - accuracy: 作答平均準確率（float）
#   - responses: 學生回應清單（list[dict]），包含：
#       - student_id: 學號
#       - answer: 學生答案（str）
#       - qaType: 類型 (來自enum QuestionType)
#       - chars_num: 字數（int）
#       - total_time: 作答時間（float）
#       - copy: 是否可疑複製（bool）
#       - wrong: 評語/錯誤資訊（str 或 None）
#       - score: 分數（int）
def add_question(qid, question, source, student_id, unit, topic):
    question_bank_db.hset(f"question:{qid}", mapping={
        "question": question,
        "source": source,
        "generated_by": student_id or "",  # None or str
        "unit": unit,
        "topic": topic,
        "answered_count": 0,
        "accuracy": 0.0,
        "responses": json.dumps([])
    })

# 新增學生作答記錄並更新三大資料庫（題庫、子單元、學生）欄位：
#
# 1️⃣ 更新題庫資料庫（question_bank_db）
#   - 將學生答題加入 responses 陣列
#   - 更新 answered_count 與 accuracy（正確率）
#   
#
# 2️⃣ 更新主單元與子單元資料庫（unit_vector_db）
#   - 更新 answered_count 與 accuracy（同一題答多次會平均）
#
# 3️⃣ 更新學生資料庫（student_db）
#   - 更新 progress[topic] = [次數, 平均分數]
#   - 若符合條件（3 次以上，且平均 >= 70 分） -> 加入 completed_topics
#   - 根據 completed_topics 計算 unit_progress 百分比
#   - 若主單元所有子題都完成 -> 加入 completed_units
#   - 根據學生的作答優劣與常錯誤題，更新壓縮記憶（compressive_memory），包含參考未更新的壓縮記憶
def add_response_to_question(qid, student_id, answer, total_time, char_len, is_copy, correct, score, feedback):
    qkey = f"question:{qid}"
    question_data = question_bank_db.hgetall(qkey)
    topic = question_data[b"topic"].decode("utf-8")
    unit = question_data[b"unit"].decode("utf-8")

    responses = json.loads(question_data.get(b"responses", b"[]").decode("utf-8"))
    responses.append({
        "student_id": student_id,
        "answer": answer,
        "chars_num": char_len,
        "total_time": total_time,
        "copy": is_copy,
        "wrong": feedback if not correct else None,
        "score": score
    })

    question_bank_db.hset(qkey, "responses", json.dumps(responses))
    question_bank_db.hincrby(qkey, "answered_count", 1)
    if correct and score is not None:
        current_avg = float(question_data.get(b"accuracy", b"0.0").decode("utf-8"))
        count = int(question_bank_db.hget(qkey, "answered_count"))
        new_accuracy = round((current_avg * (count - 1) + (score / 10) * 100) / count, 2)
        question_bank_db.hset(qkey, "accuracy", new_accuracy)

    skey = f"subtopic:{topic}"
    unit_vector_db.hincrby(skey, "answered_count", 1)
    topic_count = int(unit_vector_db.hget(skey, "answered_count"))
    prev_accuracy = float(unit_vector_db.hget(skey, "accuracy") or 0.0)
    updated_accuracy = round((prev_accuracy * (topic_count - 1) + (score or 0) / 10 * 100) / topic_count, 2)
    unit_vector_db.hset(skey, "accuracy", updated_accuracy)

    ukey = f"user:{student_id}"
    progress = json.loads(student_db.hget(ukey, "progress") or "{}")
    topic_progress = progress.get(topic, [0, 0.0])
    topic_progress[0] += 1
    topic_progress[1] = round((topic_progress[1] * (topic_progress[0] - 1) + score) / topic_progress[0], 2)
    progress[topic] = topic_progress
    student_db.hset(ukey, "progress", json.dumps(progress))

    completed_topics = json.loads(student_db.hget(ukey, "completed_topics") or "[]")
    if topic_progress[0] >= 3 and topic_progress[1] >= 7 and topic not in completed_topics:
        completed_topics.append(topic)
        student_db.hset(ukey, "completed_topics", json.dumps(completed_topics))

    unit_progress = json.loads(student_db.hget(ukey, "unit_progress") or "{}")
    unit_topics = unit_topic_list[unit]
    done = sum(1 for t in unit_topics if t in completed_topics)
    unit_progress[unit] = round(done / len(unit_topics) * 100, 2)
    student_db.hset(ukey, "unit_progress", json.dumps(unit_progress))

    completed_units = json.loads(student_db.hget(ukey, "completed_units") or "[]")
    if unit_progress[unit] == 100.0 and unit not in completed_units:
        completed_units.append(unit)
        student_db.hset(ukey, "completed_units", json.dumps(completed_units))

# 放入問題種類(QuestionType)到題庫資料庫
def add_question_type(qid, qa_type):
    qkey = f"question:{qid}"
    if not question_bank_db.exists(qkey):
        return False, "問題不存在"
    
    # 檢查 qa_type 是否為 QuestionType 的成員
    if not isinstance(qa_type, QuestionType):
        return False, "無效的問題類型"

    question_bank_db.hset(qkey, "qaType", qa_type.value)
    return True, "問題類型已更新"

# 根據學生子單元表現自動推進至下一子單元（若符合條件）：
#
# 條件：
#   - 該 topic 答題次數 >= 3
#   - 平均成績 >= 70 分
#   - 尚未完成該主單元下所有子單元
#
# 結果：
#   - 自動將下一個子單元加入 progress，初始化為 [0, 0.0]
def advance_if_ready(student_id, topic):
    ukey = f"user:{student_id}"
    progress = json.loads(student_db.hget(ukey, "progress") or "{}")
    unit = topic_unit_map.get(topic)
    if not unit:
        return

    if topic not in progress:
        return
    attempts, avg_score = progress[topic]
    if attempts < 3 or avg_score < 7:
        return

    unit_topics = unit_topic_list[unit]
    try:
        next_index = unit_topics.index(topic) + 1
        next_topic = unit_topics[next_index]
    except IndexError:
        return  # 已是最後一個子單元

    if next_topic not in progress:
        progress[next_topic] = [0, 0.0]
        student_db.hset(ukey, "progress", json.dumps(progress))


# 登入 API
# @app.route("/api/login", methods=["POST"])
def login():
    try:
        data = request.get_json()
        if not data:
            return jsonify({"success": False, "message": "請提供 JSON 格式的資料"}), 400

        student_id = data.get("student_id")
        password = data.get("password")
        

        success, message = login_logic(student_id, password)
        return jsonify({"success": success, "message": message})
    except Exception as e:
        import traceback
        traceback.print_exc()
        return jsonify({"success": False, "message": "伺服器錯誤"}), 200

# 第一次登入，記住學生的 discord_id並根據student_id寫入學生資料庫

def get_discord_id(std_id,discord_id): # 傳入student_id和discord_id，從學生資料庫中找到對應的學生資料
    if not std_id or not discord_id:    
        return jsonify({"success": False, "message": "缺少 student_id 或 discord_id"}), 200
    key = f"user:{std_id}"
    if not student_db.exists(key):
        return jsonify({"success": False, "message": "學號不存在"}), 200
    # 更新學生資料庫中的 discord_id
    student_db.hset(key, "discord_id", discord_id)
    return jsonify({"success": True, "message": "學生 discord_id 更新成功"}), 200
    

  

# 確認學生是否登入中
@app.route("/api/is_logged_in", methods=["POST"])
def is_logged_in(student_id):
    
    if not student_id:
        return jsonify({"success": False, "message": "缺少 student_id"}), 400

    key = f"user:{student_id}"
    if not student_db.exists(key):
        return jsonify({"success": False, "message": "帳號不存在"}), 404

    active_users = int(student_db.hget(key, "active_users") or 0)
    return jsonify({"success": True, "is_logged_in": bool(active_users)})

# 登出功能（清除 active_users 資料）
# @app.route("/api/logout", methods=["POST"])
def logout():
    try:
        data = request.get_json()
        if not data:
            return jsonify({"success": False, "message": "請提供 JSON 格式的資料"}), 400

        # student_id = data.get("student_id")
        # success, message = logout_logic(student_id)
        # 取得discord_id
        
        discord_id = data.get("discord_id")
        success, message = logout_logic(discord_id)
        return jsonify({"success": success, "message": message})
    except Exception as e:
        import traceback
        traceback.print_exc()
        return jsonify({"success": False, "message": "伺服器錯誤"}), 500
    
def logout_logic(discord_id):

    # 確認 discord_id 是否存在於 active_users_db
    if not discord_id:
        return False, "缺少 discord_id 資料"
    
    key = discord_id  # 使用 discord_id 作為 key
    if not active_users_db.exists(key):
        return False, "沒有登入過(discord_id未在 active_users_db 中找到)"
    
    std = active_users_db.hget(key, "std_id")
    # 確認學生已在active_users_db中，將該學生資料(key與欄位)從 active_users_db 中刪除    
    active_users_db.delete(key)
    
    student_db.hset(std, "active_users", 0)# 將學生 active_users 欄位設為 0，表示已登出
    return True, "登出成功"

def login_logic(student_id, password,discord_id):
    if not student_id or not password:
        return False, "缺少學號或密碼", None

    key = f"user:{student_id}"
    if not student_db.exists(key):
        return False, "帳號不存在", None

    hash_pw = student_db.hget(key, "hash_password").decode("utf-8")
    if not bcrypt.checkpw(password.encode("utf-8"), hash_pw.encode("utf-8")):
        return False, "密碼錯誤", None
    
    # 確認是否帳號已登入中
    active_users = int(student_db.hget(key, "active_users") or 0)
    if active_users:
        return False, "帳號已登入中，請先登出", None

    # student_db 的 active_users 欄位設為 1，表示已登入
    student_db.hset(key, "active_users", 1)

    get_discord_id(student_id,discord_id) # 登入時更新學生的 discord_id

    student_info = {
        "student_id": student_id,
        "name": student_db.hget(key, "name").decode("utf-8"),
        "email": student_db.hget(key, "email").decode("utf-8"),
        "class": student_db.hget(key, "class").decode("utf-8")
    }
    # active_users的key為discord_id
    # 欄位:
    #   - std_id: 學生學號（str）

    # 登入時新增登入學生discord_id，並將學生學號寫入active_users_db
    active_users_db.hset(discord_id, "std_id", student_id)
    return True, "登入成功", student_info

# 從active_users_db中取得登入學生的學號

def get_active_student_id(discord_id):
    if not discord_id:
        return None, "缺少 discord_id"

    if not active_users_db.exists(discord_id):
        return None, "該 discord_id 未登入"

    student_id = active_users_db.hget(discord_id, "std_id")
    if not student_id:
        return None, "未找到學生學號"

    # 將學生學號轉換為字串並返回
    return student_id.decode("utf-8"), None

# 清空題庫資料庫
# clear_unit_vector_db()

# 程式碼如果被刷新，則會清空 active_users_db 資料庫
active_users_db.flushdb()  # 清空 active_users_db 資料庫
# 程式碼如果被刷新，則會將所有 student_db 的 active_users 設為 0
for key in student_db.keys("user:*"):
    student_db.hset(key, "active_users", 0)  # 將所有學生的 active_users 設為 0



# 註冊 API
if __name__ == "__main__":
    app.run(debug=True, port=5001)  # 可自訂 port