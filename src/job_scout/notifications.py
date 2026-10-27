"""Build and deliver explainable top-job digests through ntfy, Telegram or SMTP.

The module never obtains or persists credentials: callers must supply them from
environment variables or Streamlit secrets. Missing vacancy information is
reported as an item to verify, never treated as a negative fact.
"""
from __future__ import annotations

import html
import re
import smtplib
import ssl
from email.message import EmailMessage
from typing import Any, Iterable
from urllib.parse import urlparse

import requests


MAX_TOP_JOBS = 10
TELEGRAM_MESSAGE_LIMIT = 3500
NTFY_MESSAGE_LIMIT = 3800


class NotificationError(RuntimeError):
    """A notification could not be delivered; messages are safe to show in UI."""


def _text(value: Any, fallback: str = "") -> str:
    if value is None:
        return fallback
    text = str(value).strip()
    if text.casefold() in {"", "none", "nan", "<na>", "null"}:
        return fallback
    return text


def _number(value: Any, fallback: float = 0.0) -> float:
    try:
        number = float(value)
        return number if number == number else fallback
    except (TypeError, ValueError):
        return fallback


def _safe_url(value: Any) -> str:
    url = _text(value)
    try:
        parsed = urlparse(url)
    except ValueError:
        return ""
    return url if parsed.scheme in {"http", "https"} and parsed.netloc else ""


def analyse_digest_entry(job: dict[str, Any], rank: int = 1) -> dict[str, Any]:
    """Create transparent pros / points-to-check from fields actually present."""
    title = _text(job.get("title"), "Puesto sin título")
    company = _text(job.get("company"), "Empresa sin especificar")
    score = round(max(0.0, min(100.0, _number(job.get("calculated_score", job.get("score"))))))
    url = _safe_url(job.get("job_url")) or _safe_url(job.get("source_url"))
    apply_url = _safe_url(job.get("job_url_direct")) or _safe_url(job.get("apply_url"))
    source = _text(job.get("source"), "Fuente no indicada").replace("_", " ").title()
    salary = _text(job.get("salary"))
    salary_known = bool(job.get("salary_known")) or job.get("salary_eur_year_min") is not None
    experience = _text(job.get("experience_level"), "No indicado")
    contract = _text(job.get("employment_type_label"), "No indicado")
    work_mode = _text(job.get("work_mode_label"), "No indicado")
    duration = _text(job.get("duration_band"), "No indicado")
    requirements = job.get("requirements")
    requirements = [str(item) for item in requirements if _text(item)] if isinstance(requirements, (list, tuple, set)) else []
    mismatch = job.get("domain_mismatch")
    if not isinstance(mismatch, dict):
        mismatch = {}

    pros: list[str] = []
    checks: list[str] = []
    if score >= 70:
        pros.append(f"Índice de relevancia alto ({score}/100)")
    elif score >= 45:
        pros.append(f"Índice de relevancia intermedio ({score}/100)")
    else:
        pros.append(f"Relevancia por revisar ({score}/100)")
    if url or apply_url:
        pros.append(f"Enlace específico disponible ({source})")
    if salary:
        pros.append(f"Salario publicado: {salary}")
    elif salary_known:
        pros.append("El anuncio contiene información salarial detectable")
    if experience != "No indicado":
        pros.append(f"Nivel detectado: {experience}")
    if contract != "No indicado":
        pros.append(f"Contrato: {contract}")
    if work_mode != "No indicado":
        pros.append(f"Modalidad: {work_mode}")
    if requirements:
        pros.append("Herramientas mencionadas: " + ", ".join(requirements[:4]))
    if duration != "No indicado":
        pros.append(f"Duración: {duration}")

    if not salary or not salary_known:
        checks.append("Salario no indicado o no comparable; confirmar en el anuncio")
    if experience == "No indicado":
        checks.append("Experiencia requerida no especificada claramente")
    if contract == "No indicado":
        checks.append("Tipo de contrato no indicado")
    if work_mode == "No indicado":
        checks.append("Modalidad de trabajo por confirmar")
    if duration == "No indicado":
        checks.append("Duración no indicada")
    reason = _text(mismatch.get("reason"))
    if reason:
        checks.insert(0, "Posible desajuste de área: " + reason)
    if not _text(job.get("description")):
        checks.append("Descripción incompleta; abrir la fuente para valorar funciones")
    if not url and not apply_url:
        checks.append("No se encontró un enlace específico verificable")
    if not checks:
        checks.append("Verificar funciones, requisitos y condiciones en la fuente original")
    if not pros:
        pros.append("Revisar el anuncio original antes de decidir")

    return {
        "rank": rank,
        "title": title,
        "company": company,
        "score": score,
        "location": _text(job.get("location"), "Ubicación no indicada"),
        "source": source,
        "salary": salary or ("No indicado" if not salary_known else "Detectado; revisar detalle"),
        "experience": experience,
        "contract": contract,
        "work_mode": work_mode,
        "duration": duration,
        "requirements": requirements,
        "pros": pros[:4],
        "cons": checks[:4],
        "job_url": url,
        "apply_url": apply_url,
    }


def build_top_jobs_digest(jobs: Iterable[dict[str, Any]], limit: int = MAX_TOP_JOBS) -> list[dict[str, Any]]:
    """Rank valid job records and prepare no more than the ten best entries."""
    safe_limit = max(0, min(MAX_TOP_JOBS, int(limit)))
    rows = [dict(job) for job in jobs if isinstance(job, dict) and _text(job.get("title"))]
    rows.sort(key=lambda job: _number(job.get("calculated_score", job.get("score"))), reverse=True)
    return [analyse_digest_entry(job, rank=index + 1) for index, job in enumerate(rows[:safe_limit])]


def render_digest_text(entries: Iterable[dict[str, Any]]) -> str:
    entries = list(entries)
    lines = [
        f"JobScout Pro · Top {len(entries)} ofertas",
        "Selección orientativa según relevancia y filtros actuales. Revisa siempre la fuente original.",
        "",
    ]
    for entry in entries:
        lines.extend([
            f"{entry['rank']}. {entry['title']} — {entry['company']} · Relevancia {entry['score']}/100",
            f"   Ubicación: {entry['location']} | Salario: {entry['salary']}",
            f"   Contrato: {entry['contract']} | Experiencia: {entry['experience']} | Modalidad: {entry['work_mode']}",
            "   A favor: " + "; ".join(entry["pros"]),
            "   A revisar: " + "; ".join(entry["cons"]),
        ])
        if entry.get("job_url"):
            lines.append(f"   Anuncio: {entry['job_url']}")
        if entry.get("apply_url") and entry["apply_url"] != entry.get("job_url"):
            lines.append(f"   Candidatura: {entry['apply_url']}")
        lines.append("")
    return "\n".join(lines).strip()


def _split_digest_chunks(
    text: str,
    limit: int,
    *,
    byte_limit: int | None = None,
) -> list[str]:
    """Split on job boundaries and enforce character/UTF-8 byte limits without dropping text."""
    def fits(value: str) -> bool:
        return len(value) <= limit and (
            byte_limit is None or len(value.encode("utf-8")) <= byte_limit
        )

    def split_long_block(block: str) -> list[str]:
        if fits(block):
            return [block]
        parts: list[str] = []
        current_part = ""
        for character in block:
            candidate_part = current_part + character
            if current_part and not fits(candidate_part):
                parts.append(current_part)
                current_part = character
            else:
                current_part = candidate_part
        if current_part:
            parts.append(current_part)
        return parts

    chunks: list[str] = []
    current = ""
    for block in text.split("\n\n"):
        candidate = block if not current else current + "\n\n" + block
        if fits(candidate):
            current = candidate
            continue
        if current:
            chunks.append(current)
            current = ""
        parts = split_long_block(block)
        chunks.extend(parts[:-1])
        current = parts[-1] if parts else ""
    if current:
        chunks.append(current)
    return chunks


def send_telegram_digest(
    entries: Iterable[dict[str, Any]],
    bot_token: str,
    chat_id: str,
    *,
    timeout: float = 12.0,
) -> int:
    """Send the digest through Telegram Bot API; return the number of messages."""
    token, destination = _text(bot_token), _text(chat_id)
    if not token or not destination:
        raise NotificationError("Falta configurar el token del bot o el chat ID de Telegram.")
    text = render_digest_text(entries)
    if not text:
        raise NotificationError("No hay ofertas para enviar.")
    chunks = _split_digest_chunks(text, TELEGRAM_MESSAGE_LIMIT)
    for chunk in chunks:
        try:
            response = requests.post(
                f"https://api.telegram.org/bot{token}/sendMessage",
                json={"chat_id": destination, "text": chunk, "disable_web_page_preview": True},
                timeout=timeout,
            )
            response.raise_for_status()
            payload = response.json()
            if not payload.get("ok", False):
                raise NotificationError("Telegram no aceptó el mensaje; revisa el bot y el chat ID.")
        except NotificationError:
            raise
        except Exception as exc:
            # Do not include request URLs or exception text: the URL contains the bot token.
            raise NotificationError("No se pudo entregar el mensaje a Telegram. Revisa la conexión y la configuración.") from exc
    return len(chunks)


def send_ntfy_digest(
    entries: Iterable[dict[str, Any]],
    topic: str,
    *,
    timeout: float = 12.0,
) -> int:
    """Publish a plain-text digest to an ntfy.sh topic without account credentials."""
    destination = _text(topic)
    if not re.fullmatch(r"[A-Za-z0-9_-]{20,64}", destination):
        raise NotificationError(
            "El canal ntfy debe tener entre 20 y 64 caracteres y usar solo letras, números, guiones o guiones bajos."
        )
    entries = list(entries)
    if not entries:
        raise NotificationError("No hay ofertas para enviar.")
    message_text = render_digest_text(entries)

    chunks = _split_digest_chunks(message_text, NTFY_MESSAGE_LIMIT, byte_limit=NTFY_MESSAGE_LIMIT)
    url = f"https://ntfy.sh/{destination}"
    for index, chunk in enumerate(chunks, start=1):
        try:
            response = requests.post(
                url,
                data=chunk.encode("utf-8"),
                headers={
                    "Title": f"JobScout Pro Top 10 ({index}/{len(chunks)})",
                    "Priority": "default",
                    "Tags": "briefcase",
                    "Content-Type": "text/plain; charset=utf-8",
                },
                timeout=timeout,
            )
            response.raise_for_status()
        except Exception as exc:
            # Do not expose the topic or request details in a user-facing error.
            raise NotificationError(
                "No se pudo publicar el aviso en ntfy. Comprueba la conexión y el nombre del canal."
            ) from exc
    return len(chunks)


def render_email_html(entries: Iterable[dict[str, Any]]) -> str:
    rows = []
    for entry in entries:
        pros = "".join(f"<li>{html.escape(str(item))}</li>" for item in entry.get("pros", []))
        cons = "".join(f"<li>{html.escape(str(item))}</li>" for item in entry.get("cons", []))
        link = ""
        if entry.get("job_url"):
            link += f'<a href="{html.escape(entry["job_url"], quote=True)}">Abrir anuncio</a>'
        if entry.get("apply_url") and entry["apply_url"] != entry.get("job_url"):
            link += (" · " if link else "") + f'<a href="{html.escape(entry["apply_url"], quote=True)}">Candidatura</a>'
        rows.append(
            "<article style='margin:0 0 20px;padding:18px;border:1px solid #dbe3ef;border-radius:12px'>"
            f"<h2>{entry['rank']}. {html.escape(entry['title'])} — {html.escape(entry['company'])}</h2>"
            f"<p><b>Relevancia:</b> {entry['score']}/100 · <b>Ubicación:</b> {html.escape(entry['location'])}</p>"
            f"<p><b>Salario:</b> {html.escape(entry['salary'])} · <b>Contrato:</b> {html.escape(entry['contract'])}"
            f" · <b>Experiencia:</b> {html.escape(entry['experience'])} · <b>Modalidad:</b> {html.escape(entry['work_mode'])}</p>"
            f"<h3>A favor</h3><ul>{pros}</ul><h3>A revisar</h3><ul>{cons}</ul><p>{link}</p></article>"
        )
    return (
        "<!doctype html><html lang='es'><meta charset='utf-8'><body style='font-family:Arial,sans-serif;max-width:860px;margin:auto;padding:24px;color:#152238'>"
        "<h1>JobScout Pro · Top de oportunidades</h1>"
        "<p>Ranking orientativo sobre los datos disponibles. Los campos no publicados se señalan como pendientes de confirmar.</p>"
        + "".join(rows)
        + "</body></html>"
    )


def send_email_digest(
    entries: Iterable[dict[str, Any]],
    *,
    smtp_host: str,
    smtp_port: int,
    smtp_username: str,
    smtp_password: str,
    sender: str,
    recipient: str,
    timeout: float = 15.0,
) -> None:
    """Send an HTML and plain-text digest using authenticated SMTP with TLS."""
    host = _text(smtp_host)
    username, password = _text(smtp_username), _text(smtp_password)
    sender, recipient = _text(sender), _text(recipient)
    if not all([host, username, password, sender, recipient]):
        raise NotificationError("Falta configurar SMTP_HOST, SMTP_USER, SMTP_PASSWORD, SMTP_FROM y el destinatario.")
    entries = list(entries)
    if not entries:
        raise NotificationError("No hay ofertas para enviar.")
    message = EmailMessage()
    message["Subject"] = f"JobScout Pro · Top {len(entries)} ofertas"
    message["From"] = sender
    message["To"] = recipient
    message.set_content(render_digest_text(entries))
    message.add_alternative(render_email_html(entries), subtype="html")
    try:
        context = ssl.create_default_context()
        if int(smtp_port) == 465:
            with smtplib.SMTP_SSL(host, int(smtp_port), timeout=timeout, context=context) as smtp:
                smtp.login(username, password)
                smtp.send_message(message)
        else:
            with smtplib.SMTP(host, int(smtp_port), timeout=timeout) as smtp:
                smtp.ehlo()
                smtp.starttls(context=context)
                smtp.ehlo()
                smtp.login(username, password)
                smtp.send_message(message)
    except Exception as exc:
        raise NotificationError("No se pudo enviar el correo. Revisa los datos SMTP, la contraseña de aplicación y la conexión.") from exc
