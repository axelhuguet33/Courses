#!/usr/bin/env python3
"""
Génère correspondances.csv à partir des produits connus.

Lance ce script UNE SEULE FOIS pour créer le fichier de mapping.
Ensuite, ouvre correspondances.csv dans Numbers ou Excel pour
corriger/compléter les noms simplifiés à la main.

L'extraction (extract_tickets.py) lira ensuite ce fichier
automatiquement à chaque lancement.
"""

import pandas as pd
import re
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent

# ─── Règles de simplification ────────────────────────────────────────────────
# Ordre important : du plus spécifique au plus général.
# Format : (regex, nom_simplifié)

REGLES = [
    # ── Produits laitiers ────────────────────────────────────────────────────
    (r'FROMAGE BLANC|PAT FROMAGE BLANC|TOP BUDGET FROM BLAN|PETITS.*FROM.*BLANC', 'Fromage blanc'),
    (r'PAT FROM FRAIS|FROM FRAIS',               'Fromage frais'),
    (r'PAT SUISSE',                              'Petit-suisse nature'),
    (r'COTTAGE CHEESE',                          'Cottage cheese'),
    (r'PATURAGES MOZZA|MOZZARELLA',              'Mozzarella'),
    (r'BURRATA',                                 'Burrata'),
    (r'FETA',                                    'Feta'),
    (r'PARMIGIA|PARMIGIANO',                     'Parmesan râpé'),
    (r'BEURRE CACAHUETES',                       'Beurre de cacahuètes'),
    (r'BEURRE MOULE|BEURRE DOUX|BEURRE.*PAY',   'Beurre'),
    (r'PETIT YOPLAIT|YOPLAIT',                   'Yaourt Yoplait'),

    # ── Boissons végétales ───────────────────────────────────────────────────
    (r'BOISSON AMAN|BOIS\.AMANDE|LAIT AMANDE|PAT VEG BOISSON AMAN|BJORG BOIS', "Lait d'amande"),
    (r'SOJASUN.*UHT|TONYU|SOJA.*1\s*L',         'Boisson soja'),
    (r'AVOINE SANS SUCRES|AVOINE.*1L',           "Lait d'avoine"),
    (r'LAIT DE COCO|LAIT COCO|KARA LAIT|SUZI WAN LAIT|KARA LAIT', 'Lait de coco'),
    (r'PREP CULINAIRE SOJA|PREPARATION SOJA|CUISINE VEGETALE', 'Crème végétale (cuisine)'),

    # ── Œufs ─────────────────────────────────────────────────────────────────
    (r'OEUF|OEUFS|VOLAE.*OEUF',                 'Œufs'),

    # ── Houmous ──────────────────────────────────────────────────────────────
    (r'HOUMOU|HOUMMOUS',                         'Houmous'),

    # ── Tofu ─────────────────────────────────────────────────────────────────
    (r'TOFU',                                    'Tofu'),

    # ── Légumineuses ─────────────────────────────────────────────────────────
    (r'LENTILLES CORAIL',                        'Lentilles corail'),
    (r'POIS CHICH',                              'Pois chiches'),
    (r'HARICOT',                                 'Haricots'),

    # ── Céréales / grains ────────────────────────────────────────────────────
    (r'COUSCOUS',                                'Couscous'),
    (r'QUINOA',                                  'Quinoa'),
    (r'RIZ BASMATI|ST ELOI RIZ',                'Riz basmati'),
    (r'RIZ LONG|RIZ SEMI',                       'Riz semi-complet'),
    (r'EBLY|BLE NAT',                            'Blé'),
    (r'FLOCONS.*AVOINE',                         "Flocons d'avoine"),
    (r'EPEAUTRE',                                'Épeautre'),
    (r'GRAINES.*SESAME',                         'Graines de sésame'),
    (r'GERME.*BLE',                              'Germe de blé'),
    (r'PROTEINES.*SOJA',                         'Protéines de soja'),
    (r'SEITAN',                                  'Seitan'),
    (r'TABOULE',                                 'Taboulé'),

    # ── Pain / toast ─────────────────────────────────────────────────────────
    (r'TOASTLIGNE|TOAST.*COMP|GRANDES.*TRANCH.*COMP|PDM.*COMP', 'Pain de mie complet'),
    (r'TOAST.*CERE|REGAIN TOAST',                'Toast céréales'),
    (r'NOUILLE.*RIZ|NOUILLES.*RIZ|VERMICELLE|NOUILL.*RIZ', 'Nouilles de riz'),
    (r'FARINE.*T45|FARINE BLE T45',             'Farine T45'),
    (r'FARINE.*COMP|FARINE.*SEMI|CHAB FARINE',  'Farine complète'),
    (r'FARINE.*SARRASIN',                        'Farine de sarrasin'),
    (r'FARINE.*POIS|FARINES.*POIS',             'Farine de pois'),
    (r'CHAPELURE',                               'Chapelure'),
    (r'LEVURE|ALSA LEV',                         'Levure chimique'),
    (r'SUCRE POUDRE|PERRUCHE|CASSONA',          'Sucre'),
    (r'COMPOTE',                                 'Compote'),
    (r'CEREALES.*TIPIAK|TIPIAK.*CEREAL',         'Céréales'),

    # ── Conserves / boîtes poisson ───────────────────────────────────────────
    (r'FILET MAQ|FILETS MAQ|MAQX|MAQU|ODYSSEE MAQ|FILET MAQUEREAU', 'Maquereau (boîte)'),
    (r'ODYSSEE THON|THON',                       'Thon (boîte)'),
    (r'SARDINE',                                 'Sardines (boîte)'),
    (r'ANCHOIS',                                 'Anchois'),
    (r'TIELLES',                                 'Tielles sétoises'),
    (r'PARMENTIER SARD',                         'Parmentier de sardines'),

    # ── Surgelés Picard — poisson ─────────────────────────────────────────────
    (r'Fil colin|Filet.*colin|Tr.*colin|colin Alaska', 'Colin (surgelé)'),
    (r'Filet.*dorade',                            'Dorade (surgelée)'),
    (r'Cocktail.*mer|M[eé]l moule',             'Fruits de mer (surgelé)'),
    (r'Sal.*frt|Saumon.*frt',                    'Saumon (surgelé)'),
    (r'Julienne',                                'Julienne (surgelée)'),
    (r'Encornet|ENCORNET',                       'Encornet'),
    (r'TOP BUDGET TRUITE|TRUITE.*FUMEE|TRUITE.*MER', 'Truite fumée'),

    # ── Surgelés Picard — légumes ─────────────────────────────────────────────
    (r'L[eé]g.*wok|L[eé]g pour wok|L[eé]gume basq', 'Légumes wok (surgelé)'),
    (r'Po[eê]l[eé].*l[eé]g|Poele.*legum',       'Poêlée de légumes (surgelée)'),
    (r'Ratatouille',                             'Ratatouille (surgelée)'),
    (r'Cubes XL',                                'Cubes légumes XL (surgelé)'),
    (r'Patade douce|Patate dou',                 'Patate douce (surgelée)'),
    (r'Salade.*F\.exo|Salade.*exo',             'Salade exotique (surgelée)'),

    # ── Légumes frais ────────────────────────────────────────────────────────
    (r'AVOCAT',                                  'Avocat'),
    (r'CONCOMBRE',                               'Concombre'),
    (r'COURGETTE',                               'Courgette'),
    (r'POIVRON ROUGE',                           'Poivron rouge'),
    (r'POIVRON JAUNE',                           'Poivron jaune'),
    (r'POIVRON',                                 'Poivron'),
    (r'TOMATE CERISE',                           'Tomates cerises'),
    (r'TOMATE COTELEE|TOMATE.*NOIRE',           'Tomate'),
    (r'POMME DE TERRE',                          'Pomme de terre'),
    (r'CAROTTE',                                 'Carotte'),
    (r'CHOU ROUGE|ST ELOI CHOU',                'Chou rouge'),
    (r'SALADE.*MACHE|MACHE.*SAC|MERCI SALADE|ST ELOI.*MACHE', 'Mâche'),
    (r'SUCRINE',                                 'Salade sucrine'),
    (r'ARTICHAUT|ARTIG',                         'Artichaut'),
    (r'PETITPOIS|PETIT POIS|ST ELOI.*POIS',     'Petits pois'),

    # ── Fruits frais ─────────────────────────────────────────────────────────
    (r'BANANE',                                  'Banane'),
    (r'ABRICOT',                                 'Abricot'),
    (r'PECHE JAUNE',                             'Pêche jaune'),
    (r'PECHE BLAN',                              'Pêche blanche'),
    (r'PECHE',                                   'Pêche'),
    (r'ANANAS KIWI',                             'Ananas Kiwi (jus)'),
    (r'ANANAS',                                  'Ananas'),
    (r'PASTEQUE',                                'Pastèque'),
    (r'MELON',                                   'Melon'),
    (r'CITRON JAUNE|CITRON',                     'Citron'),
    (r'MANDARINE',                               'Mandarine'),
    (r'POMME GALA|POMME GOLDEN|POMME BICOL',    'Pomme'),

    # ── Épices / condiments ──────────────────────────────────────────────────
    (r'CANNELLE',                                'Cannelle'),
    (r'GINGEMBRE',                               'Gingembre'),
    (r'CURCUMA',                                 'Curcuma'),
    (r'PAPRIKA',                                 'Paprika'),
    (r'MUSCADE',                                 'Muscade'),
    (r'ORIGAN',                                  'Origan'),
    (r'ANETH',                                   'Aneth'),
    (r'FLEUR DE SEL',                            'Fleur de sel'),
    (r'SIROP.*AGAVE|AGAVE.*SIROP|REGAIN.*AGAVE|SUNNYBIO.*AGAVE', "Sirop d'agave"),
    (r'PUREE.*SESAME|SESAME.*TAHIN|TAHIN',      'Tahini'),
    (r'SAUCE TAMARI|TAMARI',                     'Sauce tamari'),
    (r'DOUBLE CONCENTRE TOMATE',                 'Concentré de tomate'),
    (r'MAYO|MAYONNAISE',                         'Mayonnaise'),
    (r'MOUTARDE.*ANC|MOUTARDE.*AOP',            "Moutarde à l'ancienne"),
    (r'MOUTARDE',                                'Moutarde'),
    (r'VINAIGRE',                                'Vinaigre'),
    (r'HUILE DE COCO',                           'Huile de coco'),

    # ── Protéines végétales ──────────────────────────────────────────────────
    (r'HACHE.*VEGETAL|HACHE.*SOJA|HACHE.*HEURA|HACHE.*TEMPEH', 'Steak haché végétal'),
    (r'EMINCE VEGGIE|EMINCES.*VEGET',           'Émincés végétaux'),
    (r'FARCE.*VEGETAL',                          'Farce végétale'),
    (r'SPECIAL KEBAB.*VEGETAL',                  'Kebab végétal'),
    (r'GG LE CLASSIQUE SOJA',                    'Steaks soja-blé'),
    (r'ALLUMETTES VEGGIE',                       'Allumettes végétales'),
    (r'MA PREPARATION VEGGIE',                   'Préparation veggie'),
    (r'GALETTES.*EPIN',                          'Galettes épinard-fromage'),
    (r'STEAK.*GOURMAND',                         'Steak végétal'),

    # ── Boissons ─────────────────────────────────────────────────────────────
    (r'EAU DE COCO|PAQUITO EAU DE COCO',        'Eau de coco'),
    (r'PUR JUS POMME',                           'Jus de pomme'),
    (r'GINGER BEER|SCHWEPPES GINGER',           'Ginger beer'),
    (r'CRISTALINE|EAU SOURCE',                   'Eau plate'),
    (r'SAN PELLEGRINO|SANPELLEGRINO|S PELLEGRINO|S\.PELLEGRINO', 'San Pellegrino'),
    (r'COCA COLA',                               'Coca-Cola'),
    (r'TOURTEL',                                 'Bière sans alcool'),
    (r'AFFLIGEM|BIERE AFFLIGEM',                'Bière Affligem'),
    (r'CHABLIS|AOP.*MR 75|VDF CUVEE|PRINCE.*VIN', 'Vin'),

    # ── Capsules café ────────────────────────────────────────────────────────
    (r'CAPS.*ALU|CAPSUL.*ALU|CN LUNGO|CN ESPR', 'Capsules café'),

    # ── Chips / snacks ───────────────────────────────────────────────────────
    (r'CHIPS|CURLY|BRET',                        'Chips / snacks'),
    (r'NUII',                                    'Barre chocolatée'),
    (r'CHOC.*NOIR.*85|CHOCOLAT.*85|LINDT.*8[05]|LES CREAT.*CHOC|LES CREA.*CHOC|CHOCO.*EXCELLENCE', 'Chocolat noir 85%'),
    (r'CHOC|CHOCOLAT',                           'Chocolat'),
    (r'BLINI',                                   'Blinis'),

    # ── Hygiène / maison ─────────────────────────────────────────────────────
    (r'PAPIER HYGIENIQUE|PH BLANC',             'Papier toilette'),
    (r'MOUCHOIRS|BTE MOUCHOIRS',                'Mouchoirs'),
    (r'ESSUIE TOUT',                             'Essuie-tout'),
    (r'SHP.*AVOCAT|SHP.*KARITE|SHAMPOOING|SHAMPOO', 'Shampoing'),
    (r'SAVON NOIR',                              'Savon noir'),
    (r'LESS.*EXPRESS|LESSIVE',                  'Lessive'),
    (r'DECOLOR STOP',                            'Décolor Stop'),
    (r'SUN.*DW|LAVE.*VAISSELLE',                'Liquide vaisselle'),
    (r'EPONGE|SPONTEX|APTA EPONGE',             'Éponges'),
    (r'NETT.*VITRO|VITROCLEN',                  'Nettoyant vitrocéramique'),
    (r'DSITRIB SPRAY|SPRAY.*PLAST',             'Spray nettoyant'),
    (r'SACS POUBEL|SAC POUB|APTA SAC',         'Sacs poubelle'),

    # ── Charcuterie ──────────────────────────────────────────────────────────
    (r'FUET.*PORC|DEB FUET',                    'Fuet (charcuterie)'),
    (r'JAMBON SPECK|IDS.*SPECK',                'Jambon Speck'),
    (r'MORTADELLE|IDS MORTADEL',                'Mortadelle'),
    (r'F\.MICHON|MICHON',                        'Charcuterie Michon'),
    (r'GAULOIS.*ESC|ESC.*GAULOIS|ESCARGOT',     'Escargots surgelés'),

    # ── Sucreries / glaces───────────────────────────────────────────────────
    (r'MAG.*DBL.*NOISETTE|MAGNUM.*NOISETTE',    'Magnum double noisette'),
    (r'LINDT|EXCELLENCE NOI',                   'Chocolat Lindt'),

    # ── Snacks / condiments ──────────────────────────────────────────────────
    (r'TORTILLA.*MAIS|IDS.*TORTILLA',           'Tortillas maïs'),
    (r'AMANDE.*DECOR|HOLYFRUIT|HOLY.*FRUITS|AMANDE.*500',  'Amandes'),
    (r'GOURD.*MULT|PAQUITO GOURD|PAQUI GOURD',  'Gourde de fruits'),
    (r'NOIX DE CAJOU',                           'Noix de cajou'),

    # ── Volaille / viande ────────────────────────────────────────────────────
    (r'Ch.{0,3}minc|POULET.*EMINC|EMINC.*POULET',        'Poulet émincé'),
    (r'FLTS MQX|FILETS.*MAQUER|MAQUER.*TOMATE',           'Filets de maquereaux sauce tomate'),

    # ── Vrac (vente au poids) ────────────────────────────────────────────────
    (r'\d+[,.]\d+\s*kg\s*[Xx]\s*\d',            'Vrac (vente au poids)'),

    # ── Huile d'olive ────────────────────────────────────────────────────────
    (r'DELYSSA|HOVE.*BIO|HUILE.*OLIVE',         "Huile d'olive"),

    # ── Eau / boissons nomades ───────────────────────────────────────────────
    (r'PTITE BTL|BTL.*EAU|PETITE.*EAU|EAU.*CAN', 'Eau (petite bouteille)'),

    # ── Fruits & légumes vrac ────────────────────────────────────────────────
    (r'^FRUITS ET LEGUMES$',                     'Fruits et légumes'),

    # ── Divers ───────────────────────────────────────────────────────────────
    (r'SAC CABAS',                               'Sac cabas'),
    (r'OLIVES NOIRES',                           'Olives noires'),
    (r'PIMENT|EPULSE',                           'Piment'),
    (r'FREED.*MENT|AIRWAVES',                   'Chewing-gum'),
]

# Familles pour lesquelles on distingue le format du lot (x2, x6, x12...).
PACK_AWARE_FAMILIES = {
    'Œufs',
    'Yaourt Yoplait',
    'Compote',
    'Eau plate',
    'San Pellegrino',
    'Tofu',
    'Seitan',
    'Mozzarella',
    'Capsules café',
    'Tortillas maïs',
}


def extraire_taille_lot(nom: str):
    """Retourne la taille de lot détectée dans un libellé (ex: 6 dans 'X6')."""
    patterns = [
        r'\bX\s*(\d{1,3})\b',
        r'\b(\d{1,3})\s*[xX]\s*\d+[,.]?\d*\s*(?:G|GR|KG|ML|CL|L)\b',
        r'\b(\d{1,3})\s*[xX]\b',
    ]
    for pattern in patterns:
        m = re.search(pattern, nom, re.IGNORECASE)
        if m:
            return int(m.group(1))
    return None


def simplifier(nom: str) -> str:
    """Applique les règles de simplification dans l'ordre."""
    # Cas spécial : oeufs en lot (x6, x10, x12...) pour éviter de comparer
    # des formats de boîtes différents ensemble.
    if re.search(r'OEUF|OEUFS|VOLAE.*OEUF', nom, re.IGNORECASE):
        m_pack = re.search(r'\bX\s*(\d{1,2})\b', nom, re.IGNORECASE)
        if not m_pack:
            m_pack = re.search(r'\b(\d{1,2})\s*OEUFS?\b', nom, re.IGNORECASE)
        if m_pack:
            return f"Œufs x{int(m_pack.group(1))}"
        return 'Œufs'

    for pattern, simplifie in REGLES:
        if re.search(pattern, nom, re.IGNORECASE):
            if simplifie in PACK_AWARE_FAMILIES:
                lot = extraire_taille_lot(nom)
                if lot:
                    return f"{simplifie} x{lot}"
            return simplifie
    return nom  # Pas de règle → on garde le nom original


def main():
    produits_csv = BASE_DIR / 'produits.csv'
    if not produits_csv.exists():
        print("❌ produits.csv introuvable. Lance d'abord extract_tickets.py.")
        return

    df = pd.read_csv(produits_csv)
    produits_uniques = df['produit'].dropna().unique()

    lignes = []
    for p in sorted(produits_uniques):
        lignes.append({'produit_original': p, 'nom_simplifié': simplifier(p)})

    df_corr = pd.DataFrame(lignes)
    sortie = BASE_DIR / 'correspondances.csv'
    df_corr.to_csv(sortie, index=False, encoding='utf-8-sig')

    mappes   = df_corr[df_corr['nom_simplifié'] != df_corr['produit_original']]
    non_mappes = df_corr[df_corr['nom_simplifié'] == df_corr['produit_original']]

    print(f"✅ {len(df_corr)} produits traités → correspondances.csv")
    print(f"   {len(mappes)} noms simplifiés automatiquement")
    print(f"   {len(non_mappes)} sans correspondance (à compléter manuellement) :\n")
    for _, row in non_mappes.iterrows():
        print(f"  - {row['produit_original']}")

    print("\n💡 Ouvre correspondances.csv dans Numbers ou Excel pour compléter/corriger.")


if __name__ == '__main__':
    main()
