from flask import Flask, request, jsonify
import threading
import json
import random
import time
import sys
from prompt_toolkit import PromptSession
from prompt_toolkit.patch_stdout import patch_stdout
from prompt_toolkit.formatted_text import HTML
from prompt_toolkit.styles import Style
from prompt_toolkit.key_binding import KeyBindings
from prompt_toolkit.application import Application
from prompt_toolkit.widgets import Label, Frame, TextArea
from prompt_toolkit.layout import Layout, HSplit

from question_gpt4o import generate_random_questions_gpt4o, evaluate_answer_gpt4o, classify_question_type
from database import (
    student_db, unit_vector_db, question_bank_db, ensure_unit_data_loaded,get_active_student_id,
    add_question, add_response_to_question, unit_order, login, logout, logout_logic,
    login_logic, add_question_type, app
)

# ensure_unit_data_loaded()
# app = Flask(__name__)

unit_name_list = [
    "單元一：堆積與優先佇列基礎",
    "單元二：進階堆積結構與變形",
    "單元三：搜尋樹與平衡結構"
]



# ========== Flask API ==========
# 加上port與前端對接
@app.route("/api/menu", methods=["GET"])
def get_main_menu():
    return jsonify({"menu": ["1. 登入學生", "2. 登出系統"]})

# 登入後介面: 1.查看進度 2.開始答題 3.離開介面
@app.route("/api/student/<did>/menu", methods=["GET"])
def get_student_menu(did):
    student_key, err = get_active_student_id(did)
    if err:
        return jsonify({"error": err})
    student_key = f"user:{student_key}"
    if not student_db.exists(student_key): # 學生不存在或未登入，回傳有問題的student_key
        return jsonify({"error": f"{student_key} not found or not logged in"})

    menu = ["1. 查看進度", "2. 開始答題"]
    # if len(completed_units) == len(unit_order):
        # menu.append("4. 完成所有單元，查看總結")
    if err:
        return jsonify({"error": err, "menu": []})

    return jsonify({"menu": menu})

# 選擇開始答題後介面: 選擇主單元(列出所有主單元)根據數字選擇，最後一個選項增加返回上一頁
@app.route("/api/student/<did>/units/menu", methods=["GET"])
def get_units_menu(did):
    
    # 從unit_name_map中獲取所有主單元
    menu = [f"{i+1}. {topic}" for i, topic in enumerate(unit_name_list)]
    menu.append("0. 返回上一頁")    
    
    return jsonify({"menu": menu})

# 選擇完主單元後介面: 根據主單元讓使用者選擇子主題(列出所有子主題)根據數字選擇，最後一個選項增加返回上一頁
@app.route("/api/student/<did>/topics/menu", methods=["GET"])
def get_topics_menu(did): # 根據unitkey(學生選擇的主單元)獲取對應的子主題列表 
    # unit_vector_db中unitkey為unit欄位的值，將unit欄內容與unitkey相同的子主題(key)列出
    unitkey = request.args.get("unitkey")  # 從請求參數中獲取unitkey
    if not unitkey:
        return jsonify({"error": "unitkey is required"})
    keys = unit_vector_db.keys(f"subtopic:*")
    topics = []
    for key in keys:
        topic = key.decode("utf-8").replace("subtopic:", "")
        unit = unit_vector_db.hget(key, "unit").decode("utf-8")
        if unit == unitkey:
            topics.append(topic)
    if not topics:
        return jsonify({"error": "no topics found for this unit"})
    menu = [f"{i+1}. {topic}" for i, topic in enumerate(topics)]
    menu.append("0. 返回上一頁")  # 增加返回上一頁選項

    return jsonify({"menu": menu})

#【注意：按鈕面對過長的題目會用．．．省略，需修改】
@app.route("/api/student/<did>/questions", methods=["POST"]) # 根據學生選擇的topic生成問題
def api_generate_questions(did):
    # 跟前端請求獲得topic
    topic = request.json.get("topic") # 從請求參數中獲取topic
    if not topic:
        return jsonify({"error": "topic is required"})

    questions = generate_random_questions_gpt4o(topic, 3)
    if not questions:
        return jsonify({"error": "no questions generated"})
    # 輸出question的格式
    # [{"question": "問題內容", "options": ["選項1", "選項2", ...], "type": "問題類型"}, ...]
    
    return jsonify({"questions": questions})

@app.route("/api/student/<did>/question", methods=["POST"]) # 根據學生選擇的問題選項(問題ID)獲取問題內容
def api_get_question(did): # question_data是字串
    question_data = request.args.get("question_data") # 從請求參數中獲取問題數據
    if not question_data:
        return jsonify({"error": "question_data is required"})

    # 如果問題ID裡有數字(如:1.(問題內容)或2.(問題內容))，則刪掉題號
   
    # 移除題號（1.、2.、3.）
    if question_data.startswith(("1.", "2.", "3.")):
        question_data = question_data.split(".", 1)[1].strip()

       # 包裝問題

    full_question = f"請回答 {question_data}。並依題目給出最合適的答案，答案越詳盡越好。"

    return jsonify({"question": full_question})
                                                              


@app.route("/api/student/<did>/answer", methods=["POST"]) # 提交答案
def api_submit_answer(did):
    sid, err = get_active_student_id(did)
    data = request.json # 獲取JSON數據(包含answer, question, unit, topic字段與total_start_time, typing_start_time時間
    # -answer: 學生的答案
    # -question: 學生回答的問題
    # -unit: 單元名稱
    # -topic: 子主題名稱
    # -total_start_time: 總開始時間
    # -typing_start_time: 輸入開始時間
    answer = data.get("answer", "")
    question = data.get("question")
    unit = data.get("unit")
    topic = data.get("topic")
    total_start_time = data.get("total_start_time", time.time()) 
    typing_start_time = data.get("typing_start_time", time.time())

    is_suspected, cps = detect_ai_like_answer(answer, typing_start_time, total_start_time)

    if is_suspected:
        score = 0
        feedback = "⚠️ 可疑複製貼上，該題不予計分。"
    else:
        result = evaluate_answer_gpt4o(question, answer)
        score, feedback = 0, ""
        for line in result.splitlines():
            if any(k in line for k in ["分數", "score"]):
                try:
                    score = int(''.join(filter(str.isdigit, line)))
                except:
                    pass
            elif not feedback:
                feedback = line.strip()
        score = max(0, min(score, 10))
        feedback = feedback or "無評語"

    qid = f"Q{random.randint(1000, 9999)}" # 隨機生成問題ID

    # qid格式：
    # 【問題類型】問題內容。
    # 例如：【選擇題】請問堆積的定義是什麼？
    # 【....】中為問題類型
    # 將"qa_type"字串從 qid的【】中取出
    qa_type = question.split("】")[0].replace("【", "") if "】" in question else "未知類型"
    
    # 透過add_question_type函數添加到問題庫
    add_question_type(qid, qa_type) # 將問題類型加入問題庫
    # question_type = classify_question_type(question) # 判斷問題類型
    add_response_to_question(qid, sid, answer, time.time() - total_start_time, len(answer), is_suspected, not is_suspected, score, feedback)
    # 將答案加入學生的問題庫
    # 回傳分數、評語、是否可疑、CPS等信息
    # 【未來加上空白要求前端再次要求學生作答】
    return jsonify({"score": score, "feedback": feedback, "is_suspected": is_suspected, "cps": cps})

# @app.route("/api/student/<sid>/summary", methods=["GET"]) # 獲取學生總結
# def api_summary(sid):
    # key = f"user:{sid}"
    # if not student_db.exists(key):
        # return jsonify({"error": "not found"}), 404

    # data = {
       # "completed_units": json.loads(student_db.hget(key, "completed_units") or "[]"),
       # "completed_topics": json.loads(student_db.hget(key, "completed_topics") or "[]"),
       # "unit_progress": json.loads(student_db.hget(key, "unit_progress") or "{}"),
       # "progress": json.loads(student_db.hget(key, "progress") or "{}"),
       # "score": int(student_db.hget(key, "score") or 0),
       # "accuracy": float(student_db.hget(key, "accuracy") or 0.0)
    #}
    #return jsonify(data)

# 註解掉register功能
#@app.route("/api/register", methods=["POST"])
#def api_register():
    #sid = request.json.get("student_id")
    #result = register_student(sid)
    #return jsonify({"message": result})

@app.route("/api/login", methods=["POST"]) # 使用database的login()登入學生
def api_login(): 
    sid = request.json.get("student_id")
    password = request.json.get("password")
    discord_id = request.json.get("discord_id")
    
    success, message, info = login_logic(sid, password, discord_id)

    if success:
        return jsonify({"message": message, "sid": sid, "info": info})
    else:
        return jsonify({"message": message})

    
@app.route("/api/logout", methods=["POST"]) # 使用database的logout()登出學生
def api_logout():
    did = request.json.get("discord_id")
    success, message = logout_logic(did)
    if success:
        return jsonify({"message": message})
    else:
        return jsonify({"message": message})
    
@app.route("/api/student/<did>/units", methods=["GET"]) # 取得學生的單元進度
def api_get_units(did,sid):
    student_key = f"user:{sid}"
    if not student_db.exists(student_key):
        return jsonify({"error": "not found"}), 404

    completed_units = json.loads(student_db.hget(student_key, "completed_units") or "[]")
    unit_progress = json.loads(student_db.hget(student_key, "unit_progress") or "{}")

    units = []
    for unit in unit_order:
        unit_data = {
            "unit": unit,
            # "name": unit_name_map.get(unit, unit),
            "completed": unit in completed_units,
            "progress": unit_progress.get(unit, 0)
        }
        units.append(unit_data)

    return jsonify(units)

@app.route("/api/student/<did>/progress", methods=["GET"]) # 取得學生的進度
def api_student_progress(did,sid):
    student_key = f"user:{sid}"
    student_progress = json.loads(student_db.hget(student_key, "progress") or "{}")
    return jsonify({"progress": student_progress})


@app.route("/api/student/<did>/topics", methods=["GET"]) # 取得學生的子主題
def api_get_topics(did):
    keys = unit_vector_db.keys("subtopic:*")
    unit_topic_map = {}
    for key in keys:
        topic = key.decode("utf-8").replace("subtopic:", "")
        unit = unit_vector_db.hget(key, "unit").decode("utf-8")
        unit_topic_map.setdefault(unit, []).append(topic)
    return jsonify(unit_topic_map)





# ========== 原有 CLI 入口 ==========
# 這個函數用於偵測是否為可疑的 AI 或複製貼上輸入。
def detect_ai_like_answer(answer_text, typing_start_time, total_start_time, min_chars=30, max_cps=3.0, min_suspect_chars=50):
    char_len = len(answer_text.strip())
    if char_len < min_chars:
        return False, 0.0
    duration = typing_start_time # 計算輸入時間
    cps = char_len / duration if duration > 0 else float('inf')
    if cps > max_cps and char_len >= min_suspect_chars:
        return True, cps
    return False, cps

# sid = get_student_id("885576463552765984")
# print(sid)
app.run(debug=False, host="0.0.0.0", port=5000)

"""
# 原本 CLI 主程式入口
from main_cli import main as cli_main

if __name__ == "__main__":
    if "--cli" in sys.argv:
        cli_main()
    else:
        app.run(debug=True, host="0.0.0.0", port=5000)
"""
