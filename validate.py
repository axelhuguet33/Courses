#!/usr/bin/env python3
"""Script de validation des données extraites."""
import pandas as pd
import pdfplumber
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent
TICKET_DIR = BASE_DIR.parent

df_t = pd.read_csv(BASE_DIR / 'tickets.csv', parse_dates=['date'])
df_p = pd.read_csv(BASE_DIR / 'produits.csv', parse_dates=['date'])

print("=" * 60)
print("TICKETS — vue d'ensemble")
print("=" * 60)
print(df_t[['date', 'enseigne', 'total_brut', 'remise', 'total_net', 'nb_articles']].to_string())

print()
print("=" * 60)
print("ANOMALIES TICKETS")
print("=" * 60)
print("Dates manquantes    :", df_t['date'].isna().sum())
print("Totaux nets manquants:", df_t['total_net'].isna().sum())
print("nb_articles manquants:", df_t['nb_articles'].isna().sum())

print()
print("=" * 60)
print("STATS PRODUITS")
print("=" * 60)
print("Nb lignes produits  :", len(df_p))
print("Prix unitaire nul/NaN:", df_p[df_p['prix_unitaire'].isna() | (df_p['prix_unitaire'] == 0)].shape[0])
print("Produits sans nom   :", df_p[df_p['produit'].isna() | (df_p['produit'].str.strip() == '')].shape[0])

print()
print("=" * 60)
print("COHERENCE : somme des produits vs total_brut du ticket")
print("(écart > 0.05 € signale un problème d'extraction)")
print("=" * 60)
somme = df_p.groupby('fichier')['prix_total'].sum().reset_index()
somme.columns = ['fichier', 'somme_produits']
cmp = df_t.merge(somme, on='fichier', how='left')
cmp['ecart'] = (cmp['total_brut'] - cmp['somme_produits']).round(2)
cmp['somme_produits'] = cmp['somme_produits'].round(2)

# Lignes avec écart significatif
problemes = cmp[cmp['ecart'].abs() > 0.05]
ok = cmp[cmp['ecart'].abs() <= 0.05]
print(f"✅ Tickets OK         : {len(ok)}")
print(f"⚠️  Tickets avec écart : {len(problemes)}")
if not problemes.empty:
    print()
    print(problemes[['fichier', 'enseigne', 'total_brut', 'somme_produits', 'ecart']].to_string(index=False))

print()
print("=" * 60)
print("TICKETS SANS PRODUITS (extraction vide)")
print("=" * 60)
fichiers_avec_produits = set(df_p['fichier'].unique())
sans_produits = df_t[~df_t['fichier'].isin(fichiers_avec_produits)]
if sans_produits.empty:
    print("✅ Tous les tickets ont au moins un produit extrait")
else:
    print(sans_produits[['fichier', 'enseigne', 'date']].to_string(index=False))

print()
print("=" * 60)
print("RECAP PAR ENSEIGNE")
print("=" * 60)
recap = df_t.groupby('enseigne').agg(
    nb_tickets=('total_net', 'count'),
    total_depense=('total_net', 'sum'),
    ticket_moyen=('total_net', 'mean'),
    total_economise=('remise', 'sum'),
).round(2)
print(recap.to_string())
