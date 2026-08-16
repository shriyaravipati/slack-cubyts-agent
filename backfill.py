import os
import time
import psycopg2
from dotenv import load_dotenv
from slack_sdk import WebClient

load_dotenv()

client = WebClient(token=os.environ.get("SLACK_BOT_TOKEN"))

def get_db_connection():
    return psycopg2.connect(os.environ.get("DATABASE_URL"))

def save_message(channel_id, is_private, msg):
    if msg.get("subtype") is not None:
        return
    if not msg.get("text"):
        return

    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute(
        """
        INSERT INTO messages (slack_ts, channel_id, user_id, text, thread_ts, is_private)
        VALUES (%s, %s, %s, %s, %s, %s)
        ON CONFLICT DO NOTHING
        """,
        (
            msg.get("ts"),
            channel_id,
            msg.get("user"),
            msg.get("text"),
            msg.get("thread_ts"),
            is_private
        )
    )
    conn.commit()
    cur.close()
    conn.close()

def backfill_channel(channel_id, is_private):
    print(f"Backfilling channel {channel_id}...")
    cursor = None
    total = 0

    while True:
        response = client.conversations_history(
            channel=channel_id,
            cursor=cursor,
            limit=200
        )
        messages = response["messages"]

        for msg in messages:
            save_message(channel_id, is_private, msg)
            total += 1

        cursor = response.get("response_metadata", {}).get("next_cursor")
        if not cursor:
            break
        time.sleep(1)  # be polite to Slack's rate limits

    print(f"Done. Inserted/skipped {total} messages from {channel_id}.")

if __name__ == "__main__":
    # Fill in your actual channel IDs below
    channels = [
        {"id": "C0BPF9W2MDJ", "is_private": False},
        {"id": "C0BP5C5KNUB", "is_private": True},
        {"id": "C0BNW85JFTR", "is_private": False},
    ]

    for ch in channels:
        backfill_channel(ch["id"], ch["is_private"])