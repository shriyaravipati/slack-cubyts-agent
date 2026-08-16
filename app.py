import os
import logging
import json
import psycopg2
import voyageai
import anthropic
from dotenv import load_dotenv
from slack_bolt import App

load_dotenv()
logging.basicConfig(level=logging.INFO)

app = App(
    token=os.environ.get("SLACK_BOT_TOKEN"),
    signing_secret=os.environ.get("SLACK_SIGNING_SECRET")
)

vo = voyageai.Client(api_key=os.environ.get("VOYAGE_API_KEY"))
claude = anthropic.Anthropic()

def get_db_connection():
    return psycopg2.connect(os.environ.get("DATABASE_URL"))

def save_message(event):
    if event.get("subtype") is not None:
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
            event.get("ts"), event.get("channel"), event.get("user"),
            event.get("text"), event.get("thread_ts"),
            event.get("channel_type") == "group"
        )
    )
    conn.commit()
    cur.close()
    conn.close()

def get_user_channels(user_id):
    """Return list of channel_ids this user is a member of."""
    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute("SELECT channel_id FROM channel_members WHERE user_id = %s", (user_id,))
    rows = cur.fetchall()
    cur.close()
    conn.close()
    return [r[0] for r in rows]

def semantic_search(query_text, allowed_channels, top_k=8):
    """Embed the query and find the most similar messages, filtered by permission."""
    if not allowed_channels:
        return []

    result = vo.embed([query_text], model="voyage-3.5", input_type="query")
    query_embedding = result.embeddings[0]

    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute(
        """
        SELECT text, channel_id, slack_ts, 1 - (embedding <=> %s::vector) AS similarity
        FROM messages
        WHERE channel_id = ANY(%s) AND embedding IS NOT NULL
        ORDER BY embedding <=> %s::vector
        LIMIT %s
        """,
        (query_embedding, allowed_channels, query_embedding, top_k)
    )
    rows = cur.fetchall()
    cur.close()
    conn.close()
    return rows

def entity_search(query_text, allowed_channels):
    """Find messages whose extracted entities loosely match the query text."""
    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute(
        """
        SELECT DISTINCT m.text, m.channel_id, m.slack_ts, e.entity_type, e.entity_value
        FROM entities e
        JOIN messages m ON m.id = e.message_id
        WHERE m.channel_id = ANY(%s)
        AND e.entity_value ILIKE %s
        """,
        (allowed_channels, f"%{query_text}%")
    )
    rows = cur.fetchall()
    cur.close()
    conn.close()
    return rows

def synthesize_answer(query, semantic_results, entity_results):
    context_lines = []
    for text, channel_id, ts, similarity in semantic_results:
        context_lines.append(f"[Semantic match, channel {channel_id}]: {text}")
    for text, channel_id, ts, etype, evalue in entity_results:
        context_lines.append(f"[Entity match ({etype}={evalue}), channel {channel_id}]: {text}")

    context = "\n".join(context_lines) if context_lines else "No relevant messages found."

    prompt = f"""A user asked: "{query}"

Here are relevant Slack messages retrieved by search:

{context}

Answer the user's question using this context. Separate your answer into two parts:
1. Direct answer based on messages that clearly and explicitly relate to the question
2. Related context — connections you inferred between messages that aren't explicitly stated but seem relevant (explain why you think they're connected)

If nothing relevant was found, say so honestly rather than making things up."""

    response = claude.messages.create(
        model="claude-sonnet-4-5",
        max_tokens=800,
        messages=[{"role": "user", "content": prompt}]
    )
    return response.content[0].text

@app.event("message")
def handle_message_events(event, logger):
    logger.info(f"Saving message: {event.get('text')}")
    save_message(event)

@app.command("/ask")
def handle_ask_command(ack, respond, command, logger):
    ack()  # acknowledge immediately, Slack requires a response within 3 seconds

    query = command["text"]
    user_id = command["user_id"]
    logger.info(f"User {user_id} asked: {query}")

    allowed_channels = get_user_channels(user_id)
    semantic_results = semantic_search(query, allowed_channels)
    entity_results = entity_search(query, allowed_channels)

    answer = synthesize_answer(query, semantic_results, entity_results)
    respond(answer)

if __name__ == "__main__":
    app.start(port=3000)