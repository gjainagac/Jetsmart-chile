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

CHECK_INTERVAL_MINUTES = int(os.getenv("CHECK_INTERVAL_MINUTES", "20"))
SEARCH_TERM = os.getenv("SEARCH_TERM", "JetSMART")

SEEN_FILE = "seen_news.json"

MEDIA_SITES = [
    {
        "name": "Emol",
        "domain": "emol.com",
    },
    {
        "name": "La Tercera",
        "domain": "latercera.com",
    },
    {
        "name": "Diario Financiero",
        "domain": "df.cl",
    },
    {
        "name": "BioBioChile",
        "domain": "biobiochile.cl",
    },
    {
        "name": "Cooperativa",
        "domain": "cooperativa.cl",
    },
    {
        "name": "CNN Chile",
        "domain": "cnnchile.com",
    },
    {
        "name": "T13",
        "domain": "t13.cl",
    },
    {
        "name": "24 Horas",
        "domain": "24horas.cl",
    },
    {
        "name": "Meganoticias",
        "domain": "meganoticias.cl",
    },
    {
        "name": "El Mostrador",
        "domain": "elmostrador.cl",
    },
    {
        "name": "La Nación",
        "domain": "lanacion.cl",
    },
    {
        "name": "Pulso",
        "domain": "latercera.com/pulso",
    },
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


def load_seen_news():
    try:
        with open(SEEN_FILE, "r", encoding="utf-8") as file:
            return set(json.load(file))
    except FileNotFoundError:
        return set()
    except Exception as e:
        print("Error leyendo seen_news.json:", e, flush=True)
        return set()


def save_seen_news(seen):
    try:
        with open(SEEN_FILE, "w", encoding="utf-8") as file:
            json.dump(list(seen), file, ensure_ascii=False, indent=2)
    except Exception as e:
        print("Error guardando seen_news.json:", e, flush=True)


def make_news_id(title, link):
    raw = f"{title}|{link}"
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def build_google_news_rss_url(media):
    query = f'"{SEARCH_TERM}" site:{media["domain"]} when:1d'
    encoded_query = quote_plus(query)

    return (
        f"https://news.google.com/rss/search?"
        f"q={encoded_query}&hl=es-419&gl=CL&ceid=CL:es-419"
    )


def is_relevant_entry(entry):
    title = entry.get("title", "").lower()
    summary = entry.get("summary", "").lower()

    search = SEARCH_TERM.lower()

    if search.lower() in title or search.lower() in summary:
        return True

    # Variantes frecuentes de escritura
    variants = [
        "jet smart",
        "jetsmart",
        "jetSMART".lower(),
    ]

    return any(variant in title or variant in summary for variant in variants)


def clean_google_news_link(link):
    return link


def build_alert_message(media_name, entry):
    title = entry.get("title", "Sin título")
    link = clean_google_news_link(entry.get("link", ""))
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
    print(f"Revisando {media['name']}...", flush=True)

    rss_url = build_google_news_rss_url(media)

    try:
        feed = feedparser.parse(rss_url)
    except Exception as e:
        print(f"Error leyendo RSS de {media['name']}: {e}", flush=True)
        return []

    alerts = []

    entries = feed.entries[:10]

    if not entries:
        print(f"Sin resultados recientes en {media['name']}", flush=True)
        return alerts

    for entry in entries:
        title = entry.get("title", "")
        link = entry.get("link", "")

        if not title or not link:
            continue

        if not is_relevant_entry(entry):
            continue

        news_id = make_news_id(title, link)

        if news_id in seen:
            continue

        alerts.append(entry)
        seen.add(news_id)

    return alerts


def run_check():
    print("Iniciando revisión de noticias sobre JetSMART...", flush=True)

    seen = load_seen_news()
    total_alerts = 0

    for media in MEDIA_SITES:
        try:
            alerts = check_media(media, seen)

            for entry in alerts:
                message = build_alert_message(media["name"], entry)
                send_telegram_message(message)
                total_alerts += 1
                time.sleep(2)

            time.sleep(3)

        except Exception as e:
            print(f"Error revisando {media['name']}: {e}", flush=True)

    save_seen_news(seen)

    print(f"Revisión terminada. Alertas nuevas enviadas: {total_alerts}", flush=True)


def main():
    print("Bot de monitoreo JetSMART iniciado", flush=True)

    send_telegram_message(
        "✅ Bot de monitoreo de noticias sobre JetSMART iniciado correctamente."
    )

    while True:
        run_check()
        print(f"Esperando {CHECK_INTERVAL_MINUTES} minutos...", flush=True)
        time.sleep(CHECK_INTERVAL_MINUTES * 60)


if __name__ == "__main__":
    main()
