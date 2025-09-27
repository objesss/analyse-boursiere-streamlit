# -*- coding: utf-8 -*-
import streamlit as st
import yfinance as yf
import pandas as pd
import numpy as np
import altair as alt

# --- CONFIGURATION INITIALE ET ÉTAT DE SESSION ---

# Initialiser l'état de session pour stocker les résultats et le type de graphique
if 'analysis_data' not in st.session_state:
    st.session_state.analysis_data = None
if 'graph_type' not in st.session_state:
    st.session_state.graph_type = 'Ligne' # Défaut pour le type de graphique
if 'ticker_input' not in st.session_state:
    st.session_state.ticker_input = 'TEST'


# --- Fonctions utilitaires ---

def calculate_cagr(data_series, min_points=2, max_years=5):
    """Calcule le Taux de Croissance Annuel Composé (TCAC) sur la période max. disponible (jusqu'à 5 ans)."""
    data_series = pd.to_numeric(data_series, errors='coerce').dropna()
    data_series_cagr = data_series.tail(max_years)
    
    if data_series_cagr.empty or len(data_series_cagr) < min_points:
        return None
    
    data_series_cagr = data_series_cagr.sort_index(ascending=True)
    start_value = data_series_cagr.iloc[0]
    end_value = data_series_cagr.iloc[-1]
    
    if start_value <= 0 or end_value <= 0:
        return None
        
    actual_years = len(data_series_cagr) - 1
    if actual_years == 0:
        return None
        
    return ((end_value / start_value) ** (1 / actual_years) - 1) * 100

def safe_format(val, is_percent=False, decimals=2):
    """Formate les valeurs en string, gère None/nan, et utilise le format français."""
    if val is None or (isinstance(val, str) and (val == "nan" or val.strip().lower() == 'none')):
        return "Non disponible"
    if isinstance(val, (int, float, np.number)):
         # Assure le format français (séparateur de milliers: espace, décimal: virgule)
         if is_percent:
            formatted = f"{val:,.2f}".replace('.', '#').replace(',', ' ').replace('#', ',')
         elif decimals == 0:
            formatted = f"{val:,.0f}".replace('.', '#').replace(',', ' ').replace('#', ',')
         else:
            formatted = f"{val:,.{decimals}f}".replace('.', '#').replace(',', ' ').replace('#', ',')
         
         return formatted + ('%' if is_percent else '')
    return str(val)

def create_plot_df(series, name):
    """Crée une DataFrame robuste pour le plotting Streamlit (Année: object, Valeur: float)."""
    if series.empty:
        return pd.DataFrame()
    
    df = series.to_frame(name=name).reset_index()
    df.columns = ['Année', name]
    
    # Conversion de l'index date en année string pour Altair (type Nominal)
    if pd.api.types.is_datetime64_any_dtype(df['Année']):
        df['Année'] = df['Année'].dt.year.astype(str)
    elif pd.api.types.is_numeric_dtype(df['Année']):
         df['Année'] = df['Année'].astype(int).astype(str)
         
    df[name] = pd.to_numeric(df[name], errors='coerce')
    
    return df.dropna(subset=[name]).sort_values(by='Année')

def get_financial_data(ticker):
    """Récupère et calcule les données financières, de valorisation et l'historique des ratios."""

    data = {
        'cagr_revenue': None, 'cagr_fcf': None, 'roce': None, 'net_debt_fcf_ratio': None,
        'latest_fcf': None, 'market_cap': None, 'enterprise_value': None, 'ev_fcf_ratio': None,
        'pe_ratio': None, 'pb_ratio': None, 'diagnosis': "",
        'raw_data_for_plot': {}, 
        'valuation_history': pd.DataFrame() 
    }
    
    skip_api_calls = False
    
    # Clés alternatives pour yfinance (mis à jour pour plus de robustesse)
    REVENUE_KEYS = ['Total Revenue', 'totalRevenue']
    OCF_KEYS = ['Operating Cash Flow', 'operatingCashflow']
    CAPEX_KEYS = ['Capital Expenditures', 'Capital Expenditure', 'Capital Spending', 'Purchase Of Property Plant And Equipment', 'Investment In Property Plant And Equipment']
    DEBT_TOTAL_KEYS = ['Total Debt', 'totalDebt', 'Total Liabilities'] # Ajout de Total Liabilities comme fallback pour la dette
    CASH_KEYS = ['Cash', 'Cash And Cash Equivalents', 'cash']
    EBIT_KEYS = ['ebit', 'Operating Income', 'operatingIncome']
    TOTAL_ASSETS_KEYS = ['Total Assets', 'Total assets']
    CURRENT_LIABILITIES_KEYS = ['Total Current Liabilities', 'Current Liabilities']
    NET_INCOME_KEYS = ['Net Income', 'NetIncome']
    BOOK_VALUE_KEYS = ['Total Stockholder Equity', 'Stockholders Equity']

    # --- Mode de Données Simulées (TEST) ---
    if ticker.upper() == "TEST":
        data['cagr_revenue'] = 18.5; data['cagr_fcf'] = 22.1; data['roce'] = 35.5
        data['net_debt_fcf_ratio'] = -0.5; data['latest_fcf'] = 15000000000 
        data['market_cap'] = 300000000000; data['enterprise_value'] = 290000000000 
        data['ev_fcf_ratio'] = 19.33; data['pe_ratio'] = 25.5; data['pb_ratio'] = 5.2
        data['diagnosis'] = "Mode TEST actif : Les données sont simulées."
        
        years_str = [str(y) for y in range(2020, 2025)]
        
        # DataFrames pour Streamlit 
        data['raw_data_for_plot']['Revenue'] = pd.DataFrame(
            {'Année': years_str, 'Chiffre d\'Affaires (USD)': [100e9, 115e9, 132e9, 152e9, 175e9]}
        )
        data['raw_data_for_plot']['FCF'] = pd.DataFrame(
            {'Année': years_str, 'Free Cash Flow (USD)': [50e9, 62e9, 77e9, 95e9, 115e9]}
        )
        data['raw_data_for_plot']['ROCE'] = pd.DataFrame(
            {'Année': years_str, 'ROCE (%)': [25.0, 30.0, 35.0, 32.0, 35.5]}
        )
        data['raw_data_for_plot']['NetDebt'] = pd.DataFrame(
            {'Année': years_str, 'Dette Nette (USD)': [5e9, 2e9, -1e9, -5e9, -8e9]}
        )
        
        # Historique de Valorisation Simulé (avec une NaN initiale pour tester la robustesse)
        data['valuation_history'] = pd.DataFrame({
            'Année': years_str,
            'EV/FCF (Valeur Ent./FCF)': [np.nan, 20.5, 18.0, 19.5, 19.3], 
            'P/E (Prix/Bénéfice)': [28.0, 26.5, 23.0, 24.5, 25.5],
            'P/B (Prix/Valeur Comptable)': [4.5, 4.8, 5.0, 5.5, 5.2]
        })
        
        skip_api_calls = True
        
    if not skip_api_calls:
        
        # --- 1. Récupération via yfinance ---
        try:
            stock = yf.Ticker(ticker) 
            info = stock.info
            
            # DataFrames
            cash_flow = pd.DataFrame(stock.cashflow).T
            income_stmt = pd.DataFrame(stock.financials).T
            balance_sheet = pd.DataFrame(stock.balance_sheet).T
            
            for df in [cash_flow, income_stmt, balance_sheet]:
                if not df.empty:
                    df.index = pd.to_datetime(df.index)
                    df.sort_index(ascending=True, inplace=True)

            # --- Calculs pour les Graphiques Historiques (CA, FCF, ROCE, Dette) ---
            
            # 1. Revenue (CA) - Correction appliquée ici
            revenue_key = next((key for key in REVENUE_KEYS if key in income_stmt.columns), None)
            if revenue_key and not income_stmt.empty:
                raw_rev = pd.to_numeric(income_stmt[revenue_key], errors='coerce').dropna()
                data['cagr_revenue'] = calculate_cagr(raw_rev)
                # S'assurer qu'il y a des données avant de créer le DF de plot
                if not raw_rev.empty:
                    data['raw_data_for_plot']['Revenue'] = create_plot_df(raw_rev, 'Chiffre d\'Affaires (USD)')
            
            # 2. Free Cash Flow (FCF)
            ocf_key = next((key for key in OCF_KEYS if key in cash_flow.columns), None)
            capex_key = next((key for key in CAPEX_KEYS if key in cash_flow.columns), None)
            
            if ocf_key and capex_key and not cash_flow.empty:
                 # Assurer l'addition correcte même si capex est négatif
                 fcf_series_raw = cash_flow[ocf_key] + cash_flow[capex_key] 
                 fcf_series = pd.to_numeric(fcf_series_raw, errors='coerce').dropna()
                 data['cagr_fcf'] = calculate_cagr(fcf_series)

                 if not fcf_series.empty:
                     data['latest_fcf'] = fcf_series.iloc[-1]
                     data['raw_data_for_plot']['FCF'] = create_plot_df(fcf_series, 'Free Cash Flow (USD)')
            
            # 3. ROCE
            latest_ebit_key = next((key for key in EBIT_KEYS if key in income_stmt.columns), None)
            latest_assets_key = next((key for key in TOTAL_ASSETS_KEYS if key in balance_sheet.columns), None)
            latest_liabilities_key = next((key for key in CURRENT_LIABILITIES_KEYS if key in balance_sheet.columns), None)
            
            roce_history_data = {}
            common_dates = income_stmt.index.intersection(balance_sheet.index).unique().sort_values(ascending=True)

            if latest_ebit_key and latest_assets_key and latest_liabilities_key and not common_dates.empty:
                for date in common_dates:
                    try:
                        ebit = income_stmt.loc[date, latest_ebit_key]
                        assets = balance_sheet.loc[date, latest_assets_key]
                        liabilities = balance_sheet.loc[date, latest_liabilities_key]
                        
                        if pd.notna(ebit) and pd.notna(assets) and pd.notna(liabilities):
                            capital_employed = assets - liabilities
                            if capital_employed != 0:
                                roce_val = (ebit / capital_employed) * 100
                                if roce_val > 1000: roce_val = np.nan # Évite les outliers extrêmes
                                roce_history_data[date] = roce_val
                                if date == common_dates[-1]: data['roce'] = roce_val
                    except Exception:
                        continue 

                roce_series = pd.Series(roce_history_data, name='ROCE (%)').resample('YE').last().dropna()
                data['raw_data_for_plot']['ROCE'] = create_plot_df(roce_series, 'ROCE (%)')
            
            # 4. Dette Nette
            cash_key = next((key for key in CASH_KEYS if key in balance_sheet.columns), None)
            debt_key_agg = next((key for key in DEBT_TOTAL_KEYS if key in balance_sheet.columns), None)
            total_debt, total_cash = 0, 0 

            net_debt_history = {}
            common_dates_debt = balance_sheet.index.unique().sort_values(ascending=True) 
            
            if cash_key and debt_key_agg and not common_dates_debt.empty:
                for date in common_dates_debt:
                    try:
                        total_cash_hist = balance_sheet.loc[date, cash_key]
                        total_debt_hist = balance_sheet.loc[date, debt_key_agg] if pd.notna(balance_sheet.loc[date, debt_key_agg]) else 0
                        
                        if pd.notna(total_cash_hist):
                            net_debt_history[date] = total_debt_hist - total_cash_hist
                            if date == common_dates_debt[-1]: 
                                total_debt = total_debt_hist
                                total_cash = total_cash_hist

                    except Exception:
                        continue
                
                if data['latest_fcf'] is not None and data['latest_fcf'] != 0:
                    net_debt = total_debt - total_cash
                    data['net_debt_fcf_ratio'] = net_debt / data['latest_fcf']
                
                net_debt_series = pd.Series(net_debt_history, name='Dette Nette (USD)').resample('YE').last().dropna()
                data['raw_data_for_plot']['NetDebt'] = create_plot_df(net_debt_series, 'Dette Nette (USD)')
            
            # 5. Valorisation et Historique des Ratios
            data['market_cap'] = info.get('marketCap')
            data['pe_ratio'] = info.get('trailingPE')
            data['pb_ratio'] = info.get('priceToBook')
            
            if data['market_cap'] is not None:
                data['enterprise_value'] = data['market_cap'] + total_debt - total_cash
                if data['enterprise_value'] is not None and data['latest_fcf'] is not None and data['latest_fcf'] > 0:
                    data['ev_fcf_ratio'] = data['enterprise_value'] / data['latest_fcf']
                    
            # 6. Historique des Ratios (Correction du EV/FCF dans la construction de la DataFrame)
            valuation_data_points = []
            prices = stock.history(period="5y")['Close'].resample('YE').last().dropna()
            
            years_for_val = prices.index.year.intersection(income_stmt.index.year).intersection(balance_sheet.index.year).intersection(cash_flow.index.year).unique().sort_values(ascending=True)
            shares_outstanding = info.get('sharesOutstanding') 

            for year in years_for_val:
                try:
                    latest_inc_date = income_stmt.index[income_stmt.index.year == year].max()
                    latest_bal_date = balance_sheet.index[balance_sheet.index.year == year].max()
                    latest_cf_date = cash_flow.index[cash_flow.index.year == year].max()

                    if latest_inc_date and latest_bal_date and latest_cf_date and shares_outstanding:
                        
                        net_income_val = income_stmt.loc[latest_inc_date, next((k for k in NET_INCOME_KEYS if k in income_stmt.columns), None)]
                        book_value_val = balance_sheet.loc[latest_bal_date, next((k for k in BOOK_VALUE_KEYS if k in balance_sheet.columns), None)]
                        
                        fcf_key = next((k for k in OCF_KEYS if k in cash_flow.columns), None)
                        capex_key_cf = next((k for k in CAPEX_KEYS if k in cash_flow.columns), None)
                        fcf_val = cash_flow.loc[latest_cf_date, fcf_key] + cash_flow.loc[latest_cf_date, capex_key_cf] 
                        
                        debt_key = next((k for k in DEBT_TOTAL_KEYS if k in balance_sheet.columns), None)
                        cash_key_bal = next((k for k in CASH_KEYS if k in balance_sheet.columns), None)

                        total_debt_hist = balance_sheet.loc[latest_bal_date, debt_key] if debt_key in balance_sheet.columns else 0
                        total_cash_hist = balance_sheet.loc[latest_bal_date, cash_key_bal] if cash_key_bal in balance_sheet.columns else 0
                        
                        price_index = prices.index[prices.index.year == year]
                        price = prices.loc[price_index[0]] if not price_index.empty else None
                        
                        if price is not None and pd.notna(net_income_val) and pd.notna(book_value_val) and pd.notna(fcf_val):
                            market_cap_hist = price * shares_outstanding
                            
                            pe = market_cap_hist / net_income_val if net_income_val > 0 else np.nan
                            pb = market_cap_hist / book_value_val if book_value_val > 0 else np.nan
                            
                            ev_hist = market_cap_hist + total_debt_hist - total_cash_hist
                            
                            # Correction: Éviter la division par zéro/valeur négative
                            ev_fcf = ev_hist / fcf_val if fcf_val > 0 else np.nan 

                            valuation_data_points.append({
                                'Année': str(year),
                                'P/E (Prix/Bénéfice)': pe,
                                'P/B (Prix/Valeur Comptable)': pb,
                                'EV/FCF (Valeur Ent./FCF)': ev_fcf,
                            })
                            
                except Exception:
                    continue
            
            # --- Préparation finale pour l'affichage des ratios ---
            val_df = pd.DataFrame(valuation_data_points).round(2).replace([np.inf, -np.inf], np.nan)
            # Garder uniquement les lignes qui ont au moins 1 valeur non-NaN dans les ratios
            val_df = val_df.dropna(subset=['EV/FCF (Valeur Ent./FCF)', 'P/E (Prix/Bénéfice)', 'P/B (Prix/Valeur Comptable)'], how='all')
            
            data['valuation_history'] = val_df

        except Exception as e:
            data['diagnosis'] = f"Erreur yfinance (Connexion/Ticker): La requête vers Yahoo! Finance a échoué. Détails: {e}"
            
    # --- Formatage des données pour l'affichage ---
    data['cagr_revenue'] = safe_format(data['cagr_revenue'], is_percent=True)
    data['cagr_fcf'] = safe_format(data['cagr_fcf'], is_percent=True)
    data['roce'] = safe_format(data['roce'], is_percent=True)
    data['ev_fcf_ratio'] = safe_format(data['ev_fcf_ratio'], decimals=2)
    data['pe_ratio'] = safe_format(data['pe_ratio'], decimals=2)
    data['pb_ratio'] = safe_format(data['pb_ratio'], decimals=2)
        
    if data['net_debt_fcf_ratio'] is not None and isinstance(data['net_debt_fcf_ratio'], (int, float)):
        val = data['net_debt_fcf_ratio']
        formatted = safe_format(abs(val), decimals=2)
        if val < 0:
            data['net_debt_fcf_ratio'] = f"-{formatted} (Trésorerie Nette Positive)"
        else:
            data['net_debt_fcf_ratio'] = formatted
    else:
        data['net_debt_fcf_ratio'] = "Non disponible"

    data['market_cap'] = safe_format(data['market_cap'], decimals=0)
    data['enterprise_value'] = safe_format(data['enterprise_value'], decimals=0)
    data['latest_fcf'] = safe_format(data['latest_fcf'], decimals=0)

    return data

def analyze_stock(ticker):
    """Analyse les données financières par rapport aux critères de Guillaume Bettin."""
    data = get_financial_data(ticker)
    
    results = {}
    
    # ... (Logique de check des critères inchangée, non reproduite pour la concision) ...
    def get_float_val(val_str):
        if val_str and isinstance(val_str, str) and val_str not in ["Non disponible"]:
            clean_val_str = val_str.split('(')[0].replace('%', '').replace(' ', '').replace('.', '').replace(',', '.').strip()
            if not clean_val_str: return None
            try:
                return float(clean_val_str)
            except ValueError:
                return None
        return None
        
    def check_cagr(cagr_val_str):
        val = get_float_val(cagr_val_str)
        if val is not None:
            return "✅ Réussi" if val > 10 else "❌ Échoué"
        return "⚪ Données indisponibles"
        
    results['cagr_revenue_check'] = check_cagr(data['cagr_revenue'])
    results['cagr_fcf_check'] = check_cagr(data['cagr_fcf'])

    roce_val = get_float_val(data['roce'])
    if roce_val is not None:
        results['roce_check'] = "✅ Réussi" if roce_val > 15 else "❌ Échoué"
    else:
        results['roce_check'] = "⚪ Données indisponibles"
        
    net_debt_ratio_val = data['net_debt_fcf_ratio']
    if net_debt_ratio_val and isinstance(net_debt_ratio_val, str):
        try:
            val_part = net_debt_ratio_val.split('(')[0].strip()
            sign = -1 if val_part.startswith('-') else 1
            val = get_float_val(val_part.replace('-', ''))
            
            if val is not None:
                 if sign == 1:
                    results['net_debt_fcf_check'] = "✅ Réussi" if val < 4 else "❌ Échoué"
                 else:
                    results['net_debt_fcf_check'] = "✅ Réussi (Trésorerie Nette)"
            else:
                 results['net_debt_fcf_check'] = "⚪ Données indisponibles"
        except ValueError:
            results['net_debt_fcf_check'] = "⚪ Données indisponibles"
    else:
        results['net_debt_fcf_check'] = "⚪ Données indisponibles"
        
    results['cagr_shares_check'] = "⚪ Non calculé dans cet exemple (données historiques non fiables via cette source)."
    
    return data, results


# --- Fonction de tracé SIMPLIFIÉE (sans gestion de thème manuelle) ---
def display_altair_chart(col, df_plot, value_column, title, graph_type='Ligne', is_ratio=False):
    """
    Crée et affiche un graphique Altair simplifié, utilisant le thème Streamlit par défaut.
    """
    
    with col:
        st.markdown(f"##### {title}")

        if df_plot is None or df_plot.empty or value_column not in df_plot.columns:
            st.info("Graphique non disponible (données insuffisantes).")
            return

        df_plot_copy = df_plot.copy() 
        df_plot_copy['Année'] = df_plot_copy['Année'].astype(str)
        
        # Nettoyage des données
        df_plot_copy[value_column] = pd.to_numeric(df_plot_copy[value_column], errors='coerce').replace([np.inf, -np.inf], np.nan)
        df_plot_clean = df_plot_copy.dropna(subset=[value_column])
        
        if df_plot_clean.empty:
            st.info("Graphique non disponible (données nettoyées insuffisantes).")
            return
            
        # Configuration des axes
        y_axis = alt.Y(value_column, title=value_column)
        # Pour les ratios comme ROCE, EV/FCF, on force l'axe Y à ne pas commencer à 0 si les valeurs sont loin de 0
        if is_ratio:
            y_axis = alt.Y(value_column, title=value_column, scale=alt.Scale(zero=False))
            
        # Configuration de base du graphique
        chart_base = alt.Chart(df_plot_clean).properties(
            height=250
        ).encode( 
            x=alt.X('Année:N', title='Année'),
            y=y_axis,
            tooltip=['Année', alt.Tooltip(value_column, format=',.2f')]
        ).interactive() # Permet le zoom et le déplacement
        
        # Utilisation de mark_line pour les ratios ou le mode Ligne
        if graph_type == 'Ligne':
             chart = chart_base.mark_line(point=True)
        else: # Barres
             chart = chart_base.mark_bar()
        
        try:
             # Utiliser 'streamlit' comme thème pour la compatibilité maximale
             # Suppression des configurations de thème manuelles
             st.altair_chart(chart.resolve_scale(y='independent'), use_container_width=True, theme='streamlit')
        except Exception as e:
             st.error(f"Erreur de rendu du graphique Altair ({title}). Le problème persiste. Détails: {e}")
             st.caption("Vérifiez les données brutes dans le code.")


# --- Fonction Principale ---

def main():
    """Fonction principale de l'application Streamlit."""
    st.set_page_config(page_title="Analyse Boursière", layout="wide")
    
    st.title("📈 Analyse Boursière Simplifiée et Valorisation Multi-Ratios")
    st.markdown("""
        Cette application analyse une action selon les critères de croissance, de rentabilité (ROCE), de santé financière (Dette/FCF)
        et intègre les principaux ratios de valorisation.
        ---
    """)
    
    # 1. Zone de saisie du ticker et sélecteurs
    col_t, col_g = st.columns([3, 1])
    
    # Récupérer le dernier ticker ou laisser vide
    default_ticker = st.session_state.get('ticker_input', 'TEST')
    ticker = col_t.text_input("Entrez le symbole boursier (ex: MSFT, AAPL) ou utilisez **TEST** pour un résultat simulé :", default_ticker).upper()
    
    # Gestion du type de graphique (ligne/barre)
    # Mise à jour directe de l'état de session via on_change
    def update_graph_type():
        st.session_state.graph_type = st.session_state.graph_radio_key
    
    graph_type = col_g.radio(
        "Type de graphique :",
        ('Ligne', 'Barre'),
        horizontal=True,
        key="graph_radio_key",
        on_change=update_graph_type,
        index=['Ligne', 'Barre'].index(st.session_state.graph_type)
    )
    
    # 2. Bouton de déclenchement de l'Analyse
    if st.button("Lancer l'Analyse") or (st.session_state.analysis_data is None and ticker != 'TEST'):
        
        if not ticker:
            st.error("Veuillez entrer un symbole boursier pour commencer.")
            # Si aucune donnée n'existe, on doit sortir ici si le ticker est vide
            if st.session_state.analysis_data is None: return
        
        # Enregistrement du ticker pour la persistance
        st.session_state.ticker_input = ticker

        if ticker:
            with st.spinner(f"Récupération et analyse des données pour **{ticker}** (Peut prendre quelques secondes, utilise yfinance)..."):
                data, results = analyze_stock(ticker)
            
            # Stockage des résultats complets dans l'état de session
            st.session_state.analysis_data = data
            st.session_state.analysis_results = results
            st.session_state.current_ticker = ticker
    
    
    # 3. Affichage des Résultats (Utilisation de l'état de session)
    if st.session_state.analysis_data:
        data = st.session_state.analysis_data
        results = st.session_state.analysis_results
        graph_type_current = st.session_state.graph_type
        
        # --- Affichage des Résultats ---
        
        st.markdown(f"## Résultats pour **{st.session_state.current_ticker}**")

        # 1. Diagnostic des erreurs API (si présent)
        if data.get('diagnosis'):
            if st.session_state.current_ticker == "TEST":
                 st.success("✅ Diagnostic du mode TEST :")
            else:
                 st.warning("🚨 Diagnostic de l'API (yfinance) : Les données manquantes peuvent être dues à un ticker non supporté ou à une structure de données irrégulière pour cette entreprise.")
            st.markdown(f"```\n{data['diagnosis']}\n```")

        # 2. Tableau des Critères d'Analyse
        st.subheader("✅ Critères d'Analyse (Guillaume Bettin)")
        st.table(pd.DataFrame({
            'Critères': ["1. Croissance du CA > 10%", "2. Croissance du FCF > 10%", "3. ROCE > 15%", "4. Ratio Dette Nette / FCF < 4", "5. Dilution des actions (TCAC < 5%)"],
            'Statut': [results['cagr_revenue_check'], results['cagr_fcf_check'], results['roce_check'], results['net_debt_fcf_check'], results['cagr_shares_check']]
        }))
        
        # 3. VALORISATION
        st.subheader("💰 Valorisation (Ratios Multiples)")
        
        def format_value_dollars(val):
            return f"{val} USD" if val != "Non disponible" else val

        st.table(pd.DataFrame({
            'Métriques': [
                "Market Cap (Capitalisation Boursière)", "Enterprise Value (Valeur d'Entreprise)", "Total Free Cash Flow (FCF) Annuel", "---",
                "Ratio EV / FCF", "Ratio P/E (Prix / Bénéfice)", "Ratio P/B (Prix / Valeur Comptable)",
            ],
            'Valeurs': [
                format_value_dollars(data.get('market_cap')), format_value_dollars(data.get('enterprise_value')), format_value_dollars(data.get('latest_fcf')), "---",
                data.get('ev_fcf_ratio'), data.get('pe_ratio'), data.get('pb_ratio')
            ],
            'Interprétation Rapide': [
                "Valeur de marché des actions.", "Coût total pour acheter l'entreprise (dette incluse).", "Flux de trésorerie disponible pour l'entreprise.", "---",
                "Multiple basé sur la valeur d'entreprise et le cash-flow.", "Multiple basé sur les bénéfices. Plus il est bas, moins cher est le bénéfice.", "Multiple basé sur les actifs nets (fonds propres)."
            ]
        }))

        # --- 4. Visualisations Historiques ---
        raw_data_for_plot = data.get('raw_data_for_plot', {})
        valuation_history = data.get('valuation_history')

        st.subheader(f"📊 Visualisations Historiques (Type: {graph_type_current})")
        st.markdown("---")
        
        # --- LIGNE 1 : Graphiques Financiers (4 colonnes) ---
        col_ca, col_fcf, col_roce, col_dette = st.columns(4) 
        
        # CA (Colonne 1 - Altair, Non Ratio)
        display_altair_chart(col_ca, raw_data_for_plot.get('Revenue'), "Chiffre d'Affaires (USD)", "Chiffre d'Affaires (CA)", graph_type_current, is_ratio=False)
        # FCF (Colonne 2 - Altair, Non Ratio)
        display_altair_chart(col_fcf, raw_data_for_plot.get('FCF'), "Free Cash Flow (USD)", "Free Cash Flow (FCF)", graph_type_current, is_ratio=False)
        # ROCE (Colonne 3 - Altair, Ratio)
        display_altair_chart(col_roce, raw_data_for_plot.get('ROCE'), "ROCE (%)", "ROCE", graph_type_current, is_ratio=True)
        # Dette Nette (Colonne 4 - Altair, Non Ratio)
        display_altair_chart(col_dette, raw_data_for_plot.get('NetDebt'), "Dette Nette (USD)", "Dette Nette", graph_type_current, is_ratio=False)
        
        st.markdown("---") 
        
        # --- LIGNE 2 : Graphiques de Valorisation (3 colonnes) ---
        st.markdown("#### Historique des Ratios de Valorisation")
        
        if valuation_history.empty:
             st.info("Historique des ratios de valorisation non disponible (données insuffisantes ou manquantes pour le calcul).")
        else:
            val_col_evfcf, val_col_pe, val_col_pb, val_col_spacer = st.columns([1, 1, 1, 1])
            
            # EV/FCF (Colonne 1 - Altair, Ratio)
            display_altair_chart(val_col_evfcf, valuation_history, 'EV/FCF (Valeur Ent./FCF)', "Ratio EV/FCF Historique", 'Ligne', is_ratio=True)

            # P/E (Colonne 2 - Altair, Ratio)
            display_altair_chart(val_col_pe, valuation_history, 'P/E (Prix/Bénéfice)', "Ratio P/E Historique", 'Ligne', is_ratio=True)
            # P/B (Colonne 3 - Altair, Ratio)
            display_altair_chart(val_col_pb, valuation_history, 'P/B (Prix/Valeur Comptable)', "Ratio P/B Historique", 'Ligne', is_ratio=True)
            
            # La 4ème colonne est vide.


if __name__ == '__main__':
    main()
