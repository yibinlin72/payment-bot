import os
import re
import requests
import psycopg2
from flask import Flask, request, abort, jsonify
from datetime import datetime

app = Flask(__name__)

LINE_CHANNEL_ACCESS_TOKEN = os.environ.get("LINE_CHANNEL_ACCESS_TOKEN")
DATABASE_URL = os.environ.get("DATABASE_URL")

# Render 健康檢查 + LINE verify 測試
@app.route("/", methods=["GET", "HEAD", "POST"])
def index():
    if request.method == "POST":
        return ("OK", 200)
    return ("", 200)

# LINE Webhook
@app.route("/webhook", methods=["POST"])
def webhook():
    body = request.get_json()
    if not body:
        abort(400)

    print("Received event:", body)

    for event in body.get("events", []):
        if event["type"] == "message" and event["message"]["type"] == "text":
            user_text = event["message"]["text"].strip()
            reply_token = event["replyToken"]

            # 預設回覆：echo
            messages = [{"type": "text", "text": f"收到: {user_text}"}]

            if user_text.startswith("/"):
                command_reply = handle_command(user_text)
                if command_reply:
                    messages.append({"type": "text", "text": command_reply})

            reply_messages(reply_token, messages)

    return jsonify({"status": "ok"}), 200


def handle_command(text):
    if text == "/hello":
        return "哈囉！很高興見到你 👋"

    elif text.startswith("/add"):
        parts = re.split(r"[,\s]+", text[4:].strip())
        if len(parts) != 4:
            return "格式錯誤，請輸入：/add 日期 類別 描述 金額"

        try:
            pay_dt, category, item, amount = parts
            amount = int(amount)

            insert_payment(pay_dt, category, item, amount)
            return f"✅ 新增成功：{pay_dt}, {category}, {item}, {amount}"

        except ValueError as e:
            return f"❌ 錯誤：{e}"
        except Exception as e:
            print("Add error:", e)
            return "❌ 新增失敗，請檢查格式：/add 日期 類別 描述 金額"

    elif text == "/list":
        return "這是你的消費紀錄"

    elif text == "/help":
        return (
            "可用指令：\n"
            "/hello：打招呼\n"
            "/add 日期 類別 描述 金額：新增消費紀錄\n"
            "/list：列出消費紀錄\n"
            "/help：顯示幫助"
        )

    else:
        return f"未知的指令：{text}"

def validate_date_format(date_str):
    """檢查日期是否符合 yyyy-MM-dd 格式"""
    pattern = r"^\d{4}-\d{2}-\d{2}$"
    if not re.match(pattern, date_str):
        return False
    try:
        datetime.strptime(date_str, "%Y-%m-%d")  # 驗證日期有效性
        return True
    except ValueError:
        return False


def insert_payment(pay_dt, category, item, amount):
    """寫入 payment 資料表"""

    if not validate_date_format(pay_dt):
        raise ValueError("日期格式錯誤，必須為 yyyy-MM-dd")

    conn = psycopg2.connect(DATABASE_URL)
    cur = conn.cursor()

    cur.execute(
        """
        INSERT INTO payment (pay_dt, category, item, amount)
        VALUES (%s, %s, %s, %s)
        """,
        (pay_dt, category, item, amount)
    )

    conn.commit()
    cur.close()
    conn.close()


def reply_messages(reply_token, messages):
    """一次回覆多則訊息"""
    url = "https://api.line.me/v2/bot/message/reply"
    headers = {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {LINE_CHANNEL_ACCESS_TOKEN}"
    }
    payload = {
        "replyToken": reply_token,
        "messages": messages
    }
    response = requests.post(url, headers=headers, json=payload)
    print("LINE API response:", response.status_code, response.text)
    return response


if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port)
