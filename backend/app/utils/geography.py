"""
Geography utilities for country code mapping and geographic filtering.

This module provides centralized geography utilities used across the application
for consistent country code handling and geographic filtering.
"""

from typing import Optional, Dict, List

# ISO 3166-1 alpha-2 country code to country name mapping
COUNTRY_CODE_TO_NAME: Dict[str, str] = {
    "AW": "Aruba",
    "AF": "Afghanistan",
    "AO": "Angola",
    "AI": "Anguilla",
    "AX": "Åland Islands",
    "AL": "Albania",
    "AD": "Andorra",
    "AE": "United Arab Emirates",
    "AR": "Argentina",
    "AM": "Armenia",
    "AS": "American Samoa",
    "AQ": "Antarctica",
    "TF": "French Southern Territories",
    "AG": "Antigua and Barbuda",
    "AU": "Australia",
    "AT": "Austria",
    "AZ": "Azerbaijan",
    "BI": "Burundi",
    "BE": "Belgium",
    "BJ": "Benin",
    "BQ": "Bonaire, Sint Eustatius and Saba",
    "BF": "Burkina Faso",
    "BD": "Bangladesh",
    "BG": "Bulgaria",
    "BH": "Bahrain",
    "BS": "Bahamas",
    "BA": "Bosnia and Herzegovina",
    "BL": "Saint Barthélemy",
    "BY": "Belarus",
    "BZ": "Belize",
    "BM": "Bermuda",
    "BO": "Bolivia, Plurinational State of",
    "BR": "Brazil",
    "BB": "Barbados",
    "BN": "Brunei Darussalam",
    "BT": "Bhutan",
    "BV": "Bouvet Island",
    "BW": "Botswana",
    "CF": "Central African Republic",
    "CA": "Canada",
    "CC": "Cocos (Keeling) Islands",
    "CH": "Switzerland",
    "CL": "Chile",
    "CN": "China",
    "CI": "Côte d'Ivoire",
    "CM": "Cameroon",
    "CD": "Congo, The Democratic Republic of the",
    "CG": "Congo",
    "CK": "Cook Islands",
    "CO": "Colombia",
    "KM": "Comoros",
    "CV": "Cabo Verde",
    "CR": "Costa Rica",
    "CU": "Cuba",
    "CW": "Curaçao",
    "CX": "Christmas Island",
    "KY": "Cayman Islands",
    "CY": "Cyprus",
    "CZ": "Czechia",
    "DE": "Germany",
    "DJ": "Djibouti",
    "DM": "Dominica",
    "DK": "Denmark",
    "DO": "Dominican Republic",
    "DZ": "Algeria",
    "EC": "Ecuador",
    "EG": "Egypt",
    "ER": "Eritrea",
    "EH": "Western Sahara",
    "ES": "Spain",
    "EE": "Estonia",
    "ET": "Ethiopia",
    "FI": "Finland",
    "FJ": "Fiji",
    "FK": "Falkland Islands (Malvinas)",
    "FR": "France",
    "FO": "Faroe Islands",
    "FM": "Micronesia, Federated States of",
    "GA": "Gabon",
    "GB": "United Kingdom",
    "GE": "Georgia",
    "GG": "Guernsey",
    "GH": "Ghana",
    "GI": "Gibraltar",
    "GN": "Guinea",
    "GP": "Guadeloupe",
    "GM": "Gambia",
    "GW": "Guinea-Bissau",
    "GQ": "Equatorial Guinea",
    "GR": "Greece",
    "GD": "Grenada",
    "GL": "Greenland",
    "GT": "Guatemala",
    "GF": "French Guiana",
    "GU": "Guam",
    "GY": "Guyana",
    "HK": "Hong Kong",
    "HM": "Heard Island and McDonald Islands",
    "HN": "Honduras",
    "HR": "Croatia",
    "HT": "Haiti",
    "HU": "Hungary",
    "ID": "Indonesia",
    "IM": "Isle of Man",
    "IN": "India",
    "IO": "British Indian Ocean Territory",
    "IE": "Ireland",
    "IR": "Iran, Islamic Republic of",
    "IQ": "Iraq",
    "IS": "Iceland",
    "IL": "Israel",
    "IT": "Italy",
    "JM": "Jamaica",
    "JE": "Jersey",
    "JO": "Jordan",
    "JP": "Japan",
    "KZ": "Kazakhstan",
    "KE": "Kenya",
    "KG": "Kyrgyzstan",
    "KH": "Cambodia",
    "KI": "Kiribati",
    "KN": "Saint Kitts and Nevis",
    "KR": "Korea, Republic of",
    "KW": "Kuwait",
    "LA": "Lao People's Democratic Republic",
    "LB": "Lebanon",
    "LR": "Liberia",
    "LY": "Libya",
    "LC": "Saint Lucia",
    "LI": "Liechtenstein",
    "LK": "Sri Lanka",
    "LS": "Lesotho",
    "LT": "Lithuania",
    "LU": "Luxembourg",
    "LV": "Latvia",
    "MO": "Macao",
    "MF": "Saint Martin (French part)",
    "MA": "Morocco",
    "MC": "Monaco",
    "MD": "Moldova, Republic of",
    "MG": "Madagascar",
    "MV": "Maldives",
    "MX": "Mexico",
    "MH": "Marshall Islands",
    "MK": "North Macedonia",
    "ML": "Mali",
    "MT": "Malta",
    "MM": "Myanmar",
    "ME": "Montenegro",
    "MN": "Mongolia",
    "MP": "Northern Mariana Islands",
    "MZ": "Mozambique",
    "MR": "Mauritania",
    "MS": "Montserrat",
    "MQ": "Martinique",
    "MU": "Mauritius",
    "MW": "Malawi",
    "MY": "Malaysia",
    "YT": "Mayotte",
    "NA": "Namibia",
    "NC": "New Caledonia",
    "NE": "Niger",
    "NF": "Norfolk Island",
    "NG": "Nigeria",
    "NI": "Nicaragua",
    "NU": "Niue",
    "NL": "Netherlands",
    "NO": "Norway",
    "NP": "Nepal",
    "NR": "Nauru",
    "NZ": "New Zealand",
    "OM": "Oman",
    "PK": "Pakistan",
    "PA": "Panama",
    "PN": "Pitcairn",
    "PE": "Peru",
    "PH": "Philippines",
    "PW": "Palau",
    "PG": "Papua New Guinea",
    "PL": "Poland",
    "PR": "Puerto Rico",
    "KP": "Korea, Democratic People's Republic of",
    "PT": "Portugal",
    "PY": "Paraguay",
    "PS": "Palestine, State of",
    "PF": "French Polynesia",
    "QA": "Qatar",
    "RE": "Réunion",
    "RO": "Romania",
    "RU": "Russian Federation",
    "RW": "Rwanda",
    "SA": "Saudi Arabia",
    "SD": "Sudan",
    "SN": "Senegal",
    "SG": "Singapore",
    "GS": "South Georgia and the South Sandwich Islands",
    "SH": "Saint Helena, Ascension and Tristan da Cunha",
    "SJ": "Svalbard and Jan Mayen",
    "SB": "Solomon Islands",
    "SL": "Sierra Leone",
    "SV": "El Salvador",
    "SM": "San Marino",
    "SO": "Somalia",
    "PM": "Saint Pierre and Miquelon",
    "RS": "Serbia",
    "SS": "South Sudan",
    "ST": "Sao Tome and Principe",
    "SR": "Suriname",
    "SK": "Slovakia",
    "SI": "Slovenia",
    "SE": "Sweden",
    "SZ": "Eswatini",
    "SX": "Sint Maarten (Dutch part)",
    "SC": "Seychelles",
    "SY": "Syrian Arab Republic",
    "TC": "Turks and Caicos Islands",
    "TD": "Chad",
    "TG": "Togo",
    "TH": "Thailand",
    "TJ": "Tajikistan",
    "TK": "Tokelau",
    "TM": "Turkmenistan",
    "TL": "Timor-Leste",
    "TO": "Tonga",
    "TT": "Trinidad and Tobago",
    "TN": "Tunisia",
    "TR": "Turkey",
    "TV": "Tuvalu",
    "TW": "Taiwan, Province of China",
    "TZ": "Tanzania, United Republic of",
    "UG": "Uganda",
    "UA": "Ukraine",
    "UM": "United States Minor Outlying Islands",
    "UY": "Uruguay",
    "US": "United States",
    "UZ": "Uzbekistan",
    "VA": "Holy See (Vatican City State)",
    "VC": "Saint Vincent and the Grenadines",
    "VE": "Venezuela, Bolivarian Republic of",
    "VG": "Virgin Islands, British",
    "VI": "Virgin Islands, U.S.",
    "VN": "Viet Nam",
    "VU": "Vanuatu",
    "WF": "Wallis and Futuna",
    "WS": "Samoa",
    "YE": "Yemen",
    "ZA": "South Africa",
    "ZM": "Zambia",
    "ZW": "Zimbabwe",
}

# Create reverse mapping (country name to code) for efficient lookup
COUNTRY_NAME_TO_CODE: Dict[str, str] = {
    name: code for code, name in COUNTRY_CODE_TO_NAME.items()
}

# Add common alternative names and variations
COUNTRY_NAME_TO_CODE.update(
    {
        "United States of America": "US",
        "USA": "US",
        "UK": "GB",
        "Britain": "GB",
        "Great Britain": "GB",
        "South Korea": "KR",
        "North Korea": "KP",
        "Russia": "RU",
        "Czech Republic": "CZ",
        "Iran": "IR",
        "Syria": "SY",
        "Congo": "CG",
        "DRC": "CD",
        "Democratic Republic of Congo": "CD",
        "Bolivia": "BO",
        "Venezuela": "VE",
        "Moldova": "MD",
        "Laos": "LA",
        "Ivory Coast": "CI",
        "Cape Verde": "CV",
        "East Timor": "TL",
        "Myanmar": "MM",
        "Burma": "MM",
    }
)


def get_country_code(country_name: str) -> Optional[str]:
    """
    Convert a country name to its ISO 3166-1 alpha-2 country code.

    Args:
        country_name: The country name to convert

    Returns:
        The two-letter country code (e.g., "FR" for "France") or None if not found

    Examples:
        >>> get_country_code("France")
        "FR"
        >>> get_country_code("United States")
        "US"
        >>> get_country_code("UK")
        "GB"
    """
    if not country_name:
        return None

    return COUNTRY_NAME_TO_CODE.get(country_name.strip())


def get_country_name(country_code: str) -> Optional[str]:
    """
    Convert an ISO 3166-1 alpha-2 country code to its country name.

    Args:
        country_code: The two-letter country code to convert

    Returns:
        The country name (e.g., "France" for "FR") or None if not found

    Examples:
        >>> get_country_name("FR")
        "France"
        >>> get_country_name("US")
        "United States"
        >>> get_country_name("GB")
        "United Kingdom"
    """
    if not country_code:
        return None

    return COUNTRY_CODE_TO_NAME.get(country_code.upper())


def convert_country_codes_to_names(country_codes: List[str]) -> Optional[str]:
    """
    Convert a list of ISO country codes to readable country names.

    This is primarily used for display purposes in the analysis results.

    Args:
        country_codes: List of ISO 3166-1 alpha-2 country codes

    Returns:
        Comma-separated string of country names, or None if no valid codes

    Examples:
        >>> convert_country_codes_to_names(["FR", "DE", "GB"])
        "France, Germany, United Kingdom"
    """
    if not country_codes or not isinstance(country_codes, list):
        return None

    country_names = []
    for code in country_codes:
        if code and isinstance(code, str):
            name = get_country_name(code)
            if name:
                country_names.append(name)
            else:
                # Keep unknown codes as-is for debugging
                country_names.append(code)

    return ", ".join(sorted(set(country_names))) if country_names else None


def get_country_code_from_geography_filter(
    geography_filter: Optional[List[str]]
) -> Optional[str]:
    """
    Extract the first country code from a geography filter list.

    This is a convenience function for services that need to extract a single
    country code from the geography filter parameter.

    Args:
        geography_filter: List of country names from geography filter

    Returns:
        ISO country code for the first country, or None if no valid countries

    Examples:
        >>> get_country_code_from_geography_filter(["France", "Germany"])
        "FR"
        >>> get_country_code_from_geography_filter([])
        None
    """
    if not geography_filter or len(geography_filter) == 0:
        return None

    country_name = geography_filter[0]
    country_code = get_country_code(country_name)

    # If we can't map the name, it might be a special region (e.g., "Europe", "OECD")
    # Pass it through as-is for the service to handle
    return country_code or country_name
