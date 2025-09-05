from __future__ import annotations

import asyncio
import logging
from datetime import date
from pathlib import Path
from typing import List, Optional

import pandas as pd

from app.core.config import settings
from app.services.analysis.prompts import BOOLEAN_QUERY_SYSTEM_PROMPT
from openai import AsyncOpenAI
from app.services.openalex import OpenAlexService
from app.services.overton import OvertonService
from .utils_doc_ids import stable_doc_id


def convert_country_codes_to_names(country_codes):
    """Convert ISO country codes to readable country names."""
    if not country_codes or not isinstance(country_codes, list):
        return None

    # Common country code to name mapping
    country_mapping = {
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

    # Convert codes to names, filter out unknown codes
    country_names = []
    for code in country_codes:
        if code and isinstance(code, str) and code.upper() in country_mapping:
            country_names.append(country_mapping[code.upper()])
        elif code:  # Keep unknown codes as-is
            country_names.append(code)

    return ", ".join(sorted(set(country_names))) if country_names else None


logger = logging.getLogger(__name__)


class ReferencesService:
    def __init__(self, export_dir: Optional[str] = None):
        self.export_dir = Path(export_dir or settings.EXPORT_FILES_DIR)
        self.export_dir.mkdir(parents=True, exist_ok=True)
        self._openai_client: Optional[AsyncOpenAI] = None

    @property
    def openai_client(self) -> AsyncOpenAI:
        if self._openai_client is None:
            if not settings.OPENAI_API_KEY:
                raise ValueError("OPENAI_API_KEY required for boolean query generation")
            self._openai_client = AsyncOpenAI(api_key=settings.OPENAI_API_KEY)
        return self._openai_client

    async def generate_boolean_query(self, natural_query: str) -> str:
        """Generate a boolean query deterministically (temperature 0)."""
        logger.info("🔍 Generating boolean query for: '%s'", natural_query)
        logger.debug("Using model: %s with temperature: 0.0", settings.LLM_MODEL)

        try:
            resp = await self.openai_client.chat.completions.create(
                model=settings.LLM_MODEL,
                temperature=0.0,
                messages=[
                    {"role": "system", "content": BOOLEAN_QUERY_SYSTEM_PROMPT},
                    {"role": "user", "content": natural_query},
                ],
                max_tokens=1000,
            )
            boolean_query = (resp.choices[0].message.content or natural_query).strip()

            logger.info("✅ Generated boolean query: '%s'", boolean_query)
            if resp.usage:
                logger.debug(
                    "Token usage - Prompt: %d, Completion: %d, Total: %d",
                    resp.usage.prompt_tokens,
                    resp.usage.completion_tokens,
                    resp.usage.total_tokens,
                )

            return boolean_query
        except Exception as e:
            logger.warning("❌ Boolean query generation failed: %s", e)
            logger.info("🔄 Falling back to original query: '%s'", natural_query)
            return natural_query

    async def build_references(
        self,
        query: str,
        sources: List[str],
        limit: int,
        date_from: Optional[str] = None,
        date_to: Optional[str] = None,
        mode: str = "semantic",  # "boolean" | "semantic"
        boolean_query: Optional[str] = None,
    ) -> Path:
        """Fetch and normalize references, write references.csv, and return its path."""

        tasks = []
        openalex_service = OpenAlexService() if "openalex" in sources else None
        overton_service = OvertonService() if "overton" in sources else None

        # Parse optional dates
        df_val = date.fromisoformat(date_from) if date_from else None
        dt_val = date.fromisoformat(date_to) if date_to else None

        # Determine OpenAlex query string
        openalex_query_str = query
        logger.info("🔎 Building references with mode: '%s'", mode)
        logger.debug("Original query: '%s'", query)

        if mode == "boolean":
            openalex_query_str = boolean_query or query
            logger.info("📋 Using provided boolean query: '%s'", openalex_query_str)
        elif mode == "semantic":
            # Generate boolean query from natural query
            logger.info(
                "🧠 Semantic mode: generating boolean query from natural language"
            )
            openalex_query_str = await self.generate_boolean_query(query)
            logger.info("🎯 Final OpenAlex query string: '%s'", openalex_query_str)

        if openalex_service:
            tasks.append(
                openalex_service.search(
                    query=openalex_query_str,
                    max_results=limit,
                    min_citations=settings.DEFAULT_MIN_CITATIONS,
                    date_from=df_val,
                    date_to=dt_val,
                )
            )
            # Also collect raw OpenAlex responses for debugging
            tasks.append(
                openalex_service.fetch_raw(
                    query=openalex_query_str,
                    max_results=limit,
                    min_citations=settings.DEFAULT_MIN_CITATIONS,
                    date_from=df_val,
                    date_to=dt_val,
                )
            )

        if overton_service:
            # Overton supports semantic search directly; when boolean mode is requested,
            # pass the boolean query via query= and disable semantic.
            if mode == "semantic":
                logger.info(
                    "🔍 Overton semantic search with original query: '%s'", query
                )
                tasks.append(
                    overton_service.search(
                        query=query,
                        max_results=limit,
                        semantic_search=True,
                    )
                )
            else:
                overton_boolean_query = boolean_query or query
                logger.info(
                    "📋 Overton boolean search with query: '%s'", overton_boolean_query
                )
                tasks.append(
                    overton_service.search(
                        query=overton_boolean_query,
                        max_results=limit,
                        semantic_search=False,
                    )
                )
            # Add raw Overton first-page JSON for debugging
            tasks.append(
                overton_service.fetch_raw(
                    **(
                        {"squery": query}
                        if mode == "semantic"
                        else {"query": boolean_query or query}
                    ),
                    min_similarity=0.3,
                    pp=limit if limit and limit < 50 else 50,
                )
            )

        results: List[pd.DataFrame] = []
        raw_openalex: list = []
        raw_overton: dict | list | None = None
        if tasks:
            gathered = await asyncio.gather(*tasks, return_exceptions=True)
            for g in gathered:
                if isinstance(g, Exception):
                    logger.error("Reference fetch error: %s", g)
                elif isinstance(g, pd.DataFrame):
                    results.append(g)
                elif isinstance(g, list) and openalex_service:
                    raw_openalex = g
                elif isinstance(g, dict) or isinstance(g, list):
                    raw_overton = g

        if not results:
            df = pd.DataFrame(
                columns=[
                    "doc_id",
                    "source",
                    "source_id",
                    "title",
                    "abstract_or_summary",
                    "year",
                    "doi",
                    "authors",
                    "landing_page_url",
                    "pdf_url",
                    "is_oa",
                    "type",
                ]
            )
        else:
            frames: List[pd.DataFrame] = []
            for idx, df in enumerate(results):
                if "overton_url" in df.columns:
                    source = "overton"
                    source_id_col = "id"
                    doi_col = "doi"
                    year_col = "publication_year"
                    title_col = "title"
                    abs_col = "abstract"
                    landing_col = "landing_page_url"
                    pdf_col = "pdf_url"
                    type_value = df.get("source_type", pd.Series([None] * len(df)))
                    authors_col = "authors"
                else:
                    source = "openalex"
                    source_id_col = "id"
                    doi_col = "doi"
                    year_col = "publication_year"
                    title_col = "title"
                    abs_col = "abstract"
                    landing_col = "landing_page_url"
                    pdf_col = "pdf_url"
                    type_value = df.get("work_type", pd.Series([None] * len(df)))
                    authors_col = "authors"

                normalized = pd.DataFrame(
                    {
                        "source": source,
                        "source_id": df.get(
                            source_id_col, pd.Series([None] * len(df))
                        ).astype(str),
                        "title": df.get(title_col, pd.Series([None] * len(df))),
                        "abstract_or_summary": df.get(
                            abs_col, pd.Series([None] * len(df))
                        ),
                        "year": df.get(year_col, pd.Series([None] * len(df))),
                        "doi": df.get(doi_col, pd.Series([None] * len(df))),
                        "authors": df.get(authors_col, pd.Series([None] * len(df))),
                        "landing_page_url": df.get(
                            landing_col, pd.Series([None] * len(df))
                        ),
                        "pdf_url": df.get(pdf_col, pd.Series([None] * len(df))),
                        "is_oa": df.get("is_oa", pd.Series([None] * len(df))),
                        "type": type_value,
                        # Essential fields: citation count and source country
                        "cited_by_count": df.get(
                            "cited_by_count", pd.Series([None] * len(df))
                        ),
                    }
                )

                # Handle source_country differently for OpenAlex vs Overton
                if source == "openalex":
                    # For OpenAlex, convert author institution countries to readable names
                    if "author_institution_countries" in df.columns:
                        normalized["source_country"] = df[
                            "author_institution_countries"
                        ].apply(convert_country_codes_to_names)
                    else:
                        normalized["source_country"] = pd.Series([None] * len(df))
                else:
                    # For Overton, use the existing source_country field
                    normalized["source_country"] = df.get(
                        "source_country", pd.Series([None] * len(df))
                    )

                # Include author institution countries when available (OpenAlex)
                if "author_institution_countries" in df.columns:
                    normalized["author_institution_countries"] = df[
                        "author_institution_countries"
                    ].apply(
                        lambda v: v
                        if isinstance(v, list)
                        else ([] if pd.isna(v) else [v])
                    )
                else:
                    normalized["author_institution_countries"] = [
                        list() for _ in range(len(df))
                    ]

                # Build stable doc_ids
                normalized["doc_id"] = [
                    stable_doc_id(
                        doi=(
                            row["doi"]
                            if isinstance(row["doi"], str) and row["doi"]
                            else None
                        ),
                        source_id=row["source_id"],
                        title=row["title"],
                        year=int(row["year"]) if pd.notna(row["year"]) else None,
                    )
                    for _, row in normalized.iterrows()
                ]

                frames.append(
                    normalized[
                        [
                            "doc_id",
                            "source",
                            "source_id",
                            "title",
                            "abstract_or_summary",
                            "year",
                            "doi",
                            "authors",
                            "landing_page_url",
                            "pdf_url",
                            "is_oa",
                            "type",
                            "author_institution_countries",
                            # Essential new fields
                            "cited_by_count",
                            "source_country",
                        ]
                    ]
                )

            df = pd.concat(frames, ignore_index=True).drop_duplicates(
                subset=["doc_id"]
            )  # de-dupe by doc_id

        # Ensure export directory exists
        self.export_dir.mkdir(parents=True, exist_ok=True)
        references_csv = self.export_dir / "references.csv"
        df.to_csv(references_csv, index=False)

        # Save raw payloads for debugging
        import json

        debug_dir = self.export_dir / "debug"
        debug_dir.mkdir(parents=True, exist_ok=True)
        if raw_openalex:
            (debug_dir / "openalex_raw.json").write_text(
                json.dumps(raw_openalex, ensure_ascii=False, indent=2), encoding="utf-8"
            )
        if raw_overton is not None:
            (debug_dir / "overton_raw.json").write_text(
                json.dumps(raw_overton, ensure_ascii=False, indent=2), encoding="utf-8"
            )

        logger.info("Wrote references.csv with %d rows to %s", len(df), references_csv)
        return references_csv
