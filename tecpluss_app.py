import base64
import math
from datetime import timedelta

import cufflinks as cf
import numpy as np
import pandas as pd
import streamlit as st

# Config App
from matplotlib import pyplot as plt

cf.set_config_file(sharing='public', theme='ggplot', offline='True')
st.set_page_config(page_title='Reporte TecPluss', page_icon=':bar_chart:')
hide_menu_style = """
    <style>
    #MainMenu {visibility: hidden; }
    footer {visibility: hidden;}
    </style>
"""

st.markdown(hide_menu_style, unsafe_allow_html=True)

# Web App Title
st.markdown('''
# **Generación de Reporte de Penalización de TecPluss**
---
''')

# Upload CSV data
with st.sidebar.header('1. Carga del archivo del proveedor TecPluss con formato CSV'):
    uploaded_fileg = st.sidebar.file_uploader("Carga el archivo del proveedor TecPluss CSV", type=["csv"])

# Upload CSV data
with st.sidebar.header('2. Carga del archivo generado en Proactivanet del proveedor TecPluss con formato CSV'):
    uploaded_filet = st.sidebar.file_uploader("Carga el archivo generado en Proactivanet del proveedor TecPluss CSV", type=["csv"])

# Pandas Profiling Report
if uploaded_fileg is not None:
    @st.cache_resource
    def load_csv():
        csv = pd.read_csv(uploaded_fileg, usecols=['Code Incidente Proactivanet',
                                                   'Fecha y hora de 1a respuesta',
                                                   'Fecha límite de resolución según SLA',
                                                   'Tipo de equipo',
                                                   ], encoding='latin-1')
        return csv
    df_general = load_csv()
    df_general = df_general.rename(columns={'Code Incidente Proactivanet': 'Código'})
    df_general = df_general.rename(columns={'Fecha y hora de 1a respuesta': 'Fecha y hora primera respuesta'})
    df_general['Fecha y hora primera respuesta'] = pd.to_datetime(df_general['Fecha y hora primera respuesta'],
                                                                  dayfirst=True)

    df_general = df_general.dropna(how='all')
    st.header('DataFrame del archivo enviado por TecPluss')
    st.write(df_general)
    st.write('---')

else:
    st.info('Esperando la carga del archivo General CSV.')

if uploaded_filet is not None:
    @st.cache(allow_output_mutation=True)
    def load_csv():
        csv = pd.read_csv(uploaded_filet, usecols=['Código',
                                                   'Fecha de registro',
                                                   'Fecha Asignado',
                                                   'Fecha Reasignado',
                                                   'Localización',
                                                   'Fecha firma solución'
                                                   ], encoding='latin-1')
        return csv
    df_tecpluss = load_csv()
    df_tecpluss = df_tecpluss.dropna(how='all')
    st.header('DataFrame del archivo generado en Proactivanet del proveedor TecPluss')
    st.write(df_tecpluss)
    st.write('---')

else:
    st.info('Esperando la carga del archivo TecPluss CSV.')

if (uploaded_filet is not None) & (uploaded_fileg is not None):
    @st.cache_resource
    def create_report_no_match():
        no_match = df_tecpluss[~df_tecpluss['Código'].isin(df_general['Código'])]
        no_match = no_match.dropna(how='all')
        return no_match


    df_no_match = create_report_no_match()
    data = df_no_match.to_csv('Reporte No Match.csv', encoding='utf8', index=False)

    st.header('DataFrame de los reportes sin Match')
    st.write(df_no_match)

    file_name = 'Reporte No Match.csv'
    csv_exp = df_no_match.to_csv(data)
    b64 = base64.b64encode(csv_exp.encode()).decode()  # some strings <-> bytes conversions necessary here
    href = f'<a href="data:file/csv;base64,{b64}" download="{file_name}" > Download No Match  (CSV) </a>'
    st.markdown(href, unsafe_allow_html=True)
    st.write('---')
if (uploaded_filet is not None) & (uploaded_fileg is not None):
    @st.cache(allow_output_mutation=True, suppress_st_warning=True)
    def create_report():
        df_match = pd.merge(df_tecpluss, df_general, on="Código")
        df_match['Fecha Asignado'] = np.where(df_match['Fecha Reasignado'].isnull(), df_match['Fecha Asignado'],
                                              df_match['Fecha Reasignado'])
        df_match = df_match.drop(['Fecha Reasignado'], axis=1)
        df_match['Tipo de incidencia'] = df_match['Código'].str[0:3]

        # ********************************* Validacion 1er SLA REQ *********************************

        in_REQ = df_match['Tipo de incidencia'] == 'REQ'

        df_matchR = df_match[in_REQ]

        pd.options.mode.chained_assignment = None  # default='warn'

        df_matchR['Fecha Asignado'] = pd.to_datetime(df_matchR['Fecha Asignado'], dayfirst=True)

        df_matchR['Dif. Días 1era Respuesta'] = df_matchR.apply(
            lambda df_matchR: (df_matchR['Fecha y hora primera respuesta'] - df_matchR['Fecha Asignado']), 1)
        df_matchR['Dif. Días 1era Respuesta'] = df_matchR['Dif. Días 1era Respuesta'].dt.total_seconds() / 60

        # Calculo de los días laborales sin contar fines de semana y días festivos

        holiday = ['2022-01-01', '2022-02-07', '2022-03-21', '2022-05-05', '2022-09-14', '2022-09-16', '2022-10-12', '2022-11-21']

        start = df_matchR['Fecha y hora primera respuesta'].values.astype('datetime64[D]')
        end = df_matchR['Fecha Asignado'].values.astype('datetime64[D]')

        # dias habiles solamente entre fecha Asignado y Fecha de 1era Respuesta
        days = np.busday_count(end, start, weekmask='Mon Tue Wed Thu Fri', holidays=holiday)

        df_matchR['Dif. Días 1R'] = days - 1

        # Establecer las 19:00 del primer día

        def insert_time(row):
            return row['Fecha Asignado'].replace(hour=19, minute=0, second=0, microsecond=0)

        df_matchR['Hora termino dia 1'] = df_matchR.apply(lambda r: insert_time(r), axis=1)

        # Establecer las 08:00 del último día

        def insert_time(row):
            return row['Fecha y hora primera respuesta'].replace(hour=8, minute=0, second=0, microsecond=0)

        df_matchR['Hora inicio dia ultimo'] = df_matchR.apply(lambda r: insert_time(r), axis=1)

        # minutos del pimer día
        df_matchR['Dif. Horas dia 1'] = df_matchR.apply(
            lambda df_matchR: (df_matchR['Hora termino dia 1'] - df_matchR['Fecha Asignado']), 1)

        df_matchR['Dif. Horas (minutos) dia 1'] = df_matchR['Dif. Horas dia 1'].dt.total_seconds() / 60

        df_matchR['Dif. Horas (minutos) dia 1'] = np.where(df_matchR['Dif. Horas (minutos) dia 1'] < 0, 0,
                                                           df_matchR['Dif. Horas (minutos) dia 1'])

        # minutos del ultimo día
        df_matchR['Dif. Horas (minutos) dia ultimo'] = df_matchR.apply(
            lambda df_matchR: (
                    df_matchR['Fecha y hora primera respuesta'] - df_matchR['Hora inicio dia ultimo']),
            1)

        df_matchR['Dif. Horas (minutos) dia ultimo'] = df_matchR[
                                                           'Dif. Horas (minutos) dia ultimo'].dt.total_seconds() / 60

        df_matchR['Dif. Horas (minutos) dia ultimo'] = np.where(df_matchR['Dif. Horas (minutos) dia ultimo'] < 0, 0,
                                                                df_matchR['Dif. Horas (minutos) dia ultimo'])

        # minutos de los días de enmedio
        df_matchR['Dif. Horas (minutos) dias adicionales'] = (660 * df_matchR['Dif. Días 1R'])

        df_matchR['Dif. Horas (minutos) dias adicionales'] = np.where(
            df_matchR['Dif. Horas (minutos) dias adicionales'] < 0, 0,
            df_matchR['Dif. Horas (minutos) dias adicionales'])

        # Tiempo tolerancia en Minutos 4320 equivalente a 3 días
        df_matchR['Tolerancia (minutos)'] = 4320

        # Tiempo de atención toatl al usuario en Minutos
        df_matchR['SLA TAU (Tiempo de Atención al Usuario, primera respuesta) Minutos'] = np.where(
            df_matchR['Dif. Días 1R'] < 0, df_matchR['Dif. Días 1era Respuesta'],
            df_matchR.apply(
                lambda df_matchR: (
                        df_matchR['Dif. Horas (minutos) dia 1'] + df_matchR['Dif. Horas (minutos) dia ultimo'] +
                        df_matchR['Dif. Horas (minutos) dias adicionales']), 1)
        )

        # Tiempo de atención toatl al usuario en Minutos - Tiempo tolerancia en Minutos
        df_matchR['TA - Tolerancia (minutos)'] = np.where(
            df_matchR['Dif. Días 1R'] < 0, df_matchR['Dif. Días 1era Respuesta'],
            df_matchR.apply(
                lambda df_matchR: (
                        df_matchR['Dif. Horas (minutos) dia 1'] + df_matchR['Dif. Horas (minutos) dia ultimo'] +
                        df_matchR['Dif. Horas (minutos) dias adicionales']), 1)
        )

        df_matchR['TA - Tolerancia (minutos)'] = df_matchR['TA - Tolerancia (minutos)'] - 4320

        conditionlist = [
            (df_matchR['TA - Tolerancia (minutos)'] <= 0),
            (df_matchR['TA - Tolerancia (minutos)'] > 0)]
        choicelist = ['SI', 'NO']

        df_matchR['Cumple 1er SLA'] = np.select(conditionlist, choicelist, default='Not Specified')

        # ********************************* Validación 2da Respuesta Requerimientos *********************************

        pd.options.mode.chained_assignment = None  # default='warn'

        df_matchR['Fecha firma solución'] = pd.to_datetime(df_matchR['Fecha firma solución'], dayfirst=True)

        df_matchR['Dif. Días 2da Respuesta'] = df_matchR.apply(
            lambda df_matchR: (df_matchR['Fecha firma solución'] -
                               df_matchR['Fecha Asignado']), 1)

        df_matchR['Dif. Días 2da Respuesta'] = df_matchR['Dif. Días 2da Respuesta'].dt.total_seconds() / 60

        # Calculo de los días laborales sin contar fines de semana y días festivos

        holiday = ['2022-01-01', '2022-02-07', '2022-03-21', '2022-05-05', '2022-09-14', '2022-09-16', '2022-10-12', '2022-11-21']

        start = df_matchR['Fecha Asignado'].values.astype('datetime64[D]')
        end = df_matchR['Fecha firma solución'].values.astype('datetime64[D]')
        if df_matchR['Fecha firma solución'].isnull().values.any():
            st.header('El archivo no puede tener fecha firma solución en blanco.')
        else:
            # dias habiles solamente entre fecha Asignado y Fecha de 1era Respuesta
            days = np.busday_count(end, start, weekmask='Mon Tue Wed Thu Fri', holidays=holiday)

        df_matchR['Dif. Días 2da'] = (days - 1) * -1

        # Establecer las 19:00 del primer día

        def insert_time(row):
            return row['Fecha Asignado'].replace(hour=19, minute=0, second=0, microsecond=0)

        df_matchR['Hora termino dia 1'] = df_matchR.apply(lambda r: insert_time(r), axis=1)

        # Establecer las 08:00 del último día

        def insert_time(row):
            return row['Fecha firma solución'].replace(hour=8, minute=0, second=0, microsecond=0)

        df_matchR['Hora inicio dia ultimo'] = df_matchR.apply(lambda r: insert_time(r), axis=1)

        # minutos del pimer día
        df_matchR['Dif. Horas dia 1'] = df_matchR.apply(
            lambda df_matchR: (
                    df_matchR['Hora termino dia 1'] - df_matchR['Fecha Asignado']), 1)

        df_matchR['Dif. Horas (minutos) dia 1'] = df_matchR['Dif. Horas dia 1'].dt.total_seconds() / 60

        df_matchR['Dif. Horas (minutos) dia 1'] = np.where(df_matchR['Dif. Horas (minutos) dia 1'] < 0, 0,
                                                           df_matchR['Dif. Horas (minutos) dia 1'])

        # minutos del ultimo día
        df_matchR['Dif. Horas (minutos) dia ultimo'] = df_matchR.apply(
            lambda df_matchR: (
                    df_matchR['Fecha firma solución'] - df_matchR['Hora inicio dia ultimo']),
            1)

        df_matchR['Dif. Horas (minutos) dia ultimo'] = df_matchR[
                                                           'Dif. Horas (minutos) dia ultimo'].dt.total_seconds() / 60

        df_matchR['Dif. Horas (minutos) dia ultimo'] = np.where(df_matchR['Dif. Horas (minutos) dia ultimo'] < 0, 0,
                                                                df_matchR['Dif. Horas (minutos) dia ultimo'])

        # minutos de los días de enmedio
        df_matchR['Dif. Horas (minutos) dias adicionales'] = (660 * (df_matchR['Dif. Días 2da'] - 2))

        df_matchR['Dif. Horas (minutos) dias adicionales'] = np.where(
            df_matchR['Dif. Horas (minutos) dias adicionales'] < 0, 0,
            df_matchR['Dif. Horas (minutos) dias adicionales'])

        # Tiempo tolerancia en Minutos 2do SLA. Solución: 5 días SCJN y 16 Horas CCJ
        df_matchR['Tolerancia (2do SLA) (minutos)'] = np.where(
            df_matchR['Localización'].str[1:4] == 'CCJ', 960, 7200)

        # Tiempo total de atención al usuario en Minutos
        df_matchR['SLA TAU (Tiempo de Atención al Usuario, 2da respuesta) Minutos 2do SLA'] = np.where(
            df_matchR['Dif. Días 2da'] < 2, df_matchR['Dif. Días 2da Respuesta'],
            df_matchR.apply(
                lambda df_matchR: (
                        df_matchR['Dif. Horas (minutos) dia 1'] + df_matchR['Dif. Horas (minutos) dia ultimo'] +
                        df_matchR['Dif. Horas (minutos) dias adicionales']), 1)
        )

        # Tiempo total de atención al usuario en Minutos menos Tiempo tolerancia en Minutos
        df_matchR['TA - Tolerancia (2do SLA) (minutos)'] = np.where(
            df_matchR['Dif. Días 2da'] < 2, df_matchR['Dif. Días 2da Respuesta'],
            df_matchR.apply(
                lambda df_matchR: (
                        df_matchR['Dif. Horas (minutos) dia 1'] + df_matchR['Dif. Horas (minutos) dia ultimo'] +
                        df_matchR['Dif. Horas (minutos) dias adicionales']), 1)
        )

        df_matchR['TA - Tolerancia (2do SLA) (minutos)'] = df_matchR['TA - Tolerancia (2do SLA) (minutos)'] - df_matchR[
            'Tolerancia (2do SLA) (minutos)']

        # Aqui comienza lo del calculo de la fecha limite de atención del ticket y el tiempo de tolerancia en días
        # naturales.
        ccj = timedelta(days=0, seconds=0,
                        microseconds=0,
                        milliseconds=0,
                        minutes=960, hours=0)
        scjn = timedelta(days=0, seconds=0,
                         microseconds=0,
                         milliseconds=0,
                         minutes=7200, hours=0)
        # Seleccionar la tolerancia
        df_matchR['tolerancia_min'] = np.where(df_matchR['Localización'].str[1:4] == 'CCJ', 960, 3200)

        def selector(row):
            dia = -1
            try:
                for d in range(6):
                    if (row['tolerancia_min'] <= 0) & (row['tolerancia_min'] < 660):
                        break
                    elif dia == -1:
                        dia = dia + 1
                        if row['tolerancia_min'] <= row['Dif. Horas (minutos) dia 1']:
                            row['Fecha límite de atención a ticket 2do nivel'] = row['Fecha Asignado'] + \
                                                                                 timedelta(days=dia, seconds=0,
                                                                                           microseconds=0,
                                                                                           milliseconds=0, minutes=0,
                                                                                           hours=0)
                            row['Fecha límite de atención a ticket 2do nivel'] = row[
                                                                                     'Fecha límite de atención a ticket 2do nivel'] + pd.to_timedelta(
                                row['tolerancia_min'], unit='m')
                            break
                        else:
                            row['tolerancia_min'] = row['tolerancia_min'] - row['Dif. Horas (minutos) dia 1']
                    else:
                        dia = dia + 1
                        if row['tolerancia_min'] <= 660:
                            row['Fecha límite de atención a ticket 2do nivel'] = row['Fecha Asignado'].replace(hour=8,
                                                                                                               minute=0,
                                                                                                               second=0,
                                                                                                               microsecond=0)
                            row['Fecha límite de atención a ticket 2do nivel'] = row[
                                                                                     'Fecha límite de atención a ticket 2do nivel'] + \
                                                                                 timedelta(days=dia, seconds=0,
                                                                                           microseconds=0,
                                                                                           milliseconds=0, minutes=0,
                                                                                           hours=0)
                            row['Fecha límite de atención a ticket 2do nivel'] = row[
                                                                                     'Fecha límite de atención a ticket 2do nivel'] + pd.to_timedelta(
                                row['tolerancia_min'], unit='m')
                            break
                        else:
                            row['tolerancia_min'] = row['tolerancia_min'] - 660
                return row['Fecha límite de atención a ticket 2do nivel']
            except Exception as e:
                return print('selector:',e)

        df_matchR['Fecha límite de atención a ticket 2do nivel'] = df_matchR.apply(lambda row: selector(row), axis=1)

        df_matchR['Fecha límite de atención a ticket 2do nivel'] = pd.to_datetime(
            df_matchR['Fecha límite de atención a ticket 2do nivel'], dayfirst=True)

        df_matchR['Horas penalizables 2do respuesta'] = df_matchR.apply(
            lambda df_matchR: (df_matchR['Fecha firma solución'] -
                               df_matchR['Fecha límite de atención a ticket 2do nivel']), 1)
        df_matchR['Horas penalizables 2do respuesta'] = df_matchR[
                                                            'Horas penalizables 2do respuesta'].dt.total_seconds() / 3600

        df_matchR['Horas penalizables 2do respuesta'] = df_matchR['Horas penalizables 2do respuesta'].values.astype(
            'int32')

        # Aqui termina lo del calculo de la fecha limite de atención del ticket y el tiempo de tolerancia en días
        # naturales.

        conditionlist = [
            (df_matchR['TA - Tolerancia (2do SLA) (minutos)'] <= 0),
            (df_matchR['TA - Tolerancia (2do SLA) (minutos)'] > 0)]
        choicelist = ['SI', 'NO']

        df_matchR['Cumple 2do SLA'] = np.select(conditionlist, choicelist, default='Not Specified')

        # *********************************  Validacion Incidencias 1era Respuesta *********************************

        in_INC = df_match['Tipo de incidencia'] == 'INC'

        df_matchI = df_match[in_INC]

        pd.options.mode.chained_assignment = None  # default='warn'

        df_matchI['Fecha Asignado'] = pd.to_datetime(df_matchI['Fecha Asignado'], dayfirst=True)

        df_matchI['Dif. Días 1era Respuesta'] = df_matchI.apply(
            lambda df_matchI: (df_matchI['Fecha y hora primera respuesta'] - df_matchI['Fecha Asignado']), 1)

        df_matchI['Dif. Días 1era Respuesta'] = df_matchI['Dif. Días 1era Respuesta'].dt.total_seconds() / 60

        # Calculo de los días laborales sin contar fines de semana y días festivos

        holiday = ['2022-01-01', '2022-02-07', '2022-03-21', '2022-05-05', '2022-09-14', '2022-09-16', '2022-10-12', '2022-11-21']

        start = df_matchI['Fecha y hora primera respuesta'].values.astype('datetime64[D]')
        end = df_matchI['Fecha Asignado'].values.astype('datetime64[D]')

        # dias habiles solamente entre fecha Asignado y Fecha de 1era Respuesta
        days = np.busday_count(end, start, weekmask='Mon Tue Wed Thu Fri', holidays=holiday)

        df_matchI['Dif. Días 1R'] = days - 1

        # Establecer las 19:00 del primer día

        def insert_time(row):
            return row['Fecha Asignado'].replace(hour=19, minute=0, second=0, microsecond=0)

        df_matchI['Hora termino dia 1'] = df_matchI.apply(lambda r: insert_time(r), axis=1)

        # Establecer las 08:00 del último día

        def insert_time(row):
            return row['Fecha y hora primera respuesta'].replace(hour=8, minute=0, second=0, microsecond=0)

        df_matchI['Hora inicio dia ultimo'] = df_matchI.apply(lambda r: insert_time(r), axis=1)

        # minutos del pimer día
        df_matchI['Dif. Horas dia 1'] = df_matchI.apply(
            lambda df_matchI: (df_matchI['Hora termino dia 1'] - df_matchI['Fecha Asignado']), 1)

        df_matchI['Dif. Horas (minutos) dia 1'] = df_matchI['Dif. Horas dia 1'].dt.total_seconds() / 60

        df_matchI['Dif. Horas (minutos) dia 1'] = np.where(df_matchI['Dif. Horas (minutos) dia 1'] < 0, 0,
                                                           df_matchI['Dif. Horas (minutos) dia 1'])

        # minutos del ultimo dia
        df_matchI['Dif. Horas (minutos) dia ultimo'] = df_matchI.apply(
            lambda df_matchI: (
                    df_matchI['Fecha y hora primera respuesta'] - df_matchI['Hora inicio dia ultimo']),
            1)

        df_matchI['Dif. Horas (minutos) dia ultimo'] = df_matchI[
                                                           'Dif. Horas (minutos) dia ultimo'].dt.total_seconds() / 60

        df_matchI['Dif. Horas (minutos) dia ultimo'] = np.where(df_matchI['Dif. Horas (minutos) dia ultimo'] < 0, 0,
                                                                df_matchI['Dif. Horas (minutos) dia ultimo'])

        # minutos de los días de enmedio
        df_matchI['Dif. Horas (minutos) dias adicionales'] = (660 * df_matchI['Dif. Días 1R'])

        df_matchI['Dif. Horas (minutos) dias adicionales'] = np.where(
            df_matchI['Dif. Horas (minutos) dias adicionales'] < 0, 0,
            df_matchI['Dif. Horas (minutos) dias adicionales'])

        # Tiempo tolerancia en Incidecnias 1er SLA: 30 minutos
        df_matchI['Tolerancia (minutos)'] = 30

        # Tiempo real de atención al usuario en Minutos
        df_matchI['SLA TAU (Tiempo de Atención al Usuario, primera respuesta) Minutos'] = np.where(
            df_matchI['Dif. Días 1R'] < 0, df_matchI['Dif. Días 1era Respuesta'],
            df_matchI.apply(
                lambda df_matchI: (
                        df_matchI['Dif. Horas (minutos) dia 1'] + df_matchI['Dif. Horas (minutos) dia ultimo'] +
                        df_matchI['Dif. Horas (minutos) dias adicionales']), 1)
        )

        # Tiempo real de atención al usuario en Minutos Temp
        df_matchI['TA - Tolerancia (minutos)'] = np.where(
            df_matchI['Dif. Días 1R'] < 0, df_matchI['Dif. Días 1era Respuesta'],
            df_matchI.apply(
                lambda df_matchI: (
                        df_matchI['Dif. Horas (minutos) dia 1'] + df_matchI['Dif. Horas (minutos) dia ultimo'] +
                        df_matchI['Dif. Horas (minutos) dias adicionales']), 1)
        )

        df_matchI['TA - Tolerancia (minutos)'] = df_matchI['TA - Tolerancia (minutos)'] - 30

        conditionlist = [
            (df_matchI['TA - Tolerancia (minutos)'] <= 0),
            (df_matchI['TA - Tolerancia (minutos)'] > 0)]
        choicelist = ['SI', 'NO']

        df_matchI['Cumple 1er SLA'] = np.select(conditionlist, choicelist, default='Not Specified')

        # ********************************* Validacion 2da Respuesta Incidencias *********************************

        pd.options.mode.chained_assignment = None  # default='warn'

        df_matchI['Fecha Asignado'] = pd.to_datetime(df_matchI['Fecha Asignado'], dayfirst=True)
        df_matchI['Fecha firma solución'] = pd.to_datetime(df_matchI['Fecha firma solución'], dayfirst=True)

        df_matchI['Dif. Días 2da Respuesta'] = df_matchI.apply(
            lambda df_matchI: (
                    df_matchI['Fecha firma solución'] - df_matchI['Fecha Asignado']), 1)

        df_matchI['Dif. Días 2da Respuesta'] = df_matchI['Dif. Días 2da Respuesta'].dt.total_seconds() / 60

        # Calculo de los días laborales sin contar fines de semana y días festivos

        holiday = ['2022-01-01', '2022-02-07', '2022-03-21', '2022-05-05', '2022-09-14', '2022-09-16', '2022-10-12', '2022-11-21']

        start = df_matchI['Fecha Asignado'].values.astype('datetime64[D]')
        end = df_matchI['Fecha firma solución'].values.astype('datetime64[D]')
        days = np.busday_count(end, start, weekmask='Mon Tue Wed Thu Fri', holidays=holiday)

        df_matchI['Dif. Días 2da'] = (days - 1) * -1

        # Establecer las 19:00 del primer día

        def insert_time(row):
            return row['Fecha Asignado'].replace(hour=19, minute=0, second=0, microsecond=0)

        df_matchI['Hora termino dia 1'] = df_matchI.apply(lambda r: insert_time(r), axis=1)

        # Establecer las 08:00 del último día

        def insert_time(row):
            return row['Fecha firma solución'].replace(hour=8, minute=0, second=0, microsecond=0)

        df_matchI['Hora inicio dia ultimo'] = df_matchI.apply(lambda r: insert_time(r), axis=1)

        # minutos del pimer día
        df_matchI['Dif. Horas dia 1'] = df_matchI.apply(
            lambda df_matchI: (df_matchI['Hora termino dia 1'] -
                               df_matchI['Fecha Asignado']), 1)

        df_matchI['Dif. Horas (minutos) dia 1'] = df_matchI['Dif. Horas dia 1'].dt.total_seconds() / 60

        df_matchI['Dif. Horas (minutos) dia 1'] = np.where(df_matchI['Dif. Horas (minutos) dia 1'] < 0, 0,
                                                           df_matchI['Dif. Horas (minutos) dia 1'])
        # minutos del ultimo día
        df_matchI['Dif. Horas (minutos) dia ultimo'] = df_matchI.apply(
            lambda df_matchI: (
                    df_matchI['Fecha firma solución'] - df_matchI['Hora inicio dia ultimo']),
            1)

        df_matchI['Dif. Horas (minutos) dia ultimo'] = df_matchI[
                                                           'Dif. Horas (minutos) dia ultimo'].dt.total_seconds() / 60

        df_matchI['Dif. Horas (minutos) dia ultimo'] = np.where(df_matchI['Dif. Horas (minutos) dia ultimo'] < 0, 0,
                                                                df_matchI['Dif. Horas (minutos) dia ultimo'])

        # minutos de los días de enmedio
        df_matchI['Dif. Horas (minutos) dias adicionales'] = (660 * (df_matchI['Dif. Días 2da'] - 2))

        df_matchI['Dif. Horas (minutos) dias adicionales'] = np.where(
            df_matchI['Dif. Horas (minutos) dias adicionales'] < 0, 0,
            df_matchI['Dif. Horas (minutos) dias adicionales'])

        # Tiempo tolerancia en Minutos
        df_matchI['Tolerancia (2do SLA) (minutos)'] = np.where(
            df_matchI['Localización'].str[1:4] == 'CCJ', 960, 480)

        # Tiempo total de atención al usuario en Minutos
        df_matchI['SLA TAU (Tiempo de Atención al Usuario, 2da respuesta) Minutos 2do SLA'] = np.where(
            df_matchI['Dif. Días 2da'] < 2, df_matchI['Dif. Días 2da Respuesta'],
            df_matchI.apply(
                lambda df_matchI: (
                        df_matchI['Dif. Horas (minutos) dia 1'] + df_matchI['Dif. Horas (minutos) dia ultimo'] +
                        df_matchI['Dif. Horas (minutos) dias adicionales']), 1)
        )

        # Tiempo total de atención al usuario en Minutos menos Tiempo tolerancia en Minutos
        df_matchI['TA - Tolerancia (2do SLA) (minutos)'] = np.where(
            df_matchI['Dif. Días 2da'] < 2, df_matchI['Dif. Días 2da Respuesta'],
            df_matchI.apply(
                lambda df_matchI: (
                        df_matchI['Dif. Horas (minutos) dia 1'] + df_matchI['Dif. Horas (minutos) dia ultimo'] +
                        df_matchI['Dif. Horas (minutos) dias adicionales']), 1)
        )

        df_matchI['TA - Tolerancia (2do SLA) (minutos)'] = df_matchI['TA - Tolerancia (2do SLA) (minutos)'] - df_matchI[
            'Tolerancia (2do SLA) (minutos)']

        # Aqui comienza lo del calculo de la fecha limite de atención del ticket y el tiempo de tolerancia en días
        # naturales.
        ccj = timedelta(days=0, seconds=0,
                        microseconds=0,
                        milliseconds=0,
                        minutes=960, hours=0)
        scjn = timedelta(days=0, seconds=0,
                         microseconds=0,
                         milliseconds=0,
                         minutes=480, hours=0)
        # Seleccionar la tolerancia
        df_matchI['tolerancia_min'] = np.where(df_matchI['Localización'].str[1:4] == 'CCJ', 960, 480)

        def selector(row):
            dia = -1
            try:
                for d in range(3):
                    if (row['tolerancia_min'] <= 0) & (row['tolerancia_min'] < 660):
                        break
                    elif dia == -1:
                        dia = dia + 1
                        if row['tolerancia_min'] <= row['Dif. Horas (minutos) dia 1']:
                            row['Fecha límite de atención a ticket 2do nivel'] = row['Fecha Asignado'] + \
                                                                                 timedelta(days=dia, seconds=0,
                                                                                           microseconds=0,
                                                                                           milliseconds=0, minutes=0,
                                                                                           hours=0)
                            row['Fecha límite de atención a ticket 2do nivel'] = row[
                                                                                     'Fecha límite de atención a ticket 2do nivel'] + pd.to_timedelta(
                                row['tolerancia_min'], unit='m')
                            break
                        else:
                            row['tolerancia_min'] = row['tolerancia_min'] - row['Dif. Horas (minutos) dia 1']
                    else:
                        dia = dia + 1
                        if row['tolerancia_min'] <= 660:
                            row['Fecha límite de atención a ticket 2do nivel'] = row['Fecha Asignado'].replace(hour=8,
                                                                                                               minute=0,
                                                                                                               second=0,
                                                                                                               microsecond=0)
                            row['Fecha límite de atención a ticket 2do nivel'] = row[
                                                                                     'Fecha límite de atención a ticket 2do nivel'] + \
                                                                                 timedelta(days=dia, seconds=0,
                                                                                           microseconds=0,
                                                                                           milliseconds=0, minutes=0,
                                                                                           hours=0)
                            row['Fecha límite de atención a ticket 2do nivel'] = row[
                                                                                     'Fecha límite de atención a ticket 2do nivel'] + pd.to_timedelta(
                                row['tolerancia_min'], unit='m')
                            break
                        else:
                            row['tolerancia_min'] = row['tolerancia_min'] - 660
                return row['Fecha límite de atención a ticket 2do nivel']
            except Exception as e:
                return print('selector:', e)

        df_matchI['Fecha límite de atención a ticket 2do nivel'] = df_matchI.apply(lambda row: selector(row), axis=1)

        df_matchI['Fecha límite de atención a ticket 2do nivel'] = pd.to_datetime(
            df_matchI['Fecha límite de atención a ticket 2do nivel'], dayfirst=True)

        df_matchI['Horas penalizables 2do respuesta'] = df_matchI.apply(
            lambda df_matchI: (df_matchI['Fecha firma solución'] -
                               df_matchI['Fecha límite de atención a ticket 2do nivel']), 1)
        df_matchI['Horas penalizables 2do respuesta'] = df_matchI[
                                                            'Horas penalizables 2do respuesta'].dt.total_seconds() / 3600

        df_matchI['Horas penalizables 2do respuesta'] = df_matchI['Horas penalizables 2do respuesta'].values.astype(
            'int32')
        # Aqui termina lo del calculo de la fecha limite de atención del ticket y el tiempo de tolerancia en días
        # naturales.

        conditionlist = [
            (df_matchI['TA - Tolerancia (2do SLA) (minutos)'] <= 0),
            (df_matchI['TA - Tolerancia (2do SLA) (minutos)'] > 0)]
        choicelist = ['SI', 'NO']

        df_matchI['Cumple 2do SLA'] = np.select(conditionlist, choicelist, default='Not Specified')

        df_result = pd.merge(df_matchI, df_matchR, how='outer')
        # del (df_result['Fecha de 1era Respuesta'])
        df_result = df_result.rename(columns={'Código': 'Número de incidente / requerimiento',
                                              'Fecha de registro': 'Fecha de registro incidente / requerimiento',
                                              'Fecha Asignado': 'Fecha Asignado a Tec Pluss'})

        # Aqui van los drops:
        df_result = df_result.drop(
            ['Dif. Días 1era Respuesta',
             'Dif. Días 1R', 'Hora termino dia 1', 'Dif. Días 1era Respuesta',
             'Hora inicio dia ultimo', 'Dif. Horas dia 1', 'Dif. Días 2da Respuesta',
             'Dif. Horas (minutos) dia 1', 'Dif. Horas (minutos) dia ultimo', 'Dif. Horas (minutos) dias adicionales',
             'Dif. Días 2da Respuesta', 'Dif. Días 2da'], axis=1)

        # Get names of indexes for which column Stock has value No
        indexNames = df_result[(df_result['Cumple 1er SLA'] == 'SI') & (df_result['Cumple 2do SLA'] == 'SI')].index
        # Delete these row indexes from dataFrame
        df_result.drop(indexNames, inplace=True)
        return df_result


    df_final = create_report()
    st.header('Reporte de registros con Match de Tecpluss')


    # st.write(df_final)

    def color_df(val):
        if val == 'SI':
            color = 'green'
        else:
            color = 'red'
        return f'background-color: {color}'


    st.dataframe(df_final.style.applymap(color_df, subset=['Cumple 1er SLA', 'Cumple 2do SLA']))
    file_name = 'Reporte Match TecPluss.csv'
    csv_exp = df_final.to_csv(data, index=False)
    b64 = base64.b64encode(csv_exp.encode()).decode()  # some strings <-> bytes conversions necessary here
    href = f'<a href="data:file/csv;base64,{b64}" download="{file_name}" > Download Reporte Match TecPluss  (CSV) </a>'
    st.markdown(href, unsafe_allow_html=True)
    st.write('---')
    st.header('Reporte Final Penalizacion Tecpluss')
    df_penalizacion = df_final.copy()
    df_penalizacion = df_penalizacion.rename(columns={'Nombre': 'Usuario'})
    conditionlist = [
        (df_penalizacion['Tipo de equipo'] == 'UCMB'),
        (df_penalizacion['Tipo de equipo'] == 'UCME'),
        (df_penalizacion['Tipo de equipo'] == 'UA'),
        (df_penalizacion['Tipo de equipo'] == 'UCMBA'),
        (df_penalizacion['Tipo de equipo'] == 'UCMBP'),
        (df_penalizacion['Tipo de equipo'] == 'UCFPI'),
        (df_penalizacion['Tipo de equipo'] == 'UCFPII'),
        (df_penalizacion['Tipo de equipo'] == 'Laptop')]
    choicelist = [577, 656, 183.50, 1160, 2112, 7562, 9812, 1]

    df_penalizacion['Costo mensual equipo'] = np.select(conditionlist, choicelist, default='Not Specified')


    def calcula_pena1(row):
        monto = 0
        try:
            if row['Cumple 1er SLA'] == 'NO':
                if row['Cumple 1er SLA'] == 'NO':
                    if row['TA - Tolerancia (minutos)'] < 0:
                        monto = 0
                    elif (row['TA - Tolerancia (minutos)'] > 0) & (row['TA - Tolerancia (minutos)'] <= 100):
                        monto = (math.ceil(int(row['TA - Tolerancia (minutos)']) / 10) / 100) * float(
                            row['Costo mensual equipo'])
                    elif (row['TA - Tolerancia (minutos)'] > 100) & (row['TA - Tolerancia (minutos)'] <= 1000):
                        monto = (math.ceil(int(row['TA - Tolerancia (minutos)']) / 10) / 100) * float(
                            row['Costo mensual equipo'])
                    else:
                        monto = (math.ceil(int(row['TA - Tolerancia (minutos)']) / 10) / 100) * float(
                            row['Costo mensual equipo'])

            else:
                monto = 0
        except Exception as e: print('calcula_pena1:', e)

        return round(monto, 2)


    df_penalizacion['Penalizacion 1era respuesta'] = df_penalizacion.apply(lambda r: calcula_pena1(r), axis=1)


    def calcula_pena2(row):
        monto = 0
        try:
            if row['Cumple 2do SLA'] == 'NO':
                if row['Horas penalizables 2do respuesta'] > 0:
                    monto = int(row['Horas penalizables 2do respuesta']) * (
                            0.01 * float(row['Costo mensual equipo']))

                elif row['TA - Tolerancia (2do SLA) (minutos)'] < 0:
                    monto = 0

            else:
                monto = 0
        except Exception as e: print('calcula_pena2:', e)

        return round(monto, 2)


    df_penalizacion['Penalizacion 2da respuesta'] = df_penalizacion.apply(lambda r: calcula_pena2(r), axis=1)

    df_penalizacion['Sumatoria Penalizacion 1era y 2da respuesta'] = df_penalizacion.apply(lambda df_penalizacion: (
            df_penalizacion['Penalizacion 1era respuesta'] + df_penalizacion['Penalizacion 2da respuesta']), 1)


    def calcula_penaFinal(row):
        monto = 0
        try:
            if row['Sumatoria Penalizacion 1era y 2da respuesta'] > (0.30 * float(row['Costo mensual equipo'])):
                monto = round((0.30 * float(row['Costo mensual equipo'])), 2)

            else:
                monto = row['Sumatoria Penalizacion 1era y 2da respuesta']
        except Exception as e: print('calcula_penaFinal:',e)

        return round(monto, 2)


    df_penalizacion['Total Final Penalizacion'] = df_penalizacion.apply(lambda r: calcula_penaFinal(r), axis=1)
    # del (df_penalizacion['Usuario'])
    del (df_penalizacion['Tipo de equipo'])
    # del (df_penalizacion['Fecha firma cierre'])
    # del (df_penalizacion['Fecha y hora de creación'])
    del (df_penalizacion['Tipo de incidencia'])
    df_penalizacion = df_penalizacion.rename(
        columns={'Fecha primera respuesta Cherwell TecPluss': 'Fecha primera respuesta',
                 'Fecha firma solución': 'Fecha y hora firma solución',
                 'Tolerancia (minutos)': 'Tolerancia primera respuesta (minutos)',
                 'TA - Tolerancia (minutos)': 'Tiempo de Atención - Tolerancia de primera respuesta (minutos) (G-F)',
                 'SLA TAU (Tiempo de Atención al Usuario, primera respuesta) Minutos': 'Tiempo de atención total primera respuesta 1er SLA  (minutos). (D-C)',
                 'SLA TAU (Tiempo de Atención al Usuario, 2da respuesta) Minutos 2do SLA': 'Tiempo de atención total segunda respuesta  (horas). Horario Laboral.  ( O-D )',
                 'Tolerancia (2do SLA) (minutos)': 'Tiempo de tolerancia resolución 2do. SLA (horas)',
                 'TA - Tolerancia (2do SLA) (minutos)': 'Tiempo de atención total - Tolerancia (2do SLA) (horas) ( K-J )',
                 'Penalizacion 1era respuesta': 'Costo total penalizacion 1era respuesta. ( H/10 ) * (S * 1%)',
                 'Penalizacion 2da respuesta': 'Costo total penalizacion 2da respuesta - Reporte Automático.  P * (S* 1%)',
                 'Sumatoria Penalizacion 1era y 2da respuesta': 'Costo total sumatoria penalizacion primera respuesta y segunda respuesta.  (R+S)',
                 'Total Final Penalizacion': 'Costo total de la proporcionalidad del 30%.'})


    df_penalizacion = df_penalizacion.reindex(
        columns=['Número de incidente / requerimiento', 'Fecha de registro incidente / requerimiento',
                 'Fecha Asignado a Tec Pluss', 'Fecha y hora primera respuesta', 'Localización',
                 'Tolerancia primera respuesta (minutos)',
                 'Tiempo de atención total primera respuesta 1er SLA  (minutos). (D-C)',
                 'Tiempo de Atención - Tolerancia de primera respuesta (minutos) (G-F)',
                 'Cumple 1er SLA',
                 'Tiempo de tolerancia resolución 2do. SLA (horas)',
                 'Tiempo de atención total segunda respuesta  (horas). Horario Laboral.  ( O-D )',
                 'Tiempo de atención total - Tolerancia (2do SLA) (horas) ( K-J )',
                 'Cumple 2do SLA',
                 'Fecha límite de atención a ticket 2do nivel',
                 'Fecha y hora firma solución',
                 'Horas penalizables 2do respuesta',
                 'Costo mensual equipo',
                 'Costo total penalizacion 1era respuesta. ( H/10 ) * (S * 1%)',
                 'Costo total penalizacion 2da respuesta - Reporte Automático.  P * (S* 1%)',
                 'Costo total sumatoria penalizacion primera respuesta y segunda respuesta.  (R+S)',
                 'Costo total de la proporcionalidad del 30%.'])
    df_penalizacion['Tiempo de tolerancia resolución 2do. SLA (horas)'] = df_penalizacion['Tiempo de tolerancia resolución 2do. SLA (horas)']/60
    df_penalizacion['Tiempo de atención total segunda respuesta  (horas). Horario Laboral.  ( O-D )'] = df_penalizacion['Tiempo de atención total segunda respuesta  (horas). Horario Laboral.  ( O-D )'] / 60
    df_penalizacion['Tiempo de atención total - Tolerancia (2do SLA) (horas) ( K-J )'] = df_penalizacion['Tiempo de atención total - Tolerancia (2do SLA) (horas) ( K-J )'] / 60
    # Obtiene las filas para las cuales la columna: Costo total sumatoria penalizacion primera respuesta y segunda
    # respuesta.  (R+S), tiene el valor 0
    indexNames = df_penalizacion[df_penalizacion['Costo total sumatoria penalizacion primera respuesta y segunda respuesta.  (R+S)'] == 0.00].index
    # Borra estas columnas del dataFrame
    df_penalizacion.drop(indexNames, inplace=True)

    file_name = 'Reporte Penalizacion TecPluss.csv'
    st.dataframe(df_penalizacion)
    csv_exp = df_penalizacion.to_csv(data, index=False)
    b64 = base64.b64encode(csv_exp.encode()).decode()  # some strings <-> bytes conversions necessary here
    href = f'<a href="data:file/csv;base64,{b64}" download="{file_name}" ' \
           f'> Download Reporte Penalizacion TecPluss  (CSV) </a>'
    st.markdown(href, unsafe_allow_html=True)

    st.write('---')

    st.header('TecPluss Graficos')
    df_new = df_final.copy()
    df_new = df_new.rename_axis('Tipo de incidencia')
    options = st.multiselect(
        'Escoge un SLA', ['Cumple 1er SLA', 'Cumple 2do SLA'], ['Cumple 1er SLA']
    )
    if not options:
        st.error("Por favor selecciona un tipo de SLA.")
    if options == ['Cumple 2do SLA', 'Cumple 1er SLA']:
        st.error("Por favor selecciona solo un tipo de SLA a la vez.")
    if options == ['Cumple 1er SLA']:
        data = df_new.groupby(['Cumple 1er SLA']).size()
        if hasattr(data, 'SI') & hasattr(data, 'NO'):
            df = pd.DataFrame({'SI': {'Cumple 1er SLA': data.SI}, 'NO': {'Cumple 1er SLA': data.NO}})
            st.write(df)
            figura = df.iplot(kind="bar", bins=20, theme="white", title="Cumple 1er SLA",
                              xTitle='Cumple 1er SLA - No / Si', yTitle='Count', asFigure=True)
            st.plotly_chart(figura)
            df_new['Porcentajes'] = (df_new.groupby('Cumple 1er SLA').size() / df_new['Cumple 1er SLA'].count()) * 100
            Si_No = (df_new.groupby('Cumple 1er SLA').size() / df_new['Cumple 1er SLA'].count()) * 100
            respuestas = [Si_No.SI, Si_No.NO]
            tipo = ['SI', 'NO']
            explode = [0.2, 0]  # Destacar algunos
            fig, ax = plt.subplots()
            ax.pie(respuestas, labels=tipo, explode=explode, autopct='%1.1f%%', shadow=True, startangle=90)
            st.title('Cumple 1er SLA - TECPLUSS %')
            # st.table(Si_No)
            st.pyplot(fig)
            # png_exp = plt.savefig('Grafica Pie Si-No.jpeg')
            st.write('---')
            df_new["porcentajes"] = (df_new.groupby('Cumple 1er SLA').size() / df_new['Cumple 1er SLA'].count()) * 100
            fig3 = df_new["Cumple 1er SLA"].iplot(kind="histogram", bins=20, theme="white", title="Cumple 1er SLA",
                                                  xTitle='Cumple 1er SLA - No / Si', yTitle='Count', asFigure=True)
            # st.plotly_chart(fig3)
            # st.write('---')
            df_new['Porcentajes'] = (df_new.groupby('Cumple 1er SLA').size() / df_new['Cumple 1er SLA'].count()) * 100
            Si_No = (df_new.groupby('Cumple 1er SLA').size() / df_new['Cumple 1er SLA'].count()) * 100
            respuestas = [Si_No.SI, Si_No.NO]
            tipo = ['SI', 'NO']
            explode = [0.2, 0]  # Destacar algunos
            fig, ax = plt.subplots()
            ax.pie(respuestas, labels=tipo, explode=explode, autopct='%1.1f%%', shadow=True, startangle=90)
        elif hasattr(data, 'SI'):
            df = pd.DataFrame({'SI': {'Cumple 1er SLA': data.SI}})
            st.write(df)
            figura = df.iplot(kind="bar", bins=20, theme="white", title="Cumple 1er SLA",
                              xTitle='Cumple 1er SLA - Si', yTitle='Count', asFigure=True)
            st.plotly_chart(figura)
            df_new['Porcentajes'] = (df_new.groupby('Cumple 1er SLA').size() / df_new['Cumple 1er SLA'].count()) * 100
            Si_No = (df_new.groupby('Cumple 1er SLA').size() / df_new['Cumple 1er SLA'].count()) * 100
            respuestas = [Si_No.SI]
            tipo = ['SI']
            explode = [0]  # Destacar algunos
            fig, ax = plt.subplots()
            ax.pie(respuestas, labels=tipo, explode=explode, autopct='%1.1f%%', shadow=True, startangle=90)
            st.title('Cumple 1er SLA - TECPLUSS %')
            # st.table(Si_No)
            st.pyplot(fig)
            # png_exp = plt.savefig('Grafica Pie Si-No.jpeg')
            st.write('---')
            df_new["porcentajes"] = (df_new.groupby('Cumple 1er SLA').size() / df_new['Cumple 1er SLA'].count()) * 100
            fig3 = df_new["Cumple 1er SLA"].iplot(kind="histogram", bins=20, theme="white", title="Cumple 1er SLA",
                                                  xTitle='Cumple 1er SLA - Si', yTitle='Count', asFigure=True)
            # st.plotly_chart(fig3)
            # st.write('---')
            df_new['Porcentajes'] = (df_new.groupby('Cumple 1er SLA').size() / df_new['Cumple 1er SLA'].count()) * 100
            Si_No = (df_new.groupby('Cumple 1er SLA').size() / df_new['Cumple 1er SLA'].count()) * 100
            respuestas = [Si_No.SI]
            tipo = ['SI']
            explode = [0]  # Destacar algunos
            fig, ax = plt.subplots()
            ax.pie(respuestas, labels=tipo, explode=explode, autopct='%1.1f%%', shadow=True, startangle=90)
        elif hasattr(data, 'NO'):
            df = pd.DataFrame({'NO': {'Cumple 1er SLA': data.NO}})
            st.write(df)
            figura = df.iplot(kind="bar", bins=20, theme="white", title="Cumple 1er SLA",
                              xTitle='Cumple 1er SLA - NO', yTitle='Count', asFigure=True)
            st.plotly_chart(figura)
            df_new['Porcentajes'] = (df_new.groupby('Cumple 1er SLA').size() / df_new['Cumple 1er SLA'].count()) * 100
            Si_No = (df_new.groupby('Cumple 1er SLA').size() / df_new['Cumple 1er SLA'].count()) * 100
            respuestas = [Si_No.NO]
            tipo = ['NO']
            explode = [0]  # Destacar algunos
            fig, ax = plt.subplots()
            ax.pie(respuestas, labels=tipo, explode=explode, autopct='%1.1f%%', shadow=True, startangle=90)
            st.title('Cumple 1er SLA - TECPLUSS %')
            # st.table(Si_No)
            st.pyplot(fig)
            # png_exp = plt.savefig('Grafica Pie Si-No.jpeg')
            st.write('---')
            df_new["porcentajes"] = (df_new.groupby('Cumple 1er SLA').size() / df_new['Cumple 1er SLA'].count()) * 100
            fig3 = df_new["Cumple 1er SLA"].iplot(kind="histogram", bins=20, theme="white", title="Cumple 1er SLA",
                                                  xTitle='Cumple 1er SLA - NO', yTitle='Count', asFigure=True)
            # st.plotly_chart(fig3)
            # st.write('---')
            df_new['Porcentajes'] = (df_new.groupby('Cumple 1er SLA').size() / df_new['Cumple 1er SLA'].count()) * 100
            Si_No = (df_new.groupby('Cumple 1er SLA').size() / df_new['Cumple 1er SLA'].count()) * 100
            respuestas = [Si_No.NO]
            tipo = ['NO']
            explode = [0]  # Destacar algunos
            fig, ax = plt.subplots()
            ax.pie(respuestas, labels=tipo, explode=explode, autopct='%1.1f%%', shadow=True, startangle=90)



    if options == ['Cumple 2do SLA']:
        data = df_new.groupby(['Cumple 2do SLA']).size()
        if hasattr(data, 'SI') & hasattr(data, 'NO'):
            df = pd.DataFrame({'SI': {'Cumple 2do SLA': data.SI}, 'NO': {'Cumple 2do SLA': data.NO}})
            st.write(df)
            figura = df.iplot(kind="bar", bins=20, theme="white", title="Cumple 2do SLA",
                              xTitle='Cumple 2do SLA - No / Si', yTitle='Count', asFigure=True)
            st.plotly_chart(figura)
            df_new["porcentajes"] = (df_new.groupby('Cumple 1er SLA').size() / df_new['Cumple 1er SLA'].count()) * 100
            fig3 = df_new["Cumple 1er SLA"].iplot(kind="histogram", bins=20, theme="white", title="Cumple 1er SLA",
                                                  xTitle='Cumple 1er SLA - No / Si', yTitle='Count', asFigure=True)
            st.write('---')
            df_new['Porcentajes'] = (df_new.groupby('Cumple 2do SLA').size() / df_new['Cumple 2do SLA'].count()) * 100
            Si_No = (df_new.groupby('Cumple 2do SLA').size() / df_new['Cumple 2do SLA'].count()) * 100
            respuestas = [Si_No.SI, Si_No.NO]
            tipo = ['SI', 'NO']
            explode = [0.2, 0]  # Destacar algunos
            fig, ax = plt.subplots()
            ax.pie(respuestas, labels=tipo, explode=explode, autopct='%1.1f%%', shadow=True, startangle=90)
            st.title('Cumple 2do SLA - TECPLUSS %')
            st.pyplot(fig)
            # png_exp = plt.savefig('Grafica Pie Si-No.jpeg')
            st.write('---')
        elif hasattr(data, 'SI'):
            df = pd.DataFrame({'SI': {'Cumple 2do SLA': data.SI}})
            st.write(df)
            figura = df.iplot(kind="bar", bins=20, theme="white", title="Cumple 2do SLA",
                              xTitle='Cumple 2do SLA - Si', yTitle='Count', asFigure=True)
            st.plotly_chart(figura)
            df_new["porcentajes"] = (df_new.groupby('Cumple 1er SLA').size() / df_new['Cumple 1er SLA'].count()) * 100
            fig3 = df_new["Cumple 1er SLA"].iplot(kind="histogram", bins=20, theme="white", title="Cumple 1er SLA",
                                                  xTitle='Cumple 1er SLA - Si', yTitle='Count', asFigure=True)
            st.write('---')
            df_new['Porcentajes'] = (df_new.groupby('Cumple 2do SLA').size() / df_new['Cumple 2do SLA'].count()) * 100
            Si_No = (df_new.groupby('Cumple 2do SLA').size() / df_new['Cumple 2do SLA'].count()) * 100
            respuestas = [Si_No.SI]
            tipo = ['SI']
            explode = [0]  # Destacar algunos
            fig, ax = plt.subplots()
            ax.pie(respuestas, labels=tipo, explode=explode, autopct='%1.1f%%', shadow=True, startangle=90)
            st.title('Cumple 2do SLA - TECPLUSS %')
            st.pyplot(fig)
            # png_exp = plt.savefig('Grafica Pie Si-No.jpeg')
            st.write('---')
        elif hasattr(data, 'NO'):
            df = pd.DataFrame({'NO': {'Cumple 2do SLA': data.NO}})
            st.write(df)
            figura = df.iplot(kind="bar", bins=20, theme="white", title="Cumple 2do SLA",
                              xTitle='Cumple 2do SLA - No', yTitle='Count', asFigure=True)
            st.plotly_chart(figura)
            df_new["porcentajes"] = (df_new.groupby('Cumple 1er SLA').size() / df_new['Cumple 1er SLA'].count()) * 100
            fig3 = df_new["Cumple 1er SLA"].iplot(kind="histogram", bins=20, theme="white", title="Cumple 1er SLA",
                                                  xTitle='Cumple 1er SLA - No', yTitle='Count', asFigure=True)
            st.write('---')
            df_new['Porcentajes'] = (df_new.groupby('Cumple 2do SLA').size() / df_new['Cumple 2do SLA'].count()) * 100
            Si_No = (df_new.groupby('Cumple 2do SLA').size() / df_new['Cumple 2do SLA'].count()) * 100
            respuestas = [Si_No.NO]
            tipo = ['NO']
            explode = [0]  # Destacar algunos
            fig, ax = plt.subplots()
            ax.pie(respuestas, labels=tipo, explode=explode, autopct='%1.1f%%', shadow=True, startangle=90)
            st.title('Cumple 2do SLA - TECPLUSS %')
            st.pyplot(fig)
            # png_exp = plt.savefig('Grafica Pie Si-No.jpeg')
            st.write('---')
