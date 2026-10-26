from __future__ import annotations

import html
import os
from typing import Any
from urllib.parse import quote

import requests

from jobscout_links import load_config, load_jobs_from_sqlite, score_job, choose_job_links


TELEGRAM_API = "https://api.telegram.org"


def enviar_telegram(token: str, chat_id: str, mensaje: str) -> None:
    response = requests.post(
        f"{TELEGRAM_API}/bot{token}/sendMessage",
        json={
            "chat_id": chat_id,
            "text": mensaje,
            "parse_mode": "HTML",
            "disable_web_page_preview": True,
        },
        timeout=20,
    )
    response.raise_for_status()
    payload = response.json()
    if not payload.get("ok"):
        raise RuntimeError("Telegram no confirmó el envío. Comprueba bot y chat ID.")


def escapar(value: Any) -> str:
    return html.escape(str(value or "").strip(), quote=True)


def construir_mensajes(ofertas: list[dict[str, Any]], max_chars: int = 3600) -> list[str]:
    header = "<b>JOBSCOUT · OFERTAS RECOMENDADAS</b>\nEl índice es una señal de relevancia, no una probabilidad de contratación.\n\n"
    mensajes: list[str] = []
    actual = header
    for n, job in enumerate(ofertas, 1):
        title = escapar(job.get("title") or "Puesto sin título")
        company = escapar(job.get("company") or "Empresa sin especificar")
        location = escapar(job.get("location") or "Ubicación no especificada")
        score = int(job.get("score", 0))
        source, apply = choose_job_links(job)
        url = source or apply
        link = f'<a href="{html.escape(url, quote=True)}">Abrir anuncio</a>' if url else "Sin enlace específico"
        block = f"<b>{n}. {title}</b>\n🏢 {company}\n📍 {location}\n⭐ Encaje: <b>{score}/100</b>\n🔗 {link}\n\n"
        if len(actual) + len(block) > max_chars and actual.strip():
            mensajes.append(actual)
            actual = ""
        actual += block
    if actual.strip():
        mensajes.append(actual)
    return mensajes


def main() -> int:
    config, config_path = load_config()
    # Secrets must come from environment variables, never from a public YAML file.
    token = os.getenv("TELEGRAM_BOT_TOKEN", "").strip()
    chat_id = os.getenv("TELEGRAM_CHAT_ID", "").strip()
    if not token or not chat_id:
        print("Faltan TELEGRAM_BOT_TOKEN y/o TELEGRAM_CHAT_ID. Configúralos como variables de entorno.")
        print("En PowerShell: $env:TELEGRAM_BOT_TOKEN='TOKEN_NUEVO'; $env:TELEGRAM_CHAT_ID='TU_CHAT_ID'")
        return 2

    jobs, diagnostics = load_jobs_from_sqlite(config)
    if not jobs:
        print("No se encontraron ofertas en una base de datos conocida:")
        for item in diagnostics:
            print(f" - {item}")
        return 1

    scoring = config.get("scoring", {}) if isinstance(config.get("scoring", {}), dict) else {}
    try:
        min_score = int(scoring.get("min_alert_score", 45))
    except (TypeError, ValueError):
        min_score = 45

    ranked: list[dict[str, Any]] = []
    seen: set[str] = set()
    for job in jobs:
        source, apply = choose_job_links(job)
        if not (source or apply):
            continue
        # Keep the title, company and link tied to the same row from the database.
        identity = source or apply
        if identity in seen:
            continue
        seen.add(identity)
        score = score_job(job, config)
        if score < min_score:
            continue
        item = dict(job)
        item["job_url"] = source
        item["job_url_direct"] = apply
        item["score"] = score
        ranked.append(item)

    ranked.sort(key=lambda job: (job["score"], str(job.get("date_posted") or "")), reverse=True)
    ranked = ranked[:25]
    if not ranked:
        print(f"No hay ofertas con enlace específico y puntuación >= {min_score}.")
        return 0

    messages = construir_mensajes(ranked)
    print(f"Configuración: {config_path or 'no encontrada'}")
    print(f"Ofertas seleccionadas: {len(ranked)}. Mensajes a enviar: {len(messages)}.")
    for i, message in enumerate(messages, 1):
        try:
            enviar_telegram(token, chat_id, message)
            print(f"Mensaje {i}/{len(messages)} enviado.")
        except (requests.RequestException, RuntimeError) as exc:
            print(f"Error al enviar el mensaje {i}: {exc}")
            return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
