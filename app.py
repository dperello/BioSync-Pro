import streamlit as st
import pandas as pd
import numpy as np
import plotly.graph_objects as go
from plotly.subplots import make_subplots
import fitparse
from scipy.stats import pearsonr
from datetime import datetime
import io
from fpdf import FPDF
from fpdf.enums import XPos, YPos

# 1. PAGE CONFIG & DESIGN
st.set_page_config(page_title="BioSync Pro - Advanced Drift & HRV", layout="wide")

def apply_custom_css():
    st.markdown("""
        <style>
        .main {
            background-color: #fcfdfe;
            color: #1a1c23;
        }
        .stMetric {
            background-color: #ffffff;
            padding: 20px;
            border-radius: 12px;
            border: 1px solid #e1e4e8;
            box-shadow: 0 4px 6px rgba(0,0,0,0.05);
            min-height: 120px;
        }
        .stMetric:hover {
            border: 1px solid #4361ee;
        }
        .drift-alert {
            background-color: #fff0f3;
            padding: 15px;
            border-radius: 12px;
            border: 2px solid #f72585;
            box-shadow: 0 4px 10px rgba(247, 37, 133, 0.1);
            min-height: 120px;
        }
        [data-testid="stSidebar"] {
            background-color: #f8f9fa;
            border-right: 1px solid #e1e4e8;
        }
        .diagnosis-box {
            background-color: #ffffff;
            padding: 20px;
            border-radius: 12px;
            border-left: 6px solid #4cc9f0;
            border: 1px solid #e1e4e8;
            border-left: 6px solid #4cc9f0;
            margin-bottom: 20px;
            box-shadow: 0 4px 6px rgba(0,0,0,0.05);
        }
        .drift-alert {
            background-color: #fff0f3;
            padding: 15px;
            border-radius: 12px;
            border: 2px solid #f72585;
            box-shadow: 0 4px 10px rgba(247, 37, 133, 0.1);
            min-height: 120px;
        }
        h1, h2, h3 {
            color: #1a1c23 !important;
            font-family: 'Outfit', sans-serif;
            font-weight: 700;
        }
        .stButton>button {
            border-radius: 8px;
            background-color: #4361ee;
            color: white;
        }
        </style>
    """, unsafe_allow_html=True)

apply_custom_css()

# 2. DATA PROCESSING (BACKEND)
@st.cache_data
def get_fit_data(uploaded_file):
    try:
        fit_file = fitparse.FitFile(uploaded_file)
        
        # Extract Records
        records = []
        for record in fit_file.get_messages('record'):
            r_data = record.get_values()
            records.append(r_data)
        
        df = pd.DataFrame(records)
        
        if df.empty:
            return None, None, None
            
        # Clean timestamps
        if 'timestamp' in df.columns:
            df['timestamp'] = pd.to_datetime(df['timestamp']).dt.tz_localize(None)
        
        # Conversions
        if 'enhanced_speed' in df.columns:
            # m/s to min/km
            df['pace'] = df['enhanced_speed'].apply(lambda x: (1000/60)/x if x > 0 else 0)
            df['speed_kmh'] = df['enhanced_speed'] * 3.6
        
        # Fill gaps
        df = df.infer_objects(copy=False).interpolate(method='linear').ffill().bfill()
        
        # Extract Laps
        laps = []
        for lap in fit_file.get_messages('lap'):
            l_data = lap.get_values()
            # Calculate robust end time
            if 'start_time' in l_data and 'total_elapsed_time' in l_data:
                s = pd.to_datetime(l_data['start_time']).tz_localize(None)
                l_data['start_time'] = s
                l_data['end_time'] = s + pd.Timedelta(seconds=l_data['total_elapsed_time'])
            elif 'timestamp' in l_data:
                l_data['end_time'] = pd.to_datetime(l_data['timestamp']).tz_localize(None)
                if 'start_time' in l_data:
                    l_data['start_time'] = pd.to_datetime(l_data['start_time']).tz_localize(None)
            
            laps.append(l_data)
        
        # Extract HRV (RR Intervals) with approximate timestamps
        hrv_data = []
        start_ts = df['timestamp'].min() if not df.empty else None
        curr_offset = 0
        
        for hrv in fit_file.get_messages('hrv'):
            rrs = hrv.get_value('time')
            if rrs:
                if not isinstance(rrs, (list, tuple)):
                    rrs = [rrs]
                for rr in rrs:
                    if rr is not None:
                        # rr is in ms or 1/1000s usually
                        # we skip very large values (gaps)
                        if rr < 3000: 
                            hrv_data.append({
                                'timestamp': start_ts + pd.Timedelta(milliseconds=curr_offset) if start_ts else None,
                                'rr': rr
                            })
                            curr_offset += rr # rr is usually in ms
        
        hrv_df = pd.DataFrame(hrv_data)
        if not hrv_df.empty and hrv_df['timestamp'].isnull().any():
             # fallback if no start_ts
             hrv_df = pd.DataFrame()
        
        # Extract User Profile & Session Stats
        user_profile = {}
        for up in fit_file.get_messages('user_profile'):
            user_profile = up.get_values()
            break
            
        session_stats = {}
        for s in fit_file.get_messages('session'):
            session_stats = s.get_values()
            break

        return df, laps, hrv_df, user_profile, session_stats
    except Exception as e:
        st.error(f"Error processing file: {e}")
        return None, None, None, None, None

def calculate_nutrition(user, session, objective):
    """
    Calculates nutritional needs based on session intensity, user metrics, and objective.
    """
    weight = user.get('weight', 70) 
    hours = session.get('total_timer_time', 3600) / 3600
    calories = session.get('total_calories', 0)
    avg_hr = session.get('avg_heart_rate', 0)
    
    # Baseline CHO per hour
    cho_h = 45
    obj_tip = ""
    
    if objective == "Flexibilidad Metabólica":
        cho_h = 20 # Low CHO to force fat oxidation
        obj_tip = "🎯 Objetivo: Optimizar la oxidación de grasas. Mantén la ingesta de CHO baja durante la sesión."
    elif objective == "Trabajo Umbral (Tempo)":
        cho_h = 75
        obj_tip = "🎯 Objetivo: Mantener intensidad alta. Requiere alta disponibilidad de glucógeno."
    elif objective == "Ritmo Maratón":
        cho_h = 60
        obj_tip = "🎯 Objetivo: Simulación de carrera. Entrena tu sistema digestivo para absorber 60-80g/h."
    elif objective == "Intervalos VO2max":
        cho_h = 90
        obj_tip = "🎯 Objetivo: Máxima potencia. La glucosa es el combustible crítico aquí."
    elif objective == "Sesión Suave (Recuperación)":
        cho_h = 30
        obj_tip = "🎯 Objetivo: Flujo sanguíneo y recuperación. No te obsesiones con los CHO."
    elif objective == "Tirada Larga (Endurance)":
        cho_h = 60
        obj_tip = "🎯 Objetivo: Resistencia. El enfoque debe ser la hidratación constante y soporte energético."

    hydration = hours * 750 # Slightly more aggressive hydration
    total_cho = cho_h * hours
    recovery_prot = weight * 0.4
    
    return {
        "weight": weight,
        "height": user.get('height', 0),
        "total_cals": calories,
        "hydration": hydration,
        "cho_per_h": cho_h,
        "total_cho": total_cho,
        "protein": recovery_prot,
        "gender": user.get('gender', 'N/A'),
        "obj_tip": obj_tip
    }

# 3. PHYSIOLOGICAL ENGINE
def analyze_lap_physiology(lap_df, hrv_segment=None):
    if lap_df.empty or len(lap_df) < 10:
        return None
    
    # Split in halves
    mid = len(lap_df) // 2
    h1 = lap_df.iloc[:mid]
    h2 = lap_df.iloc[mid:]
    
    # Efficiency Factor (EF) = Speed (m/min) / HR
    # We use enhanced_speed (m/s) * 60
    def calc_ef(df_half):
        avg_hr = df_half['heart_rate'].mean()
        avg_speed = df_half['enhanced_speed'].mean() * 60
        if avg_hr > 0:
            return avg_speed / avg_hr
        return 0

    ef1 = calc_ef(h1)
    ef2 = calc_ef(h2)
    
    drift = 0
    if ef1 > 0:
        drift = ((ef1 - ef2) / ef1) * 100
    
    # Inference Engine
    explanations = []
    status = "Stable" # Default
    
    # Case A: Terrain
    if 'enhanced_altitude' in lap_df.columns:
        alt_diff = h2['enhanced_altitude'].mean() - h1['enhanced_altitude'].mean()
        if alt_diff > 5:
            explanations.append("⚠️ Deriva por Desnivel Positivo (Carga Externa).")
        elif alt_diff < -5:
            explanations.append("ℹ️ Desnivel negativo puede enmascarar la deriva.")
            
    # Case B: Intensity
    v1 = h1['enhanced_speed'].mean()
    v2 = h2['enhanced_speed'].mean()
    if v2 > v1 * 1.05:
        explanations.append("⚠️ Deriva por Aumento de Ritmo (Aceleración).")
    
    # Case C: Cadence Lock
    if 'cadence' in lap_df.columns:
        corr, _ = pearsonr(lap_df['cadence'], lap_df['heart_rate'])
        if corr > 0.95:
            explanations.append("⚠️ Posible Error de Sensor (Cadence Lock Detectado).")
            status = "Warning"

    # Case D: Pure Physiological
    if abs(v1 - v2) / (v1 + 0.001) < 0.03 and drift > 5:
        explanations.append("🔴 Deriva Cardíaca Real: Posible deshidratación, fatiga central o estrés térmico.")
        status = "Drift"
    
    if not explanations:
        if drift < 5:
            explanations.append("✅ Eficiencia cardiovascular estable.")
        else:
            explanations.append("🟡 Deriva observada sin causa mecánica clara.")

    # HRV Calculation (Simplified SDNN)
    neural_load = "N/A"
    if hrv_segment is not None and not hrv_segment.empty:
        # hrv_segment['rr'] is in seconds (or 1/1000s)
        # Garmin: rr is usually in units of 1/1000 s
        rr_ms = hrv_segment['rr'].values
        sdnn = np.std(rr_ms) 
        neural_load = f"{sdnn:.1f}ms (SDNN)"

    # FINAL CONCLUSIONS ENGINE
    conclusion = ""
    if drift < 3:
        conclusion = "🌟 Excelente estado de forma aeróbica. Tu corazón mantiene la eficiencia constante."
    elif drift < 5:
        conclusion = "✅ Buena estabilidad cardiovascular. Entrenamiento controlado y eficiente."
    elif drift < 10:
        conclusion = "⚠️ Deriva moderada. Considera revisar la hidratación o reducir ligeramente la intensidad en sesiones largas."
    else:
        conclusion = "🔴 Deriva crítica detectada. Es posible que estés sobreentrenando, deshidratado o bajo mucho estrés térmico."

    return {
        "drift": drift,
        "ef_delta": ef2 - ef1,
        "avg_hr": lap_df['heart_rate'].mean(),
        "avg_pace": lap_df['pace'].mean(),
        "explanation": " ".join(explanations),
        "status": status,
        "neural_load": neural_load,
        "conclusion": conclusion
    }

# 4. APP UI
st.title("🏃 BioSync Pro")
st.subheader("Advanced Drift & HRV Analytics")

with st.sidebar:
    st.header("⚙️ Configuración")
    uploaded_file = st.file_uploader("Subir archivo Garmin .FIT", type=["fit"])
    
    st.divider()
    st.markdown("""
    ### 🧠 Fundamentos Fisiológicos
    **BioSync Pro** analiza la eficiencia aeróbica mediante el **Desacople ($Pw:HR$)**.
    
    #### 🧬 Metodología Joe Friel
    Dividimos el esfuerzo en dos mitades y calculamos el **Efficiency Factor (EF)**:
    $$EF = \\frac{\\text{Velocidad (m/min)}}{\\text{FC Media}}$$
    
    El **Drift %** es la pérdida de eficiencia entre la primera mitad ($EF_1$) y la segunda ($EF_2$):
    $$\\text{Drift} = \\left( \\frac{EF_1 - EF_2}{EF_1} \\right) \\times 100$$
    
    ---
    #### 📚 Fuentes y Autores
    *   **[Joe Friel](https://joefrieltraining.com/):** Autor de *The Triathlete's Training Bible*. [[Twitter](https://twitter.com/jfriend)]
    *   **[Stephen Seiler](https://twitter.com/StephenSeiler):** Investigador líder en fisiología del ejercicio. [[ResearchGate](https://www.researchgate.net/profile/Stephen-Seiler)]
    *   **[Marco Altini](https://www.marcoaltini.com/):** Experto en HRV y Biofeedback. [[Twitter](https://twitter.com/altini_marco)]
    
    *Umbral crítico: > 5% indica fatiga o estrés térmico.*
    
    ---
    #### 👨‍💻 Autor
    **David Perelló**  
    📸 [Instagram: @davidoutdoorsports](https://www.instagram.com/davidoutdoorsports)  
    📧 [dperello33@gmail.com](mailto:dperello33@gmail.com)
    """)

if uploaded_file:
    df, laps, hrv_df, user_profile, session_stats = get_fit_data(uploaded_file)
    if df is not None:
        # 0. OBJECTIVE SELECTOR
        st.markdown("### 🎯 Objetivo de la Sesión")
        objectives = [
            "Flexibilidad Metabólica", 
            "Trabajo Umbral (Tempo)", 
            "Ritmo Maratón", 
            "Intervalos VO2max", 
            "Sesión Suave (Recuperación)", 
            "Tirada Larga (Endurance)"
        ]
        session_obj = st.selectbox("¿Qué buscabas hoy?", objectives, index=4)

        # 1. NUTRITION SECTION (TOP)
        nutrition = calculate_nutrition(user_profile, session_stats, session_obj)
        
        with st.container():
            st.markdown(f"""
                <div style="background-color: #f0f7ff; padding: 20px; border-radius: 12px; border: 1px solid #4361ee; margin-bottom: 25px;">
                    <div style="display: flex; justify-content: space-between; align-items: center;">
                        <h2 style="color: #4361ee; margin: 0;">🥗 Estrategia para {session_obj}</h2>
                        <span style="background: #4361ee; color: white; padding: 4px 12px; border-radius: 20px; font-size: 0.8rem;">Perfil: {nutrition['gender'].capitalize()} | {nutrition['weight']}kg | {nutrition['height']}m</span>
                    </div>
                    <div style="display: grid; grid-template-columns: repeat(4, 1fr); gap: 15px; margin-top: 20px;">
                        <div style="text-align: center;">
                            <p style="margin:0; color: #666; font-size: 0.9rem;">Gasto Energía</p>
                            <h3 style="margin:0; color: #1a1c23;">{nutrition['total_cals']} kcal</h3>
                        </div>
                        <div style="text-align: center;">
                            <p style="margin:0; color: #666; font-size: 0.9rem;">Hidratación Objetivo</p>
                            <h3 style="margin:0; color: #1a1c23;">{nutrition['hydration']:.0f} ml</h3>
                        </div>
                        <div style="text-align: center;">
                            <p style="margin:0; color: #666; font-size: 0.9rem;">Carbohidratos</p>
                            <h3 style="margin:0; color: #1a1c23;">{nutrition['cho_per_h']} g/hora</h3>
                        </div>
                        <div style="text-align: center;">
                            <p style="margin:0; color: #666; font-size: 0.9rem;">Proteína Recovery</p>
                            <h3 style="margin:0; color: #1a1c23;">{nutrition['protein']:.0f} g</h3>
                        </div>
                    </div>
                    <p style="margin-top: 15px; font-size: 0.95rem; color: #1a1c23; background: #e0eeff; padding: 10px; border-radius: 5px;">{nutrition['obj_tip']}</p>
                </div>
            """, unsafe_allow_html=True)

        # 2. LAP SELECTION
        st.markdown("### 🏁 Selección de Segmento")
        lap_options = ["Vista Global"] + [f"Lap {i+1} ({l.get('total_distance', 0)/1000:.2f}km)" for i, l in enumerate(laps)]
        selected_lap_idx = st.radio("Elige un lap para el análisis detallado:", range(len(lap_options)), format_func=lambda x: lap_options[x], horizontal=True)
    else:
        st.error("No valid data found.")

if uploaded_file and df is not None:
    # Filter Data based on selection
    if selected_lap_idx == 0:
        plot_df = df
        analysis = analyze_lap_physiology(df, hrv_df) # Global check
        title = "Global Activity Analysis"
    else:
        lap = laps[selected_lap_idx - 1]
        
        # We already computed start_time and end_time in get_fit_data
        start = lap.get('start_time')
        end = lap.get('end_time')

        # Apply slice
        plot_df = df[(df['timestamp'] >= start) & (df['timestamp'] <= end)].copy()

        # WIDE SEARCH FALLBACK: If strict slice fails, try to find nearest records
        if plot_df.empty and not df.empty:
            # Maybe there is a timezone offset between Laps and Records (common in some Garmin exports)
            # We try to align based on relative time if absolute fails
            data_start = df['timestamp'].min()
            lap_offset = (start - data_start).total_seconds() if start else 0
            # This is complex, let's try a simpler approach: check if data covers the total duration
            pass

        # DEBUG (Hidden in expander if it fails)
        if plot_df.empty:
            with st.expander("🛠 Diagnostic: Lap slice failed"):
                st.write(f"Lap Start: {start}")
                st.write(f"Lap End: {end}")
                st.write(f"Records Min: {df['timestamp'].min()}")
                st.write(f"Records Max: {df['timestamp'].max()}")
                st.info("The timestamps in your file for Laps don't seem to overlap with the data points. This often happens due to timezone mismatches.")
        
        # Slice HRV
        if hrv_df is not None and not hrv_df.empty:
            lap_hrv = hrv_df[(hrv_df['timestamp'] >= start) & (hrv_df['timestamp'] <= end)]
        else:
            lap_hrv = None
            
        analysis = analyze_lap_physiology(plot_df, lap_hrv)
        title = f"Analysis: Lap {selected_lap_idx}"

    if analysis:
        # KPI Row
        col1, col2, col3, col4 = st.columns(4)
        col1.metric("FC Media", f"{analysis['avg_hr']:.0f} bpm")
        
        pace_min = int(analysis['avg_pace'])
        pace_sec = int((analysis['avg_pace'] - pace_min) * 60)
        col2.metric("Ritmo Medio", f"{pace_min}:{pace_sec:02d} /km")
        
        # Color coding for drift
        drift_val = analysis['drift']
        drift_label = f"{drift_val:.1f}%"
        
        if drift_val > 5:
            col3.markdown(f"""
                <div class="drift-alert">
                    <p style='margin:0; font-size: 0.85rem; color: #f72585; font-weight: 600;'>⚠️ CARDIAC DRIFT</p>
                    <h2 style='margin:0; color: #f72585; font-size: 2rem;'>{drift_label}</h2>
                </div>
            """, unsafe_allow_html=True)
        else:
            col3.metric("Cardiac Drift", drift_label)
        
        col4.metric("Neural Load (HRV)", analysis['neural_load'])

        # Diagnosis Box
        diag_class = "diagnosis-box" if analysis['drift'] < 5 else "diagnosis-box diagnosis-error"
        st.markdown(f"""
            <div class="{diag_class}">
                <h3>🔍 Fisiological Diagnosis</h3>
                <p style='font-size: 1.2rem;'>{analysis['explanation']}</p>
            </div>
        """, unsafe_allow_html=True)

        # Plotly Chart
        fig = make_subplots(specs=[[{"secondary_y": True}]])

        # HR Trace
        fig.add_trace(
            go.Scatter(x=plot_df['timestamp'], y=plot_df['heart_rate'], name="Heart Rate", line=dict(color='#f72585', width=2)),
            secondary_y=False,
        )

        # Pace Trace (inverted for logic)
        fig.add_trace(
            go.Scatter(x=plot_df['timestamp'], y=plot_df['pace'], name="Pace", line=dict(color='#4361ee', width=1, dash='dot')),
            secondary_y=True,
        )

        # Background indicator
        bg_color = "rgba(76, 201, 240, 0.1)" if analysis['drift'] < 5 else "rgba(247, 37, 133, 0.1)"
        fig.add_vrect(
            x0=plot_df['timestamp'].min(), x1=plot_df['timestamp'].max(),
            fillcolor=bg_color, layer="below", line_width=0,
        )

        fig.update_layout(
            title=dict(text=title, font=dict(color="#1a1c23", size=24)),
            paper_bgcolor='white',
            plot_bgcolor='white',
            xaxis=dict(gridcolor='#f0f0f0', title="Time", tickfont=dict(color="#666")),
            legend=dict(font=dict(color="#333"), bgcolor="rgba(255,255,255,0.8)"),
            margin=dict(l=20, r=20, t=60, b=20),
            hovermode="x unified"
        )
        
        fig.update_yaxes(title_text="Heart Rate (bpm)", secondary_y=False, gridcolor='#f0f0f0', tickfont=dict(color="#f72585"), range=[plot_df['heart_rate'].min()-5, plot_df['heart_rate'].max()+10])
        fig.update_yaxes(title_text="Pace (min/km)", secondary_y=True, autorange="reversed", tickfont=dict(color="#4361ee"))

        st.plotly_chart(fig, use_container_width=True)

        # 5. FINAL CONCLUSIONS CARD
        st.markdown(f"""
            <div style="background-color: #f8f9fa; padding: 25px; border-radius: 12px; border: 1px solid #e1e4e8; margin-top: 20px;">
                <h2 style="color: #4361ee; margin-top:0;">📋 Conclusiones del Análisis</h2>
                <p style="font-size: 1.1rem; line-height: 1.6;">{analysis['conclusion']}</p>
                <i style="color: #666; font-size: 0.9rem;">Analizado mediante motores BioSync Pro v1.2</i>
            </div>
        """, unsafe_allow_html=True)

        # 6. REPORT GENERATOR
        st.divider()
        st.subheader("📄 Generar Informe de Sesión")
        
        def clean_text(text):
            """Removes emojis and special chars that FPDF core fonts can't handle."""
            if not text: return ""
            # Simple approach: keep only latin-1 compatible chars or replace emojis
            return text.encode("latin-1", "ignore").decode("latin-1")

        def generate_pdf_report():
            pdf = FPDF()
            pdf.add_page()
            pdf.set_font("Helvetica", "B", 16)
            
            # Header
            pdf.cell(0, 10, clean_text("Informe Fisiológico BioSync Pro"), new_x=XPos.LMARGIN, new_y=YPos.NEXT, align="C")
            pdf.set_font("Helvetica", "", 10)
            pdf.cell(0, 5, f"Fecha: {datetime.now().strftime('%Y-%m-%d %H:%M')}", new_x=XPos.LMARGIN, new_y=YPos.NEXT, align="R")
            pdf.cell(0, 5, f"Actividad: {clean_text(uploaded_file.name)}", new_x=XPos.LMARGIN, new_y=YPos.NEXT, align="R")
            pdf.ln(10)
            
            # 1. Nutrition & Profile
            pdf.set_font("Helvetica", "B", 14)
            pdf.set_fill_color(240, 247, 255)
            pdf.cell(0, 10, clean_text(f"1. Perfil y Estrategia: {session_obj}"), new_x=XPos.LMARGIN, new_y=YPos.NEXT, fill=True)
            pdf.set_font("Helvetica", "", 11)
            pdf.ln(2)
            pdf.cell(0, 7, f"Perfil: {clean_text(nutrition['gender']).capitalize()} | {nutrition['weight']}kg | {nutrition['height']}m", new_x=XPos.LMARGIN, new_y=YPos.NEXT)
            pdf.cell(0, 7, f"Gasto Energético: {nutrition['total_cals']} kcal", new_x=XPos.LMARGIN, new_y=YPos.NEXT)
            pdf.cell(0, 7, f"Hidratación Necesaria: {nutrition['hydration']:.0f} ml", new_x=XPos.LMARGIN, new_y=YPos.NEXT)
            pdf.cell(0, 7, f"Objetivo CHO: {nutrition['cho_per_h']} g/hora", new_x=XPos.LMARGIN, new_y=YPos.NEXT)
            pdf.cell(0, 7, f"Proteína Recuperación: {nutrition['protein']:.1f} g", new_x=XPos.LMARGIN, new_y=YPos.NEXT)
            pdf.ln(5)
            
            # 2. Main Analysis (Selected Segment)
            pdf.set_font("Helvetica", "B", 14)
            pdf.set_fill_color(248, 249, 250)
            pdf.cell(0, 10, clean_text(f"2. Análisis del Segmento: {title}"), new_x=XPos.LMARGIN, new_y=YPos.NEXT, fill=True)
            pdf.set_font("Helvetica", "", 11)
            pdf.ln(2)
            pdf.cell(0, 7, f"FC Media: {analysis['avg_hr']:.0f} bpm", new_x=XPos.LMARGIN, new_y=YPos.NEXT)
            pm = int(analysis['avg_pace'])
            ps = int((analysis['avg_pace'] - pm) * 60)
            pdf.cell(0, 7, f"Ritmo Medio: {pm}:{ps:02d} min/km", new_x=XPos.LMARGIN, new_y=YPos.NEXT)
            pdf.cell(0, 7, f"Cardiac Drift: {analysis['drift']:.2f}%", new_x=XPos.LMARGIN, new_y=YPos.NEXT)
            pdf.cell(0, 7, f"Carga Neural (HRV): {clean_text(analysis['neural_load'])}", new_x=XPos.LMARGIN, new_y=YPos.NEXT)
            pdf.ln(5)
            
            # 3. Conclusions
            pdf.set_font("Helvetica", "B", 14)
            pdf.cell(0, 10, clean_text("3. Diagnóstico y Conclusiones"), new_x=XPos.LMARGIN, new_y=YPos.NEXT)
            pdf.set_font("Helvetica", "I", 11)
            pdf.multi_cell(0, 7, clean_text(analysis['explanation']))
            pdf.ln(2)
            pdf.set_font("Helvetica", "B", 11)
            pdf.multi_cell(0, 7, clean_text(f"Conclusión Final: {analysis['conclusion']}"))
            pdf.ln(10)
            
            # 4. Table of ALL Laps
            if len(laps) > 0:
                pdf.set_font("Helvetica", "B", 14)
                pdf.cell(0, 10, clean_text("4. Desglose detallado de todos los Laps"), new_x=XPos.LMARGIN, new_y=YPos.NEXT)
                pdf.ln(2)
                
                # Table Header
                pdf.set_font("Helvetica", "B", 10)
                pdf.set_fill_color(200, 220, 255)
                pdf.cell(20, 10, "Lap", 1, 0, "C", True)
                pdf.cell(40, 10, "Distancia", 1, 0, "C", True)
                pdf.cell(40, 10, "Duración", 1, 0, "C", True)
                pdf.cell(40, 10, "FC Media", 1, 0, "C", True)
                pdf.cell(40, 10, "Drift %", 1, 1, "C", True)
                
                pdf.set_font("Helvetica", "", 10)
                for i, l in enumerate(laps):
                    l_start = l.get('start_time')
                    l_end = l.get('end_time')
                    l_df = df[(df['timestamp'] >= l_start) & (df['timestamp'] <= l_end)]
                    l_analysis = analyze_lap_physiology(l_df)
                    
                    if l_analysis:
                        dist = l.get('total_distance', 0) / 1000
                        dur_sec = l.get('total_elapsed_time', 0)
                        mm, ss = divmod(int(dur_sec), 60)
                        
                        pdf.cell(20, 8, str(i+1), 1, 0, "C")
                        pdf.cell(40, 8, f"{dist:.2f} km", 1, 0, "C")
                        pdf.cell(40, 8, f"{mm}:{ss:02d}", 1, 0, "C")
                        pdf.cell(40, 8, f"{l_analysis['avg_hr']:.0f} bpm", 1, 0, "C")
                        pdf.cell(40, 8, f"{l_analysis['drift']:.2f}%", 1, 1, "C")
                
            # Footer / Authors
            pdf.ln(10)
            pdf.set_font("Helvetica", "I", 9)
            pdf.cell(0, 5, "Basado en metodologías de Joe Friel, Stephen Seiler y Marco Altini.", new_x=XPos.LMARGIN, new_y=YPos.NEXT, align="C")
            pdf.cell(0, 5, "Generado por BioSync Pro - Advanced Drift & HRV Analytics", new_x=XPos.LMARGIN, new_y=YPos.NEXT, align="C")
            
            # Critical: Use BytesIO to get actual bytes
            buffer = io.BytesIO()
            pdf.output(buffer)
            return buffer.getvalue()

        pdf_bytes = generate_pdf_report()
        st.download_button(
            label="📥 Descargar Informe Completo (PDF)",
            data=pdf_bytes,
            file_name=f"BioSync_Report_{datetime.now().strftime('%Y%m%d_%H%M')}.pdf",
            mime="application/pdf"
        )

    else:
        st.warning(f"No hay suficientes datos en este segmento ({len(plot_df)} puntos). Se requiere un mínimo de 10 para el análisis fisiológico.")
        if not plot_df.empty:
            st.info("Sugerencia: Si el lap es corto o el sensor falló, intenta analizar la actividad completa.")

else:
    # Landing Page / No file state
    st.info("👋 Welcome to BioSync Pro. Please upload a .FIT file to begin the physiological analysis.")
    # Show a placeholder image or design
    st.markdown("""
    ### 🧠 Physiological Foundation
    This app uses the **Joe Friel Decoupling (Pw:HR)** methodology. 
    
    *   **Efficiency Factor (EF)**: Ratio of output (Normalized Speed) to input (Heart Rate).
    *   **Cardiac Drift**: The percentage loss of efficiency between the first and second half of a steady-state effort.
    *   **Interpretation**: Drift < 5% indicates good aerobic fitness for the intensity. > 5% indicates physiological strain (heat, dehydration, or fatigue).
    
    ---
    Developed by **David Perelló** | [Instagram @davidoutdoorsports](https://www.instagram.com/davidoutdoorsports) | dperello33@gmail.com
    """)
