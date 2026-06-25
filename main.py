import os
import time
import json
import hashlib
import requests
import feedparser
from urllib.parse import quote_plus
from dotenv import load_dotenv

load_dotenv()

TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID")

X_BEARER_TOKEN = os.getenv("X_BEARER_TOKEN")

CHECK_INTERVAL_MINUTES = int(os.getenv("CHECK_INTERVAL_MINUTES", "20"))
SEARCH_TERM = os.getenv("SEARCH_TERM", "JetSMART")

SEEN_FILE = "seen_items.json"

MEDIA_SITES = [
    {"name": "Emol", "domain": "emol.com"},
    {"name": "La Tercera", "domain": "latercera.com"},
    {"name": "Diario Financiero", "domain": "df.cl"},
    {"name": "BioBioChile", "domain": "biobiochile.cl"},
    {"name": "Cooperativa", "domain": "cooperativa.cl"},
    {"name": "CNN Chile", "domain": "cnnchile.com"},
    {"name": "T13", "domain": "t13.cl"},
    {"name": "24 Horas", "domain": "24horas.cl"},
    {"name": "Meganoticias", "domain": "meganoticias.cl"},
    {"name": "El Mostrador", "domain": "elmostrador.cl"},
    {"name": "La Nación", "domain": "lanacion.cl"},
    {"name": "Pulso", "domain": "latercera.com/pulso"},
]


def send_telegram_message(message):
    if not TELEGRAM_BOT_TOKEN or not TELEGRAM_CHAT_ID:
        print("Faltan TELEGRAM_BOT_TOKEN o TELEGRAM_CHAT_ID", flush=True)
        return

    url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"

    payload = {
        "chat_id": TELEGRAM_CHAT_ID,
        "text": message,
        "parse_mode": "HTML",
        "disable_web_page_preview": False,
    }

    try:
        response = requests.post(url, json=payload, timeout=20)

        if response.status_code != 200:
            print("Error enviando mensaje a Telegram:", response.text, flush=True)
        else:
            print("Mensaje enviado a Telegram correctamente", flush=True)

    except Exception as e:
        print("Error conectando con Telegram:", e, flush=True)


def load_seen_items():
    try:
        with open(SEEN_FILE, "r", encoding="utf-8") as file:
            return set(json.load(file))
    except FileNotFoundError:
        return set()
    except Exception as e:
        print("Error leyendo seen_items.json:", e, flush=True)
        return set()


def save_seen_items(seen):
    try:
        with open(SEEN_FILE, "w", encoding="utf-8") as file:
            json.dump(list(seen), file, ensure_ascii=False, indent=2)
    except Exception as e:
        print("Error guardando seen_items.json:", e, flush=True)


def make_item_id(source_type, title_or_text, link_or_id):
    raw = f"{source_type}|{title_or_text}|{link_or_id}"
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def is_relevant_text(text):
    text = text.lower()

    variants = [
        "jetsmart",
        "jet smart",
        "@jetsmart",
        "#jetsmart",
    ]

    return any(variant in text for variant in variants)


def build_google_news_rss_url(media):
    query = f'"{SEARCH_TERM}" site:{media["domain"]} when:1d'
    encoded_query = quote_plus(query)

    return (
        f"https://news.google.com/rss/search?"
        f"q={encoded_query}&hl=es-419&gl=CL&ceid=CL:es-419"
    )


def build_news_alert_message(media_name, entry):
    title = entry.get("title", "Sin título")
    link = entry.get("link", "")
    published = entry.get("published", "Fecha no disponible")

    return f"""
📰 <b>Nueva noticia sobre JetSMART</b>

🏛️ Medio: <b>{media_name}</b>
🗞️ Título: <b>{title}</b>
🕒 Publicación: {published}

🔗 Ver noticia:
{link}
""".strip()


def check_media(media, seen):
    print(f"Revisando medio: {media['name']}...", flush=True)

    rss_url = build_google_news_rss_url(media)

    try:
        feed = feedparser.parse(rss_url)
    except Exception as e:
        print(f"Error leyendo RSS de {media['name']}: {e}", flush=True)
        return 0

    sent_count = 0
    entries = feed.entries[:10]

    if not entries:
        print(f"Sin resultados recientes en {media['name']}", flush=True)
        return sent_count

    for entry in entries:
        title = entry.get("title", "")
        link = entry.get("link", "")
        summary = entry.get("summary", "")

        if not title or not link:
            continue

        if not is_relevant_text(f"{title} {summary}"):
            continue

        item_id = make_item_id("news", title, link)

        if item_id in seen:
            continue

        message = build_news_alert_message(media["name"], entry)
        send_telegram_message(message)

        seen.add(item_id)
        sent_count += 1
        time.sleep(2)

    return sent_count


def build_x_query():
    # -is:retweet evita retuits.
    # lang:es prioriza español, pero no excluye todos los casos útiles.
    return '(JetSMART OR "Jet SMART" OR @JetSMART OR #JetSMART) -is:retweet lang:es'


def search_x_mentions():
    if not X_BEARER_TOKEN:
        print("Falta X_BEARER_TOKEN. Se omite revisión de X.", flush=True)
        return []

    url = "https://api.x.com/2/tweets/search/recent"

    params = {
        "query": build_x_query(),
        "max_results": 10,
        "tweet.fields": "created_at,author_id,public_metrics,lang",
        "expansions": "author_id",
        "user.fields": "username,name,verified",
    }

    headers = {
        "Authorization": f"Bearer {X_BEARER_TOKEN}",
    }

    try:
        response = requests.get(url, headers=headers, params=params, timeout=25)

        if response.status_code != 200:
            print("Error consultando X:", response.status_code, response.text, flush=True)
            return []

        data = response.json()

    except Exception as e:
        print("Error conectando con X:", e, flush=True)
        return []

    tweets = data.get("data", [])
    users = data.get("includes", {}).get("users", [])

    users_by_id = {user["id"]: user for user in users if "id" in user}

    results = []

    for tweet in tweets:
        author_id = tweet.get("author_id")
        user = users_by_id.get(author_id, {})

        username = user.get("username", "")
        author_name = user.get("name", "Usuario de X")

        tweet_id = tweet.get("id", "")
        text = tweet.get("text", "")
        created_at = tweet.get("created_at", "")

        if not tweet_id or not text:
            continue

        tweet_url = f"https://x.com/{username}/status/{tweet_id}" if username else f"https://x.com/i/web/status/{tweet_id}"

        results.append(
            {
                "id": tweet_id,
                "text": text,
                "created_at": created_at,
                "username": username,
                "author_name": author_name,
                "url": tweet_url,
            }
        )

    return results


def build_x_alert_message(tweet):
    username = tweet.get("username", "")
    author = tweet.get("author_name", "Usuario de X")
    text = tweet.get("text", "")
    created_at = tweet.get("created_at", "")
    url = tweet.get("url", "")

    display_user = f"{author} (@{username})" if username else author

    return f"""
🐦 <b>Nueva mención de JetSMART en X</b>

👤 Usuario: <b>{display_user}</b>
🕒 Fecha: {created_at}

💬 Publicación:
{text}

🔗 Ver en X:
{url}
""".strip()


def check_x(seen):
    print("Revisando menciones en X...", flush=True)

    tweets = search_x_mentions()

    if not tweets:
        print("Sin menciones nuevas o sin acceso a X.", flush=True)
        return 0

    sent_count = 0

    for tweet in tweets:
        item_id = make_item_id("x", tweet["text"], tweet["id"])

        if item_id in seen:
            continue

        message = build_x_alert_message(tweet)
        send_telegram_message(message)

        seen.add(item_id)
        sent_count += 1
        time.sleep(2)

    return sent_count


def run_check():
    print("Iniciando revisión de JetSMART en noticias y X...", flush=True)

    seen = load_seen_items()
    total_alerts = 0

    for media in MEDIA_SITES:
        try:
            total_alerts += check_media(media, seen)
            time.sleep(3)

        except Exception as e:
            print(f"Error revisando {media['name']}: {e}", flush=True)

    try:
        total_alerts += check_x(seen)
    except Exception as e:
        print(f"Error revisando X: {e}", flush=True)

    save_seen_items(seen)

    print(f"Revisión terminada. Alertas nuevas enviadas: {total_alerts}", flush=True)


def main():
    print("Bot de monitoreo JetSMART iniciado", flush=True)

    send_telegram_message(
        "✅ Bot de monitoreo de noticias y X sobre JetSMART iniciado correctamente."
    )

    while True:
        run_check()
        print(f"Esperando {CHECK_INTERVAL_MINUTES} minutos...", flush=True)
        time.sleep(CHECK_INTERVAL_MINUTES * 60)


if __name__ == "__main__":
    main()
