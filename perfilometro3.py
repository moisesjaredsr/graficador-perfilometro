import streamlit as st
import pandas as pd
import xml.etree.ElementTree as ET
import io
import plotly.express as px
import plotly.graph_objects as go

# Configuración de la página
st.set_page_config(page_title="Analizador de Perfilómetro", layout="wide")

st.title("MJ Visualizador de Datos de Perfilómetro")

# --- FUNCIONES DE SOPORTE ---

def parse_profilometer_data(uploaded_file):
    """Lee el archivo 'txt' con estructura XML."""
    try:
        uploaded_file.seek(0)
        tree = ET.parse(uploaded_file)
        root = tree.getroot()
        
        data_points = []
        for data in root.findall('.//Data'):
            x_val = float(data.find('X').text)
            z_val = float(data.find('Z').text)
            data_points.append({'X': x_val, 'Z': z_val})
            
        return pd.DataFrame(data_points)
    except Exception as e:
        st.error(f"Error leyendo {uploaded_file.name}: {e}")
        return None

def generate_combined_excel(data_dict, chart_title="Comparativa General"):
    """
    Genera un Excel con TODAS las series y una gráfica combinada.
    data_dict: Diccionario {'nombre_archivo': dataframe}
    """
    output = io.BytesIO()
    with pd.ExcelWriter(output, engine='xlsxwriter') as writer:
        workbook = writer.book
        sheet_name = 'Datos Combinados'
        worksheet = workbook.add_worksheet(sheet_name)
        
        # Crear objeto de gráfica
        chart = workbook.add_chart({'type': 'scatter', 'subtype': 'straight'})
        
        # Escribir datos columna por columna (Lado a lado)
        col_idx = 0
        
        for name, df in data_dict.items():
            # Escribir encabezados
            worksheet.write(0, col_idx, f"X - {name}")
            worksheet.write(0, col_idx + 1, f"Z - {name}")
            
            # Escribir datos
            for row_num, (x, z) in enumerate(zip(df['X'], df['Z'])):
                worksheet.write(row_num + 1, col_idx, x)
                worksheet.write(row_num + 1, col_idx + 1, z)
            
            # Agregar serie a la gráfica
            max_row = len(df)
            chart.add_series({
                'name':       name,
                'categories': [sheet_name, 1, col_idx, max_row, col_idx],     # Eje X
                'values':     [sheet_name, 1, col_idx + 1, max_row, col_idx + 1], # Eje Y
                'line':       {'width': 1.25},
            })
            
            col_idx += 2 # Mover 2 columnas a la derecha para el siguiente archivo

        # Configuración final de la gráfica Excel
        chart.set_title({'name': chart_title})
        chart.set_x_axis({'name': 'Eje X'})
        chart.set_y_axis({'name': 'Eje Z'})
        
        # Insertar gráfica grande en el Excel
        worksheet.insert_chart('A10', chart, {'x_scale': 2.5, 'y_scale': 2.5})
        
    return output.getvalue()

def generate_single_excel(df, filename):
    """Genera Excel para un solo archivo (función legacy mejorada)."""
    # Reutilizamos la lógica del combinado pero pasando solo uno
    return generate_combined_excel({filename: df}, chart_title=f"Gráfica de {filename}")

# --- INTERFAZ PRINCIPAL ---

# 1. Carga de Archivos
uploaded_files = st.file_uploader("Sube tus archivos .txt aquí", 
                                  type=['txt', 'xml'], 
                                  accept_multiple_files=True)

if uploaded_files:
    # --- PRE-PROCESAMIENTO ---
    # Leemos todos los archivos primero para poder hacer la gráfica general
    all_data = {} # Diccionario para guardar nombre -> dataframe
    
    for up_file in uploaded_files:
        df = parse_profilometer_data(up_file)
        if df is not None:
            all_data[up_file.name] = df

    if all_data:
        st.divider()
        
        # --- SECCIÓN 1: GRÁFICA GENERAL Y PERSONALIZACIÓN ---
        st.subheader("📊 Gráfica General Comparativa")
        
        # Controles de Personalización
        with st.expander("🎨 Personalizar Gráfica General", expanded=True):
            c1, c2, c3 = st.columns(3)
            with c1:
                title_x = st.text_input("Etiqueta Eje X", "Distancia (X)")
            with c2:
                title_y = st.text_input("Etiqueta Eje Y", "Altura (Z)")
            with c3:
                invert_global = st.checkbox("🔄 Invertir Ejes (Global)", help="Afecta a todos los archivos en esta gráfica")

        # Preparar datos para Plotly
        combined_df_list = []
        for name, df in all_data.items():
            temp_df = df.copy()
            # Aplicar inversión global si se seleccionó
            if invert_global:
                temp_df = temp_df.rename(columns={'X': 'Z', 'Z': 'X'})
            
            temp_df['Archivo'] = name # Etiqueta para la leyenda
            combined_df_list.append(temp_df)
        
        big_df = pd.concat(combined_df_list)

        # Generar Gráfica Interactiva con Plotly
        fig = px.line(big_df, x='X', y='Z', color='Archivo', 
                      title="Comparativa de Mediciones",
                      labels={'X': title_x, 'Z': title_y, 'Archivo': 'Muestra'})
        
        fig.update_layout(height=500, template="plotly_white")
        fig.update_traces(mode="lines", hovertemplate=None)
        fig.update_layout(hovermode="x unified") # Tooltip moderno al pasar el mouse
        
        st.plotly_chart(fig, use_container_width=True)

        # Botón Descarga Excel GENERAL
        # Preparamos el diccionario invertido si el usuario pidió invertir
        data_export = {}
        for name, df in all_data.items():
            if invert_global:
                df_inv = df.rename(columns={'X': 'Z_temp', 'Z': 'X_temp'})
                data_export[name] = df_inv.rename(columns={'Z_temp': 'Z', 'X_temp': 'X'})[['X','Z']]
            else:
                data_export[name] = df

        excel_global = generate_combined_excel(data_export, chart_title="Comparativa General")
        
        col_dwn, _ = st.columns([1, 4])
        with col_dwn:
            st.download_button(
                label="📥 Descargar Excel con TODAS las gráficas",
                data=excel_global,
                file_name="Reporte_General_Perfilometro.xlsx",
                mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            )

        st.divider()

        # --- SECCIÓN 2: GRÁFICAS ESPECÍFICAS (OCULTAS) ---
        # Botón/Expander para ver detalles individuales
        with st.expander("📂 Ver Gráficas Específicas y Detalles (Individuales)", expanded=False):
            st.info("Aquí puedes analizar cada archivo por separado e invertir sus ejes individualmente.")
            
            for name, df in all_data.items():
                st.markdown(f"#### 📄 {name}")
                
                col_ctrl, col_viz = st.columns([1, 3])
                
                with col_ctrl:
                    # Checkbox único para cada archivo
                    inv_local = st.checkbox("Intercambiar Ejes", key=f"inv_{name}")
                    
                    # Preparar DF local
                    if inv_local:
                        df_plot = df.rename(columns={'X': 'Z_temp', 'Z': 'X_temp'})
                        df_plot = df_plot.rename(columns={'Z_temp': 'Z', 'X_temp': 'X'})[['X','Z']]
                    else:
                        df_plot = df
                    
                    # Botón descarga individual
                    excel_single = generate_single_excel(df_plot, name)
                    st.download_button(
                        label="📥 Descargar Excel",
                        data=excel_single,
                        file_name=f"{name.split('.')[0]}.xlsx",
                        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                        key=f"btn_{name}"
                    )

                with col_viz:
                    # Usamos st.line_chart para las pequeñas (más ligero) o plotly si prefieres consistencia
                    # Usaré Plotly simple aquí también para que se vea igual de bien
                    fig_small = px.line(df_plot, x='X', y='Z')
                    fig_small.update_layout(xaxis_title="X", yaxis_title="Z", 
                                          showlegend=False, height=300, margin=dict(l=0,r=0,t=0,b=0))
                    st.plotly_chart(fig_small, use_container_width=True)
                
                st.write("---")

else:
    st.info("Sube archivos .txt o .xml para visualizar el reporte.")
