import os
import json
import psycopg2
import anthropic
from dotenv import load_dotenv

load_dotenv()

client = anthropic.Anthropic()  # reads ANTHROPIC_API_KEY from environment automatically

def get_db_connection():
    return psycopg2.connect(os.environ.get("DATABASE_URL"))

def fetch_messages_without_entities():
    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute("""
        SELECT m.id, m.text FROM messages m
        LEFT JOIN entities e ON e.message_id = m.id
        WHERE e.id IS NULL
    """)
    rows = cur.fetchall()
    cur.close()
    conn.close()
    return rows

def extract_entities(text):
    prompt = f"""Extract structured entities from this Slack message. Return ONLY valid JSON, no other text.

Message: "{text}"

Return a JSON array of objects, each with "entity_type" (one of: person, project, decision, date) and "entity_value" (a short string). Only include entities that are clearly present. If none, return an empty array.

Example output: [{{"entity_type": "person", "entity_value": "Sarah"}}, {{"entity_type": "project", "entity_value": "mobile redesign"}}]"""

    response = client.messages.create(
        model="claude-sonnet-4-5",
        max_tokens=500,
        messages=[{"role": "user", "content": prompt}]
    )

    raw = response.content[0].text.strip()

    # Strip markdown code fences if present
    if raw.startswith("```"):
        raw = raw.split("\n", 1)[1]  # remove first line (```json or ```)
        raw = raw.rsplit("```", 1)[0]  # remove trailing ```
        raw = raw.strip()

    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        print(f"Failed to parse: {raw}")
        return []

def save_entities(message_id, entities):
    conn = get_db_connection()
    cur = conn.cursor()
    for e in entities:
        cur.execute(
            "INSERT INTO entities (message_id, entity_type, entity_value) VALUES (%s, %s, %s)",
            (message_id, e.get("entity_type"), e.get("entity_value"))
        )
    conn.commit()
    cur.close()
    conn.close()

def main():
    rows = fetch_messages_without_entities()
    print(f"Found {len(rows)} messages needing entity extraction.")

    for message_id, text in rows:
        entities = extract_entities(text)
        save_entities(message_id, entities)
        print(f"Message {message_id}: extracted {len(entities)} entities")

    print("Done.")

if __name__ == "__main__":
    main()