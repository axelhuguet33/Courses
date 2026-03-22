#!/usr/bin/env python3
"""
Tableau de bord budgétaire — Analyse de mes courses.
Lancer avec : streamlit run app.py
"""

import streamlit as st
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
from pathlib import Path
import re
import unicodedata

st.set_page_config(
    page_title="Mes Courses 🛒",
    page_icon="🛒",
    layout="wide",
)

BASE_DIR = Path(__file__).resolve().parent
DATA_TICKETS  = BASE_DIR / 'tickets.csv'
DATA_PRODUITS = BASE_DIR / 'produits.csv'

COULEURS = {
    'Leclerc':    '#0055A5',
    'Picard':     '#E30613',
    'Intermarché':'#FF8C00',
}

# ─── Chargement ──────────────────────────────────────────────────────────────

@st.cache_data
def load_tickets():
    df = pd.read_csv(DATA_TICKETS, parse_dates=['date'])
    df = df.sort_values('date').reset_index(drop=True)
    df['mois'] = df['date'].dt.to_period('M').dt.to_timestamp()
    df['remise'] = df['remise'].fillna(0)
    return df

@st.cache_data
def load_produits():
    df = pd.read_csv(DATA_PRODUITS, parse_dates=['date'])
    return df


def normalize_for_search(text: str) -> str:
    """Normalise un texte pour des recherches tolérantes aux accents/ligatures."""
    if text is None:
        return ''
    text = str(text).lower()
    text = text.replace('œ', 'oe').replace('æ', 'ae')
    text = ''.join(
        c for c in unicodedata.normalize('NFKD', text)
        if not unicodedata.combining(c)
    )
    text = re.sub(r'\s+', ' ', text).strip()
    return text

# ─── Garde : CSV manquant ─────────────────────────────────────────────────────

if not DATA_TICKETS.exists():
    st.error("❌ Le fichier `tickets.csv` n'existe pas encore.")
    st.info("Lance d'abord le script d'extraction :\n```\npython3 extract_tickets.py\n```")
    st.stop()

df = load_tickets()

# ─── Sidebar : filtres ───────────────────────────────────────────────────────

st.sidebar.title("🛒 Filtres")

enseignes_dispo = sorted(df['enseigne'].unique())
selected_enseignes = st.sidebar.multiselect(
    "Enseignes", enseignes_dispo, default=enseignes_dispo
)

date_min_data = df['date'].min().date()
date_max_data = df['date'].max().date()
date_range = st.sidebar.date_input(
    "Période",
    value=(date_min_data, date_max_data),
    min_value=date_min_data,
    max_value=date_max_data,
)

start_date = pd.Timestamp(date_range[0])
end_date   = pd.Timestamp(date_range[1] if len(date_range) > 1 else date_range[0])

df_f = df[
    df['enseigne'].isin(selected_enseignes) &
    (df['date'] >= start_date) &
    (df['date'] <= end_date)
].copy()

# ─── Titre ───────────────────────────────────────────────────────────────────

st.title("📊 Analyse de mes Courses")
st.caption(
    f"Données du **{date_min_data.strftime('%d/%m/%Y')}** "
    f"au **{date_max_data.strftime('%d/%m/%Y')}** — "
    f"{len(df_f)} ticket{'s' if len(df_f) > 1 else ''} sélectionné{'s' if len(df_f) > 1 else ''}"
)

if df_f.empty:
    st.warning("Aucune donnée pour les filtres sélectionnés.")
    st.stop()

# ─── KPIs ────────────────────────────────────────────────────────────────────

total_depense  = df_f['total_net'].sum()
moy_ticket     = df_f['total_net'].mean()
total_economise= df_f['remise'].sum()
nb_courses     = len(df_f)

# Dépense mensuelle moyenne
nb_mois = max((end_date - start_date).days / 30, 1)
moy_mensuelle = total_depense / nb_mois

col1, col2, col3, col4, col5 = st.columns(5)
col1.metric("💶 Total dépensé",       f"{total_depense:.2f} €")
col2.metric("📅 Moy. mensuelle",       f"{moy_mensuelle:.2f} €")
col3.metric("🧾 Ticket moyen",         f"{moy_ticket:.2f} €")
col4.metric("🏷️ Total économisé",      f"{total_economise:.2f} €")
col5.metric("🛍️ Nb de courses",        str(nb_courses))

st.divider()

# ─── Dépenses mensuelles ─────────────────────────────────────────────────────

st.subheader("📅 Dépenses par mois et par enseigne")

par_mois_enseigne = (
    df_f.groupby(['mois', 'enseigne'])['total_net']
    .sum()
    .reset_index()
)

col_a, col_b = st.columns([3, 2])

with col_a:
    fig_bar = px.bar(
        par_mois_enseigne,
        x='mois', y='total_net', color='enseigne',
        labels={'mois': '', 'total_net': 'Dépenses (€)', 'enseigne': 'Enseigne'},
        title='Dépenses mensuelles',
        color_discrete_map=COULEURS,
        text_auto='.0f',
    )
    fig_bar.update_layout(
        xaxis_tickformat='%b %Y',
        bargap=0.15,
        legend=dict(orientation='h', yanchor='bottom', y=1.02),
    )
    st.plotly_chart(fig_bar, use_container_width=True)

with col_b:
    par_enseigne_total = df_f.groupby('enseigne')['total_net'].sum().reset_index()
    fig_pie = px.pie(
        par_enseigne_total,
        values='total_net', names='enseigne',
        title='Répartition par enseigne',
        color='enseigne',
        color_discrete_map=COULEURS,
    )
    fig_pie.update_traces(textinfo='percent+label', textposition='inside')
    st.plotly_chart(fig_pie, use_container_width=True)

# ─── Moyenne mobile 30 jours ─────────────────────────────────────────────────

st.subheader("📈 Dépense lissée sur 30 jours (moyenne mobile)")
st.caption(
    "Lisse les gros achats de fin de mois pour estimer ta dépense réelle "
    "en vitesse de croisière. La barre bleue = les achats du jour, "
    "la courbe = la moyenne glissante."
)

par_jour = (
    df_f.groupby('date')['total_net']
    .sum()
    .reset_index()
    .set_index('date')
    .resample('D')
    .sum()
    .fillna(0)
    .reset_index()
)
par_jour['moyenne_30j'] = par_jour['total_net'].rolling(30, min_periods=1).mean()

fig_smooth = go.Figure()
fig_smooth.add_trace(go.Bar(
    x=par_jour['date'], y=par_jour['total_net'],
    name='Dépenses brutes', marker_color='#93C5FD', opacity=0.6,
))
fig_smooth.add_trace(go.Scatter(
    x=par_jour['date'], y=par_jour['moyenne_30j'],
    name='Moyenne mobile 30j', mode='lines',
    line=dict(color='#1D4ED8', width=2.5),
))
fig_smooth.update_layout(
    xaxis_title='', yaxis_title='€',
    legend=dict(orientation='h', yanchor='bottom', y=1.02),
    hovermode='x unified',
)
st.plotly_chart(fig_smooth, use_container_width=True)

st.divider()

# ─── Tableau des tickets ──────────────────────────────────────────────────────

st.subheader("🧾 Détail des tickets")

df_display = df_f[['date', 'enseigne', 'nb_articles', 'total_brut', 'remise', 'total_net']].copy()
df_display = df_display.sort_values('date', ascending=False)
df_display.columns = ['Date', 'Enseigne', 'Nb articles', 'Total brut (€)', 'Remise (€)', 'Total payé (€)']
df_display['Date'] = df_display['Date'].dt.strftime('%d/%m/%Y')

st.dataframe(
    df_display,
    use_container_width=True,
    hide_index=True,
    column_config={
        'Total brut (€)': st.column_config.NumberColumn(format="%.2f €"),
        'Remise (€)':     st.column_config.NumberColumn(format="%.2f €"),
        'Total payé (€)': st.column_config.NumberColumn(format="%.2f €"),
    }
)

# ─── Section produits (si disponible) ────────────────────────────────────────

if DATA_PRODUITS.exists():
    st.divider()
    st.subheader("🔍 Explorer les produits")

    df_prod = load_produits()
    df_prod_f = df_prod[
        df_prod['enseigne'].isin(selected_enseignes) &
        (pd.to_datetime(df_prod['date']) >= start_date) &
        (pd.to_datetime(df_prod['date']) <= end_date)
    ]

    col_x, col_y = st.columns([2, 1])
    with col_x:
        recherche = st.text_input("🔎 Rechercher un produit", placeholder="ex: avocat, eau, riz…")
    with col_y:
        enseigne_prod = st.selectbox("Enseigne", ['Toutes'] + enseignes_dispo)

    df_recherche = df_prod_f.copy()
    has_simplifie = 'nom_simplifié' in df_recherche.columns
    if recherche:
        needle = normalize_for_search(recherche)
        produit_norm = df_recherche['produit'].fillna('').map(normalize_for_search)
        mask = produit_norm.str.contains(re.escape(needle), na=False)
        if has_simplifie:
            simplifie_norm = df_recherche['nom_simplifié'].fillna('').map(normalize_for_search)
            mask = mask | simplifie_norm.str.contains(re.escape(needle), na=False)
        df_recherche = df_recherche[mask]
    if enseigne_prod != 'Toutes':
        df_recherche = df_recherche[df_recherche['enseigne'] == enseigne_prod]

    if not df_recherche.empty:
        cols_display = ['date', 'enseigne']
        if has_simplifie:
            cols_display.append('nom_simplifié')
        cols_display += ['produit', 'quantite', 'prix_unitaire', 'prix_total']
        df_recherche_display = df_recherche[cols_display].copy()
        rename_map = {'date': 'Date', 'enseigne': 'Enseigne', 'nom_simplifié': 'Nom simplifié',
                      'produit': 'Produit (original)', 'quantite': 'Qté',
                      'prix_unitaire': 'Prix unitaire (€)', 'prix_total': 'Prix total (€)'}
        df_recherche_display.rename(columns=rename_map, inplace=True)
        df_recherche_display['Date'] = pd.to_datetime(df_recherche_display['Date']).dt.strftime('%d/%m/%Y')
        st.dataframe(df_recherche_display, use_container_width=True, hide_index=True)
        st.caption(f"{len(df_recherche)} article(s) trouvé(s)")
    elif recherche:
        st.info("Aucun produit trouvé pour cette recherche.")

    # ─── Comparateur de prix inter-enseignes ──────────────────────────────────

    st.divider()
    st.subheader("⚖️ Comparateur de prix entre enseignes")
    st.caption(
        "Choisis un produit pour comparer son prix moyen selon l'enseigne. "
        "Les produits achetés dans plusieurs magasins apparaissent en premier."
    )

    has_simplifie_comp = 'nom_simplifié' in df_prod.columns
    if has_simplifie_comp:
        # Dropdown : multi-enseigne en premier, puis tous les autres
        ens_par_nom = df_prod.groupby('nom_simplifié')['enseigne'].nunique()
        noms_multi = sorted(ens_par_nom[ens_par_nom >= 2].index.tolist())
        noms_tous  = sorted(df_prod['nom_simplifié'].dropna().unique().tolist())
        noms_options = noms_multi + [n for n in noms_tous if n not in noms_multi]
        # Combine : multi-enseigne en premier, puis les autres
        noms_options = noms_multi + [n for n in noms_tous if n not in noms_multi]
        mot_cle = st.selectbox(
            "🔎 Produit à comparer",
            ['— choisir —'] + noms_options,
            key="comparateur_input",
        )
        if mot_cle == '— choisir —':
            mot_cle = ''
        use_simplifie_search = True
    else:
        mot_cle = st.text_input(
            "🔎 Mot-clé produit à comparer",
            placeholder="ex: avocat, couscous, fromage blanc, eau…",
            key="comparateur_input",
        )
        use_simplifie_search = False

    if mot_cle:
        if use_simplifie_search:
            # Cherche sur nom_simplifié (sans filtre enseigne)
            df_comp = df_prod[
                (df_prod['nom_simplifié'] == mot_cle) &
                (pd.to_datetime(df_prod['date']) >= start_date) &
                (pd.to_datetime(df_prod['date']) <= end_date)
            ].copy()
        else:
            df_comp = df_prod[
                df_prod['produit'].fillna('').map(normalize_for_search).str.contains(
                    re.escape(normalize_for_search(mot_cle)), na=False
                ) &
                (pd.to_datetime(df_prod['date']) >= start_date) &
                (pd.to_datetime(df_prod['date']) <= end_date)
            ].copy()

        if df_comp.empty:
            st.info(f"Aucun produit « {mot_cle} » trouvé dans la période sélectionnée.")
        else:
            # Calcul des statistiques par enseigne
            stats = (
                df_comp.groupby('enseigne')['prix_unitaire']
                .agg(
                    Prix_min='min',
                    Prix_moyen='mean',
                    Prix_max='max',
                    Nb_achats='count',
                )
                .reset_index()
                .round(2)
            )
            stats.columns = ['Enseigne', 'Min (€)', 'Moy. (€)', 'Max (€)', 'Nb achats']

            col_graph, col_table = st.columns([3, 2])

            with col_graph:
                # Barres : min / moyen / max par enseigne
                fig_comp = go.Figure()
                for _, row in stats.iterrows():
                    color = COULEURS.get(row['Enseigne'], '#888')
                    fig_comp.add_trace(go.Bar(
                        name=row['Enseigne'],
                        x=[row['Enseigne']],
                        y=[row['Moy. (€)']],
                        error_y=dict(
                            type='data',
                            symmetric=False,
                            array=[row['Max (€)'] - row['Moy. (€)']],
                            arrayminus=[row['Moy. (€)'] - row['Min (€)']],
                        ),
                        marker_color=color,
                        text=f"{row['Moy. (€)']:.2f} €",
                        textposition='outside',
                    ))
                fig_comp.update_layout(
                    title=f"Prix moyen de « {mot_cle} » (barres d'erreur = min/max)",
                    yaxis_title='Prix unitaire (€)',
                    showlegend=False,
                    height=380,
                )
                st.plotly_chart(fig_comp, use_container_width=True)

            with col_table:
                st.markdown("**Récapitulatif**")
                # Mettre en vert la ligne la moins chère
                min_moy = stats['Moy. (€)'].min()
                st.dataframe(
                    stats,
                    use_container_width=True,
                    hide_index=True,
                    column_config={
                        'Min (€)':    st.column_config.NumberColumn(format="%.2f €"),
                        'Moy. (€)':   st.column_config.NumberColumn(format="%.2f €"),
                        'Max (€)':    st.column_config.NumberColumn(format="%.2f €"),
                    }
                )
                # Indiquer le gagnant
                gagnant = stats.loc[stats['Moy. (€)'].idxmin(), 'Enseigne']
                ecart = stats['Moy. (€)'].max() - stats['Moy. (€)'].min()
                if len(stats) > 1:
                    st.success(f"✅ **{gagnant}** est le moins cher en moyenne (écart max : **{ecart:.2f} €**)")

            # Historique des prix dans le temps
            df_comp['date'] = pd.to_datetime(df_comp['date'])
            hover_cols = ['produit']
            if 'nom_simplifié' in df_comp.columns:
                hover_cols = ['produit', 'nom_simplifié']
            fig_hist = px.scatter(
                df_comp.sort_values('date'),
                x='date', y='prix_unitaire',
                color='enseigne',
                color_discrete_map=COULEURS,
                hover_data=hover_cols,
                title=f"Historique des prix — « {mot_cle} »",
                labels={'date': '', 'prix_unitaire': 'Prix unitaire (€)', 'enseigne': 'Enseigne'},
            )
            fig_hist.update_traces(marker_size=10)
            fig_hist.update_layout(
                xaxis_tickformat='%d/%m/%Y',
                legend=dict(orientation='h', yanchor='bottom', y=1.02),
                height=320,
            )
            st.plotly_chart(fig_hist, use_container_width=True)

    # ─── Top 10 produits ──────────────────────────────────────────────────────

    st.divider()
    st.subheader("🏆 Top 10 — produits où tu dépenses le plus")
    st.caption("Cumul de toutes les dépenses par produit sur la période sélectionnée.")

    grp_col = 'nom_simplifié' if 'nom_simplifié' in df_prod_f.columns else 'produit'
    top10 = (
        df_prod_f.groupby(grp_col)['prix_total']
        .sum()
        .reset_index()
        .sort_values('prix_total', ascending=False)
        .head(10)
    )
    top10['prix_total'] = top10['prix_total'].round(2)

    fig_top = px.bar(
        top10.sort_values('prix_total'),
        x='prix_total', y=grp_col,
        orientation='h',
        color_discrete_sequence=['#555'],
        labels={'prix_total': 'Total dépensé (€)', grp_col: '', 'enseigne': 'Enseigne'},
        text='prix_total',
    )
    fig_top.update_traces(texttemplate='%{text:.2f} €', textposition='outside')
    fig_top.update_layout(
        height=420,
        showlegend=True,
        legend=dict(orientation='h', yanchor='bottom', y=1.02),
        xaxis_title='Total dépensé (€)',
        margin=dict(l=10),
    )
    st.plotly_chart(fig_top, use_container_width=True)

    # ─── Détection d'inflation personnelle ───────────────────────────────────

    st.divider()
    st.subheader("📈 Inflation personnelle")
    st.caption(
        "Sélectionne un produit que tu achètes régulièrement pour voir si son prix "
        "a évolué depuis le début de tes courses. L'évolution est calculée entre "
        "le premier et le dernier achat."
    )

    # Produits achetés au moins 2 fois dans 2 mois différents
    # On groupe par nom_simplifié pour regrouper les variantes cross-enseigne
    df_prod_f2 = df_prod_f.copy()
    df_prod_f2['mois_achat'] = pd.to_datetime(df_prod_f2['date']).dt.to_period('M')
    grp_infl = 'nom_simplifié' if 'nom_simplifié' in df_prod_f2.columns else 'produit'
    eligibles = (
        df_prod_f2.groupby(grp_infl)
        .agg(nb_achats=('prix_unitaire', 'count'), nb_mois=('mois_achat', 'nunique'))
        .query('nb_achats >= 2 and nb_mois >= 2')
        .sort_values('nb_achats', ascending=False)
        .index.tolist()
    )

    if not eligibles:
        st.info("Pas assez d'achats répétés sur 2 mois différents pour calculer l'inflation.")
    else:
        produit_infl = st.selectbox(
            "Choisir un produit",
            eligibles,
            key='inflation_select',
        )
        df_infl = (
            df_prod_f2[df_prod_f2[grp_infl] == produit_infl]
            .sort_values('date')[['date', 'enseigne', 'produit', 'prix_unitaire']]
            .copy()
        )
        df_infl['date'] = pd.to_datetime(df_infl['date'])

        premier_prix = df_infl.iloc[0]['prix_unitaire']
        dernier_prix = df_infl.iloc[-1]['prix_unitaire']
        evolution_pct = ((dernier_prix - premier_prix) / premier_prix) * 100

        col_i1, col_i2, col_i3 = st.columns(3)
        col_i1.metric("Premier achat", f"{premier_prix:.2f} €", delta=None)
        col_i2.metric("Dernier achat", f"{dernier_prix:.2f} €",
                      delta=f"{dernier_prix - premier_prix:+.2f} €")
        col_i3.metric("Évolution", f"{evolution_pct:+.1f} %",
                      delta=f"{evolution_pct:+.1f} %",
                      delta_color="inverse")

        fig_infl = px.scatter(
            df_infl, x='date', y='prix_unitaire',
            color='enseigne',
            color_discrete_map=COULEURS,
            hover_data=['produit'],
            trendline='ols',
            labels={'date': '', 'prix_unitaire': 'Prix unitaire (€)', 'enseigne': 'Enseigne'},
            title=f"Évolution du prix — {produit_infl}",
        )
        fig_infl.update_traces(marker_size=11, selector=dict(mode='markers'))
        fig_infl.update_layout(
            xaxis_tickformat='%d/%m/%Y',
            legend=dict(orientation='h', yanchor='bottom', y=1.02),
            height=320,
        )
        st.plotly_chart(fig_infl, use_container_width=True)

# ─── Budget prévisionnel ──────────────────────────────────────────────────────

st.divider()
st.subheader("🔮 Budget prévisionnel")
st.caption(
    "Estimation de tes dépenses pour le mois en cours, basée sur ta moyenne "
    "des 3 derniers mois. Comparaison avec ce que tu as déjà dépensé ce mois-ci."
)

aujourd_hui = pd.Timestamp.today().normalize()
debut_mois  = aujourd_hui.replace(day=1)
fin_mois    = (debut_mois + pd.offsets.MonthEnd(1))

# Moyenne sur les 3 mois complets précédents
debut_3m = (debut_mois - pd.DateOffset(months=3))
df_3m = df[
    (df['date'] >= debut_3m) &
    (df['date'] < debut_mois) &
    df['enseigne'].isin(selected_enseignes)
]
moy_3m_par_mois = df_3m.groupby(df_3m['date'].dt.to_period('M'))['total_net'].sum()
budget_prevu = moy_3m_par_mois.mean() if len(moy_3m_par_mois) > 0 else 0

# Ce qui a déjà été dépensé ce mois-ci
df_ce_mois = df_f[df_f['date'] >= debut_mois]
depense_en_cours = df_ce_mois['total_net'].sum()

# Prorata : jours écoulés / jours dans le mois
jours_ecoules = (aujourd_hui - debut_mois).days + 1
jours_total   = (fin_mois - debut_mois).days + 1
prorata       = jours_ecoules / jours_total
budget_prorata = budget_prevu * prorata
ecart_prorata  = depense_en_cours - budget_prorata

col_p1, col_p2, col_p3, col_p4 = st.columns(4)
col_p1.metric(
    "Budget prévu (moy. 3 mois)",
    f"{budget_prevu:.2f} €" if budget_prevu else "—",
)
col_p2.metric(
    f"Dépensé ce mois ({jours_ecoules}j/{jours_total}j)",
    f"{depense_en_cours:.2f} €",
)
col_p3.metric(
    "Objectif prorata",
    f"{budget_prorata:.2f} €",
    help=f"Budget prévu × ({jours_ecoules}/{jours_total} jours écoulés)",
)
col_p4.metric(
    "Écart vs prorata",
    f"{ecart_prorata:+.2f} €",
    delta=f"{ecart_prorata:+.2f} €",
    delta_color="inverse",
)

# Barre de progression
if budget_prevu > 0:
    pct_budget = min(depense_en_cours / budget_prevu, 1.5)
    couleur_barre = (
        "🟢" if pct_budget < 0.8
        else "🟡" if pct_budget < 1.0
        else "🔴"
    )
    st.markdown(
        f"{couleur_barre} **{depense_en_cours:.2f} € dépensés** sur un budget estimé de "
        f"**{budget_prevu:.2f} €** "
        f"({pct_budget * 100:.0f} %)"
    )
    st.progress(float(min(pct_budget, 1.0)))

# Historique mensuel des 3 derniers mois pour comparaison
if not df_3m.empty:
    hist_mois = (
        df_3m.groupby([df_3m['date'].dt.to_period('M').dt.to_timestamp(), 'enseigne'])['total_net']
        .sum()
        .reset_index()
    )
    hist_mois.columns = ['mois', 'enseigne', 'total_net']
    # Ajouter le mois en cours
    if not df_ce_mois.empty:
        for ens, grp in df_ce_mois.groupby('enseigne'):
            hist_mois = pd.concat([hist_mois, pd.DataFrame([{
                'mois': debut_mois, 'enseigne': ens, 'total_net': grp['total_net'].sum()
            }])], ignore_index=True)

    fig_prev = px.bar(
        hist_mois,
        x='mois', y='total_net', color='enseigne',
        color_discrete_map=COULEURS,
        labels={'mois': '', 'total_net': '€', 'enseigne': 'Enseigne'},
        title='3 derniers mois + mois en cours',
        text_auto='.0f',
    )
    # Ligne budget prévu
    fig_prev.add_hline(
        y=budget_prevu,
        line_dash='dash', line_color='gray',
        annotation_text=f"Budget estimé : {budget_prevu:.0f} €",
        annotation_position="top left",
    )
    fig_prev.update_layout(
        xaxis_tickformat='%b %Y',
        barmode='stack',
        legend=dict(orientation='h', yanchor='bottom', y=1.02),
        height=340,
    )
    st.plotly_chart(fig_prev, use_container_width=True)
