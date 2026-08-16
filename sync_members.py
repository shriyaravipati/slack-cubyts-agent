import os
import psycopg2
from dotenv import load_dotenv
from slack_sdk import WebClient

load_dotenv()

client = WebClient(token=os.environ.get("SLACK_BOT_TOKEN"))

def get_db_connection():
    return psycopg2.connect(os.environ.get("DATABASE_URL"))

def save_members(channel_id, user_ids):
    conn = get_db_connection()
    cur = conn.cursor()
    for user_id in user_ids:
        cur.execute(
            """
            INSERT INTO channel_members (channel_id, user_id)
            VALUES (%s, %s)
            ON CONFLICT DO NOTHING
            """,
            (channel_id, user_id)
        )
    conn.commit()
    cur.close()
    conn.close()

def sync_channel_members(channel_id):
    response = client.conversations_members(channel=channel_id)
    user_ids = response["members"]
    save_members(channel_id, user_ids)
    print(f"Synced {len(user_ids)} members for channel {channel_id}")

if __name__ == "__main__":
    # Reuse the same channel IDs from backfill.py
    channels = [
        "C0BPF9W2MDJ",
        "C0BP5C5KNUB",
        "C0BNW85JFTR",
    ]

    for ch in channels:
        sync_channel_members(ch)