from __future__ import annotations

import hashlib
import importlib.util
import os
import queue
import re
import subprocess
import sys
import threading
import time
from pathlib import Path
from typing import Any

import pandas as pd
import streamlit as st

SRC_DIR = Path(__file__).resolve().parent / "src"
if SRC_DIR.is_dir() and str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))

from jobscout_links import (  # noqa: E402
    canonicalize_row,
    canonical_job_identity,
    choose_job_links,
    load_config,
    load_jobs_from_sqlite,
    score_job,
)

APP_BUILD = "2026.10.26-search-db-7bd5d8a"


def _expected_database_path(config_data: dict[str, Any], loaded_config_path: Path | None) -> Path:
    """Resolve the same SQLite path the CLI uses for this loaded YAML configuration."""
    configured = str(config_data.get("db_path") or "").strip()
    if configured:
        return Path(configured).expanduser()
    profile_name = str(config_data.get("config_name") or "").strip()
    if not profile_name:
        stem = loaded_config_path.stem if loaded_config_path else "config"
        profile_name = "default" if stem == "config" else stem
    profile_name = re.sub(r"[^a-zA-Z0-9_-]", "-", profile_name).strip("-").lower() or "default"
    data_dir = Path.home() / ".local" / "share" / "job-scout"
    return data_dir / "job-scout.db" if profile_name == "default" else data_dir / f"{profile_name}.db"


st.set_page_config(
    page_title="JobScout Pro",
    page_icon="✦",
    layout="wide",
    initial_sidebar_state="expanded",
)

st.markdown(
    """
    <style>
    @import url('https://fonts.googleapis.com/css2?family=DM+Sans:wght@400;500;600;700&family=Manrope:wght@400;500;600;700;800&display=swap');
    :root { --ink:#eef4ff; --muted:#9baac2; --panel:#121d30; --line:#263752; --cyan:#67e8f9; --violet:#a78bfa; }
    html, body, [class*="css"] { font-family:'DM Sans', sans-serif; }
    .stApp { background: radial-gradient(ellipse at 12% 0%, rgba(68,91,180,.20), transparent 38%), #080e19; color:var(--ink); }
    [data-testid="stAppViewContainer"] > .main .block-container { max-width:1500px; padding-top:2.1rem; padding-bottom:3rem; }
    [data-testid="stHeader"] { background:transparent; }
    [data-testid="stSidebar"] { background:#0c1423; border-right:1px solid #1d2b42; }
    [data-testid="stSidebar"] > div { padding-top:1.5rem; }
    h1,h2,h3,h4 { font-family:'Manrope',sans-serif !important; color:#f4f7ff !important; letter-spacing:-.035em; }
    h1 { font-size:2.6rem !important; line-height:1.1 !important; }
    h2 { font-size:1.55rem !important; }
    p, label, li { color:#d8e1f0; }
    .eyebrow { color:var(--cyan); text-transform:uppercase; letter-spacing:.19em; font-size:.72rem; font-weight:800; margin-bottom:.8rem; }
    .hero { border:1px solid #283957; border-radius:24px; padding:28px 30px; margin:0 0 24px 0; background:linear-gradient(115deg, rgba(30,48,81,.96), rgba(18,29,48,.96) 58%, rgba(48,35,82,.74)); box-shadow:0 16px 48px rgba(0,0,0,.15); }
    .hero-title { color:#f4f7ff; font-family:'Manrope',sans-serif; font-size:2.25rem; font-weight:800; letter-spacing:-.055em; line-height:1.13; margin-bottom:.75rem; }
    .hero-copy { color:#b8c7df; max-width:720px; font-size:1rem; line-height:1.65; }
    .hero-chip { display:inline-block; padding:7px 11px; border-radius:99px; border:1px solid #405477; color:#cbd8ef; font-size:.75rem; font-weight:700; margin-top:14px; background:rgba(9,17,31,.4); }
    [data-testid="stMetric"] { background:linear-gradient(145deg,rgba(18,29,48,.92),rgba(13,22,37,.92)); padding:17px 19px; border:1px solid #263752; border-radius:16px; }
    [data-testid="stMetricLabel"] { color:#aab8cf !important; font-weight:600; }
    [data-testid="stMetricValue"] { color:#f2f7ff !important; font-family:'Manrope',sans-serif; }
    [data-testid="stVerticalBlockBorderWrapper"] { border-color:#263752 !important; border-radius:18px !important; background:rgba(15,25,42,.78); }
    .stButton > button, .stLinkButton > a { border-radius:11px; font-weight:700; transition:all .18s ease; }
    .stButton > button[kind="primary"] { background:linear-gradient(100deg,#67e8f9,#818cf8); color:#07111d; border:0; }
    .stButton > button:hover, .stLinkButton > a:hover { transform:translateY(-1px); border-color:#67e8f9; }
    [data-testid="stExpander"] { border:1px solid #263752; border-radius:13px; }
    div[data-baseweb="select"] > div, div[data-baseweb="input"] > div { background:#111d30; border-color:#2a3c58; }
    .soft-note { color:#9eafc8; font-size:.86rem; line-height:1.5; }
    .score-pill { color:#8fe9f2; font-size:.78rem; letter-spacing:.08em; text-transform:uppercase; font-weight:800; }
    hr { border-color:#25344d; }
    </style>
    """,
    unsafe_allow_html=True,
)

st.markdown(
    """
    <div class="hero">
      <div class="eyebrow">✦ Personal career intelligence</div>
      <div class="hero-title">Menos scroll. Más oportunidades que encajan.</div>
      <div class="hero-copy">Tu espacio de búsqueda para puestos de datos, analítica y decisión. Reúne vacantes reales, prioriza las más relevantes para tu perfil y conserva a mano las candidaturas que merecen tu tiempo.</div>
      <div class="hero-chip">RANKING EXPLICABLE · ENLACES ESPECÍFICOS · SIN OFERTAS FICTICIAS</div>
    </div>
    """,
    unsafe_allow_html=True,
)

config, config_path = load_config()
# The CLI and dashboard must read the exact same database. Do not let a fallback
# scan select another SQLite file from the repository or an old profile.
expected_db_path = _expected_database_path(config, config_path)
db_config = {**config, "db_path": str(expected_db_path)}
profile = config.get("profile", {}) if isinstance(config.get("profile", {}), dict) else {}
if "cv_text" not in st.session_state:
    st.session_state.cv_text = str(profile.get("resume_text", "") or "")
if "saved_jobs" not in st.session_state:
    st.session_state.saved_jobs = {}
if "refresh_key" not in st.session_state:
    st.session_state.refresh_key = 0
if "target_title" not in st.session_state:
    st.session_state.target_title = str(profile.get("target_title", "") or "Data Analyst / Business Analyst")
if "last_scrape" not in st.session_state:
    st.session_state.last_scrape = None
if "cv_fingerprint" not in st.session_state:
    st.session_state.cv_fingerprint = ""

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


with st.sidebar:
    st.markdown("## Tu espacio")
    st.caption("Ajusta la búsqueda a lo que de verdad te interesa.")
    st.caption(f"Motor {APP_BUILD}")
    target_title = st.text_input(
        "Puestos objetivo",
        key="target_title",
        help="Se usa para priorizar títulos relacionados; no presupone que domines una tecnología.",
    )

    uploaded_cv = st.file_uploader("CV en PDF (opcional)", type=["pdf"])
    consent = st.checkbox("Acepto procesar el CV en esta sesión.")
    if uploaded_cv and consent:
        file_bytes = uploaded_cv.getvalue()
        fingerprint = hashlib.sha256(file_bytes).hexdigest()
        if fingerprint != st.session_state.cv_fingerprint:
            try:
                from pypdf import PdfReader

                from io import BytesIO
                reader = PdfReader(BytesIO(file_bytes))
                extracted = "\n".join((page.extract_text() or "") for page in reader.pages)
                if extracted.strip():
                    st.session_state.cv_text = extracted
                    st.session_state.cv_fingerprint = fingerprint
                    st.success("CV procesado en esta sesión.")
                else:
                    st.warning("No se ha podido extraer texto del PDF; puede ser un escaneo.")
            except Exception as exc:
                st.warning(f"No se ha podido leer el CV: {exc}")
    elif uploaded_cv and not consent:
        st.caption("Marca la casilla para usar el contenido del CV en el ranking.")

    st.divider()
    st.markdown("### Filtros")
    min_score = st.slider("Relevancia mínima", 0, 100, 20, 5)
    search_text = st.text_input("Palabra clave", placeholder="Puesto, empresa o ubicación")
    location_filter = st.selectbox(
        "Modalidad / zona", ["Todas", "Madrid / España", "Remoto / Europa"]
    )
    source_filter = st.multiselect("Fuentes", available_sources, default=available_sources)
    sort_mode = st.selectbox("Ordenar por", ["Mayor relevancia", "Más recientes"])

    st.divider()
    st.markdown("### Rastreo de ofertas")
    scan_mode = st.radio(
        "Alcance de la búsqueda",
        ["⚡ Rápida", "🔎 Completa"],
        index=0,
        help="La rápida hace menos consultas, limita la paginación y evita peticiones individuales de descripción. La completa intenta cubrir más resultados y puede tardar varios minutos.",
    )
    st.caption(
        "Rápida: menos peticiones y resultados iniciales. Completa: más cobertura, aunque las fuentes pueden bloquear o ralentizar consultas."
    )
    if st.button("✦ Buscar oportunidades", type="primary", use_container_width=True):
        st.session_state["scrape_requested"] = True
        st.session_state["requested_scan_mode"] = scan_mode
        st.rerun()
    if st.button("↻ Actualizar resultados", use_container_width=True):
        st.session_state.refresh_key += 1
        st.rerun()

    with st.expander("Diagnóstico"):
        st.write(f"Configuración: {config_path or 'no encontrada'}")
        st.write(f"Base de datos esperada por el motor: {expected_db_path}")
        st.write("El panel lee en solo lectura la misma ruta SQLite que utiliza el motor.")
        for item in db_diagnostics:
            st.caption(item)
        if not st.session_state.cv_text:
            st.info("Sin CV: el ranking usa títulos y palabras clave de la configuración.")



if st.session_state.pop("scrape_requested", False):
    scan_mode = st.session_state.get("requested_scan_mode", "⚡ Rápida")
    env_config = os.getenv("JOBSCOUT_CONFIG", "").strip()
    config_file = Path(env_config).expanduser() if env_config else config_path
    if not config_file or not config_file.is_file():
        st.error("No encuentro un archivo de configuración válido para el scraper.")
    else:
        try:
            module_available = importlib.util.find_spec("job_scout.cli") is not None
        except (ImportError, ModuleNotFoundError, ValueError):
            module_available = False
        if not module_available:
            st.error("No se encuentra el motor de búsqueda. Comprueba que el despliegue use la rama principal actualizada.")
        else:
            command = [sys.executable, "-m", "job_scout.cli", "--config", str(config_file.resolve()), "scrape"]
            is_quick = scan_mode.startswith("⚡")
            if is_quick:
                command.append("--quick")
            child_env = os.environ.copy()
            child_env["PYTHONUNBUFFERED"] = "1"
            # Pass only the target titles typed in the UI; the uploaded CV stays
            # in Streamlit session state and is never copied into the subprocess env.
            child_env["JOBSCOUT_TARGET_TITLE"] = target_title
            existing_pythonpath = child_env.get("PYTHONPATH", "")
            child_env["PYTHONPATH"] = str(SRC_DIR) + (os.pathsep + existing_pythonpath if existing_pythonpath else "")
            timeout_seconds = 180 if is_quick else 900
            mode_label = "búsqueda rápida" if is_quick else "búsqueda completa"
            with st.status(f"Ejecutando {mode_label}…", expanded=True) as status:
                st.write("Conectando con las fuentes configuradas y guardando resultados reales.")
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
                        message = f"Se alcanzó el límite de {timeout_seconds // 60} min. Se conservarán los resultados que el motor ya haya guardado."
                        status.update(label="Búsqueda detenida por tiempo límite", state="error", expanded=True)
                        success = False
                    elif return_code == 0:
                        message = f"Búsqueda terminada en {elapsed} s. Ya puedes revisar las oportunidades encontradas."
                        status.update(label="Búsqueda completada", state="complete", expanded=False)
                        success = True
                    elif return_code == 2 and "No valid postings found" in "\n".join(logs):
                        message = "La búsqueda terminó, pero ninguna fuente entregó vacantes utilizables. Revisa el diagnóstico por fuente y los errores del registro."
                        status.update(label="Sin vacantes válidas: revisa las fuentes", state="error", expanded=True)
                        success = False
                    else:
                        message = f"El motor terminó con código {return_code}. Consulta el diagnóstico para ver el detalle."
                        status.update(label="La búsqueda terminó con incidencias", state="error", expanded=True)
                        success = False
                    st.session_state.last_scrape = {
                        "ok": success,
                        "message": message,
                        "logs": "\n".join(logs[-100:]),
                    }
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

scoring_config = dict(config)
scoring_config["profile"] = {**profile, "target_title": target_title}
for job in jobs:
    job["calculated_score"] = score_job(job, scoring_config, st.session_state.cv_text)

columns = [
    "title", "company", "location", "description", "job_url", "job_url_direct",
    "source", "date_posted", "salary", "id", "calculated_score", "has_specific_link",
    "_identity",
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
    elif available_sources:
        df = df.iloc[0:0]
    if sort_mode == "Más recientes" and "date_posted" in df.columns:
        df = df.assign(_posted=pd.to_datetime(df["date_posted"], errors="coerce", utc=True))
        df = df.sort_values(["_posted", "calculated_score"], ascending=[False, False], kind="stable")
        df = df.drop(columns=["_posted"])
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

tab_discover, tab_saved, tab_method = st.tabs(["✦ Oportunidades", "★ Guardadas", "ⓘ Cómo funciona"])

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
            score_label = "Encaje alto" if score >= 70 else ("Encaje medio" if score >= 45 else "Por revisar")

            with st.container(border=True):
                title_col, score_col = st.columns([5, 1])
                with title_col:
                    st.subheader(title)
                    st.markdown(f"**{company}**")
                    st.caption(" · ".join(part for part in [location, source_name, date_value, salary] if part))
                with score_col:
                    st.metric("Encaje", f"{score}/100")
                    st.caption(score_label)

                if description:
                    st.write(description[:650] + ("…" if len(description) > 650 else ""))
                else:
                    st.caption("Descripción no disponible en los datos recogidos; valora el título y abre el anuncio para comprobar los requisitos.")

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

                with st.expander("Detalles y verificación"):
                    st.write(f"Fuente: {source_name}")
                    st.write(f"Publicación: {date_value or 'No indicada'}")
                    if source_url:
                        st.write(f"Enlace del anuncio: {source_url}")
                    if apply_url and apply_url != source_url:
                        st.write(f"Enlace de candidatura: {apply_url}")
                    st.caption("El enlace se valida por estructura, no por disponibilidad. Comprueba que la vacante siga activa y que los requisitos encajen contigo.")

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
        
        Combina el título objetivo, las palabras clave que figuran en la configuración y, cuando das tu consentimiento, el solapamiento textual con el CV. Es una regla explicable para ordenar la lista: **no es una probabilidad de entrevista ni una evaluación automática de tus capacidades**.

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
