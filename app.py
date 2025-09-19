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


@app.route("/add", methods=["POST"])
def add_payment():
    data = request.get_json()
    pay_dt = data.get("pay_dt")
    category = data.get("category")
    item = data.get("item")
    amount = data.get("amount")

    try:
        insert_payment(pay_dt, category, item, int(amount))
        return jsonify({"status": "success"}), 200
    except Exception as e:
        print("Add error:", e)
        return jsonify({"status": "error", "message": str(e)}), 400


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
                    messages.append(command_reply)

            reply_messages(reply_token, messages)

    return jsonify({"status": "ok"}), 200


def handle_command(text):
    if text == "/hello":
        return {"type": "text", "text": "哈囉！很高興見到你 👋"}

    elif text.startswith("/add"):
        parts = re.split(r"[,\s]+", text[4:].strip())

        if len(parts) != 4:
            return {
                "type": "template",
                "altText": "新增消費",
                "template": {
                    "type": "buttons",
                    "title": "新增消費紀錄",
                    "text": "請點擊下方按鈕填寫表單",
                    "actions": [
                        {
                            "type": "uri",
                            "label": "開啟表單",
                            "uri": "https://payment-bot-afpn.onrender.com/static/index.html"  # 你的 LIFF 頁面
                        }
                    ]
                }
            }            

        # if len(parts) != 4:
        #     return {"type": "text", "text": "格式錯誤，請輸入：/add 日期,類別,描述,金額"}
        else:
            try:
                pay_dt, category, item, amount = parts
                amount = int(amount)

                insert_payment(pay_dt, category, item, amount)
                return {"type": "text", "text": f"✅ 新增成功：{pay_dt}, {category}, {item}, {amount}"}

            except ValueError as e:
                return {"type": "text", "text": f"❌ 錯誤：{e}"}
            except Exception as e:
                print("Add error:", e)
                return {"type": "text", "text": "❌ 新增失敗，請檢查格式：/add 日期 類別 描述 金額"}

    elif text == "/list":
        records = get_latest_payments(limit=5)
        if not records:
            return {"type": "text", "text": "目前沒有消費紀錄"}

        # 建立 Flex Message 表格
        contents = {
            "type": "bubble",
            "body": {
                "type": "box",
                "layout": "vertical",
                "spacing": "sm",
                "contents": []
            }
        }

        # 表頭
        contents["body"]["contents"].append({
            "type": "box",
            "layout": "horizontal",
            "contents": [
                {"type": "text", "text": "日期", "weight": "bold", "size": "sm", "flex": 2},
                {"type": "text", "text": "類別", "weight": "bold", "size": "sm", "flex": 2},
                {"type": "text", "text": "描述", "weight": "bold", "size": "sm", "flex": 2},
                {"type": "text", "text": "金額", "weight": "bold", "size": "sm", "flex": 1, "align": "end"}
            ]
        })
        contents["body"]["contents"].append({"type": "separator"})

        # 資料列
        for pay_dt, category, item, amount in records:
            contents["body"]["contents"].append({
                "type": "box",
                "layout": "horizontal",
                "contents": [
                    {"type": "text", "text": pay_dt.strftime("%Y-%m-%d"), "size": "sm", "flex": 2},
                    {"type": "text", "text": category, "size": "sm", "flex": 2},
                    {"type": "text", "text": item, "size": "sm", "flex": 2, "wrap": True},
                    {"type": "text", "text": str(amount), "size": "sm", "flex": 1, "align": "end"}
                ]
            })

        return {
            "type": "flex",
            "altText": "最近 5 筆消費紀錄",
            "contents": contents
        }

    elif text == "/help":
        return {"type": "text", "text": (
            "可用指令：\n"
            "/hello → 打招呼\n"
            "/add 日期 類別 描述 金額 → 新增消費紀錄\n"
            "/list → 列出最近 5 筆消費紀錄\n"
            "/summary → 日期(起) 日期(迄) → 統計消費紀錄\n"
            "/help → 顯示幫助"
        )}

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


def get_latest_payments(limit=5):
    """查詢最近的消費紀錄"""
    conn = psycopg2.connect(DATABASE_URL)
    cur = conn.cursor()

    cur.execute("""
        SELECT pay_dt, category, item, amount
        FROM payment
        ORDER BY pay_dt DESC, id DESC
        LIMIT %s
    """, (limit,))

    rows = cur.fetchall()
    cur.close()
    conn.close()
    return rows


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
