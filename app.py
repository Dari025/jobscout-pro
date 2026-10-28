from __future__ import annotations

import hashlib
import importlib.util
import json
import os
import queue
import re
import subprocess
import sys
import threading
import tempfile
import time
import uuid
from pathlib import Path
from typing import Any

import pandas as pd
import streamlit as st
import streamlit.components.v1 as components

SRC_DIR = Path(__file__).resolve().parent / "src"
if SRC_DIR.is_dir() and str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))

from jobscout_links import (  # noqa: E402
    canonicalize_row,
    canonical_job_identity,
    choose_job_links,
    load_config,
    load_jobs_from_sqlite,
    professional_domain_mismatch,
    score_job,
)
from job_scout.workspace import (  # noqa: E402
    SEARCH_LOCATION_OPTIONS,
    build_workspace_config,
    cleanup_stale_session_workspaces,
    parse_session_keywords,
    parse_target_terms,
    touch_session_workspace,
    write_workspace_config,
)
from job_scout.cv_privacy import CVProcessingError, extract_pdf_text
from job_scout.runtime_env import build_scraper_subprocess_env
from job_scout.job_analysis import (
    CONTRACT_TYPES,
    EXPERIENCE_BANDS,
    WORK_MODES,
    DURATION_BANDS,
    analyze_job,
    job_matches_optional_filters,
)
from job_scout.notifications import (
    build_top_jobs_digest,
    render_digest_text,
)

APP_BUILD = "2026.10.28-seniority-ranking-compact-cv-v7"


st.set_page_config(
    page_title="JobScout Pro",
    page_icon="✦",
    layout="wide",
    initial_sidebar_state="expanded",
)

st.markdown(
    """
    <style>
    /* System fonts avoid third-party font requests and keep the interface snappy. */
    :root { --ink:#eef4ff; --muted:#9baac2; --panel:#121d30; --line:#263752; --cyan:#67e8f9; --violet:#a78bfa; }
    html, body, [class*="css"] { font-family: Inter, ui-sans-serif, system-ui, -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif; }
    .stApp { background: radial-gradient(ellipse at 12% 0%, rgba(68,91,180,.20), transparent 38%), #080e19; color:var(--ink); }
    [data-testid="stAppViewContainer"] > .main .block-container { max-width:1500px; padding-top:2.1rem; padding-bottom:3rem; }
    [data-testid="stHeader"] { background:transparent; }
    [data-testid="stSidebar"] { background:#0c1423; border-right:1px solid #1d2b42; }
    [data-testid="stSidebar"] > div { padding-top:1.5rem; }
    h1,h2,h3,h4 { font-family: Inter, ui-sans-serif, system-ui, -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif !important; color:#f4f7ff !important; letter-spacing:-.035em; }
    h1 { font-size:2.6rem !important; line-height:1.1 !important; }
    h2 { font-size:1.55rem !important; }
    p, label, li { color:#d8e1f0; }
    .eyebrow { color:var(--cyan); text-transform:uppercase; letter-spacing:.19em; font-size:.72rem; font-weight:800; margin-bottom:.8rem; }
    .hero { border:1px solid #283957; border-radius:24px; padding:28px 30px; margin:0 0 24px 0; background:linear-gradient(115deg, rgba(30,48,81,.96), rgba(18,29,48,.96) 58%, rgba(48,35,82,.74)); box-shadow:0 16px 48px rgba(0,0,0,.15); }
    .hero-title { color:#f4f7ff; font-family: Inter, ui-sans-serif, system-ui, -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif; font-size:2.25rem; font-weight:800; letter-spacing:-.055em; line-height:1.13; margin-bottom:.75rem; }
    .hero-copy { color:#b8c7df; max-width:720px; font-size:1rem; line-height:1.65; }
    .hero-chip { display:inline-block; padding:7px 11px; border-radius:99px; border:1px solid #405477; color:#cbd8ef; font-size:.75rem; font-weight:700; margin-top:14px; background:rgba(9,17,31,.4); }
    [data-testid="stMetric"] { background:linear-gradient(145deg,rgba(18,29,48,.92),rgba(13,22,37,.92)); padding:17px 19px; border:1px solid #263752; border-radius:16px; }
    [data-testid="stMetricLabel"] { color:#aab8cf !important; font-weight:600; }
    [data-testid="stMetricValue"] { color:#f2f7ff !important; font-family: Inter, ui-sans-serif, system-ui, -apple-system, 'Segoe UI', sans-serif; }
    [data-testid="stVerticalBlockBorderWrapper"] { border-color:#263752 !important; border-radius:18px !important; background:rgba(15,25,42,.78); }
    .stButton > button, .stLinkButton > a { border-radius:11px; font-weight:700; transition:all .18s ease; }
    .stButton > button[kind="primary"] { background:linear-gradient(100deg,#67e8f9,#818cf8); color:#07111d; border:0; }
    .stButton > button:hover, .stLinkButton > a:hover { transform:translateY(-1px); border-color:#67e8f9; }
    [data-testid="stExpander"] { border:1px solid #263752; border-radius:13px; }
    [data-testid="stSidebar"] [data-testid="stExpander"] {
      margin-bottom:.35rem;
      background:rgba(17,29,48,.48);
      border-color:#2b3d59;
      border-radius:12px;
    }
    [data-testid="stSidebar"] [data-testid="stExpander"] summary {
      padding-top:.62rem;
      padding-bottom:.62rem;
      font-weight:700;
    }
    [data-testid="stSidebar"] [data-testid="stCheckbox"] label p {
      font-size:.86rem;
      line-height:1.4;
    }
    .cv-privacy-note {
      color:#b8c7df;
      background:rgba(17,29,48,.66);
      border:1px solid #263752;
      border-radius:10px;
      padding:.7rem .8rem;
      font-size:.82rem;
      line-height:1.5;
      margin:.3rem 0 .8rem;
    }
    div[data-baseweb="select"] > div, div[data-baseweb="input"] > div { background:#111d30; border-color:#2a3c58; }
    .soft-note { color:#9eafc8; font-size:.86rem; line-height:1.5; }
    .score-pill { color:#8fe9f2; font-size:.78rem; letter-spacing:.08em; text-transform:uppercase; font-weight:800; }
    hr { border-color:#25344d; }

    /* Keyboard access, touch targets, and motion preferences. */
    :focus-visible {
      outline:3px solid #fff08a !important;
      outline-offset:3px !important;
    }
    a { color:#8defff; text-decoration:underline; text-underline-offset:.16em; }
    .stLinkButton > a { text-decoration:none; }
    .stButton > button, .stLinkButton > a, [role="tab"] { min-height:44px; }
    input, textarea, select, [data-baseweb="select"] { scroll-margin-top:5rem; }

    @media (max-width:768px) {
      [data-testid="stAppViewContainer"] > .main .block-container {
        padding:1rem .75rem 2rem;
      }
      h1 { font-size:2rem !important; }
      h2 { font-size:1.35rem !important; }
      .hero { padding:1.25rem; border-radius:16px; }
      .hero-title { font-size:1.8rem; }
      .eyebrow { letter-spacing:.1em; }
      [data-testid="stMetric"] { padding:.85rem; }
    }

    @media (prefers-reduced-motion:reduce) {
      *, *::before, *::after {
        animation-duration:.01ms !important;
        animation-iteration-count:1 !important;
        scroll-behavior:auto !important;
        transition-duration:.01ms !important;
      }
      .stButton > button:hover, .stLinkButton > a:hover { transform:none; }
    }
    </style>
    """,
    unsafe_allow_html=True,
)

st.markdown(
    """
    <div class="hero">
      <div class="eyebrow">✦ Buscador personalizable de empleo</div>
      <div class="hero-title">Encuentra oportunidades que encajan contigo.</div>
      <div class="hero-copy">Empieza desde cero: introduce tus puestos, ubicaciones y, si te interesa, filtros salariales o de experiencia. El análisis de cada oferta explica qué condiciones aparecen en el anuncio y qué datos faltan.</div>
      <div class="hero-chip">OFERTAS REALES · ENLACES ESPECÍFICOS · ESPACIO AISLADO POR SESIÓN</div>
    </div>
    """,
    unsafe_allow_html=True,
)

# The hosted dashboard always starts from the public, neutral template. Never
# load a developer's private busqueda.yaml/config.yaml into a shared web app.
template_path = Path(__file__).resolve().parent / "busqueda.example.yaml"
config, config_path = load_config(template_path)

# Reset state created by older app builds once, so a browser tab cannot retain
# an old profile, CV, target title, saved list, or old search result state.
SESSION_SCHEMA = "clean-isolated-workspaces-v5-simple-share"
if st.session_state.get("_workspace_schema") != SESSION_SCHEMA:
    for stale_key in (
        "cv_text", "saved_jobs", "refresh_key", "target_title", "last_scrape",
        "cv_fingerprint", "scrape_requested", "requested_scan_mode",
        "target_title_clean", "search_locations_clean", "uploaded_cv_clean",
        "cv_consent_clean", "cv_uploader_version", "min_score_clean", "search_text_clean",
        "location_filter_clean", "source_filter_clean", "sort_mode_clean",
        "scan_mode_clean", "salary_filter_enabled", "salary_minimum_eur",
        "include_unknown_salary", "experience_filter_enabled", "experience_filter_level",
        "include_unknown_experience", "contract_filter_enabled", "contract_filter_type",
        "include_unknown_employment", "mode_filter_enabled", "mode_filter_value",
        "include_unknown_work_mode", "cv_changed_notice", "cv_cleared_notice",
        "cv_removed_notice", "cv_truncated_notice", "salary_max_filter_enabled",
        "salary_maximum_eur", "duration_filter_enabled", "duration_filter_values",
        "include_unknown_duration", "hours_filter_enabled", "maximum_hours_weekly",
        "include_unknown_hours", "published_window_clean", "include_unknown_published_date",
        "notify_auto_enabled", "notify_ntfy_enabled", "notification_ntfy_topic",
        "notification_telegram_chat_id", "notification_email_recipient",
        "notify_pending_search_id", "notify_auto_sent_id",
    ):
        st.session_state.pop(stale_key, None)
    for stale_upload_key in [
        key for key in list(st.session_state.keys())
        if str(key).startswith("uploaded_cv_clean_")
    ]:
        st.session_state.pop(stale_upload_key, None)
    st.session_state["_workspace_schema"] = SESSION_SCHEMA
    st.session_state["session_id"] = uuid.uuid4().hex

if "session_id" not in st.session_state:
    st.session_state["session_id"] = uuid.uuid4().hex
st.session_state.setdefault("cv_text", "")
st.session_state.setdefault("saved_jobs", {})
st.session_state.setdefault("refresh_key", 0)
st.session_state.setdefault("target_title_clean", "")
st.session_state.setdefault("search_locations_clean", [])
st.session_state.setdefault("last_scrape", None)
st.session_state.setdefault("cv_fingerprint", "")
st.session_state.setdefault("cv_uploader_version", 0)

# Each Streamlit browser session gets its own unguessable workspace and SQLite DB.
# The explicit db_path is strict: the reader must never fall back to another user's DB.
sessions_root = Path(tempfile.gettempdir()) / "jobscout-pro-sessions"
session_dir = sessions_root / st.session_state["session_id"]
touch_session_workspace(sessions_root, session_dir)
cleanup_stale_session_workspaces(sessions_root, session_dir, ttl_hours=24)
session_db_path = session_dir / "jobs.sqlite"
target_title = str(st.session_state.get("target_title_clean", "") or "")
search_locations = list(st.session_state.get("search_locations_clean", []) or [])
workspace_config = build_workspace_config(
    config, session_dir, target_title, search_locations
)
db_config = {**workspace_config, "db_path": str(session_db_path)}
profile = workspace_config.get("profile", {})

raw_jobs, db_diagnostics = load_jobs_from_sqlite(db_config)
jobs: list[dict[str, Any]] = []
seen: set[str] = set()
for raw in raw_jobs:
    job = canonicalize_row(raw)
    title = str(job.get("title") or "").strip()
    company = str(job.get("company") or "").strip()
    if not title or not company:
        continue
    source_url, apply_url = choose_job_links(job)
    job["job_url"], job["job_url_direct"] = source_url, apply_url
    job["has_specific_link"] = bool(source_url or apply_url)
    identity = canonical_job_identity(job)
    if identity in seen:
        continue
    seen.add(identity)
    job["_identity"] = identity
    jobs.append(job)

# Derive salary, seniority, contract, work mode and explicitly mentioned requirements.
# These fields are evidence-based; missing information remains "No indicado".
target_terms = parse_target_terms(target_title)
for job in jobs:
    analysis = analyze_job(job, st.session_state.cv_text, target_terms)
    job["salary"] = analysis.get("salary_display") or str(job.get("salary") or "")
    for field in (
        "salary_eur_year_min", "salary_eur_year_max", "salary_currency", "salary_interval", "salary_known",
        "salary_evidence", "experience_level", "experience_min_years",
        "experience_max_years", "experience_evidence", "experience_level_evidence",
        "employment_type_label", "employment_type_evidence", "work_mode_label",
        "work_mode_evidence", "duration_band", "duration_months_min", "duration_months_max",
        "duration_evidence", "hours_per_week_min", "hours_per_week_max",
        "hours_per_week_label", "hours_per_week_evidence", "requirements", "cv_matches", "cv_unconfirmed",
        "target_title_matches", "analysis_method", "analysis_notes",
    ):
        job[field] = analysis.get(field)

available_sources = sorted({str(job.get("source") or "Fuente desconocida").strip() for job in jobs if str(job.get("source") or "").strip()})

def _read_child_output(pipe, output_queue):
    try:
        for line in iter(pipe.readline, ""):
            output_queue.put(line.rstrip("\r\n"))
    finally:
        pipe.close()
        output_queue.put(None)


def _run_scraper_live(command, env, cwd, timeout_seconds, log_placeholder):
    output_queue = queue.Queue()
    process = subprocess.Popen(
        command,
        cwd=cwd,
        env=env,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        encoding="utf-8",
        errors="replace",
        bufsize=1,
    )
    reader = threading.Thread(
        target=_read_child_output, args=(process.stdout, output_queue), daemon=True
    )
    reader.start()
    logs = []
    reader_finished = False
    timed_out = False
    started = time.monotonic()
    ansi_pattern = re.compile(r"\x1b\[[0-?]*[ -/]*[@-~]")

    while not reader_finished:
        if process.poll() is None and time.monotonic() - started > timeout_seconds:
            timed_out = True
            process.terminate()
            try:
                process.wait(timeout=2)
            except subprocess.TimeoutExpired:
                process.kill()
        try:
            item = output_queue.get(timeout=0.2)
        except queue.Empty:
            continue
        if item is None:
            reader_finished = True
            continue
        clean_line = ansi_pattern.sub("", item)
        if clean_line.strip():
            logs.append(clean_line)
            log_placeholder.code("\n".join(logs[-12:]), language="text")

    try:
        return_code = process.wait(timeout=5)
    except subprocess.TimeoutExpired:
        process.kill()
        return_code = process.wait()
        timed_out = True
    reader.join(timeout=1)
    return return_code, logs, timed_out, round(time.monotonic() - started)


def _purge_uploaded_cv_widget_state() -> None:
    """Drop all cached uploader-widget values before rotating its key."""
    for upload_key in [
        key for key in list(st.session_state.keys())
        if str(key).startswith("uploaded_cv_clean_")
    ]:
        st.session_state.pop(upload_key, None)


def _clear_cv_for_session() -> None:
    """Remove extracted CV text and replace the uploader widget on the next rerun."""
    st.session_state["cv_text"] = ""
    st.session_state["cv_fingerprint"] = ""
    st.session_state["cv_consent_clean"] = False
    st.session_state["cv_uploader_version"] = int(
        st.session_state.get("cv_uploader_version", 0)
    ) + 1
    _purge_uploaded_cv_widget_state()
    st.session_state["cv_cleared_notice"] = True


def _handle_cv_consent_change() -> None:
    """Immediately purge the CV and uploader bytes when consent is withdrawn."""
    if not bool(st.session_state.get("cv_consent_clean", False)):
        st.session_state["cv_text"] = ""
        st.session_state["cv_fingerprint"] = ""
        st.session_state["cv_uploader_version"] = int(
            st.session_state.get("cv_uploader_version", 0)
        ) + 1
        _purge_uploaded_cv_widget_state()
        st.session_state["cv_removed_notice"] = True


with st.sidebar:
    st.markdown("## Tu espacio")
    st.caption("Ajusta la búsqueda a lo que de verdad te interesa.")
    st.caption(f"Motor {APP_BUILD}")
    target_title = st.text_input(
        "Puestos objetivo",
        key="target_title_clean",
        placeholder="Ej. Data Analyst, Product Analyst",
        max_chars=250,
        help="Escribe los puestos que quieres buscar, separados por comas. Máximo 250 caracteres; puedes incluir varios títulos.",
    )
    search_locations = st.multiselect(
        "Ubicaciones para buscar",
        options=SEARCH_LOCATION_OPTIONS,
        key="search_locations_clean",
        help="Elige una o varias ubicaciones. No se selecciona ninguna por defecto.",
    )

    with st.expander("Personalizar el ranking (opcional)", expanded=False):
        raw_keywords = st.text_area(
            "Tus habilidades o palabras clave",
            key="session_keywords_clean",
            placeholder="Ej. python, sql, econometría, series temporales",
            max_chars=500,
            height=90,
            help=(
                "Se usan solo para ordenar las ofertas de esta sesión. "
                "No se guardan en disco, ni en la base de datos, ni se comparten con otras sesiones."
            ),
        )
        session_keywords = parse_session_keywords(raw_keywords)
        if session_keywords:
            st.caption(
                f"{len(session_keywords)} palabra(s) clave activas solo en esta sesión: "
                + ", ".join(session_keywords[:8])
                + ("…" if len(session_keywords) > 8 else "")
            )
        else:
            st.caption(
                "Sin palabras clave, el índice de encaje se calcula solo con el título del puesto "
                "y, si subes un CV, con su contenido."
            )

    cv_status = "CV listo" if st.session_state.cv_fingerprint else (
        "pendiente" if st.session_state.get("cv_consent_clean", False) else "opcional"
    )
    with st.expander(f"📄 Currículum · {cv_status}", expanded=False):
        st.caption(
            "Opcional: úsalo para contrastar el perfil con las ofertas de esta sesión."
        )
        st.markdown(
            '<div class="cv-privacy-note"><strong>Privacidad.</strong> El PDF se procesa '
            "en la memoria de esta sesión. El dashboard no lo envía a portales de empleo "
            "ni a modelos de IA, y no lo guarda en SQLite ni en el YAML de búsqueda. "
            "Retira el consentimiento o borra el CV cuando quieras.</div>",
            unsafe_allow_html=True,
        )
        consent = st.checkbox(
            "Consiento que se procese el CV en esta sesión.",
            key="cv_consent_clean",
            on_change=_handle_cv_consent_change,
            help="Al desmarcarla, se elimina el texto extraído y se reinicia el selector.",
        )
        st.button(
            "Borrar CV",
            key="clear_cv_session_button",
            on_click=_clear_cv_for_session,
            use_container_width=True,
            help="Elimina el texto del CV de esta sesión y reinicia el selector.",
        )
        uploader_key = f"uploaded_cv_clean_{int(st.session_state.cv_uploader_version)}"
        uploaded_cv = st.file_uploader(
            "Seleccionar CV en PDF",
            type=["pdf"],
            key=uploader_key,
            disabled=not consent,
            help="Activa primero el consentimiento. Máximo 5 MB y 15 páginas; se analiza en memoria y no se guarda en disco.",
        )
        if not consent:
            st.caption("Activa el consentimiento para seleccionar el PDF.")
        if not uploaded_cv and st.session_state.cv_fingerprint:
            # The user removed the file through the uploader's own clear control.
            # Purge the extracted text; no CV remains in scoring.
            st.session_state.cv_text = ""
            st.session_state.cv_fingerprint = ""
            st.session_state["cv_removed_notice"] = True

        if uploaded_cv and consent:
            file_bytes = uploaded_cv.getvalue()
            fingerprint = hashlib.sha256(file_bytes).hexdigest()
            if fingerprint != st.session_state.cv_fingerprint:
                # Do not keep an older CV active if replacing it with an invalid PDF.
                st.session_state.cv_text = ""
                st.session_state.cv_fingerprint = ""
                try:
                    extraction = extract_pdf_text(file_bytes)
                except CVProcessingError as exc:
                    st.warning(str(exc))
                else:
                    st.session_state.cv_text = extraction.text
                    st.session_state.cv_fingerprint = fingerprint
                    st.session_state["cv_changed_notice"] = True
                    st.session_state["cv_truncated_notice"] = extraction.truncated
                    st.rerun()

    # Keep notices outside the collapsed disclosure so users can see confirmations.
    if st.session_state.pop("cv_changed_notice", False):
        st.success("CV procesado; el análisis del encaje se ha actualizado.")
    if st.session_state.pop("cv_truncated_notice", False):
        st.warning("El texto extraído se ha limitado a 100.000 caracteres para proteger los recursos del servidor.")
    if st.session_state.pop("cv_cleared_notice", False):
        st.info("CV eliminado de esta sesión.")
    if st.session_state.pop("cv_removed_notice", False):
        st.info("Se ha retirado el consentimiento o el archivo; el CV se ha eliminado de esta sesión.")

    st.divider()
    st.markdown("### Filtros")
    min_score = st.slider("Relevancia mínima", 0, 100, 20, 5, key="min_score_clean")
    search_text = st.text_input(
        "Palabra clave", placeholder="Puesto, empresa o ubicación",
        key="search_text_clean",
    )
    location_filter = st.selectbox(
        "Modalidad / zona", ["Todas", "Madrid / España", "Remoto / Europa"],
        key="location_filter_clean",
    )
    source_filter = st.multiselect(
        "Filtrar por fuentes (vacío = todas)", available_sources,
        default=available_sources,
        key="source_filter_clean",
        help="Si no seleccionas ninguna fuente, se muestran ofertas de todas las fuentes disponibles.",
    )
    sort_mode = st.selectbox(
        "Ordenar por", ["Mayor relevancia", "Más recientes", "Salario más alto"],
        key="sort_mode_clean",
    )

    st.divider()
    st.markdown("### Rastreo de ofertas")
    scan_mode = st.radio(
        "Alcance de la búsqueda",
        ["⚡ Rápida", "🔎 Completa"],
        index=0,
        key="scan_mode_clean",
        help="La rápida hace menos consultas, limita la paginación y evita peticiones individuales de descripción. La completa intenta cubrir más resultados y puede tardar varios minutos.",
    )
    st.caption(
        "Rápida: menos peticiones y resultados iniciales. Completa: más cobertura, aunque las fuentes pueden bloquear o ralentizar consultas."
    )

    st.selectbox(
        "Fecha de publicación",
        ["Cualquier fecha", "Últimos 3 días", "Últimos 7 días", "Últimos 14 días", "Últimos 30 días"],
        key="published_window_clean",
        help="Las ofertas sin fecha conocida se conservan por defecto para no perder oportunidades.",
    )
    include_unknown_published_date = st.checkbox(
        "Incluir ofertas sin fecha de publicación conocida",
        value=True,
        key="include_unknown_published_date",
    )

    with st.expander("Filtros avanzados (todos opcionales)", expanded=False):
        st.caption(
            "Los filtros solo comparan datos detectados en la oferta. "
            "Por defecto, una oferta con salario, horas, duración o experiencia no indicados se conserva."
        )
        salary_filter_enabled = st.checkbox(
            "Filtrar por salario anual bruto (EUR)", value=False, key="salary_filter_enabled",
        )
        salary_minimum_eur = None
        salary_maximum_eur = None
        include_unknown_salary = True
        if salary_filter_enabled:
            salary_minimum_eur = st.number_input(
                "Salario mínimo anual (EUR)", min_value=0, max_value=300000,
                value=25000, step=1000, key="salary_minimum_eur",
            )
            salary_max_filter_enabled = st.checkbox(
                "Añadir un límite salarial máximo", value=False, key="salary_max_filter_enabled",
            )
            if salary_max_filter_enabled:
                salary_maximum_eur = st.number_input(
                    "Salario máximo anual (EUR)", min_value=0, max_value=500000,
                    value=45000, step=1000, key="salary_maximum_eur",
                )
            include_unknown_salary = st.checkbox(
                "Incluir ofertas sin salario comparable", value=True, key="include_unknown_salary",
                help="Una oferta sin una cifra EUR/año verificable se conserva si esta opción está activada.",
            )

        experience_filter_enabled = st.checkbox(
            "Filtrar por experiencia", value=False, key="experience_filter_enabled"
        )
        experience_filter_level = None
        include_unknown_experience = True
        if experience_filter_enabled:
            experience_filter_level = st.multiselect(
                "Niveles aceptados", EXPERIENCE_BANDS, default=[], key="experience_filter_level",
                help="Puedes elegir varios niveles. Deja la selección vacía para no restringir por nivel.",
            )
            include_unknown_experience = st.checkbox(
                "Incluir ofertas sin experiencia indicada", value=True, key="include_unknown_experience",
            )

        contract_filter_enabled = st.checkbox(
            "Filtrar por tipo de contrato", value=False, key="contract_filter_enabled"
        )
        contract_filter_type = None
        include_unknown_employment = True
        if contract_filter_enabled:
            contract_filter_type = st.multiselect(
                "Tipos aceptados", CONTRACT_TYPES, default=[], key="contract_filter_type",
                help="Prácticas, parcial, completo, freelance o temporal. Puedes combinar varios.",
            )
            include_unknown_employment = st.checkbox(
                "Incluir ofertas sin tipo de contrato indicado", value=True,
                key="include_unknown_employment",
            )

        mode_filter_enabled = st.checkbox(
            "Filtrar por modalidad de trabajo", value=False, key="mode_filter_enabled"
        )
        mode_filter_value = None
        include_unknown_work_mode = True
        if mode_filter_enabled:
            mode_filter_value = st.multiselect(
                "Modalidades aceptadas", WORK_MODES, default=[], key="mode_filter_value",
            )
            include_unknown_work_mode = st.checkbox(
                "Incluir ofertas sin modalidad indicada", value=True,
                key="include_unknown_work_mode",
            )

        duration_filter_enabled = st.checkbox(
            "Filtrar por duración de la oportunidad", value=False, key="duration_filter_enabled",
        )
        duration_filter_values = None
        include_unknown_duration = True
        if duration_filter_enabled:
            duration_filter_values = st.multiselect(
                "Duraciones aceptadas", DURATION_BANDS, default=[], key="duration_filter_values",
            )
            include_unknown_duration = st.checkbox(
                "Incluir ofertas sin duración indicada", value=True, key="include_unknown_duration",
            )

        hours_filter_enabled = st.checkbox(
            "Limitar horas semanales", value=False, key="hours_filter_enabled",
            help="Solo se extraen horas cuando el anuncio indica una cifra explícita.",
        )
        maximum_hours_weekly = None
        include_unknown_hours = True
        if hours_filter_enabled:
            maximum_hours_weekly = st.number_input(
                "Máximo de horas por semana", min_value=1, max_value=60, value=25, step=5,
                key="maximum_hours_weekly",
            )
            include_unknown_hours = st.checkbox(
                "Incluir ofertas sin horas semanales indicadas", value=True, key="include_unknown_hours",
            )

    optional_filter_options = {
        "min_salary_eur_year": salary_minimum_eur if salary_filter_enabled else None,
        "max_salary_eur_year": salary_maximum_eur if salary_filter_enabled and st.session_state.get("salary_max_filter_enabled", False) else None,
        "include_unknown_salary": include_unknown_salary,
        "experience_level": experience_filter_level if experience_filter_enabled else None,
        "include_unknown_experience": include_unknown_experience,
        "employment_type": contract_filter_type if contract_filter_enabled else None,
        "include_unknown_employment": include_unknown_employment,
        "work_mode": mode_filter_value if mode_filter_enabled else None,
        "include_unknown_work_mode": include_unknown_work_mode,
        "duration_band": duration_filter_values if duration_filter_enabled else None,
        "include_unknown_duration": include_unknown_duration,
        "max_hours_per_week": maximum_hours_weekly if hours_filter_enabled else None,
        "include_unknown_hours": include_unknown_hours,
    }

    if st.button("✦ Buscar oportunidades", type="primary", use_container_width=True):
        if not parse_target_terms(target_title):
            st.warning("Escribe al menos un puesto objetivo antes de buscar.")
        elif not search_locations:
            st.warning("Selecciona al menos una ubicación para buscar.")
        else:
            st.session_state["scrape_requested"] = True
            st.session_state["requested_scan_mode"] = scan_mode
            st.rerun()
    if st.button("↻ Actualizar resultados", use_container_width=True):
        st.session_state.refresh_key += 1
        st.rerun()

    with st.expander("Diagnóstico"):
        st.write(f"Plantilla neutral: {config_path or 'no encontrada'}")
        st.write(f"Base de datos privada de esta sesión: {session_db_path}")
        st.write("Cada sesión tiene su propio perfil temporal, archivo de configuración y base de datos.")
        for item in db_diagnostics:
            st.caption(item)
        if not st.session_state.cv_text:
            st.info("Sin CV: el índice usa únicamente los puestos que hayas indicado.")



if st.session_state.pop("scrape_requested", False):
    scan_mode = st.session_state.get("requested_scan_mode", "⚡ Rápida")
    try:
        # Write only this session's search settings. CV text is never serialized.
        config_file = write_workspace_config(
            config, session_dir, target_title, search_locations
        )
    except (OSError, ValueError) as exc:
        st.error(f"No se ha podido preparar el espacio de búsqueda de esta sesión: {exc}")
        config_file = None

    if config_file:
        try:
            module_available = importlib.util.find_spec("job_scout.cli") is not None
        except (ImportError, ModuleNotFoundError, ValueError):
            module_available = False
        if not module_available:
            st.error("No se encuentra el motor de búsqueda. Comprueba que el despliegue use la rama principal actualizada.")
        else:
            command = [
                sys.executable, "-m", "job_scout.cli",
                "--config", str(config_file.resolve()), "scrape",
            ]
            is_quick = scan_mode.startswith("⚡")
            if is_quick:
                command.append("--quick")
            # Pass only runtime essentials and the selected query. Never forward
            # API keys, Telegram/email credentials, or arbitrary user/host secrets.
            # The CV remains in Streamlit session memory and is not sent to the scraper.
            child_env = build_scraper_subprocess_env(os.environ, target_title, SRC_DIR)
            timeout_seconds = 180 if is_quick else 900
            mode_label = "búsqueda rápida" if is_quick else "búsqueda completa"
            with st.status(f"Ejecutando {mode_label}…", expanded=True) as status:
                st.write("Buscando en las fuentes seleccionadas y guardando ofertas solo en tu espacio.")
                log_placeholder = st.empty()
                try:
                    return_code, logs, timed_out, elapsed = _run_scraper_live(
                        command,
                        child_env,
                        Path(__file__).resolve().parent,
                        timeout_seconds,
                        log_placeholder,
                    )
                    if timed_out:
                        message = f"Se alcanzó el límite de {timeout_seconds // 60} min. Se conservarán los resultados guardados en esta sesión."
                        status.update(label="Búsqueda detenida por tiempo límite", state="error", expanded=True)
                        success = False
                    elif return_code == 0:
                        message = f"Búsqueda terminada en {elapsed} s. Ya puedes revisar tus oportunidades."
                        status.update(label="Búsqueda completada", state="complete", expanded=False)
                        success = True
                    elif return_code == 2 and "No valid postings found" in "\n".join(logs):
                        message = "Ninguna fuente devolvió vacantes utilizables para estos puestos y ubicaciones. Revisa el diagnóstico por fuente."
                        status.update(label="Sin vacantes válidas: revisa las fuentes", state="error", expanded=True)
                        success = False
                    else:
                        message = f"El motor terminó con código {return_code}. Consulta el diagnóstico para ver el detalle."
                        status.update(label="La búsqueda terminó con incidencias", state="error", expanded=True)
                        success = False
                    search_marker = uuid.uuid4().hex
                    st.session_state.last_scrape = {
                        "id": search_marker,
                        "ok": success,
                        "message": message,
                        "logs": "\n".join(logs[-100:]),
                    }
                    if success and bool(st.session_state.get("notify_auto_enabled", False)):
                        st.session_state["notify_pending_search_id"] = search_marker
                    st.session_state.refresh_key += 1
                    st.rerun()
                except OSError as exc:
                    st.error(f"No se pudo iniciar el motor de búsqueda: {exc}")

last_scrape = st.session_state.last_scrape
if last_scrape:
    if last_scrape.get("ok"):
        st.success(last_scrape.get("message", "Búsqueda completada."))
    else:
        st.warning(last_scrape.get("message", "La búsqueda terminó con incidencias."))
    if last_scrape.get("logs"):
        with st.expander("Ver registro de la última búsqueda"):
            st.code(last_scrape["logs"], language="text")

scoring_config = build_workspace_config(
    config, session_dir, target_title, search_locations,
    custom_keywords=session_keywords,
)
for job in jobs:
    job["calculated_score"] = score_job(job, scoring_config, st.session_state.cv_text)
    job["domain_mismatch"] = professional_domain_mismatch(
        job, scoring_config, st.session_state.cv_text
    )

columns = [
    "title", "company", "location", "description", "job_url", "job_url_direct",
    "source", "date_posted", "salary", "id", "calculated_score", "has_specific_link",
    "salary_eur_year_min", "salary_eur_year_max", "salary_currency", "salary_interval", "salary_known",
    "experience_level", "experience_min_years", "experience_max_years",
    "employment_type_label", "work_mode_label", "requirements", "cv_matches",
    "cv_unconfirmed", "analysis_notes", "_identity",
]
df_all = pd.DataFrame(jobs) if jobs else pd.DataFrame(columns=columns)
df = df_all.copy()
if not df.empty:
    df = df[df["calculated_score"] >= min_score]
    if search_text.strip():
        searchable = (
            df["title"].fillna("").astype(str) + " " +
            df["company"].fillna("").astype(str) + " " +
            df["location"].fillna("").astype(str)
        )
        df = df[searchable.str.contains(search_text.strip(), case=False, na=False, regex=False)]
    if location_filter == "Madrid / España":
        df = df[df["location"].fillna("").astype(str).str.contains(
            r"madrid|spain|españa|spanien", case=False, na=False, regex=True
        )]
    elif location_filter == "Remoto / Europa":
        df = df[df["location"].fillna("").astype(str).str.contains(
            r"remote|remoto|europe|europa|worldwide|anywhere", case=False, na=False, regex=True
        )]
    if source_filter:
        df = df[df["source"].fillna("").astype(str).isin(source_filter)]
    publication_days = {"Últimos 3 días": 3, "Últimos 7 días": 7, "Últimos 14 días": 14, "Últimos 30 días": 30}
    selected_window = st.session_state.get("published_window_clean", "Cualquier fecha")
    if selected_window in publication_days and not df.empty and "date_posted" in df.columns:
        posted_at = pd.to_datetime(df["date_posted"], errors="coerce", utc=True)
        cutoff = pd.Timestamp.now(tz="UTC") - pd.Timedelta(days=publication_days[selected_window])
        keep = posted_at >= cutoff
        if include_unknown_published_date:
            keep = keep | posted_at.isna()
        df = df[keep.fillna(False)]
    if optional_filter_options and not df.empty:
        mask = df.apply(
            lambda row: job_matches_optional_filters(row.to_dict(), optional_filter_options),
            axis=1,
        )
        df = df[mask]
    if sort_mode == "Más recientes" and "date_posted" in df.columns:
        df = df.assign(_posted=pd.to_datetime(df["date_posted"], errors="coerce", utc=True))
        df = df.sort_values(["_posted", "calculated_score"], ascending=[False, False], kind="stable")
        df = df.drop(columns=["_posted"])
    elif sort_mode == "Salario más alto" and "salary_eur_year_min" in df.columns:
        df = df.sort_values(["salary_eur_year_min", "calculated_score"], ascending=[False, False], na_position="last", kind="stable")
    else:
        df = df.sort_values(["calculated_score", "title"], ascending=[False, True], kind="stable")

total_jobs = len(df_all)
high_relevance = int((df_all["calculated_score"] >= 70).sum()) if total_jobs else 0
with_link = int(df_all["has_specific_link"].fillna(False).astype(bool).sum()) if total_jobs else 0

m1, m2, m3, m4 = st.columns(4)
m1.metric("Vacantes registradas", f"{total_jobs:,}")
m2.metric("Alta relevancia", f"{high_relevance:,}", help="Índice orientativo de 70/100 o superior; no es una probabilidad de contratación.")
m3.metric("Con enlace específico", f"{with_link:,}")
m4.metric("Coinciden con filtros", f"{len(df):,}")

tab_discover, tab_saved, tab_alerts, tab_method = st.tabs(["✦ Oportunidades", "★ Guardadas", "🔔 Alertas", "ⓘ Cómo funciona"])

with tab_alerts:
    st.subheader("Tu resumen de oportunidades")
    st.caption(
        "El Top 10 se calcula con las ofertas que coinciden con tus filtros actuales y se ordena por relevancia. "
        "Cada oferta incluye pros y puntos por confirmar basados en el anuncio, sin inventar los datos que falten."
    )
    digest_entries = build_top_jobs_digest(df.to_dict(orient="records"), limit=10) if not df.empty else []
    if digest_entries:
        preview = pd.DataFrame([
            {
                "N.º": item["rank"],
                "Puesto": item["title"],
                "Empresa": item["company"],
                "Relevancia": f"{item['score']}/100",
                "Salario": item["salary"],
                "Contrato": item["contract"],
                "Modalidad": item["work_mode"],
            }
            for item in digest_entries
        ])
        st.dataframe(preview, use_container_width=True, hide_index=True)
        with st.expander("Ver análisis de pros y puntos a confirmar del Top 10"):
            for item in digest_entries:
                st.markdown(f"**{item['rank']}. {item['title']} — {item['company']}** · {item['score']}/100")
                st.markdown("**A favor**")
                for pro in item["pros"]:
                    st.markdown(f"- {pro}")
                st.markdown("**A revisar antes de decidir**")
                for con in item["cons"]:
                    st.markdown(f"- {con}")
                if item.get("job_url"):
                    st.markdown(f"[Abrir anuncio original]({item['job_url']})")
                if item.get("apply_url") and item["apply_url"] != item.get("job_url"):
                    st.markdown(f"[Ir a la candidatura]({item['apply_url']})")
                st.divider()
        with st.expander("Vista previa del mensaje completo"):
            st.code(render_digest_text(digest_entries), language="text")
    else:
        st.info("Todavía no hay ofertas que coincidan con los filtros. Lanza una búsqueda o amplía algún filtro para generar el Top 10.")

    st.divider()
    st.markdown("### Compartir el Top 10")
    st.caption(
        "Sin cuentas nuevas, bots ni contraseñas. Pulsa compartir y elige una aplicación que ya uses. "
        "Si el menú no funciona, el resumen se copiará para que lo pegues en tu correo o mensajería."
    )
    if digest_entries:
        share_text = render_digest_text(digest_entries)
        share_text_json = (
            json.dumps(share_text, ensure_ascii=False)
            .replace("<", "\\u003c")
            .replace(">", "\\u003e")
            .replace("&", "\\u0026")
        )
        share_html = f"""
        <div style="font-family:system-ui,-apple-system,'Segoe UI',sans-serif;color:#eef4ff;">
          <button id="jobscout-share" type="button" aria-label="Compartir las diez mejores ofertas"
            style="width:100%;min-height:48px;border:0;border-radius:12px;padding:12px 16px;
            background:linear-gradient(100deg,#67e8f9,#818cf8);color:#07111d;
            font-size:16px;font-weight:750;cursor:pointer;">
            Compartir Top 10
          </button>
          <p id="jobscout-share-status" role="status" aria-live="polite"
            style="margin:8px 2px 0;color:#aab8cf;font-size:13px;line-height:1.45;">
            Se abrirá el menú de compartir de tu dispositivo, si el navegador lo admite.
          </p>
          <style>
            #jobscout-share:focus-visible {{ outline:3px solid #fff08a; outline-offset:3px; }}
            #jobscout-share:disabled {{ opacity:.65; cursor:wait; }}
          </style>
          <script>
            const digestText = {share_text_json};
            const shareButton = document.getElementById("jobscout-share");
            const shareStatus = document.getElementById("jobscout-share-status");
            shareButton.addEventListener("click", async () => {{
              const copyDigest = async () => {{
                try {{
                  await navigator.clipboard.writeText(digestText);
                  shareStatus.textContent = "Resumen copiado. Abre tu correo o mensajería y pégalo en el mensaje.";
                }} catch (copyError) {{
                  shareStatus.textContent = "No se pudo compartir ni copiar. Usa la descarga de texto que aparece debajo.";
                }}
              }};
              shareButton.disabled = true;
              try {{
                if (!navigator.share) {{
                  await copyDigest();
                  return;
                }}
                await navigator.share({{ title: "JobScout Pro · Top 10", text: digestText }});
                shareStatus.textContent = "Se ha abierto el menú de compartir.";
              }} catch (error) {{
                if (error && error.name !== "AbortError") {{
                  await copyDigest();
                }}
              }} finally {{
                shareButton.disabled = false;
              }}
            }});
          </script>
        </div>
        """
        components.html(share_html, height=106, scrolling=False)
        st.download_button(
            "Descargar resumen completo (.txt)",
            data=share_text,
            file_name="jobscout-top10.txt",
            mime="text/plain; charset=utf-8",
            use_container_width=True,
            help="Último recurso si el navegador no permite ni compartir ni copiar. Incluye el Top 10, pros, puntos a revisar y enlaces.",
        )
    else:
        st.info("Haz una búsqueda para generar el Top 10 que quieras compartir.")

    st.caption(
        "Nota: compartir es manual. Para enviar correos automáticamente sin que tú confirmes el envío, "
        "la aplicación necesitaría credenciales o un servicio de envío; no hace falta nada de eso para compartir ahora."
    )

with tab_discover:
    left, right = st.columns([3, 1])
    with left:
        st.subheader(f"Tu shortlist · {len(df)} oportunidades")
        st.caption("Empieza por las puntuaciones más altas, pero abre la descripción y verifica siempre los requisitos.")
    with right:
        if not df.empty:
            st.download_button(
                "↓ Exportar CSV",
                data=df.drop(columns=["_identity"], errors="ignore").to_csv(index=False).encode("utf-8-sig"),
                file_name="jobscout_oportunidades.csv",
                mime="text/csv",
                use_container_width=True,
            )

    if df.empty:
        if total_jobs == 0:
            st.info("Aún no hay ofertas guardadas. Lanza una búsqueda desde la barra lateral; la primera recogida puede tardar mientras los portales responden.")
            st.markdown(
                '<div class="soft-note">Consejo: prueba primero la búsqueda rápida. Si devuelve pocos resultados, lanza la completa cuando quieras ampliar cobertura.</div>',
                unsafe_allow_html=True,
            )
        else:
            st.info("Ninguna vacante coincide con los filtros actuales. Baja la relevancia mínima o amplía las fuentes y la ubicación.")
    else:
        for display_index, (_, row) in enumerate(df.iterrows()):
            title = str(row.get("title") or "Puesto sin título").strip()
            company = str(row.get("company") or "Empresa sin especificar").strip()
            location = str(row.get("location") or "Ubicación no indicada").strip()
            description = str(row.get("description") or "").strip()
            score = int(row.get("calculated_score") or 0)
            source_url, apply_url = choose_job_links(row.to_dict())
            source_name = str(row.get("source") or "Fuente no indicada").replace("_", " ").title()
            date_value = str(row.get("date_posted") or "").strip()
            salary = str(row.get("salary") or "").strip()
            identity = str(row.get("_identity") or f"{title}|{company}|{location}")
            score_label = "Relevancia alta" if score >= 70 else ("Relevancia media" if score >= 45 else "Por revisar")

            with st.container(border=True):
                title_col, score_col = st.columns([5, 1])
                with title_col:
                    st.subheader(title)
                    st.markdown(f"**{company}**")
                    st.caption(" · ".join(part for part in [location, source_name, date_value, salary] if part))
                    st.caption(
                        " · ".join([
                            f"Experiencia: {row.get('experience_level') or 'No indicado'}",
                            f"Contrato: {row.get('employment_type_label') or 'No indicado'}",
                            f"Modalidad: {row.get('work_mode_label') or 'No indicado'}",
                            f"Duración: {row.get('duration_band') or 'No indicado'}",
                            f"Horas: {row.get('hours_per_week_label') or 'No indicado'}",
                        ])
                    )
                with score_col:
                    st.metric("Relevancia", f"{score}/100")
                    st.caption(score_label)

                if description:
                    st.write(description[:650] + ("…" if len(description) > 650 else ""))
                else:
                    st.caption("Descripción no disponible en los datos recogidos; valora el título y abre el anuncio para comprobar los requisitos.")

                mismatch = row.get("domain_mismatch")
                if isinstance(mismatch, dict) and mismatch.get("reason"):
                    st.warning(
                        "Posible incompatibilidad profesional: " + mismatch["reason"]
                        + " La puntuación se ha limitado para evitar que coincidencias genéricas la coloquen arriba."
                    )

                link_col, apply_col, save_col = st.columns([1.35, 1.35, 1])
                with link_col:
                    if source_url:
                        st.link_button("Abrir anuncio ↗", source_url, use_container_width=True)
                    else:
                        st.caption("No hay enlace de anuncio validable")
                with apply_col:
                    if apply_url and apply_url != source_url:
                        st.link_button("Candidatura ↗", apply_url, use_container_width=True)
                    elif source_url:
                        st.caption("Candidatura desde el anuncio")
                    else:
                        st.caption("Sin enlace de candidatura validable")
                with save_col:
                    key = "save_" + hashlib.sha256(identity.encode("utf-8")).hexdigest()[:16]
                    if identity in st.session_state.saved_jobs:
                        st.button("✓ Guardada", key=key, disabled=True, use_container_width=True)
                    elif st.button("☆ Guardar", key=key, use_container_width=True):
                        st.session_state.saved_jobs[identity] = {
                            "title": title,
                            "company": company,
                            "location": location,
                            "score": score,
                            "job_url": source_url,
                            "job_url_direct": apply_url,
                            "source": source_name,
                            "description": description,
                        }
                        st.toast("Vacante guardada en esta sesión.")
                        st.rerun()

                with st.expander("Análisis automático de requisitos y condiciones"):
                    st.caption(
                        "Lectura explicable del texto y de los metadatos del anuncio; no es una predicción de contratación. "
                        "Cuando un dato no aparece, se marca como no indicado en lugar de inventarlo."
                    )
                    salary_evidence = str(row.get("salary_evidence") or "sin información salarial verificable")
                    salary_value = str(row.get("salary") or "No indicado")
                    st.markdown(f"**Salario publicado:** {salary_value}")
                    st.caption(f"Base: {salary_evidence}. El filtro salarial compara solo cantidades expresables en EUR/año.")
                    experience_level = str(row.get("experience_level") or "No indicado")
                    experience_evidence = str(row.get("experience_evidence") or "No se ha encontrado un requisito de años verificable.")
                    years_min = row.get("experience_min_years")
                    years_max = row.get("experience_max_years")
                    if pd.notna(years_min) and years_min is not None:
                        if pd.notna(years_max) and years_max is not None:
                            years_text = f"{int(years_min)}–{int(years_max)} años"
                        else:
                            years_text = f"{int(years_min)}+ años"
                    else:
                        years_text = "Años no especificados"
                    st.markdown(f"**Experiencia detectada:** {experience_level} · {years_text}")
                    st.caption(f"Evidencia: {experience_evidence}")
                    st.markdown(
                        f"**Tipo de contrato:** {row.get('employment_type_label') or 'No indicado'} "
                        f"· {row.get('employment_type_evidence') or 'Sin evidencia clara'}"
                    )
                    st.markdown(
                        f"**Modalidad:** {row.get('work_mode_label') or 'No indicado'} "
                        f"· {row.get('work_mode_evidence') or 'Sin evidencia clara'}"
                    )

                    requirements = row.get("requirements")
                    if isinstance(requirements, list) and requirements:
                        st.markdown("**Herramientas y requisitos mencionados**")
                        st.write(", ".join(str(item) for item in requirements))
                    else:
                        st.caption("No se han detectado herramientas de la lista de comprobación en el texto disponible.")

                    if st.session_state.cv_text:
                        cv_matches = row.get("cv_matches")
                        cv_unconfirmed = row.get("cv_unconfirmed")
                        cv_matches = cv_matches if isinstance(cv_matches, list) else []
                        cv_unconfirmed = cv_unconfirmed if isinstance(cv_unconfirmed, list) else []
                        st.markdown("**Contraste con el CV de esta sesión**")
                        if cv_matches:
                            st.success("Detectado en el texto del CV: " + ", ".join(cv_matches))
                        else:
                            st.caption("No se han detectado coincidencias exactas con los requisitos identificados en el texto del CV.")
                        if cv_unconfirmed:
                            st.caption(
                                "No localizado en el texto del CV (no significa que no tengas esa habilidad): "
                                + ", ".join(cv_unconfirmed)
                            )
                    else:
                        st.caption("Sube un CV en la barra lateral para contrastar las herramientas detectadas; es opcional.")

                    if source_url:
                        st.write(f"Enlace del anuncio: {source_url}")
                    if apply_url and apply_url != source_url:
                        st.write(f"Enlace de candidatura: {apply_url}")
                    st.caption("El análisis se basa en el texto recibido por el scraper. Las descripciones incompletas pueden limitar la detección; abre el anuncio para confirmar las condiciones.")

    with st.expander("Preparar borrador de carta"):
        st.caption("Plantilla editable: revisa y personaliza el contenido; no se atribuyen habilidades que no hayas confirmado.")
        titles = df["title"].tolist() if not df.empty else []
        selected = st.selectbox("Vacante", titles, key="letter_title") if titles else ""
        if selected:
            selected_row = df[df["title"] == selected].iloc[0]
            company_name = str(selected_row.get("company") or "el equipo de selección")
            user_name = str(profile.get("name") or "[Tu nombre]")
            letter = (
                f"Estimado equipo de selección de {company_name},\n\n"
                f"Me gustaría presentar mi candidatura al puesto de {selected}. Mi formación en Economía "
                "y mi especialización en sistemas de decisión me han llevado a interesarme por el análisis "
                "de datos y la resolución de problemas de negocio. Estoy ampliando mis competencias técnicas "
                "y me interesa aplicarlas en un entorno profesional.\n\n"
                "Me gustaría conocer mejor las necesidades del equipo y explicar cómo mi formación podría contribuir al puesto.\n\n"
                f"Un saludo,\n{user_name}"
            )
            st.text_area("Borrador editable", letter, height=230)

with tab_saved:
    st.subheader("Tu lista de seguimiento")
    st.caption("Las vacantes guardadas permanecen en esta sesión; no se sincronizan entre dispositivos.")
    saved_items = list(st.session_state.saved_jobs.values())
    if not saved_items:
        st.info("Todavía no has guardado ninguna vacante. Usa ☆ Guardar en una tarjeta para crear tu shortlist.")
    else:
        for index, saved in enumerate(saved_items):
            with st.container(border=True):
                saved_title_col, saved_score_col = st.columns([5, 1])
                with saved_title_col:
                    st.markdown(f"**{saved.get('title', 'Puesto sin título')}**")
                    st.caption(" · ".join(str(saved.get(k) or "") for k in ("company", "location", "source") if saved.get(k)))
                with saved_score_col:
                    st.metric("Encaje", f"{saved.get('score', 0)}/100")
                saved_source = saved.get("job_url") or ""
                saved_apply = saved.get("job_url_direct") or ""
                if saved_source:
                    st.link_button("Abrir anuncio ↗", saved_source, key=f"saved_source_{index}")
                if saved_apply and saved_apply != saved_source:
                    st.link_button("Ir a candidatura ↗", saved_apply, key=f"saved_apply_{index}")
                if st.button("Quitar de guardadas", key=f"remove_saved_{index}"):
                    remove_key = next((key for key, value in st.session_state.saved_jobs.items() if value is saved), None)
                    if remove_key is not None:
                        del st.session_state.saved_jobs[remove_key]
                    st.rerun()

with tab_method:
    st.subheader("Transparencia antes que humo")
    st.markdown(
        """
        **Qué hace el índice de encaje**
        
        Combina el título objetivo, las palabras clave que figuran en la configuración y, cuando das tu consentimiento, el solapamiento textual con el CV. Si el objetivo indica un perfil senior (o el CV aporta señales claras de experiencia senior), el ranking limita las ofertas de prácticas y reduce las junior para que no desplacen a puestos de nivel adecuado. Es una heurística explicable, no una probabilidad de entrevista.

        Si has cargado un CV, también se comprueba si el perfil y la vacante parecen pertenecer a ámbitos profesionales claramente distintos. Cuando hay señales fuertes de incompatibilidad (por ejemplo, geociencias frente a oncología), el índice se limita y la tarjeta muestra el motivo. Esta comprobación usa reglas conservadoras y puede equivocarse; un cambio de carrera intencional se puede indicar escribiendo el puesto objetivo correspondiente.

        **Análisis de condiciones**
        
        El análisis automático extrae salarios explícitos, periodo de pago, requisitos de experiencia, tipo de contrato, modalidad de trabajo y herramientas mencionadas. El salario mínimo compara importes en euros normalizados a una cifra anual; no realiza conversiones de otras monedas. Los filtros avanzados son opcionales y están desactivados por defecto. Cuando un anuncio no incluye información, se conserva en los resultados por defecto y se etiqueta como “No indicado”. Si subes el CV con consentimiento, se comparan las herramientas extraídas con el texto disponible; que una habilidad no aparezca en el CV no implica que no la tengas.

        **Qué significa un enlace válido**
        
        JobScout descarta varios patrones típicos de páginas genéricas de búsqueda y conserva por separado el anuncio original y el enlace de candidatura cuando existen. La validación es estructural; no puede garantizar que la vacante siga publicada o que el portal no redirija.

        **Qué cambia entre búsqueda rápida y completa**
        
        La rápida limita las combinaciones y páginas consultadas, usa menos reintentos y evita las peticiones adicionales para descargar cada descripción de LinkedIn. La completa intenta encontrar más resultados y recuperar más información, pero depende del ritmo y de los límites de las webs externas.

        **Privacidad**
        
        El CV cargado se procesa en la sesión de la app para calcular el índice. No lo subas a un repositorio público ni introduzcas secretos en archivos de configuración publicados. Las vacantes guardadas y el CV de esta interfaz se mantienen en el estado de la sesión.
        """
    )
    with st.expander("Diagnóstico técnico de la base de datos"):
        if db_diagnostics:
            for item in db_diagnostics:
                st.write(item)
        else:
            st.caption("No hay diagnóstico de base de datos disponible.")
        st.caption("La app abre SQLite en modo de solo lectura y no crea vacantes ficticias cuando no encuentra datos.")
