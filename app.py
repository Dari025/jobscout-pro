from __future__ import annotations

import importlib.util
import os
import subprocess
import sys
from pathlib import Path
from typing import Any

import pandas as pd
import streamlit as st

# Enable the repository src-layout when running from a local checkout.
SRC_DIR = Path(__file__).resolve().parent / "src"
if SRC_DIR.is_dir() and str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))

from jobscout_links import canonicalize_row, choose_job_links, load_config, load_jobs_from_sqlite, score_job

st.set_page_config(page_title="JobScout Pro", page_icon="💼", layout="wide", initial_sidebar_state="expanded")
st.markdown("""
<style>
@import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700&display=swap');
html, body, [class*="css"] { font-family: 'Inter', sans-serif; }
.stApp { background-color: #0b0f17; color: #e2e8f0; }
[data-testid="stSidebar"] { background-color: #111827; border-right: 1px solid #1e293b; }
h1, h2, h3 { color: #f8fafc !important; font-weight: 700 !important; }
.job-card { background: #1e293b; border: 1px solid #334155; border-radius: 8px; padding: 18px; margin: 10px 0; }
.score { font-size: 1.05rem; font-weight: 700; color: #7dd3fc; }
</style>
""", unsafe_allow_html=True)

st.title("💼 JobScout Pro")
st.caption("Buscador y priorizador de vacantes. El porcentaje es un índice de relevancia, no una probabilidad de contratación.")

config, config_path = load_config()
profile = config.get("profile", {}) if isinstance(config.get("profile", {}), dict) else {}
if "cv_text" not in st.session_state:
    st.session_state.cv_text = str(profile.get("resume_text", "") or "")
if "saved_jobs" not in st.session_state:
    st.session_state.saved_jobs = {}
if "refresh_key" not in st.session_state:
    st.session_state.refresh_key = 0
if "target_title" not in st.session_state:
    st.session_state.target_title = str(profile.get("target_title", "") or "Data Analyst")

with st.sidebar:
    st.header("Perfil")
    target_title = st.text_input("Puestos objetivo", key="target_title",
        help="Se usa junto con las keywords configuradas; no se presupone que domines una tecnología.")
    uploaded_cv = st.file_uploader("Añadir CV en PDF (opcional)", type=["pdf"])
    consent = st.checkbox("Acepto procesar el texto del CV en esta sesión.")
    if uploaded_cv and consent:
        try:
            from pypdf import PdfReader
            reader = PdfReader(uploaded_cv)
            extracted = "\n".join((page.extract_text() or "") for page in reader.pages)
            if extracted.strip():
                st.session_state.cv_text = extracted
                st.success("Texto del CV leído para esta sesión.")
            else:
                st.warning("No se ha podido extraer texto del PDF. Comprueba si es un escaneo.")
        except ImportError:
            st.warning("Falta pypdf. Instálalo con: pip install pypdf")
        except Exception as exc:
            st.error(f"No se ha podido leer el PDF: {exc}")

    min_score = st.slider("Índice mínimo de relevancia", 0, 100, 20, 5)
    search_text = st.text_input("Buscar por puesto, empresa o ubicación", "")
    location_filter = st.selectbox("Ubicación", ["Todas", "Madrid", "Remoto / Europa"])
    sort_by_score = st.checkbox("Ordenar por relevancia", value=True)
    st.divider()
    left, right = st.columns(2)
    with left:
        if st.button("🔄 Actualizar datos", use_container_width=True):
            st.session_state.refresh_key += 1
            st.rerun()
    with right:
        scrape_clicked = st.button("🚀 Buscar ofertas", use_container_width=True)

    if scrape_clicked:
        try:
            module_available = importlib.util.find_spec("job_scout.cli") is not None
        except (ImportError, ModuleNotFoundError, ValueError):
            module_available = False
        if not module_available:
            st.error("No se encuentra el módulo job_scout.cli. El repositorio público no incluye src/job_scout, por lo que este botón no puede iniciar una nueva búsqueda en una instalación basada solo en GitHub. No se inventarán ofertas.")
        else:
            # Use the same config that the dashboard loaded. Otherwise the CLI
            # falls back to ~/.config/job-scout/config.yaml and fails on hosted Linux.
            env_config = os.getenv("JOBSCOUT_CONFIG", "").strip()
            config_file = Path(env_config).expanduser() if env_config else config_path
            command = [sys.executable, "-m", "job_scout.cli"]
            if config_file and config_file.is_file():
                command += ["--config", str(config_file.resolve())]
            else:
                st.error(
                    "No encuentro un archivo de configuración válido para el scraper. "
                    "Añade busqueda.yaml o configura JOBSCOUT_CONFIG."
                )
                st.stop()
            command += ["scrape"]
            with st.spinner("Buscando ofertas en las fuentes configuradas…"):
                try:
                    child_env = os.environ.copy()
                    # The package uses a src-layout; make it importable in the child CLI process too.
                    existing_pythonpath = child_env.get("PYTHONPATH", "")
                    child_env["PYTHONPATH"] = str(SRC_DIR) + (os.pathsep + existing_pythonpath if existing_pythonpath else "")
                    completed = subprocess.run(command, cwd=Path(__file__).resolve().parent,
                        env=child_env, capture_output=True, text=True, timeout=300, check=False)
                    if completed.returncode == 0:
                        st.success("Recogida terminada. Actualiza los datos para ver los resultados.")
                        if completed.stdout.strip():
                            st.code(completed.stdout[-4000:])
                        st.session_state.refresh_key += 1
                        st.rerun()
                    else:
                        st.error(f"La recogida terminó con código {completed.returncode}.")
                        st.code((completed.stderr or completed.stdout or "Sin diagnóstico")[-4000:])
                except subprocess.TimeoutExpired:
                    st.error("La recogida superó el límite de 5 minutos. Revisa el log del scraper.")
                except OSError as exc:
                    st.error(f"No se pudo ejecutar el scraper: {exc}")

    with st.expander("Configuración y diagnóstico"):
        st.write(f"Archivo de configuración cargado: {config_path or 'ninguno'}")
        st.write("Ruta SQLite: variable JOBSCOUT_DB_PATH, db_path configurado o rutas conocidas.")
        if not st.session_state.cv_text:
            st.info("No hay texto de CV disponible. El ranking utilizará solo los puestos objetivo y las keywords configuradas.")

# Read actual stored rows only. Empty DB = empty dashboard, never made-up vacancies.
raw_jobs, db_diagnostics = load_jobs_from_sqlite(config)
for diagnostic in db_diagnostics:
    st.sidebar.caption(diagnostic)
if not raw_jobs:
    st.warning("No se han encontrado vacantes reales en la base de datos. No se mostrarán ofertas de ejemplo como si fueran oportunidades de empleo.")
    st.info("Comprueba que el scraper haya terminado y revisa la ruta de la base de datos. Puedes definir JOBSCOUT_DB_PATH o db_path en una configuración local.")
    st.stop()

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
    job_id = str(job.get("id") or "").strip()
    source = str(job.get("source") or "").strip().lower()
    if job_id:
        identity = f"id:{source}:{job_id}"
    elif source_url or apply_url:
        identity = f"url:{(source_url or apply_url).rstrip('/')}"
    else:
        identity = "text:" + "|".join(str(job.get(key) or "").strip().casefold()
            for key in ("title", "company", "location", "date_posted"))
    if identity in seen:
        continue
    seen.add(identity)
    jobs.append(job)

scoring_config = dict(config)
scoring_config["profile"] = {**profile, "target_title": target_title}
for job in jobs:
    job["calculated_score"] = score_job(job, scoring_config, st.session_state.cv_text)

df_all = pd.DataFrame(jobs)
df = df_all[df_all["calculated_score"] >= min_score].copy()
if search_text:
    searchable = (df["title"].fillna("").astype(str) + " " +
        df["company"].fillna("").astype(str) + " " + df["location"].fillna("").astype(str))
    df = df[searchable.str.contains(search_text, case=False, na=False, regex=False)]
location_values = df["location"].fillna("").astype(str)
if location_filter == "Madrid":
    df = df[location_values.str.contains("madrid", case=False, na=False)]
elif location_filter == "Remoto / Europa":
    df = df[location_values.str.contains(r"remote|remoto|europe|europa|worldwide|anywhere", case=False, na=False)]
if sort_by_score:
    df = df.sort_values(["calculated_score", "title"], ascending=[False, True], kind="stable")

m1, m2, m3, m4 = st.columns(4)
m1.metric("Ofertas únicas", len(df_all))
m2.metric("Con enlace específico", int(df_all["has_specific_link"].sum()))
m3.metric("Índice ≥ 70", int((df_all["calculated_score"] >= 70).sum()))
m4.metric("Tras filtros", len(df))
st.caption("La comprobación descarta direcciones de búsqueda y páginas genéricas conocidas. No garantiza que una vacante siga activa o que el portal no haya cambiado su contenido.")

if df.empty:
    st.info("No hay ofertas con los filtros actuales. Reduce el índice mínimo o cambia la búsqueda.")
else:
    st.subheader(f"Vacantes ({len(df)})")
    st.download_button("📥 Exportar resultados CSV", data=df.to_csv(index=False).encode("utf-8-sig"),
        file_name="jobscout_resultados.csv", mime="text/csv")
    for display_index, (_, row) in enumerate(df.iterrows()):
        title = str(row.get("title") or "Puesto sin título")
        company = str(row.get("company") or "Empresa sin especificar")
        location = str(row.get("location") or "Ubicación no especificada")
        description = str(row.get("description") or "").strip()
        score = int(row.get("calculated_score") or 0)
        source_url, apply_url = choose_job_links(row.to_dict())
        identity = str(row.get("id") or source_url or apply_url or f"{title}|{company}|{location}")
        with st.container():
            st.markdown('<div class="job-card">', unsafe_allow_html=True)
            c_title, c_score = st.columns([5, 1])
            with c_title:
                st.subheader(title)
                st.write(f"**{company}** · {location}")
            with c_score:
                st.markdown(f'<div class="score">{score}/100</div>', unsafe_allow_html=True)
            if description:
                st.write(description[:700] + ("…" if len(description) > 700 else ""))
            else:
                st.warning("Esta oferta no tiene descripción guardada; la puntuación puede ser poco informativa.")
            l1, l2, l3 = st.columns([2, 2, 2])
            with l1:
                if source_url:
                    st.link_button("Abrir anuncio original", source_url, use_container_width=True)
                else:
                    st.caption("Sin enlace original específico")
            with l2:
                if apply_url and apply_url != source_url:
                    st.link_button("Ir a candidatura", apply_url, use_container_width=True)
                elif source_url:
                    st.caption("Solicita desde el anuncio original")
                else:
                    st.caption("Sin enlace de candidatura validable")
            with l3:
                if st.button("⭐ Guardar", key=f"save_{display_index}_{hash(identity)}", use_container_width=True):
                    st.session_state.saved_jobs[identity] = {
                        "title": title, "company": company, "location": location,
                        "score": score, "job_url": source_url, "job_url_direct": apply_url,
                    }
                    st.toast("Vacante guardada en esta sesión.")
            with st.expander("Ver datos y diagnóstico del enlace"):
                st.write(f"Fuente: {row.get('source') or 'No indicada'}")
                st.write(f"Fecha: {row.get('date_posted') or 'No indicada'}")
                if source_url:
                    st.write(f"Anuncio: {source_url}")
                if apply_url and apply_url != source_url:
                    st.write(f"Candidatura: {apply_url}")
                if not (source_url or apply_url):
                    st.warning("No se muestra un enlace genérico. Revisa el registro de origen en la base de datos.")
                st.write("La comprobación es estructural; para verificar identidad y vigencia hay que consultar la fuente.")
            st.markdown("</div>", unsafe_allow_html=True)

st.divider()
st.subheader("⭐ Vacantes guardadas (solo esta sesión)")
if not st.session_state.saved_jobs:
    st.caption("Todavía no has guardado ninguna vacante.")
else:
    for saved in st.session_state.saved_jobs.values():
        st.markdown(f"**{saved['title']}** — {saved['company']} · {saved['location']} · índice {saved['score']}/100")
        src = saved.get("job_url") or ""
        apply = saved.get("job_url_direct") or ""
        if src:
            st.link_button("Abrir anuncio guardado", src, key=f"saved-src-{abs(hash(src))}")
        elif apply:
            st.link_button("Abrir candidatura guardada", apply, key=f"saved-app-{abs(hash(apply))}")

st.divider()
with st.expander("Borrador de carta de presentación (plantilla, no generado por IA)"):
    st.caption("Completa y revisa el texto antes de utilizarlo. No se atribuyen habilidades no verificadas.")
    titles = df["title"].tolist()
    selected = st.selectbox("Puesto", titles, key="letter_title") if titles else ""
    if selected:
        selected_row = df[df["title"] == selected].iloc[0]
        company = str(selected_row.get("company") or "el equipo de selección")
        user_name = str(profile.get("name") or "[Tu nombre]")
        letter = (f"Estimado equipo de selección de {company},\n\n"
            f"Me gustaría presentar mi candidatura al puesto de {selected}. Mi formación en Economía "
            "y mi especialización en sistemas de decisión me han llevado a interesarme por el análisis "
            "de datos y la resolución de problemas de negocio. Estoy ampliando mis competencias técnicas "
            "y me interesa aplicarlas en un entorno profesional.\n\n"
            "Me gustaría conocer mejor las necesidades del equipo y explicar cómo mi formación podría contribuir al puesto.\n\n"
            f"Un saludo,\n{user_name}")
        st.text_area("Borrador editable", letter, height=220)
