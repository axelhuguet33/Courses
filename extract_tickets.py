#!/usr/bin/env python3
"""
Extraction des tickets de caisse PDF → CSV.
Supporte : E.Leclerc (Nice & Grasse), Picard Surgelés, Intermarché, La Fourche.

Génère deux fichiers :
  - tickets.csv   : une ligne par ticket (date, enseigne, totaux)
  - produits.csv  : une ligne par article acheté
"""

import pdfplumber
import pandas as pd
import re
import os
from datetime import datetime
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent  # /ticket de caisse/


def parse_prix(s: str) -> float:
    """Convertit une chaîne '2,50' ou '2.50' en float."""
    return float(re.sub(r'[^\d.,]', '', s).replace(',', '.'))


# ─── LECLERC ─────────────────────────────────────────────────────────────────

def extraire_leclerc(texte: str, fichier: str):
    lignes = texte.split('\n')

    # ── Date ──────────────────────────────────────────────────────────────────
    # Cherche "DD/MM/YY" dans les premières lignes (ligne code après "Caisse …")
    date = None
    for l in lignes[:15]:
        m = re.search(r'\b(\d{2}/\d{2}/\d{2})\b', l)
        if m:
            d, mo, y = m.group(1).split('/')
            date = datetime(2000 + int(y), int(mo), int(d)).date()
            break
    # Fallback : nom de fichier "Ticket du DD.MM.YYYY"
    if not date:
        m = re.search(r'(\d{2})\.(\d{2})\.(\d{4})', fichier)
        if m:
            date = datetime(int(m.group(3)), int(m.group(2)), int(m.group(1))).date()

    # ── Totaux ────────────────────────────────────────────────────────────────
    total_brut = remise = total_net = None
    nb_articles = None
    for l in lignes:
        m = re.search(r'[Tt]otal\s+(\d+)\s+articles\s+([\d.,]+)', l)
        if m:
            nb_articles = int(m.group(1))
            total_brut = parse_prix(m.group(2))
        m = re.search(r'Bon immediat\s+([\d.,]+)', l, re.IGNORECASE)
        if m:
            remise = parse_prix(m.group(1))
        m = re.search(r'Reste [àa] payer\s+([\d.,]+)', l, re.IGNORECASE)
        if m:
            total_net = parse_prix(m.group(1))

    remise = remise or 0.0
    if total_net is None and total_brut is not None:
        total_net = round(total_brut - remise, 2)

    # ── Délimitation de la section produits ───────────────────────────────────
    # Format 1 (Nice) : catégories ">>" — Format 2 (Grasse) : header "TTC TVA"
    has_categories = any(l.strip().startswith('>>') for l in lignes)

    start_idx = len(lignes)
    end_idx = len(lignes)

    if has_categories:
        for i, l in enumerate(lignes):
            if l.strip().startswith('>>'):
                start_idx = i
                break
    else:
        for i, l in enumerate(lignes):
            if l.strip() in ('TTC TVA', 'TTC', '€'):
                start_idx = i + 1
                break

    for i in range(start_idx, len(lignes)):
        if re.match(r'^-{3,}', lignes[i].strip()):
            end_idx = i
            break

    product_lines = lignes[start_idx:end_idx]

    # ── Extraction des produits ───────────────────────────────────────────────
    produits = []
    categorie = None
    i = 0
    BRUIT_LECLERC = (
        'TOTAL', 'TVA', 'BON ', 'REMIS', 'RESTE', 'CB ', 'COUPON', 'CODE',
        'NO AUTO', 'TEL', 'ARTICLE', 'CAISSE', 'HOTESSE', 'TICKET'
    )

    def nom_valide(nom: str) -> bool:
        # Doit contenir au moins une lettre (évite les lignes purement numériques OCR)
        if not re.search(r'[A-Za-zÀ-ÿ]', nom):
            return False
        up = nom.upper()
        if any(up.startswith(k.upper()) for k in BRUIT_LECLERC):
            return False
        if any(k in up for k in ('RESTE A PAYER', 'TOTAL', 'CB', 'TEL', 'NO AUTO')):
            return False
        return True

    while i < len(product_lines):
        l = product_lines[i].strip()
        i += 1

        if not l:
            continue

        if l.startswith('>>'):
            categorie = l[2:].strip()
            continue

        # Trouver la prochaine ligne non vide (pour le look-ahead)
        next_l = ''
        next_j = i
        for j in range(i, len(product_lines)):
            if product_lines[j].strip():
                next_l = product_lines[j].strip()
                next_j = j
                break

        # "N X PRIX€ TOTAL" ou "N X PRIX€ TOTAL CODE_TVA" (ex: "3 X 1.50€ 4.50" ou "3 X 1.39€ 4.17 1")
        m_qty = re.match(r'^(\d+)\s+[Xx]\s+([\d.,]+)€\s+([\d.,]+)(?:\s+\d+)?$', next_l)
        # "N,NNNkg X PRIX€/kg TOTAL" ou avec code TVA (ex: "1.628kg X 1.99€/kg 3.24" ou "0.254kg X 3.19€/kg 0.81 1")
        m_weight = re.match(r'^([\d.,]+)\s*kg\s+[Xx]\s+([\d.,]+)€/kg\s+([\d.,]+)(?:\s+\d+)?$', next_l)

        if m_qty:
            produits.append({
                'produit': l,
                'quantite': float(m_qty.group(1)),
                'prix_unitaire': parse_prix(m_qty.group(2)),
                'prix_total': parse_prix(m_qty.group(3)),
                'categorie': categorie,
            })
            i = next_j + 1
            continue

        elif m_weight:
            produits.append({
                'produit': l,
                'quantite': parse_prix(m_weight.group(1)),
                'prix_unitaire': parse_prix(m_weight.group(2)),
                'prix_total': parse_prix(m_weight.group(3)),
                'categorie': categorie,
            })
            i = next_j + 1
            continue

        # Ignorer les lignes de type quantité/poids orphelines
        if re.match(r'^\d+\s+[Xx]\s+', l) or re.match(r'^[\d.,]+\s*kg\s+[Xx]\s+', l):
            continue

        if has_categories:
            # Format 1 : "PRODUIT NOM  PRIX" ou "PRODUIT NOM  PRIX  CODE_TVA"
            # Le code TVA (chiffre final) est optionnel selon le magasin
            m = re.match(r'^(.+?)\s+([\d.,]+)(?:\s+\d+)?$', l)
            if m:
                nom = m.group(1).strip()
                prix = parse_prix(m.group(2))
                if not nom_valide(nom):
                    continue
                produits.append({
                    'produit': nom,
                    'quantite': 1,
                    'prix_unitaire': prix,
                    'prix_total': prix,
                    'categorie': categorie,
                })
        else:
            # Format sans catégories : avec ou sans code TVA final
            # Filtrer les lignes de bruit (coupons, remises nommées…)
            if any(l.upper().startswith(k.upper()) for k in BRUIT_LECLERC):
                pass  # ignoré ci-dessous
            else:
                m = re.match(r'^(.+?)\s+([\d.,]+)(?:\s+\d+)?$', l)
                if m:
                    nom = m.group(1).strip()
                    prix = parse_prix(m.group(2))
                    if prix > 0 and nom_valide(nom):
                        produits.append({
                            'produit': nom,
                            'quantite': 1,
                            'prix_unitaire': prix,
                            'prix_total': prix,
                            'categorie': None,
                        })
            # Remises lots / remise immédiate : "Remises lots -12.00" → ajuster le dernier produit
            m_remise = re.match(r'^Remises?\s+\w+\s+-(\d+[.,]\d+)$', l, re.IGNORECASE)
            if m_remise and produits:
                montant = parse_prix(m_remise.group(1))
                produits[-1]['prix_total'] = round(produits[-1]['prix_total'] - montant, 2)
                produits[-1]['prix_unitaire'] = round(produits[-1]['prix_unitaire'] - montant, 2)

    # Garde-fou OCR : on retire les lignes avec prix aberrant pour le ticket.
    if total_net and produits:
        seuil_prix_ligne = max(40.0, float(total_net) * 1.2)
        produits = [
            p for p in produits
            if p.get('prix_total') is not None and 0 < float(p['prix_total']) <= seuil_prix_ligne
        ]

    ticket = {
        'date': date,
        'enseigne': 'Leclerc',
        'total_brut': total_brut,
        'remise': remise,
        'total_net': total_net,
        'nb_articles': nb_articles,
        'fichier': os.path.basename(fichier),
    }
    return ticket, produits


# ─── PICARD ──────────────────────────────────────────────────────────────────

def extraire_picard(texte: str, fichier: str):
    lignes = texte.split('\n')

    # ── Date : ligne "N  DD.MM.YY  HH:MM  …" ─────────────────────────────────
    date = None
    for l in lignes:
        m = re.search(r'\b(\d{2}\.\d{2}\.\d{2})\s+\d{2}:\d{2}\b', l)
        if m:
            d, mo, y = m.group(1).split('.')
            date = datetime(2000 + int(y), int(mo), int(d)).date()
            break

    # ── Totaux ────────────────────────────────────────────────────────────────
    total_brut = remise = total_net = None
    nb_articles = None
    for l in lignes:
        m = re.search(r'Total sans remise\s+([\d,]+)\s+€', l)
        if m:
            total_brut = parse_prix(m.group(1))
        m = re.search(r'Total des remises\s+(-?[\d,]+)\s+€', l)
        if m:
            remise = abs(parse_prix(m.group(1)))
        m = re.search(r'TOTAL\s+\((\d+)\)\s+([\d,]+)\s+€', l)
        if m:
            nb_articles = int(m.group(1))
            total_net = parse_prix(m.group(2))

    remise = remise or 0.0
    if total_brut is None and total_net is not None:
        total_brut = round(total_net + remise, 2)

    # ── Produits ─────────────────────────────────────────────────────────────
    # Format :
    #   Achat simple  → "V1 *Nom produit  4,55 €"
    #   Achat multiple→ "V1 *Nom produit" puis "2 * 11,50  23,00 €"
    produits = []
    i = 0
    while i < len(lignes):
        l = lignes[i].strip()
        i += 1

        # Remise globale (pas un produit)
        if re.match(r'^S[eé]lection Picard', l, re.IGNORECASE):
            continue

        # Achat simple : "V1 *Nom  PRIX €"
        m_single = re.match(r'^V\d+\s+\*(.+?)\s+([\d,]+)\s+€$', l)
        if m_single:
            produits.append({
                'produit': m_single.group(1).strip(),
                'quantite': 1,
                'prix_unitaire': parse_prix(m_single.group(2)),
                'prix_total': parse_prix(m_single.group(2)),
                'categorie': 'Surgelés',
            })
            continue

        # Nom de produit seul (achat multiple, suite sur ligne suivante)
        m_name = re.match(r'^V\d+\s+\*(.+)$', l)
        if m_name:
            # Chercher la prochaine ligne non vide
            next_l = ''
            next_j = i
            for j in range(i, len(lignes)):
                if lignes[j].strip():
                    next_l = lignes[j].strip()
                    next_j = j
                    break

            m_qty = re.match(r'^(\d+)\s+\*\s+([\d,]+)\s+([\d,]+)\s+€$', next_l)
            if m_qty:
                produits.append({
                    'produit': m_name.group(1).strip(),
                    'quantite': int(m_qty.group(1)),
                    'prix_unitaire': parse_prix(m_qty.group(2)),
                    'prix_total': parse_prix(m_qty.group(3)),
                    'categorie': 'Surgelés',
                })
                i = next_j + 1
            # else : ligne mal formée, on ignore

    ticket = {
        'date': date,
        'enseigne': 'Picard',
        'total_brut': total_brut,
        'remise': remise,
        'total_net': total_net,
        'nb_articles': nb_articles,
        'fichier': os.path.basename(fichier),
    }
    return ticket, produits


# ─── INTERMARCHÉ ─────────────────────────────────────────────────────────────

def extraire_intermarche(texte: str, fichier: str):
    lignes = texte.split('\n')

    # ── Date : "HH:MM:SS  D/MM/YYYY" en bas du ticket ─────────────────────────
    date = None
    for l in lignes:
        m = re.search(r'\d{2}:\d{2}:\d{2}\s+(\d{1,2}/\d{2}/\d{4})', l)
        if m:
            parts = m.group(1).split('/')
            date = datetime(int(parts[2]), int(parts[1]), int(parts[0])).date()
            break

    # ── Totaux ────────────────────────────────────────────────────────────────
    total_brut = remise = total_net = None
    nb_articles = None
    for l in lignes:
        m = re.search(r'MONTANT DU\s+([\d,]+)\s+EUR', l)
        if m:
            total_brut = parse_prix(m.group(1))
        m = re.search(r'REMISE FIDELITE\s+([\d,]+)\s+EUR', l)
        if m:
            remise = parse_prix(m.group(1))
        # Remises immédiates (ex: "REMISES IMMEDIATES 1 -0,28 EUR")
        m = re.search(r'REMISES? IMME[DI]+ATES?\s+\d+\s+-(\d+[,.]\d+)\s+EUR', l, re.IGNORECASE)
        if m:
            remise = round((remise or 0.0) + parse_prix(m.group(1)), 2)
        m = re.search(r'CB SANS CONTACT\s+([\d,]+)\s+EUR', l)
        if m:
            total_net = parse_prix(m.group(1))
        m = re.search(r"Nombre d.articles vendus=\s*(\d+)", l)
        if m:
            nb_articles = int(m.group(1))

    remise = remise or 0.0
    if total_net is None and total_brut is not None:
        total_net = round(total_brut - remise, 2)

    # ── Produits : "NOM PRODUIT  PRIX EUR A" ─────────────────────────────────
    produits = []
    STOP = {'MONTANT', 'REMISE', 'CB SANS', 'NOMBRE', 'TOTAL', 'ESPECES',
            'A RENDRE', 'INTERMARCHE', 'OUVERT', 'TEL', 'RECAP', 'CODE TVA',
            'CARTE', 'MERCI DE', 'DE 8H', 'LE DIMA', 'AVE', '602 ', 'ST L',
            'RECAPITULATIF', 'MES AVANTAGES', 'AVANTAGE', 'ANCIEN', 'NOUVEAU',
            'RETROUVEZ', "JUSQU'", 'CE MOIS', 'DEFEND', 'MA CARTE'}
    for l in lignes:
        ls = l.strip()
        if not ls:
            continue
        if any(ls.upper().startswith(kw.upper()) for kw in STOP):
            continue

        # Produit standard : "NOM PRIX EUR [A-D]"
        m = re.match(r'^(.+?)\s+([\d,]+)\s+EUR\s+[A-D]$', ls)
        if m:
            produits.append({
                'produit': m.group(1).strip(),
                'quantite': 1,
                'prix_unitaire': parse_prix(m.group(2)),
                'prix_total': parse_prix(m.group(2)),
                'categorie': None,
            })
            continue

        # Remise immédiate inline : "2EME A -30% NOM -0,28" ou similaire
        m_remise = re.match(r'^.+\s+-(\d+[,.]\d+)$', ls)
        if m_remise and produits:
            montant = parse_prix(m_remise.group(1))
            produits[-1]['prix_total'] = round(produits[-1]['prix_total'] - montant, 2)
            produits[-1]['prix_unitaire'] = round(produits[-1]['prix_unitaire'] - montant, 2)

    ticket = {
        'date': date,
        'enseigne': 'Intermarché',
        'total_brut': total_brut,
        'remise': remise,
        'total_net': total_net,
        'nb_articles': nb_articles,
        'fichier': os.path.basename(fichier),
    }
    return ticket, produits


# ─── LA FOURCHE ──────────────────────────────────────────────────────────────

def extraire_la_fourche(texte: str, fichier: str):
    """Extraction depuis facture La Fourche (format invoice structurée avec tables pdfplumber).
    
    La Fourche est une invoice digitale générée avec pdfplumber tables extraction.
    Date et totaux extraits du texte, produits extraits des tables.
    """
    lignes = texte.split('\n')

    # ── Date : extraction via regex DD/MM/YYYY ──
    date = None
    for ligne in lignes[:15]:  # Cherche dans l'en-tête seulement
        m = re.search(r'\b(\d{2})/(\d{2})/(\d{4})\b', ligne)
        if m:
            date = datetime(int(m.group(3)), int(m.group(2)), int(m.group(1))).date()
            break

    # ── Totaux : extraction du texte ──
    total_brut = remise = total_net = None
    for ligne in lignes:
        # Cherche les totaux dans les patterns standards
        m = re.search(r'Total\s+hors\s+remise\s+([\d.,]+)\s*€', ligne, re.IGNORECASE)
        if m:
            total_brut = parse_prix(m.group(1))
            continue

        m = re.search(r'^Remise\s+([\d.,]+)\s*€', ligne, re.IGNORECASE)
        if m:
            remise = parse_prix(m.group(1))
            continue

        m = re.search(r'^Total\s+TTC\s+([\d.,]+)\s*€', ligne, re.IGNORECASE)
        if m:
            total_net = parse_prix(m.group(1))

    remise = remise or 0.0
    if total_net is None and total_brut is not None:
        total_net = round(total_brut - remise, 2)

    # ── Extraction des produits : tables pdfplumber ──
    produits = []
    try:
        with pdfplumber.open(fichier) as pdf:
            produits = _extraire_produits_la_fourche_tables(pdf)
    except FileNotFoundError:
        print(f"  ⚠️  Fichier introuvable: {fichier}")
    except Exception as e:
        print(f"  ⚠️  Erreur extraction La Fourche ({os.path.basename(fichier)}): {e}")

    nb_articles = len(produits)

    ticket = {
        'date': date,
        'enseigne': 'La Fourche',
        'total_brut': total_brut,
        'remise': remise,
        'total_net': total_net,
        'nb_articles': nb_articles,
        'fichier': os.path.basename(fichier),
    }
    return ticket, produits


def _extraire_produits_la_fourche_tables(pdf):
    """Extraction des produits depuis les tables pdfplumber d'une facture La Fourche.
    
    Format table La Fourche: [Ref, Désignation, Qte, P.U HT, TVA %, Total TTC, Remise TTC, Montant TTC]
    """
    produits = []

    for page in pdf.pages:
        tables = page.extract_tables()
        if not tables:
            continue

        for table in tables:
            # Vérifier que c'est la table des produits
            if not table or len(table) < 2:
                continue

            header = table[0]
            if not any('Référence' in str(h) for h in header):
                continue

            # Traiter les lignes de produits
            for row in table[1:]:
                if not row or not row[0]:
                    continue

                # Valider la référence produit
                ref = str(row[0]).strip()
                if not re.match(r'^\d-[A-Z]{3}-\d', ref):
                    continue  # Pas une référence La Fourche

                # Extraire les champs
                designation = _normaliser_designation(row[1] if len(row) > 1 else '')
                if not designation:
                    continue

                qte = _extraire_quantite(row[2] if len(row) > 2 else '1')
                prix_ttc = _extraire_prix(row[7] if len(row) > 7 else row[5])

                if prix_ttc <= 0:
                    continue

                produits.append({
                    'produit': designation,
                    'quantite': qte,
                    'prix_unitaire': round(prix_ttc / qte if qte > 0 else prix_ttc, 2),
                    'prix_total': prix_ttc,
                    'categorie': 'Bio/Éco',
                })

    return produits


def _normaliser_designation(designation_raw: str) -> str:
    """Normalise le nom d'un produit (compact, pas de newlines)."""
    if not designation_raw:
        return ''
    return designation_raw.replace('\n', ' ').strip()


def _extraire_quantite(qte_str: str) -> int:
    """Extrait la quantité depuis une chaîne."""
    if not qte_str:
        return 1
    try:
        return int(str(qte_str).strip())
    except ValueError:
        return 1


def _extraire_prix(prix_str: str) -> float:
    """Extrait le prix depuis une chaîne (tolérant les erreurs)."""
    if not prix_str:
        return 0.0
    try:
        return parse_prix(prix_str)
    except (ValueError, AttributeError):
        return 0.0


# ─── ORCHESTRATION ───────────────────────────────────────────────────────────

def traiter_pdf(chemin: Path, enseigne: str):
    try:
        with pdfplumber.open(chemin) as pdf:
            texte = '\n'.join(p.extract_text() or '' for p in pdf.pages)
    except Exception as e:
        print(f"  ✗ Erreur lecture {chemin.name}: {e}")
        return None, []

    if enseigne == 'Leclerc':
        return extraire_leclerc(texte, str(chemin))
    elif enseigne == 'Picard':
        return extraire_picard(texte, str(chemin))
    elif enseigne == 'Intermarché':
        return extraire_intermarche(texte, str(chemin))
    elif enseigne == 'La Fourche':
        return extraire_la_fourche(texte, str(chemin))
    return None, []


def main():
    print("🔍 Extraction des tickets de caisse...\n")

    DOSSIERS = {
        'Leclerc':     BASE_DIR / 'Leclerc',
        'Picard':      BASE_DIR / 'Picard',
        'Intermarché': BASE_DIR / 'intermarché',
        'La Fourche':  BASE_DIR / 'La Fourche',
    }

    all_tickets = []
    all_produits = []

    for enseigne, dossier in DOSSIERS.items():
        pdfs = sorted(dossier.glob('*.pdf'))
        print(f"📂 {enseigne} : {len(pdfs)} fichiers")
        for pdf_path in pdfs:
            ticket, produits = traiter_pdf(pdf_path, enseigne)
            if ticket:
                all_tickets.append(ticket)
                for p in produits:
                    p['date'] = ticket['date']
                    p['enseigne'] = enseigne
                    p['fichier'] = ticket['fichier']
                    all_produits.append(p)
                ok = ticket['total_net'] is not None
                symbole = '✓' if ok else '⚠ total manquant'
                print(f"  {'✓' if ok else '⚠'} {pdf_path.name[:55]:<55} {ticket['date']}  {ticket['total_net']} €")
            else:
                print(f"  ✗ {pdf_path.name} — extraction échouée")
        print()

    df_tickets = pd.DataFrame(all_tickets)
    df_produits = pd.DataFrame(all_produits)

    out_dir = Path(__file__).resolve().parent  # même dossier que ce script

    # ── Enrichissement nom_simplifié ──────────────────────────────────────────
    corr_path = out_dir / 'correspondances.csv'
    if corr_path.exists():
        df_corr = pd.read_csv(corr_path)
        df_produits = df_produits.merge(
            df_corr.rename(columns={'produit_original': 'produit'})[['produit', 'nom_simplifié']],
            on='produit', how='left'
        )
        df_produits['nom_simplifié'] = df_produits['nom_simplifié'].fillna(df_produits['produit'])
        nb_enrichis = df_produits['nom_simplifié'].ne(df_produits['produit']).sum()
        print(f"🏷️  {nb_enrichis}/{len(df_produits)} articles enrichis avec nom_simplifié")
    else:
        df_produits['nom_simplifié'] = df_produits['produit']
        print("ℹ️  Pas de correspondances.csv — lance generer_correspondances.py pour créer le mapping.")

    df_tickets.to_csv(out_dir / 'tickets.csv', index=False, encoding='utf-8-sig')
    df_produits.to_csv(out_dir / 'produits.csv', index=False, encoding='utf-8-sig')

    print(f"✅ {len(all_tickets)} tickets extraits  →  tickets.csv")
    print(f"✅ {len(all_produits)} lignes produits   →  produits.csv")

    if not df_tickets.empty:
        df_tickets['date'] = pd.to_datetime(df_tickets['date'])
        print("\n📊 Résumé par enseigne :")
        print(
            df_tickets.groupby('enseigne')['total_net']
            .agg(nb_tickets='count', total='sum', moyenne='mean')
            .round(2)
            .to_string()
        )
        print(f"\n💶 Total global : {df_tickets['total_net'].sum():.2f} €")


if __name__ == '__main__':
    main()
