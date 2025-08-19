# -------------------------------------------------------------------------
# PEPPOL Countries.
# -------------------------------------------------------------------------
# In v17, these 3 lists are in account.

# List of countries where Peppol should be used by default.
PEPPOL_DEFAULT_COUNTRIES = [
    'AT', 'BE', 'CH', 'CY', 'CZ', 'DE', 'DK', 'EE', 'ES', 'FI',
    'FR', 'GR', 'IE', 'IS', 'IT', 'LT', 'LU', 'LV', 'MT', 'NL',
    'NO', 'PL', 'PT', 'RO', 'SE', 'SI',
]

# List of countries where Peppol footnote will be added when sending by mail.
PEPPOL_MAILING_COUNTRIES = [
    'BE', 'LU', 'NL', 'SE', 'NO',
]

# List of countries where Peppol is accessible.
PEPPOL_LIST = PEPPOL_DEFAULT_COUNTRIES + [
    'AD', 'AL',  'BA', 'BG', 'GB', 'HR', 'HU', 'LI', 'MC', 'ME',
    'MK', 'RS', 'SK', 'SM', 'TR', 'VA',
]


# -------------------------------------------------------------------------
# ELECTRONIC ADDRESS SCHEME (EAS), see https://docs.peppol.eu/poacc/billing/3.0/codelist/eas/
# -------------------------------------------------------------------------
# In v17, this table is in account_edi_ubl_cii.
EAS_MAPPING = {
    'AD': {'9922': 'vat'},
    'AE': {'0235': 'vat'},
    'AL': {'9923': 'vat'},
    'AT': {'9915': 'vat'},
    'AU': {'0151': 'vat'},
    'BA': {'9924': 'vat'},
    'BE': {'0208': 'company_registry'},
    'BG': {'9926': 'vat'},
    'CH': {'9927': 'vat'},
    'CY': {'9928': 'vat'},
    'CZ': {'9929': 'vat'},
    'DE': {'9930': 'vat'},
    'DK': {'0184': 'company_registry', '0198': 'vat'},
    'EE': {'9931': 'vat'},
    'ES': {'9920': 'vat'},
    'FI': {'0216': None},
    'FR': {'0009': 'siret', '9957': 'vat'},
    'SG': {'0195': 'l10n_sg_unique_entity_number'},
    'GB': {'9932': 'vat'},
    'GR': {'9933': 'vat'},
    'HR': {'9934': 'vat'},
    'HU': {'9910': 'l10n_hu_eu_vat'},
    'IE': {'9935': 'vat'},
    'IS': {'0196': 'vat'},
    'IT': {'0211': 'vat', '0210': 'l10n_it_codice_fiscale'},
    'JP': {'0221': 'vat'},
    'LI': {'9936': 'vat'},
    'LT': {'9937': 'vat'},
    'LU': {'9938': 'vat'},
    'LV': {'0218': 'company_registry', '9939': 'vat'},
    'MC': {'9940': 'vat'},
    'ME': {'9941': 'vat'},
    'MK': {'9942': 'vat'},
    'MT': {'9943': 'vat'},
    # Do not add the vat for NL, since: "[NL-R-003] For suppliers in the Netherlands, the legal entity identifier
    # MUST be either a KVK or OIN number (schemeID 0106 or 0190)" in the Bis 3 rules (in PartyLegalEntity/CompanyID).
    'NL': {'0106': None, '0190': None},
    'NO': {'0192': 'l10n_no_bronnoysund_number'},
    'NZ': {'0088': 'company_registry'},
    'PL': {'9945': 'vat'},
    'PT': {'9946': 'vat'},
    'RO': {'9947': 'vat'},
    'RS': {'9948': 'vat'},
    'SE': {'0007': 'company_registry'},
    'SI': {'9949': 'vat'},
    'SK': {'9950': 'vat'},
    'SM': {'9951': 'vat'},
    'TR': {'9952': 'vat'},
    'VA': {'9953': 'vat'},
}
