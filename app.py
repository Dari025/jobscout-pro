import os
import sqlite3
import subprocess
import threading
import pandas as pd
import streamlit as st
import yaml
from pathlib import Path
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.metrics.pairwise import cosine_similarity

# Intento de carga de PyPDF para lectura de CV
try:
    from pypdf import PdfReader
    PDF_ENABLED = True
except ImportError:
    PDF_ENABLED = False

# --- CONFIGURACIÓN DE PÁGINA ---
st.set_page_config(
    page_title="JobScout AI // Pro Platform",
    page_icon="💼",
    layout="wide",
    initial_sidebar_state="expanded",
)

# --- INICIALIZACIÓN DE ESTADO (SESSION STATE) ---
if "saved_jobs" not in st.session_state:
    st.session_state.saved_jobs = []
if "cv_text" not in st.session_state:
    st.session_state.cv_text = ""
if "refresh_key" not in st.session_state:
    st.session_state.refresh_key = 0

# --- ESTILOS VISUALES CLEAN SAAS (B2B MODERN) ---
st.markdown(
    """
    <style>
    @import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700&display=swap');

    html, body, [class*="css"] { font-family: 'Inter', sans-serif; }
    .stApp { background-color: #0b0f17; color: #e2e8f0; }
    [data-testid="stSidebar"] { background-color: #111827; border-right: 1px solid #1e293b; }
    h1, h2, h3 { color: #f8fafc !important; font-weight: 700 !important; letter-spacing: -0.02em; }
    
    /* Tarjetas de ofertas */
    .saas-card {
        background-color: #1e293b; border: 1px solid #334155; border-radius: 8px;
        padding: 20px; margin-bottom: 16px; transition: all 0.2s ease;
    }
    .saas-card:hover { border-color: #3b82f6; transform: translateY(-2px); box-shadow: 0 4px 12px rgba(0,0,0,0.2); }
    
    /* Cajas de métricas (HUD) */
    .metric-box { background-color: #1e293b; border: 1px solid #334155; border-radius: 8px; padding: 16px; text-align: center; }
    .metric-box h4 { margin: 0; font-size: 0.75rem; color: #94a3b8; text-transform: uppercase; letter-spacing: 0.05em; }
    .metric-box h2 { margin: 6px 0 0 0; font-size: 1.5rem !important; color: #38bdf8 !important; }
    
    /* Botones primarios */
    .stButton>button { background-color: #2563eb !important; color: #ffffff !important; font-weight: 600 !important; border-radius: 6px !important; border: none !important; width: 100%; }
    .stButton>button:hover { background-color: #1d4ed8 !important; }
    
    /* Badges de Score */
    .score-badge-high { background-color: #064e3b; color: #34d399; border: 1px solid #059669; padding: 4px 10px; border-radius: 6px; font-weight: 700; font-size: 0.9em; }
    .score-badge-mid { background-color: #451a03; color: #fbbf24; border: 1px solid #d97706; padding: 4px 10px; border-radius: 6px; font-weight: 700; font-size: 0.9em; }
    .score-badge-low { background-color: #450a0a; color: #f87171; border: 1px solid #b91c1c; padding: 4px 10px; border-radius: 6px; font-weight: 700; font-size: 0.9em; }
    
    /* Etiquetas de Tecnologías */
    .tag-badge { background-color: #0f172a; border: 1px solid #334155; color: #94a3b8; padding: 3px 8px; border-radius: 4px; font-size: 0.75em; margin-right: 4px; display: inline-block; font-weight: 600;}
    </style>
""",
    unsafe_allow_html=True,
)

# --- CABECERA ---
st.markdown("<h1>💼 JobScout AI <span style='font-size: 0.5em; color: #38bdf8; background: #0c4a6e; padding: 4px 8px; border-radius: 4px; vertical-align: middle;'>PRO</span></h1>", unsafe_allow_html=True)
st.markdown("<p style='color: #94a3b8; margin-top: -15px;'>Plataforma Inteligente de Matcheo y Adaptación de Candidaturas</p>", unsafe_allow_html=True)

# --- AGENTE LECTOR DE PDF ---
def extraer_texto_pdf(file):
    if not PDF_ENABLED: return ""
    try:
        reader = PdfReader(file)
        return " ".join([page.extract_text() for page in reader.pages if page.extract_text()])
    except Exception:
        return ""

# --- CARGA DE CONFIGURACIÓN BÁSICA ---
@st.cache_data
def cargar_configuracion():
    config_path = Path("busqueda.yaml")
    if config_path.exists():
        try:
            with open(config_path, "r", encoding="utf-8") as f:
                return yaml.safe_load(f) or {}
        except Exception: pass
    return {}

config_user = cargar_configuracion()
profile_info = config_user.get("profile", {})
target_title = profile_info.get("target_title", "Decision Science Intern")
search_terms = config_user.get("search", {}).get("terms", [])

# Si no hay CV subido, usamos el del YAML
if not st.session_state.cv_text:
    st.session_state.cv_text = profile_info.get("resume_text", "")

# --- AGENTE DE MATRICES (SCORING SEMÁNTICO) ---
def calcular_score_semantico(row, resume_body, target_t):
    titulo = str(row.get("title", "")).lower()
    desc = str(row.get("description", "")).lower()
    empresa = str(row.get("company", "")).lower()
    texto_oferta = f"{titulo} {empresa} {desc}"

    if not desc or len(desc) < 20: return 15

    # 1. Similitud Vectorial TF-IDF
    doc_cv = f"{target_t} {resume_body}"
    try:
        vectorizer = TfidfVectorizer(stop_words="english", ngram_range=(1, 2))
        tfidf = vectorizer.fit_transform([doc_cv, texto_oferta])
        sim_bruta = cosine_similarity(tfidf[0:1], tfidf[1:2])[0][0]
    except Exception:
        sim_bruta = 0.0

    score_vectorial = min(100.0, (sim_bruta / 0.30) * 100)

    # 2. Match de Título
    score_titulo = 0
    if target_t:
        w_target = [w.lower() for w in target_t.split() if len(w) > 3 and w != "intern"]
        if w_target:
            matches_t = sum(1 for w in w_target if w in titulo)
            score_titulo = (matches_t / len(w_target)) * 100

    # 3. Stack Técnico
    stack_clave = ["python", "sql", "r", "rstudio", "bayesian", "econometrics", "anova", "spc", "tableau", "power bi", "remote"]
    matches_stack = sum(1 for kw in stack_clave if kw in texto_oferta)
    score_stack = min(100.0, (matches_stack / 4) * 100)

    score_final = (score_vectorial * 0.45) + (score_titulo * 0.35) + (score_stack * 0.20)
    return int(max(15, min(98, score_final)))

# --- AGENTE DE DATOS (LECTURA Y CACHÉ) ---
@st.cache_data(ttl=300, show_spinner=False)
def cargar_datos_procesados(_cv_text, target_t, refresh_key):
    appdata_path = Path(os.getenv("LOCALAPPDATA", "")) / "job_scout" / "jobs.db"
    rutas_candidatas = [
        Path.home() / ".local" / "share" / "job-scout" / "busqueda.db",
        appdata_path, Path("jobs.db"), Path("src/job_scout/jobs.db")
    ]
    
    for p in Path(".").rglob("*.db"):
        if "venv" not in str(p) and p not in rutas_candidatas: rutas_candidatas.append(p)

    df_final = pd.DataFrame()
    for db_path in rutas_candidatas:
        if db_path.exists():
            try:
                conn = sqlite3.connect(db_path)
                cursor = conn.cursor()
                cursor.execute("SELECT name FROM sqlite_master WHERE type='table';")
                tablas = [t[0] for t in cursor.fetchall() if not t[0].startswith("sqlite_")]
                
                for t in tablas:
                    df = pd.read_sql(f"SELECT * FROM {t}", conn)
                    if not df.empty:
                        df_final = df
                        conn.close()
                        break
                if not df_final.empty: break
            except: pass

    if df_final.empty: return pd.DataFrame(), None, None, None, None, None

    # Identificar columnas
    col_titulo = next((c for c in ["title", "job_title", "nombre", "puesto"] if c in df_final.columns), df_final.columns[0])
    col_empresa = next((c for c in ["company", "company_name", "empresa"] if c in df_final.columns), df_final.columns[1])
    col_ubicacion = next((c for c in ["location", "ubicacion", "city"] if c in df_final.columns), None)
    col_url = next((c for c in ["job_url", "url", "link"] if c in df_final.columns), None)
    col_desc = next((c for c in ["description", "descripcion", "summary"] if c in df_final.columns), None)

    # Limpieza y Cálculo
    df_final = df_final.drop_duplicates(subset=[col_titulo, col_empresa], keep="first")
    df_final["calculated_score"] = df_final.apply(lambda r: calcular_score_semantico(r, _cv_text, target_t), axis=1)
    
    return df_final, col_titulo, col_empresa, col_ubicacion, col_url, col_desc

# Cargar la base de datos
df_base, col_titulo, col_empresa, col_ubicacion, col_url, col_desc = cargar_datos_procesados(st.session_state.cv_text, target_title, st.session_state.refresh_key)

# --- BARRA LATERAL ---
with st.sidebar:
    st.header("📄 Agente de Ingestión")
    if PDF_ENABLED:
        uploaded_cv = st.file_uploader("Sube tu CV (PDF) para re-calcular match", type="pdf")
        if uploaded_cv:
            st.session_state.cv_text = extraer_texto_pdf(uploaded_cv)
            st.success("CV Procesado. Match Score actualizado.")
    else:
        st.warning("⚠️ Módulo PDF desactivado. Instala `pypdf`.")

    st.markdown("---")
    st.header("⚙️ Agente Scraper")
    c1, c2 = st.columns(2)
    with c1:
        if st.button("🚀 Scrape", help="Busca nuevas ofertas en la web"):
            threading.Thread(target=lambda: subprocess.run(["python", "-m", "job_scout.cli", "scrape"]), daemon=True).start()
            st.toast("Barrido iniciado...")
    with c2:
        if st.button("🔄 Refrescar", help="Recarga la base de datos"):
            st.session_state.refresh_key += 1
            st.rerun()

    st.markdown("---")
    st.header("🎯 Filtros Tácticos")
    min_score = st.slider("Match Score Mínimo (%)", 0, 100, 50, 5)
    ordenar_score = st.checkbox("Ordenar por mayor Match", value=True)
    filtro_texto = st.text_input("🔍 Buscar corporación o rol", "")
    modo_ubicacion = st.radio("📍 Ubicación", ["🌐 Todas", "📍 Solo Madrid", "🌐 Solo Remoto"], index=0)

    st.markdown("---")
    with st.expander("🤖 AUDITOR DE CALIDAD (IA)"):
        if not df_base.empty:
            top_matches = len(df_base[df_base["calculated_score"] >= 80])
            st.markdown(f"**Total Extraídas:** `{len(df_base)}`")
            st.markdown(f"**Alta Probabilidad (≥ 80%):** `{top_matches}`")
            if top_matches > 5:
                st.success("Mercado favorable detectado para tu perfil.")
            else:
                st.warning("Mercado duro. Sube un CV más detallado o ajusta términos.")

# --- PROCESAMIENTO Y FILTRADO FINAL ---
if df_base.empty:
    st.warning("⚠️ No hay datos. Pulsa 'Scrape' en la barra lateral para buscar ofertas.")
    st.stop()

df_filtrado = df_base.copy()
df_filtrado = df_filtrado[df_filtrado["calculated_score"] >= min_score]
if ordenar_score: df_filtrado = df_filtrado.sort_values(by="calculated_score", ascending=False)
if filtro_texto:
    df_filtrado = df_filtrado[df_filtrado[col_titulo].str.contains(filtro_texto, case=False, na=False) | df_filtrado[col_empresa].str.contains(filtro_texto, case=False, na=False)]
if col_ubicacion:
    if modo_ubicacion == "📍 Solo Madrid": df_filtrado = df_filtrado[df_filtrado[col_ubicacion].str.contains("madrid", case=False, na=False)]
    elif modo_ubicacion == "🌐 Solo Remoto": df_filtrado = df_filtrado[df_filtrado[col_ubicacion].str.contains("remote|remoto|worldwide", case=False, na=False)]

# --- INTERFAZ PRINCIPAL (TABS) ---
tab_dash, tab_tailor, tab_saved = st.tabs(["📊 Dashboard de Vacantes", "🤖 Agente CV Tailor", "📑 Mis Guardados"])

with tab_dash:
    # HUD Superior
    hud1, hud2, hud3, hud4 = st.columns(4)
    hud1.markdown(f"<div class='metric-box'><h4>VACANTES FILTRADAS</h4><h2>{len(df_filtrado)}</h2></div>", unsafe_allow_html=True)
    hud2.markdown(f"<div class='metric-box'><h4>PERFIL ACTIVO</h4><h2>{str(target_title)[:15]}</h2></div>", unsafe_allow_html=True)
    hud3.markdown("<div class='metric-box'><h4>COMPLIANCE CV</h4><h2>OK</h2></div>", unsafe_allow_html=True)
    
    # Exportar CSV
    csv_data = df_filtrado.to_csv(index=False).encode('utf-8')
    with hud4:
        st.download_button(label="📥 Exportar CSV", data=csv_data, file_name='jobscout_leads.csv', mime='text/csv', use_container_width=True)

    st.markdown("<br>", unsafe_allow_html=True)

    # Renderizado de Tarjetas (Limitado a Top 100 para rendimiento)
    for idx, row in df_filtrado.head(100).iterrows():
        t = row.get(col_titulo, "Sin título")
        e = row.get(col_empresa, "Confidencial")
        u = row.get(col_ubicacion, "No especificada") if col_ubicacion else "No especificada"
        url = row.get(col_url, "#") if col_url else "#"
        d = str(row.get(col_desc, ""))
        s = int(row.get("calculated_score", 0))

        b_class = "score-badge-high" if s >= 80 else "score-badge-mid" if s >= 50 else "score-badge-low"
        stack_detected = [kw.upper() for kw in ["python", "r", "sql", "bayesian", "econometrics", "spc", "remote"] if kw in d.lower()]

        st.markdown(
            f"""
            <div class="saas-card">
                <div style="display: flex; justify-content: space-between; align-items: flex-start;">
                    <div>
                        <h3 style="margin: 0; font-size: 1.15em;">{t}</h3>
                        <p style="color: #94a3b8; font-size: 0.9em; margin: 4px 0 10px 0;"><b>{e}</b> &nbsp;•&nbsp; 📍 {u}</p>
                        {''.join([f"<span class='tag-badge'>{kw}</span>" for kw in stack_detected])}
                    </div>
                    <div class="{b_class}">{s}% MATCH</div>
                </div>
            </div>
            """, unsafe_allow_html=True
        )

        # Botonera Acción Rápida
        cc1, cc2, cc3 = st.columns([2, 2, 8])
        with cc1:
            if url != "#": st.link_button("🔗 Ver Oferta", url)
        with cc2:
            if st.button("⭐ Guardar", key=f"save_{idx}"):
                if t not in [j['titulo'] for j in st.session_state.saved_jobs]:
                    st.session_state.saved_jobs.append({'titulo': t, 'empresa': e, 'url': url, 'score': s})
                    st.toast(f"Guardado: {t}")
        with st.expander("📄 Ver descripción completa"):
            st.write(d)

with tab_tailor:
    st.markdown("### 🤖 Generador de Cartas de Presentación y Adaptador ATS")
    st.info("Selecciona una oferta de tu base de datos para generar material de postulación personalizado.")
    
    opciones_ofertas = df_filtrado[col_titulo].tolist()
    oferta_seleccionada = st.selectbox("Selecciona la vacante objetivo:", opciones_ofertas)
    
    if st.button("✨ Ejecutar Agente Tailor (Simulación)"):
        with st.spinner("Conectando con LLM Core... Analizando brechas..."):
            import time; time.sleep(1.5) # Simulación de llamada a API
            st.success("Análisis completado.")
            
            st.markdown("#### 🎯 Gap Analysis")
            st.write("- **Falta detectar explícitamente:** Herramientas de visualización (Tableau) requeridas en la oferta.")
            st.write("- **Fortaleza a destacar:** Tu background en econometría y modelos bayesianos encaja al 95%.")
            
            st.markdown("#### 📝 Borrador de Cover Letter Generado")
            st.text_area("Copia y edita:", f"Estimado equipo de selección,\n\nEscribo para presentar mi candidatura al puesto de {oferta_seleccionada}. Mi formación en modelos de decisión y análisis estadístico avanzado...", height=150)
            
            st.warning("*(Nota: Este módulo está listo para conectar con tu clave API de OpenAI/Gemini. Actualmente corre en modo Mock/Simulación)*")

with tab_saved:
    st.markdown("### 📑 Mis Vacantes Guardadas")
    if not st.session_state.saved_jobs:
        st.write("No has guardado ninguna oferta todavía. Usa el botón ⭐ en el Dashboard.")
    else:
        for job in st.session_state.saved_jobs:
            st.markdown(f"**{job['score']}%** | {job['titulo']} en *{job['empresa']}* - [🔗 Aplicar]({job['url']})")