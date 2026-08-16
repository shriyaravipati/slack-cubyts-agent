import os
import psycopg2
import voyageai
from dotenv import load_dotenv

load_dotenv()
print("Loaded key:", os.environ.get("VOYAGE_API_KEY"))

vo = voyageai.Client(api_key=os.environ.get("VOYAGE_API_KEY"))

def get_db_connection():
    return psycopg2.connect(os.environ.get("DATABASE_URL"))

def fetch_messages_without_embeddings():
    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute("SELECT id, text FROM messages WHERE embedding IS NULL")
    rows = cur.fetchall()
    cur.close()
    conn.close()
    return rows

def update_embedding(message_id, embedding):
    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute(
        "UPDATE messages SET embedding = %s WHERE id = %s",
        (embedding, message_id)
    )
    conn.commit()
    cur.close()
    conn.close()

def main():
    rows = fetch_messages_without_embeddings()
    print(f"Found {len(rows)} messages needing embeddings.")

    # Batch texts together for efficiency
    texts = [text for (_, text) in rows]
    ids = [msg_id for (msg_id, _) in rows]

    if not texts:
        print("Nothing to embed.")
        return

    result = vo.embed(texts, model="voyage-3.5", input_type="document")

    for msg_id, embedding in zip(ids, result.embeddings):
        update_embedding(msg_id, embedding)
        print(f"Updated embedding for message {msg_id}")

    print("Done.")

if __name__ == "__main__":
    main()