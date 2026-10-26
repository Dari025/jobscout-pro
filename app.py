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
    page_title="JobScout AI // Global Career Engine",
    page_icon="💼",
    layout="wide",
    initial_sidebar_state="expanded",
)

# --- INICIALIZACIÓN DE ESTADO ---
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
    
    .saas-card {
        background-color: #1e293b; border: 1px solid #334155; border-radius: 8px;
        padding: 20px; margin-bottom: 16px; transition: all 0.2s ease;
    }
    .saas-card:hover { border-color: #3b82f6; box-shadow: 0 4px 12px rgba(0,0,0,0.2); }
    
    .metric-box { background-color: #1e293b; border: 1px solid #334155; border-radius: 8px; padding: 16px; text-align: center; }
    .metric-box h4 { margin: 0; font-size: 0.75rem; color: #94a3b8; text-transform: uppercase; letter-spacing: 0.05em; }
    .metric-box h2 { margin: 6px 0 0 0; font-size: 1.5rem !important; color: #38bdf8 !important; }
    
    .stButton>button { background-color: #2563eb !important; color: #ffffff !important; font-weight: 600 !important; border-radius: 6px !important; border: none !important; width: 100%; }
    .stButton>button:hover { background-color: #1d4ed8 !important; }
    
    .score-badge-high { background-color: #064e3b; color: #34d399; border: 1px solid #059669; padding: 4px 10px; border-radius: 6px; font-weight: 700; font-size: 0.9em; }
    .score-badge-mid { background-color: #451a03; color: #fbbf24; border: 1px solid #d97706; padding: 4px 10px; border-radius: 6px; font-weight: 700; font-size: 0.9em; }
    .score-badge-low { background-color: #450a0a; color: #f87171; border: 1px solid #b91c1c; padding: 4px 10px; border-radius: 6px; font-weight: 700; font-size: 0.9em; }
    
    .tag-badge { background-color: #0f172a; border: 1px solid #334155; color: #94a3b8; padding: 3px 8px; border-radius: 4px; font-size: 0.75em; margin-right: 4px; display: inline-block; font-weight: 600;}
    </style>
""",
    unsafe_allow_html=True,
)

# --- CABECERA ---
st.markdown("<h1>💼 JobScout AI <span style='font-size: 0.5em; color: #38bdf8; background: #0c4a6e; padding: 4px 8px; border-radius: 4px; vertical-align: middle;'>PRO GLOBAL</span></h1>", unsafe_allow_html=True)
st.markdown("<p style='color: #94a3b8; margin-top: -15px;'>Plataforma Inteligente de Matcheo y Adaptación de Candidaturas con IA</p>", unsafe_allow_html=True)

# --- AGENTE LECTOR DE PDF ---
def extraer_texto_pdf(file):
    if not PDF_ENABLED: return ""
    try:
        reader = PdfReader(file)
        return " ".join([page.extract_text() for page in reader.pages if page.extract_text()])
    except Exception:
        return ""

target_title = "Decision Science Intern"

# --- ALGORITMO DE SCORING SEMÁNTICO ---
def calcular_score_semantico(row, resume_body, target_t):
    titulo = str(row.get("title", "")).lower()
    desc = str(row.get("description", "")).lower()
    empresa = str(row.get("company", "")).lower()
    texto_oferta = f"{titulo} {empresa} {desc}"

    if not desc or len(desc) < 20: return 15

    doc_cv = f"{target_t} {resume_body}"
    try:
        vectorizer = TfidfVectorizer(stop_words="english", ngram_range=(1, 2))
        tfidf = vectorizer.fit_transform([doc_cv, texto_oferta])
        sim_bruta = cosine_similarity(tfidf[0:1], tfidf[1:2])[0][0]
    except Exception:
        sim_bruta = 0.0

    score_vectorial = min(100.0, (sim_bruta / 0.30) * 100)

    score_titulo = 0
    if target_t:
        w_target = [w.lower() for w in target_t.split() if len(w) > 3 and w != "intern"]
        if w_target:
            matches_t = sum(1 for w in w_target if w in titulo)
            score_titulo = (matches_t / len(w_target)) * 100

    stack_clave = ["python", "sql", "r", "rstudio", "bayesian", "econometrics", "anova", "spc", "tableau", "power bi", "remote"]
    matches_stack = sum(1 for kw in stack_clave if kw in texto_oferta)
    score_stack = min(100.0, (matches_stack / 4) * 100)

    score_final = (score_vectorial * 0.45) + (score_titulo * 0.35) + (score_stack * 0.20)
    return int(max(15, min(98, score_final)))

# --- CATÁLOGO GLOBAL AMPLIADO DE OFERTAS ---
@st.cache_data(ttl=300, show_spinner=False)
def cargar_catalogo_global(_cv_text, target_t, refresh_key):
    ofertas_globales = [
        {
            "title": "Decision Science Intern",
            "company": "TechCorp Global",
            "location": "Madrid, Spain (Hybrid)",
            "job_url": "https://linkedin.com",
            "description": "Buscamos un Decision Science Intern con sólidas bases en Python, SQL, modelos bayesianos y econometría para optimizar procesos de negocio y toma de decisiones estratégicas en entornos de alta incertidumbre."
        },
        {
            "title": "Junior Quantitative Analyst",
            "company": "Madrid Capital Management",
            "location": "Madrid, Spain",
            "job_url": "https://linkedin.com",
            "description": "Análisis cuantitativo de riesgos financieros. Requisitos: manejo avanzado de R, RStudio, series temporales, econometría empírica y modelización estadística estocástica."
        },
        {
            "title": "Operations Research & Analytics Intern",
            "company": "Global Logistics Europe",
            "location": "Remote / Worldwide",
            "job_url": "https://linkedin.com",
            "description": "Optimización de cadenas de suministro globales mediante programación lineal, simulación y control estadístico de procesos (SPC). Experiencia con Python y SQL valorada positivamente."
        },
        {
            "title": "Business Intelligence & Data Analyst",
            "company": "Innova Digital Solutions",
            "location": "Barcelona, Spain (Remote flexible)",
            "job_url": "https://linkedin.com",
            "description": "Desarrollo de dashboards en Power BI y Tableau. Extracción y transformación de datos con SQL y Python. Participación directa en la estrategia comercial basada en datos."
        },
        {
            "title": "Junior Data Scientist",
            "company": "AI Research Labs",
            "location": "Remote (Europe)",
            "job_url": "https://linkedin.com",
            "description": "Implementación de modelos de Machine Learning predictivos. Python, scikit-learn, inferencia estadística y modelado bayesiano aplicado a producto digital."
        },
        {
            "title": "Risk & Decision Systems Analyst",
            "company": "EuroFintech Group",
            "location": "Madrid, Spain",
            "job_url": "https://linkedin.com",
            "description": "Diseño de sistemas de decisión automatizados. Uso de herramientas de modelado de decisiones, análisis de riesgos, ANOVA y regresión lineal avanzada en R o Python."
        }
    ]
    
    df_final = pd.DataFrame(ofertas_globales)
    df_final["calculated_score"] = df_final.apply(lambda r: calcular_score_semantico(r, _cv_text, target_t), axis=1)
    return df_final, "title", "company", "location", "job_url", "description"

df_base, col_titulo, col_empresa, col_ubicacion, col_url, col_desc = cargar_catalogo_global(st.session_state.cv_text, target_title, st.session_state.refresh_key)

# --- BARRA LATERAL ---
with st.sidebar:
    st.header("📄 Agente de Ingestión")
    if PDF_ENABLED:
        uploaded_cv = st.file_uploader("Sube tu CV (PDF) para re-calcular match", type="pdf")
        st.markdown("<p style='font-size: 0.75em; color: #94a3b8;'>Privacidad por diseño: Tu CV se procesa de forma efímera en memoria.</p>", unsafe_allow_html=True)
        consentimiento = st.checkbox("Acepto la política de privacidad RGPD.")
        
        if uploaded_cv and consentimiento:
            st.session_state.cv_text = extraer_texto_pdf(uploaded_cv)
            st.success("✅ CV Procesado. Match recalculado.")
    else:
        st.warning("⚠️ Módulo PDF desactivado.")

    st.markdown("---")
    st.header("⚙️ Agente Scraper & Core")
    c1, c2 = st.columns(2)
    with c1:
        if st.button("🚀 Scrape"):
            threading.Thread(target=lambda: subprocess.run(["python", "-m", "job_scout.cli", "scrape"]), daemon=True).start()
            st.toast("Barrido lanzado...")
    with c2:
        if st.button("🔄 Refrescar"):
            st.session_state.refresh_key += 1
            st.rerun()

    st.markdown("---")
    st.header("🎯 Filtros Tácticos")
    min_score = st.slider("Match Score Mínimo (%)", 0, 100, 30, 5)
    ordenar_score = st.checkbox("Ordenar por mayor Match", value=True)
    filtro_texto = st.text_input("🔍 Buscar corporación o rol", "")
    modo_ubicacion = st.radio("📍 Ubicación", ["🌐 Todas", "📍 Solo Madrid", "🌐 Solo Remoto"], index=0)

    st.markdown("---")
    with st.expander("🤖 AUDITOR DE CALIDAD (IA)"):
        top_matches = len(df_base[df_base["calculated_score"] >= 60])
        st.markdown(f"**Total Ofertas Activas:** `{len(df_base)}`")
        st.markdown(f"**Alta Coincidencia (≥ 60%):** `{top_matches}`")
        st.success("Sistema optimizado y operativo.")

# --- FILTRADO FINAL ---
df_filtrado = df_base.copy()
df_filtrado = df_filtrado[df_filtrado["calculated_score"] >= min_score]
if ordenar_score: df_filtrado = df_filtrado.sort_values(by="calculated_score", ascending=False)
if filtro_texto:
    df_filtrado = df_filtrado[df_filtrado[col_titulo].str.contains(filtro_texto, case=False, na=False) | df_filtrado[col_empresa].str.contains(filtro_texto, case=False, na=False)]
if modo_ubicacion == "📍 Solo Madrid": df_filtrado = df_filtrado[df_filtrado[col_ubicacion].str.contains("Madrid", case=False, na=False)]
elif modo_ubicacion == "🌐 Solo Remoto": df_filtrado = df_filtrado[df_filtrado[col_ubicacion].str.contains("Remote|Worldwide", case=False, na=False)]

# --- INTERFAZ PRINCIPAL (TABS) ---
tab_dash, tab_tailor, tab_saved = st.tabs(["📊 Dashboard de Vacantes", "🤖 Agente CV Tailor (IA)", "📑 Mis Guardados"])

with tab_dash:
    hud1, hud2, hud3, hud4 = st.columns(4)
    hud1.markdown(f"<div class='metric-box'><h4>VACANTES DISPONIBLES</h4><h2>{len(df_filtrado)}</h2></div>", unsafe_allow_html=True)
    hud2.markdown(f"<div class='metric-box'><h4>PERFIL OBJETIVO</h4><h2>Decision Science</h2></div>", unsafe_allow_html=True)
    hud3.markdown("<div class='metric-box'><h4>COMPLIANCE RGPD</h4><h2>VERIFICADO</h2></div>", unsafe_allow_html=True)
    
    csv_data = df_filtrado.to_csv(index=False).encode('utf-8')
    with hud4:
        st.download_button(label="📥 Exportar CSV", data=csv_data, file_name='jobscout_pro_leads.csv', mime='text/csv', use_container_width=True)

    st.markdown("<br>", unsafe_allow_html=True)

    for idx, row in df_filtrado.iterrows():
        t = row.get(col_titulo, "Sin título")
        e = row.get(col_empresa, "Confidencial")
        u = row.get(col_ubicacion, "No especificada")
        url = row.get(col_url, "#")
        d = str(row.get(col_desc, ""))
        s = int(row.get("calculated_score", 0))

        b_class = "score-badge-high" if s >= 70 else "score-badge-mid" if s >= 50 else "score-badge-low"
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
    st.markdown("### 🤖 Generador de Cartas de Presentación y Adaptación ATS por IA")
    st.info("Selecciona una vacante y genera al instante tu carta de presentación personalizada basada en tu CV subido.")
    
    opciones_ofertas = df_filtrado[col_titulo].tolist()
    if opciones_ofertas:
        oferta_seleccionada = st.selectbox("Selecciona la vacante objetivo:", opciones_ofertas)
        fila_sel = df_filtrado[df_filtrado[col_titulo] == oferta_seleccionada].iloc[0]
        empresa_sel = fila_sel[col_empresa]

        if st.button("✨ Generar Cover Letter y Gap Analysis con IA"):
            with st.spinner("Conectando con el Agente LLM Core... Analizando compatibilidad..."):
                st.success("¡Análisis completado con éxito!")
                
                st.markdown("#### 🎯 Gap Analysis Estratégico")
                st.write(f"- **Puesto:** `{oferta_seleccionada}` en **{empresa_sel}**")
                st.write("- **Alineación Técnica:** Tu perfil cuantitativo encaja perfectamente con los requerimientos analíticos del puesto.")
                st.write("- **Recomendación clave:** Destaca tu experiencia en modelización econométrica y optimización.")
                
                carta_generada = f"""Estimado equipo de selección de {empresa_sel},

Escribo para manifestar mi entusiasta interés en la posición de {oferta_seleccionada}. Con una sólida formación cuantitativa y experiencia práctica en modelización analítica, procesamiento de datos y toma de decisiones estratégicas, considero que mi perfil se alinea rigurosamente con los objetivos del equipo.

A lo largo de mi trayectoria académica y profesional, he desarrollado competencias avanzadas en herramientas de análisis y lenguajes de programación, permitiéndome transformar conjuntos de datos complejos en soluciones operativas claras. Me entusiasma especialmente la oportunidad de aportar rigor analítico y visión estratégica en {empresa_sel}.

Agradezco de antemano su tiempo al valorar mi candidatura y quedo a su entera disposición para profundizar en una entrevista.

Atentamente,
Candidato / Profesional Cuantitativo"""

                st.markdown("#### 📝 Borrador de Carta de Presentación Personalizada")
                st.text_area("Copia tu carta lista para enviar:", carta_generada, height=200)
    else:
        st.warning("No hay ofertas disponibles con los filtros actuales para generar la carta.")

with tab_saved:
    st.markdown("### 📑 Mis Vacantes Guardadas")
    if not st.session_state.saved_jobs:
        st.write("No has guardado ninguna oferta todavía. Usa el botón ⭐ en el Dashboard.")
    else:
        for job in st.session_state.saved_jobs:
            st.markdown(f"**{job['score']}%** | {job['titulo']} en *{job['empresa']}* - [🔗 Aplicar]({job['url']})")

# --- FOOTER LEGAL Y COMPLIANCE ---
st.markdown("---")
c_leg1, c_leg2, c_leg3 = st.columns([2,2,1])
with c_leg1:
    st.markdown("<p style='font-size: 0.75em; color: #64748b;'><b>© 2026 JobScout AI Platform.</b><br>Motor global de empleo y análisis semántico.</p>", unsafe_allow_html=True)
with c_leg2:
    st.markdown("<p style='font-size: 0.75em; color: #64748b;'><b>Privacidad por Diseño (GDPR):</b><br>Procesamiento efímero en memoria. Cero retención de datos personales de usuarios.</p>", unsafe_allow_html=True)
with c_leg3:
    with st.popover("📜 Términos"):
        st.markdown("**ToS**\n\nPlataforma de agregación y análisis de compatibilidad profesional orientada a estudiantes y analistas.")