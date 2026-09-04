from __future__ import annotations

import calendar
import json
import os
import re
import shutil
import uuid
import zipfile
from html import escape
from io import BytesIO
from datetime import date, datetime, time, timedelta
from pathlib import Path

import altair as alt
import pandas as pd
import streamlit as st
import streamlit.components.v1 as components

from alerts import process_repactuation_alerts, send_daily_bid_schedule, send_obligation_alert
from art_management import art_number_key, organize_art_rows, professional_profiles
from backlog import BACKLOG_SORT_OPTIONS, sort_backlog_rows
from bdi import calculate_bdi, composed_indirect_total, tax_total
from bids import (
    COMPANY_CNPJ,
    BRAZILIAN_UF_OPTIONS as BID_UF_OPTIONS,
    DISPUTE_MODES as BID_DISPUTE_MODES,
    MODALITIES as BID_MODALITIES,
    PLATFORMS as BID_PLATFORMS,
    PNCP_MODALIDADES,
    PncpError,
    RANKING_SITUATIONS,
    SCOPE_OPTIONS as BID_SCOPE_OPTIONS,
    STATUSES as BID_STATUSES,
    bid_process_aggregate_values,
    bid_process_structure_label,
    format_estimated_value_display,
    generate_ranking_image,
    pncp_check_awarded_contracts,
    pncp_search_contratacoes,
)
from bid_viability import build_pncp_documents_zip, parse_pncp_control_number
from contract_announcement import announcement_attachments_available, build_announcement_email
from contract_tasks import notify_ata_registration, notify_contract_task_needs
from contract_utils import (
    agency_document_fields,
    contract_duration_months,
    extract_agency_acronym,
    format_cnpj,
    humanize_remaining,
    normalize_agency_name,
    now_brt,
    parse_brazilian_number,
    today_brt,
)
from data_quality import contract_review_issues
from document_factory import (
    convert_template_to_docx,
    date_in_words,
    extract_placeholders,
    format_document_number,
    generate_document,
    resolve_project_path,
    safe_filename,
)
from db import (
    SESSION_IDLE_MINUTES,
    UPLOAD_DIR,
    archive_expired_contracts,
    authenticate,
    create_user_session,
    execute,
    get_user,
    hash_password,
    init_db,
    log_action,
    next_document_sequence,
    query,
    refresh_contract_lifecycle,
    revoke_user_session,
    revoke_user_sessions,
    sync_uploads_from_storage,
    sync_uploads_to_storage_if_changed,
    validate_user_session,
)
from importer import import_workbook
from guarantees import (
    CALCULATION_LABELS,
    GUARANTEE_MODALITIES,
    GUARANTEE_TYPES,
    REQUEST_STATUSES,
    calculate_required_amount,
    days_to_expiry,
    default_legal_basis,
    guarantee_issues,
    operational_status,
)
from portfolio import annual_allocation, backlog_rows, remaining_value, workbook_bytes
from reports import (
    BID_PDF_COLUMN_CATALOG,
    build_contract_overview_summary,
    generate_backlog_pdf,
    generate_bid_processes_pdf,
    generate_contract_dossier,
    generate_indices_pdf,
)
from notifications import MAX_ATTACHMENTS_BYTES, send_email, send_test_email, smtp_status
from totp import new_secret, provisioning_uri, verify as verify_totp

APP_VERSION = "77"
APP_STAGE = "Beta"
APP_RELEASE_DATE = "30/08/2026"
AUTH_COOKIE_NAME = "engemil_auth_session"
AUTH_QUERY_PARAM = "sessao"
BURGUNDY_HEX = "5a1235"
st.set_page_config(
    page_title=f"Gestão de Contratos | ENGEMIL V{APP_VERSION} {APP_STAGE}",
    page_icon="📑",
    layout="wide",
)
APP_DIR = Path(__file__).resolve().parent
init_db()
sync_uploads_from_storage()


@st.cache_resource(show_spinner=False)
def initialize_application_runtime():
    """Marca uma nova execução do servidor e reinicia o menu inicial.

    O cache sobrevive aos reruns e ao F5, mas é recriado quando o processo do
    Streamlit é encerrado e aberto novamente.
    """
    execute("UPDATE users SET last_page='Visão geral'")
    return uuid.uuid4().hex


APPLICATION_RUNTIME_ID = initialize_application_runtime()
newly_archived_ids = archive_expired_contracts()
if newly_archived_ids:
    st.session_state.auto_archived_notice = newly_archived_ids
AUTO_ARCHIVED_IDS = st.session_state.get("auto_archived_notice", [])
ASSET_DIR = APP_DIR / "assets"
LOGO_DARK_PATH = ASSET_DIR / "logo_engemil.png"
LOGO_LIGHT_PATH = ASSET_DIR / "logo_engemil_white.png"
if "ui_theme" not in st.session_state:
    st.session_state.ui_theme = "Escuro"
MODULE_LABELS = {
    "dashboard": "Visão geral",
    "contracts": "Contratos",
    "contract_detail": "Ficha do contrato",
    "new_contract": "Novo contrato",
    "bids": "Licitações",
    "sesmt": "SESMT",
    "exports": "Exportações",
    "indices": "Índices",
    "company_documents": "Documentos padrões",
}


def apply_theme(theme_name):
    dark = theme_name == "Escuro"
    colors = {
        "app": "#101114" if dark else "#f5f6f8",
        "sidebar": "#17181c" if dark else "#ffffff",
        "surface": "#1b1c20" if dark else "#ffffff",
        "surface_alt": "#24252a" if dark else "#f8f9fb",
        "border": "#3d353a" if dark else "#dde1e7",
        "text": "#f7f7f8" if dark else "#1f2937",
        "muted": "#d3a8bd" if dark else "#6b7280",
        "subtle": "#b6bac3" if dark else "#667085",
        "track": "#34353b" if dark else "#e4e7ec",
        "shadow": "rgba(0,0,0,.26)" if dark else "rgba(16,24,40,.08)",
        "input": "#202126" if dark else "#ffffff",
        "hover": "#32252c" if dark else "#f6edf2",
        "selected": "#4a2739" if dark else "#f1dce6",
        "accent": "#c15d8d" if dark else "#771641",
        "accent_hover": "#d676a4" if dark else "#5e0f33",
        "accent_soft": "#432735" if dark else "#f7e8ef",
        "table_header": "#27242a" if dark else "#f3edf0",
        "table_alt": "#202126" if dark else "#fafbfc",
        "disabled": "#292a2f" if dark else "#e7e9ed",
        "disabled_text": "#8d9098" if dark else "#767b84",
        "success": "#63d6a2" if dark else "#16794b",
        "warning": "#f1bf62" if dark else "#9a5b00",
        "danger": "#ff8a9a" if dark else "#b4233a",
        "table_filter": "none" if dark else "invert(1) hue-rotate(180deg) brightness(1.03) contrast(.92)",
    }
    st.markdown(
        f"""
<style>
.stApp, [data-testid="stAppViewContainer"] {{
    background:{colors["app"]};color:{colors["text"]};color-scheme:{"dark" if dark else "light"};
}}
[data-testid="stHeader"] {{background:transparent}}
[data-testid="stToolbar"] button,[data-testid="stToolbar"] button * {{
    color:{colors["text"]}!important;
}}
[data-testid="stSidebar"] {{
    background:{colors["sidebar"]};border-right:1px solid {colors["border"]};
}}
.stApp p,.stApp label,.stApp h1,.stApp h2,.stApp h3,.stApp h4,.stApp h5,.stApp h6,
[data-testid="stSidebar"] p,[data-testid="stSidebar"] label,
[data-testid="stCaptionContainer"],[data-testid="stCaptionContainer"] * {{
    color:{colors["text"]}!important;
}}
.stApp a {{color:{colors["accent"]}!important}}
.stApp hr {{border-color:{colors["border"]}!important}}
[data-baseweb="input"],[data-baseweb="base-input"],[data-baseweb="select"] > div,
[data-baseweb="textarea"],textarea,input {{
    background:{colors["input"]}!important;color:{colors["text"]}!important;
    border-color:{colors["border"]}!important;
}}
[data-baseweb="input"] *,[data-baseweb="base-input"] *,[data-baseweb="select"] *,
[data-baseweb="textarea"] *,[data-testid="stSelectbox"] *,
[data-testid="stMultiSelect"] * {{
    color:{colors["text"]}!important;
}}
input::placeholder,textarea::placeholder {{
    color:{colors["subtle"]}!important;opacity:.82!important;
}}
[data-baseweb="input"]:focus-within,[data-baseweb="base-input"]:focus-within,
[data-baseweb="select"] > div:focus-within,[data-baseweb="textarea"]:focus-within {{
    border-color:{colors["accent"]}!important;
    box-shadow:0 0 0 2px {colors["accent_soft"]}!important;
}}
[data-baseweb="select"] > div > div:last-child {{
    background:{colors["surface_alt"]}!important;border-left:1px solid {colors["border"]}!important;
}}
[data-baseweb="select"] svg,[data-testid="stSelectbox"] svg,
[data-baseweb="select"] svg path,[data-testid="stSelectbox"] svg path {{
    fill:{colors["accent"]}!important;color:{colors["accent"]}!important;
    stroke:{colors["accent"]}!important;
}}
[data-baseweb="popover"],[role="listbox"],[data-baseweb="menu"],
[data-baseweb="calendar"],[data-baseweb="datepicker"] {{
    background:{colors["surface"]}!important;color:{colors["text"]}!important;
    border-color:{colors["border"]}!important;
    box-shadow:0 16px 34px {colors["shadow"]}!important;
}}
[role="option"],[role="option"] *,[data-baseweb="menu"] li,[data-baseweb="menu"] li *,
[data-baseweb="calendar"] * {{
    background:{colors["surface"]}!important;color:{colors["text"]}!important;
}}
[role="option"]:hover,[role="option"]:hover *,[data-baseweb="menu"] li:hover,
[data-baseweb="menu"] li:hover * {{
    background:{colors["hover"]}!important;color:{colors["text"]}!important;
}}
[role="option"][aria-selected="true"],[role="option"][aria-selected="true"] * {{
    background:{colors["selected"]}!important;color:{colors["text"]}!important;
}}
[data-testid="stExpander"],[data-testid="stMetric"],[data-testid="stForm"] {{
    background:{colors["surface"]}!important;border-color:{colors["border"]}!important;
    box-shadow:0 8px 22px {colors["shadow"]};
}}
[data-testid="stExpander"] summary,[data-testid="stExpander"] summary *,
[data-testid="stPopover"] button,[data-testid="stPopover"] button * {{
    color:{colors["text"]}!important;background:{colors["surface"]}!important;
}}
[data-testid="stFileUploaderDropzone"] {{
    background:{colors["surface_alt"]}!important;border-color:{colors["border"]}!important;
}}
[data-testid="stFileUploaderDropzone"] *,[data-testid="stUploadedFile"] * {{
    color:{colors["text"]}!important;
}}
[data-testid="stFileUploaderDropzone"] button,
[data-testid="stFileUploaderDropzone"] [data-testid="baseButton-secondary"] {{
    background:{colors["accent"]}!important;color:#ffffff!important;
    border:1px solid {colors["accent"]}!important;border-radius:9px!important;
}}
[data-testid="stFileUploaderDropzone"] button *,
[data-testid="stFileUploaderDropzone"] [data-testid="baseButton-secondary"] *,
[data-testid="stFileUploaderDropzone"] button svg,
[data-testid="stFileUploaderDropzone"] button svg path {{
    color:#ffffff!important;fill:#ffffff!important;stroke:#ffffff!important;
}}
[data-testid="stTabs"] [data-baseweb="tab-list"] {{
    background:{colors["surface"]}!important;border:1px solid {colors["border"]};
    border-radius:13px;padding:5px;gap:4px;
}}
[data-testid="stTabs"] [data-baseweb="tab"],[data-testid="stTabs"] [data-baseweb="tab"] * {{
    color:{colors["text"]}!important;
}}
[data-testid="stTabs"] [aria-selected="true"] {{
    background:{colors["selected"]}!important;border-radius:9px;
}}
[data-testid="stTabs"] [data-baseweb="tab-highlight"] {{
    background:{colors["accent"]}!important;
}}
[data-testid="stDataFrame"],[data-testid="stDataEditor"] {{
    background:{colors["surface"]}!important;border:1px solid {colors["border"]}!important;
    border-radius:14px;overflow:hidden;box-shadow:0 10px 26px {colors["shadow"]};
}}
[data-testid="stDataFrame"] canvas,[data-testid="stDataEditor"] canvas {{
    filter:{colors["table_filter"]};
}}
[data-testid="stDataFrame"] button,[data-testid="stDataEditor"] button,
[data-testid="stDataFrame"] button *,[data-testid="stDataEditor"] button * {{
    color:{colors["text"]}!important;
}}
[data-testid="stAlert"],[data-testid="stAlert"] * {{
    color:{colors["text"]}!important;
}}
[data-testid="stCodeBlock"],[data-testid="stCodeBlock"] pre,
[data-testid="stCodeBlock"] code {{
    background:{colors["surface_alt"]}!important;color:{colors["text"]}!important;
    border-color:{colors["border"]}!important;
}}
[data-testid="stRadio"] label,[data-testid="stCheckbox"] label,
[data-testid="stToggle"] label {{
    color:{colors["text"]}!important;
}}
div[data-testid="stButton"] > button,
div[data-testid="stDownloadButton"] > button {{
    background:{colors["surface"]}!important;color:{colors["text"]}!important;
    border:1px solid {colors["border"]}!important;border-radius:10px!important;
    min-height:2.65rem;box-shadow:0 5px 14px {colors["shadow"]};
    transition:background .18s ease,border-color .18s ease,transform .18s ease;
}}
div[data-testid="stButton"] > button *,
div[data-testid="stDownloadButton"] > button * {{
    color:{colors["text"]}!important;
}}
div[data-testid="stButton"] > button:hover,
div[data-testid="stDownloadButton"] > button:hover {{
    background:{colors["hover"]}!important;border-color:{colors["accent"]}!important;
    transform:translateY(-1px);
}}
div[data-testid="stFormSubmitButton"] > button,
div[data-testid="stButton"] > button[kind="primary"],
div[data-testid="stDownloadButton"] > button[kind="primary"] {{
    background:{colors["accent"]}!important;color:#ffffff!important;
    border-color:{colors["accent"]}!important;border-radius:10px!important;
    min-height:2.65rem;box-shadow:0 7px 18px {colors["shadow"]};
}}
div[data-testid="stFormSubmitButton"] > button *,
div[data-testid="stButton"] > button[kind="primary"] *,
div[data-testid="stDownloadButton"] > button[kind="primary"] * {{
    color:#ffffff!important;
}}
div[data-testid="stFormSubmitButton"] > button:hover,
div[data-testid="stButton"] > button[kind="primary"]:hover,
div[data-testid="stDownloadButton"] > button[kind="primary"]:hover {{
    background:{colors["accent_hover"]}!important;border-color:{colors["accent_hover"]}!important;
}}
div[data-testid="stButton"] > button:disabled,
div[data-testid="stDownloadButton"] > button:disabled,
div[data-testid="stFormSubmitButton"] > button:disabled {{
    background:{colors["disabled"]}!important;color:{colors["disabled_text"]}!important;
    border-color:{colors["border"]}!important;opacity:1!important;box-shadow:none;
    transform:none;
}}
div[data-testid="stButton"] > button:disabled *,
div[data-testid="stDownloadButton"] > button:disabled *,
div[data-testid="stFormSubmitButton"] > button:disabled * {{
    color:{colors["disabled_text"]}!important;
}}
.metric-card{{background:{colors["surface"]};border:1px solid {colors["border"]};border-radius:12px;padding:18px}}
.muted{{color:{colors["muted"]};font-size:.9rem}}.big{{font-size:1.65rem;font-weight:750}}
.ok{{color:#34d399}}.warn{{color:#fbbf24}}.danger{{color:#fb7185}}
div[data-testid="stMetric"]{{background:{colors["surface"]};border:1px solid {colors["border"]};
padding:14px;border-radius:14px;min-width:0;container-type:inline-size}}
div[data-testid="stMetric"] [data-testid="stMetricValue"],
div[data-testid="stMetric"] [data-testid="stMetricLabel"] {{
    color:{colors["text"]}!important;
}}
div[data-testid="stMetric"] [data-testid="stMetricValue"],
div[data-testid="stMetric"] [data-testid="stMetricValue"] > div {{
    max-width:none!important;overflow:visible!important;text-overflow:clip!important;
    white-space:normal!important;overflow-wrap:anywhere!important;
    font-size:clamp(1rem,7cqi,1.75rem)!important;line-height:1.2!important;
}}
.dashboard-grid{{display:grid;grid-template-columns:repeat(auto-fit,minmax(min(100%,280px),1fr));
gap:14px;margin:14px 0 24px;align-items:stretch}}
.dash-card{{min-width:0;background:linear-gradient(145deg,{colors["surface_alt"]},{colors["surface"]});
border:1px solid {colors["border"]};border-radius:16px;padding:18px 20px;
box-shadow:0 10px 28px {colors["shadow"]};container-type:inline-size;
display:flex;flex-direction:column;height:100%;min-height:124px}}
.dash-card .label{{color:{colors["muted"]};font-size:.82rem;text-transform:uppercase;
letter-spacing:.06em;margin-bottom:8px}}
.dash-card .value{{color:{colors["text"]};font-size:clamp(1rem,5.8cqi,1.72rem);
font-weight:750;line-height:1.24;white-space:normal;overflow-wrap:anywhere;
word-break:normal;text-wrap:balance;font-variant-numeric:tabular-nums}}
.dash-card .value.medium{{font-size:clamp(.94rem,5cqi,1.46rem)}}
.dash-card .value.long{{font-size:clamp(.88rem,4.2cqi,1.22rem)}}
.dash-card .note{{color:{colors["subtle"]};font-size:.78rem;margin-top:auto;padding-top:9px;
white-space:normal;overflow-wrap:anywhere}}
.dash-card.green{{border-top:3px solid #2f9e68}}.dash-card.blue{{border-top:3px solid #7b1f4d}}
.dash-card.amber{{border-top:3px solid #d99100}}.dash-card.red{{border-top:3px solid #d9485f}}
.panel{{background:{colors["surface"]};border:1px solid {colors["border"]};border-radius:16px;
padding:18px;margin:10px 0 20px;container-type:inline-size;overflow:hidden}}
.bar-row{{display:grid;grid-template-columns:minmax(108px,1fr) minmax(72px,1.55fr)
minmax(118px,max-content);gap:10px;align-items:center;margin:12px 0;min-width:0}}
.bar-label{{font-weight:650;white-space:nowrap;overflow-wrap:normal;word-break:normal;
font-size:clamp(.72rem,3.2cqi,.92rem);min-width:0}}.bar-label.long{{
font-size:clamp(.66rem,2.8cqi,.84rem)}}.bar-track{{height:12px;
background:{colors["track"]};border-radius:999px;overflow:hidden;min-width:0}}
.bar-fill{{height:100%;border-radius:999px;background:linear-gradient(90deg,#5a1235,#a44d79)}}
.bar-value{{text-align:right;color:{colors["text"]};font-variant-numeric:tabular-nums;
font-size:clamp(.72rem,3.3cqi,.9rem);white-space:nowrap;min-width:0}}
.annual-bars{{padding:18px 20px}}
.annual-bars .bar-row{{grid-template-columns:72px minmax(120px,1fr)
minmax(150px,190px);gap:14px;margin:14px 0}}
.annual-bars .bar-label{{font-size:.86rem;text-align:left}}
.annual-bars .bar-value{{font-size:clamp(.72rem,2.2cqi,.88rem);width:100%;
max-width:190px}}
.data-review-card{{background:{colors["surface"]};border:1px solid {colors["border"]};
border-left:4px solid {colors["warning"]};border-radius:13px;padding:14px 16px;
margin:10px 0 8px;box-shadow:0 7px 20px {colors["shadow"]}}}
.data-review-title{{color:{colors["text"]};font-size:.94rem;font-weight:760;
line-height:1.35;margin-bottom:4px}}
.data-review-meta{{color:{colors["subtle"]};font-size:.76rem;margin-bottom:9px}}
.data-review-issue{{display:flex;align-items:flex-start;gap:8px;color:{colors["text"]};
font-size:.82rem;line-height:1.42;margin:5px 0}}
.data-review-dot{{display:inline-grid;place-items:center;flex:0 0 18px;height:18px;
border-radius:999px;background:{"#49391f" if dark else "#fff3dc"};
color:{colors["warning"]};font-size:.68rem;font-weight:800}}
.archive-banner{{background:{colors["surface"]};border:1px solid #d99100;border-left:5px solid #d99100;
border-radius:10px;padding:12px 14px;margin:8px 0 16px}}
.ranking-grid{{display:grid;grid-template-columns:repeat(auto-fit,minmax(min(100%,320px),1fr));
gap:15px;margin:12px 0 24px}}
.ranking-card{{position:relative;min-width:0;background:linear-gradient(145deg,
{colors["surface_alt"]},{colors["surface"]});border:1px solid {colors["border"]};
border-radius:17px;padding:19px;box-shadow:0 10px 28px {colors["shadow"]};
overflow:hidden;container-type:inline-size}}
.ranking-card::before{{content:"";position:absolute;inset:0 auto 0 0;width:4px;
background:linear-gradient(180deg,{colors["accent"]},#d99100)}}
.ranking-head{{display:flex;align-items:flex-start;gap:11px;margin-bottom:14px}}
.ranking-position{{display:grid;place-items:center;flex:0 0 31px;height:31px;border-radius:10px;
background:{colors["accent_soft"]};color:{colors["accent"]};font-weight:800}}
.ranking-title{{min-width:0;color:{colors["text"]};font-weight:760;line-height:1.25;
font-size:clamp(.9rem,4.8cqi,1.04rem)}}
.ranking-contract{{color:{colors["subtle"]};font-size:.77rem;margin-top:4px}}
.ranking-values{{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:10px}}
.ranking-value{{background:{colors["surface"]};border:1px solid {colors["border"]};
border-radius:11px;padding:10px;min-width:0}}
.ranking-value span{{display:block;color:{colors["subtle"]};font-size:.68rem;
text-transform:uppercase;letter-spacing:.04em;margin-bottom:5px}}
.ranking-value strong{{display:block;color:{colors["text"]};font-size:clamp(.76rem,4.2cqi,.96rem);
white-space:nowrap;font-variant-numeric:tabular-nums}}
.ranking-footer{{display:flex;flex-wrap:wrap;gap:7px;align-items:center;margin-top:12px}}
.ranking-pill{{display:inline-flex;padding:4px 8px;border-radius:999px;background:{colors["accent_soft"]};
color:{colors["accent"]};font-size:.68rem;font-weight:730}}
.ranking-instrument{{color:{colors["subtle"]};font-size:.72rem}}
.modern-table-shell{{background:{colors["surface"]};border:1px solid {colors["border"]};
border-radius:16px;box-shadow:0 10px 28px {colors["shadow"]};overflow:hidden;
margin:10px 0 18px}}
.modern-table-scroll{{overflow:auto;scrollbar-color:{colors["accent"]} {colors["surface_alt"]}}}
.modern-table{{width:100%;border-collapse:separate;border-spacing:0;color:{colors["text"]};
font-size:.88rem}}
.modern-table thead th{{position:sticky;top:0;z-index:2;background:{colors["table_header"]};
color:{colors["muted"]};font-size:.71rem;font-weight:750;letter-spacing:.045em;
text-transform:uppercase;text-align:left;padding:13px 14px;border-bottom:1px solid {colors["border"]};
white-space:normal}}
.modern-table tbody td{{background:{colors["surface"]};color:{colors["text"]};
padding:12px 14px;border-bottom:1px solid {colors["border"]};vertical-align:top;
line-height:1.38;white-space:normal;overflow-wrap:anywhere}}
.modern-table tbody tr:nth-child(even) td{{background:{colors["table_alt"]}}}
.modern-table tbody tr:hover td{{background:{colors["hover"]}}}
.modern-table tbody tr:last-child td{{border-bottom:0}}
.modern-table td.cell-money{{white-space:nowrap;text-align:right;font-weight:720;
font-variant-numeric:tabular-nums;color:{colors["accent"]}}}
.modern-table td.cell-number{{text-align:right;font-variant-numeric:tabular-nums}}
.cell-badge{{display:inline-flex;align-items:center;padding:4px 9px;border-radius:999px;
font-size:.72rem;font-weight:750;letter-spacing:.025em;white-space:nowrap;
background:{colors["accent_soft"]};color:{colors["accent"]}}}
.cell-badge.success{{background:{"#173b2d" if dark else "#e6f6ee"};
color:{colors["success"]}}}
.cell-badge.warning{{background:{"#49391f" if dark else "#fff3dc"};
color:{colors["warning"]}}}
.cell-badge.danger{{background:{"#48252c" if dark else "#fdecef"};
color:{colors["danger"]}}}
.modern-table-meta{{display:flex;justify-content:flex-end;align-items:center;
padding:9px 14px;background:{colors["surface_alt"]};border-top:1px solid {colors["border"]};
color:{colors["subtle"]};font-size:.76rem}}
.app-footer{{margin:34px 0 4px;padding:18px 16px 8px;border-top:1px solid {colors["border"]};
text-align:center;color:{colors["subtle"]};font-size:.78rem;line-height:1.65}}
.app-footer strong{{color:{colors["text"]};font-weight:750}}
.app-footer .developer-title{{color:{colors["accent"]};font-weight:700}}
.temporary-success{{background:{"#143f2b" if dark else "#d9f4e5"};
border:1px solid {colors["success"]};border-radius:10px;padding:15px 18px;margin:10px 0 18px;
color:{colors["text"]};overflow:hidden;animation:temporary-success-hide 8s ease forwards}}
@keyframes temporary-success-hide{{0%,78%{{opacity:1;max-height:120px;padding-top:15px;
padding-bottom:15px;margin-bottom:18px}}96%{{opacity:0;max-height:120px}}100%{{opacity:0;
max-height:0;padding-top:0;padding-bottom:0;margin-top:0;margin-bottom:0;border-width:0}}}}
.contract-object{{background:{colors["surface"]};border:1px solid {colors["border"]};
border-left:4px solid {colors["accent"]};border-radius:12px;padding:15px 17px;margin:8px 0 18px;
color:{colors["text"]};line-height:1.62;text-align:justify;text-justify:inter-word;
white-space:pre-wrap;overflow-wrap:break-word}}
.contract-object strong{{color:{colors["accent"]}}}
@container(max-width:430px){{.bar-row{{grid-template-columns:minmax(0,1fr) auto;gap:6px 10px;
align-items:end}}.bar-label{{grid-column:1;white-space:nowrap;font-size:.78rem}}
.bar-value{{grid-column:2;font-size:.78rem}}.bar-track{{grid-column:1/-1;grid-row:2}}}}
@container(max-width:620px){{.annual-bars .bar-row{{grid-template-columns:58px minmax(0,1fr);
gap:6px 10px;align-items:end}}.annual-bars .bar-label{{grid-column:1}}
.annual-bars .bar-value{{grid-column:2;text-align:right;max-width:none}}
.annual-bars .bar-track{{grid-column:1/-1;grid-row:2}}}}
@media(max-width:700px){{.dashboard-grid{{grid-template-columns:1fr}}.dash-card .value{{font-size:1.3rem}}
.modern-table{{font-size:.82rem}}.modern-table thead th,.modern-table tbody td{{padding:10px 11px}}
.ranking-values{{grid-template-columns:1fr}}}}
</style>
""",
        unsafe_allow_html=True,
    )


apply_theme(st.session_state.ui_theme)


def rerun():
    st.rerun()


def temporary_success(message):
    """Exibe uma confirmação que desaparece visualmente após oito segundos."""
    st.markdown(
        f'<div class="temporary-success">{escape(str(message))}</div>',
        unsafe_allow_html=True,
    )


def browser_user_agent():
    try:
        return st.context.headers.get("User-Agent", "")
    except Exception:
        return ""


def browser_uses_https():
    try:
        forwarded = st.context.headers.get("X-Forwarded-Proto", "")
        return forwarded.lower() == "https" or str(st.context.url).lower().startswith("https://")
    except Exception:
        return False


def browser_auth_token():
    # st.context.cookies funcionaria em instalações locais/próprias, mas o
    # proxy do Streamlit Community Cloud não repassa o cabeçalho Cookie ao
    # backend Python (confirmado via diagnóstico: chega sempre vazio lá) —
    # e um <script> não consegue navegar a página pai para "devolver" o
    # cookie, pois o iframe de components.html() é sandboxed sem
    # allow-top-navigation. Por isso o parâmetro de URL é a fonte
    # confiável: ele viaja com o navegador em qualquer F5, sem depender de
    # cookie nenhum.
    try:
        request_token = st.context.cookies.get(AUTH_COOKIE_NAME)
    except Exception:
        request_token = None
    if request_token:
        return str(request_token).strip()
    try:
        relayed = st.query_params.get(AUTH_QUERY_PARAM)
    except Exception:
        relayed = None
    return str(relayed or "").strip()


def _set_auth_query_param(token):
    try:
        st.query_params[AUTH_QUERY_PARAM] = token
    except Exception:
        pass


def _clear_auth_query_param():
    try:
        if AUTH_QUERY_PARAM in st.query_params:
            del st.query_params[AUTH_QUERY_PARAM]
    except Exception:
        pass


def start_authenticated_session(authenticated_user):
    token = create_user_session(
        authenticated_user["id"],
        browser_user_agent(),
    )
    st.session_state.user = dict(authenticated_user)
    st.session_state["_auth_token"] = token
    st.session_state.ui_theme = authenticated_user["preferred_theme"] or "Escuro"
    st.session_state.navigation_page = (
        authenticated_user["last_page"] or "Visão geral"
    )
    _set_auth_query_param(token)


def restore_authenticated_session():
    """Restaura a autenticação após F5 sem guardar senha ou token no banco."""
    if "pending_2fa_user_id" in st.session_state and "user" not in st.session_state:
        return
    token = st.session_state.get("_auth_token") or browser_auth_token()
    session_user = st.session_state.get("user")
    if session_user and not token:
        current_user = get_user(session_user["id"])
        if current_user:
            start_authenticated_session(current_user)
        else:
            st.session_state.clear()
        return
    if not token:
        return
    restored_user = validate_user_session(
        token,
        browser_user_agent(),
        touch=True,
    )
    if not restored_user:
        revoke_user_session(token)
        _clear_auth_query_param()
        st.session_state.pop("_auth_token", None)
        st.session_state.pop("user", None)
        st.session_state["auth_notice"] = (
            f"Sua sessão expirou após {SESSION_IDLE_MINUTES} minutos sem atividade. "
            "Entre novamente para continuar."
        )
        return
    st.session_state.user = dict(restored_user)
    st.session_state["_auth_token"] = token
    st.session_state.ui_theme = restored_user["preferred_theme"] or "Escuro"
    if "navigation_page" not in st.session_state:
        st.session_state.navigation_page = restored_user["last_page"] or "Visão geral"
    _set_auth_query_param(token)


def finish_authenticated_session(reason="LOGOUT"):
    token = st.session_state.get("_auth_token") or browser_auth_token()
    current_user = st.session_state.get("user")
    if token:
        revoke_user_session(token)
    if current_user:
        execute(
            "UPDATE users SET last_page='Visão geral' WHERE id=?",
            (current_user["id"],),
        )
        log_action(
            current_user["id"],
            reason,
            "sessão",
            current_user["id"],
            f"Sessão encerrada. Limite de inatividade: {SESSION_IDLE_MINUTES} minutos.",
        )
    _clear_auth_query_param()
    st.session_state.clear()


def password_policy_errors(password, *, name="", email=""):
    """Retorna regras de senha não atendidas sem registrar a credencial."""
    value = str(password or "")
    errors = []
    if len(value) < 8:
        errors.append("pelo menos 8 caracteres")
    if not re.search(r"[A-Z]", value):
        errors.append("pelo menos uma letra maiúscula")
    if not re.search(r"[a-z]", value):
        errors.append("pelo menos uma letra minúscula")
    if not re.search(r"[^A-Za-z0-9]", value):
        errors.append("pelo menos um caractere especial")
    common_passwords = {
        "administrador", "alterar@123", "engemil123", "senha1234",
        "password1", "qwerty123", "12345678", "admin1234",
        "123456789012345", "admin1234567890",
        "alterar@1234567", "engemil12345678", "senha1234567890",
        "password123456", "qwerty123456789",
    }
    if value.strip().casefold() in common_passwords:
        errors.append("não ser uma senha comum ou previsível")
    lowered = value.casefold()
    identity_parts = [
        part.casefold()
        for part in (str(name or "").split() + [str(email or "").split("@", 1)[0]])
        if len(part) >= 4
    ]
    if any(part in lowered for part in identity_parts):
        errors.append("não conter nome ou parte principal do e-mail")
    return errors


def scroll_page_to_top():
    """Reposiciona o conteúdo somente quando o ambiente de navegação muda."""
    components.html(
        """
        <script>
        const doc = window.parent.document;
        const view = doc.querySelector('[data-testid="stAppViewContainer"]');
        if (view) view.scrollTo({top: 0, left: 0, behavior: 'instant'});
        window.parent.scrollTo({top: 0, left: 0, behavior: 'instant'});
        </script>
        """,
        height=0,
        width=0,
    )


def brl(value):
    try:
        amount = parse_brazilian_number(value, 0)
    except (TypeError, ValueError):
        amount = 0.0
    return f"R$ {amount:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")


def contract_amendments_with_arts(contract_id):
    """Carrega aditivos com ARTs e garantias efetivamente vinculadas."""
    amendments = [
        dict(row) for row in query(
            "SELECT * FROM amendments WHERE contract_id=? ORDER BY id",
            (contract_id,),
        )
    ]
    linked_by_amendment = {}
    for raw in query(
        """SELECT amendment_id,art_number,status
        FROM arts WHERE contract_id=? AND amendment_id IS NOT NULL
        ORDER BY issue_date,id""",
        (contract_id,),
    ):
        item = dict(raw)
        linked_by_amendment.setdefault(int(item["amendment_id"]), []).append(item)
    guarantees_by_amendment = {}
    for raw in query(
        """SELECT id,amendment_id,guarantee_type,custom_type,request_status,
        policy_number,end_date,required_amount,guaranteed_amount
        FROM contract_guarantees
        WHERE contract_id=? AND amendment_id IS NOT NULL ORDER BY id""",
        (contract_id,),
    ):
        item = dict(raw)
        guarantees_by_amendment.setdefault(int(item["amendment_id"]), []).append(item)
    for amendment in amendments:
        linked = linked_by_amendment.get(int(amendment["id"]), [])
        amendment["linked_art_count"] = len(linked)
        if linked:
            amendment["art_status"] = " · ".join(
                f"ART {item['art_number']} ({item['status'] or 'SEM STATUS'})"
                for item in linked
            )
        else:
            previous_status = str(amendment.get("art_status") or "").strip()
            amendment["art_status"] = (
                f"Sem ART vinculada · histórico: {previous_status}"
                if previous_status else "Sem ART vinculada"
            )
        linked_guarantees = guarantees_by_amendment.get(int(amendment["id"]), [])
        amendment["linked_guarantee_count"] = len(linked_guarantees)
        if linked_guarantees:
            amendment["guarantee_status"] = " · ".join(
                (
                    f"{item.get('custom_type') or item.get('guarantee_type')}: "
                    f"{operational_status(item)}"
                    + (f" até {fmt_date(item.get('end_date'))}" if item.get("end_date") else "")
                )
                for item in linked_guarantees
            )
        else:
            previous_guarantee = str(amendment.get("guarantee_status") or "").strip()
            amendment["guarantee_status"] = (
                f"Sem garantia vinculada · histórico: {previous_guarantee}"
                if previous_guarantee else "Sem garantia vinculada"
            )
    return amendments


def amendment_instrument_label(amendment):
    return " ".join(filter(None, [
        str(amendment.get("ordinal") or "").strip(),
        str(amendment.get("kind") or "").strip(),
    ])).strip() or f"Instrumento {amendment.get('id')}"


def art_instrument_reference(art):
    if art.get("amendment_id"):
        return " ".join(filter(None, [
            str(art.get("amendment_ordinal") or "").strip(),
            str(art.get("amendment_kind") or "").strip(),
        ])).strip() or "Aditivo vinculado"
    if art.get("ata_amendment_id"):
        ata_label = " · ".join(filter(None, [
            art.get("ata_contract_number"), art.get("ata_client"),
        ]))
        amendment_label = " ".join(filter(None, [
            str(art.get("ata_amendment_ordinal") or "").strip(),
            str(art.get("ata_amendment_kind") or "").strip(),
        ])).strip() or "Aditivo"
        return f"Aditivo da ATA · {ata_label} · {amendment_label}"
    if art.get("ata_contract_id"):
        ata_label = " · ".join(filter(None, [
            art.get("ata_contract_number"), art.get("ata_client"),
        ]))
        return f"Contrato da ATA · {ata_label}"
    if str(art.get("instrument_scope") or "").upper() == "CONTRATO_INICIAL":
        return "Contrato inicial"
    return "Não associado — revisar"


def fmt_percent(value, decimals=2):
    return (
        f"{float(value or 0):,.{decimals}f}%"
        .replace(",", "X")
        .replace(".", ",")
        .replace("X", ".")
    )


BDI_METHOD_LABELS = {
    "FORMULA_COMPOSTA": "Fórmula composta",
    "SOMA_DIRETA": "Soma direta",
}
BDI_ROUNDING_LABELS = {
    "TRUNCAR_4": "Truncar a fração em 4 casas",
    "ARREDONDAR_2": "Arredondar o percentual em 2 casas",
}
BDI_REGIME_LABELS = {
    "CONTRATO": "Seguir o regime do contrato",
    "ONERADO": "Onerado / não desonerado",
    "DESONERADO": "Desonerado",
    "NÃO DEFINIDO": "Não definido",
}
BDI_DB_FIELDS = (
    "name",
    "reference_name",
    "tax_regime",
    "calculation_method",
    "rounding_method",
    "indirect_costs",
    "central_administration",
    "insurance",
    "risks",
    "guarantees",
    "other_indirect_costs",
    "financial_expenses",
    "profit",
    "pis",
    "cofins",
    "iss",
    "cprb",
    "other_taxes",
    "notes",
)


def _option_index(options, value, default=0):
    try:
        return options.index(value)
    except ValueError:
        return default


def load_contract_bdis(contract_id, contract_regime=None):
    contract_regime = contract_regime or "NÃO DEFINIDO"
    result = []
    for raw in query(
        "SELECT * FROM contract_bdis WHERE contract_id=? ORDER BY id", (contract_id,)
    ):
        item = dict(raw)
        item["tax_total"] = float(tax_total(item))
        item["composed_indirect_total"] = float(composed_indirect_total(item))
        try:
            item["calculated_percentage"] = float(calculate_bdi(item))
            item["calculation_error"] = ""
        except ValueError as calculation_error:
            item["calculated_percentage"] = 0.0
            item["calculation_error"] = str(calculation_error)
        item["effective_tax_regime"] = (
            contract_regime
            if item.get("tax_regime") in (None, "", "CONTRATO")
            else item["tax_regime"]
        )
        result.append(item)
    return result


def bdi_input_fields(prefix, values=None, contract_regime="NÃO DEFINIDO"):
    values = dict(values or {})
    first, second, third = st.columns(3)
    name = first.text_input(
        "Identificação do BDI",
        value=str(values.get("name") or ""),
        placeholder="Ex.: BDI 1",
        key=f"{prefix}_name",
    )
    reference_name = second.text_input(
        "Referência/aplicação",
        value=str(values.get("reference_name") or ""),
        placeholder="Ex.: Mão de obra, materiais ou serviços",
        key=f"{prefix}_reference",
    )
    regime_options = ["CONTRATO", "ONERADO", "DESONERADO"]
    regime = third.selectbox(
        "Regime deste BDI",
        regime_options,
        index=_option_index(
            regime_options, str(values.get("tax_regime") or "CONTRATO")
        ),
        format_func=lambda option: BDI_REGIME_LABELS[option],
        key=f"{prefix}_regime",
    )
    method_options = ["FORMULA_COMPOSTA", "SOMA_DIRETA"]
    method = st.selectbox(
        "Método de cálculo",
        method_options,
        index=_option_index(
            method_options,
            str(values.get("calculation_method") or "FORMULA_COMPOSTA"),
        ),
        format_func=lambda option: BDI_METHOD_LABELS[option],
        key=f"{prefix}_method",
    )
    payload = {
        "name": name.strip(),
        "reference_name": reference_name.strip(),
        "tax_regime": regime,
        "calculation_method": method,
        "rounding_method": str(values.get("rounding_method") or "TRUNCAR_4"),
        "indirect_costs": 0.0,
        "central_administration": 0.0,
        "insurance": 0.0,
        "risks": 0.0,
        "guarantees": 0.0,
        "other_indirect_costs": 0.0,
        "financial_expenses": 0.0,
        "profit": 0.0,
        "pis": 0.0,
        "cofins": 0.0,
        "iss": 0.0,
        "cprb": 0.0,
        "other_taxes": 0.0,
    }
    if method == "FORMULA_COMPOSTA":
        rounding_options = ["TRUNCAR_4", "ARREDONDAR_2"]
        payload["rounding_method"] = st.selectbox(
            "Tratamento das casas decimais",
            rounding_options,
            index=_option_index(
                rounding_options,
                str(values.get("rounding_method") or "TRUNCAR_4"),
            ),
            format_func=lambda option: BDI_ROUNDING_LABELS[option],
            key=f"{prefix}_rounding",
        )
        st.caption(
            "Fórmula: ((1 + (AC + S + R + G + outros)/100) × (1 + DF/100) × "
            "(1 + L/100) ÷ (1 − T/100)) − 1."
        )
        columns = st.columns(3)
        payload["central_administration"] = columns[0].number_input(
            "Administração central – AC (%)", min_value=0.0, value=float(
                values.get("central_administration") or 0
            ), step=0.01, format="%.4f", key=f"{prefix}_ac",
        )
        payload["insurance"] = columns[1].number_input(
            "Seguros – S (%)", min_value=0.0,
            value=float(values.get("insurance") or 0), step=0.01,
            format="%.4f", key=f"{prefix}_insurance",
        )
        payload["risks"] = columns[2].number_input(
            "Riscos – R (%)", min_value=0.0,
            value=float(values.get("risks") or 0), step=0.01,
            format="%.4f", key=f"{prefix}_risks",
        )
        columns = st.columns(3)
        payload["guarantees"] = columns[0].number_input(
            "Garantias – G (%)", min_value=0.0,
            value=float(values.get("guarantees") or 0), step=0.01,
            format="%.4f", key=f"{prefix}_guarantees",
        )
        payload["other_indirect_costs"] = columns[1].number_input(
            "Outros custos indiretos (%)", min_value=0.0,
            value=float(values.get("other_indirect_costs") or 0), step=0.01,
            format="%.4f", key=f"{prefix}_other_indirect",
        )
        payload["financial_expenses"] = columns[2].number_input(
            "Despesas financeiras – DF (%)", min_value=0.0,
            value=float(values.get("financial_expenses") or 0), step=0.01,
            format="%.4f", key=f"{prefix}_df",
        )
    else:
        st.caption(
            "Soma direta: Custos indiretos + Lucro + PIS + COFINS + ISS + CPRB "
            "+ outros tributos."
        )
        payload["indirect_costs"] = st.number_input(
            "Custos indiretos (%)", min_value=0.0,
            value=float(values.get("indirect_costs") or 0), step=0.01,
            format="%.4f", key=f"{prefix}_indirect",
        )

    payload["profit"] = st.number_input(
        "Lucro – L (%)", min_value=0.0, value=float(values.get("profit") or 0),
        step=0.01, format="%.4f", key=f"{prefix}_profit",
    )
    st.markdown("##### Tributos")
    tax_columns = st.columns(3)
    payload["pis"] = tax_columns[0].number_input(
        "PIS (%)", min_value=0.0, value=float(values.get("pis") or 0),
        step=0.01, format="%.4f", key=f"{prefix}_pis",
    )
    payload["cofins"] = tax_columns[1].number_input(
        "COFINS (%)", min_value=0.0, value=float(values.get("cofins") or 0),
        step=0.01, format="%.4f", key=f"{prefix}_cofins",
    )
    payload["iss"] = tax_columns[2].number_input(
        "ISS (%)", min_value=0.0, value=float(values.get("iss") or 0),
        step=0.01, format="%.4f", key=f"{prefix}_iss",
    )
    tax_columns = st.columns(2)
    payload["cprb"] = tax_columns[0].number_input(
        "CPRB (%)", min_value=0.0, value=float(values.get("cprb") or 0),
        step=0.01, format="%.4f", key=f"{prefix}_cprb",
    )
    payload["other_taxes"] = tax_columns[1].number_input(
        "Outros tributos (%)", min_value=0.0,
        value=float(values.get("other_taxes") or 0), step=0.01,
        format="%.4f", key=f"{prefix}_other_taxes",
    )
    payload["notes"] = st.text_area(
        "Observações e fundamento da composição",
        value=str(values.get("notes") or ""),
        key=f"{prefix}_notes",
    )
    error = ""
    calculated = 0.0
    try:
        calculated = float(calculate_bdi(payload))
    except ValueError as calculation_error:
        error = str(calculation_error)
        st.error(error)
    effective_regime = (
        contract_regime if regime == "CONTRATO" else regime
    )
    responsive_cards([
        (
            "BDI calculado",
            fmt_percent(calculated),
            BDI_METHOD_LABELS[method],
            "green",
        ),
        (
            "Total dos tributos",
            fmt_percent(tax_total(payload)),
            "PIS + COFINS + ISS + CPRB + outros",
            "amber",
        ),
        (
            "Regime aplicável",
            BDI_REGIME_LABELS.get(effective_regime, effective_regime),
            "Referência para conferência do faturamento",
            "blue",
        ),
    ])
    return payload, error


def parse_brl_input(value):
    text = str(value or "").strip().replace("R$", "").replace("\u00a0", "").replace(" ", "")
    if not text:
        return 0.0
    if "," in text:
        text = text.replace(".", "").replace(",", ".")
    elif text.count(".") > 1:
        text = text.replace(".", "")
    parsed = float(text)
    if parsed < 0:
        raise ValueError("O valor não pode ser negativo.")
    return parsed


def currency_input(container, label, value, key):
    return container.text_input(label, value=brl(value), key=key)


def fmt_date(value):
    if not value:
        return "—"
    try:
        parsed = date.fromisoformat(str(value)[:10])
        months = [
            "janeiro", "fevereiro", "março", "abril", "maio", "junho",
            "julho", "agosto", "setembro", "outubro", "novembro", "dezembro",
        ]
        return f"{parsed.day:02d} de {months[parsed.month - 1]} de {parsed.year}"
    except ValueError:
        return str(value)


def fmt_date_long(value):
    if not value:
        return "Não informada"
    try:
        parsed = date.fromisoformat(str(value)[:10])
    except ValueError:
        return str(value)
    months = [
        "janeiro", "fevereiro", "março", "abril", "maio", "junho",
        "julho", "agosto", "setembro", "outubro", "novembro", "dezembro",
    ]
    return f"{parsed.day:02d} de {months[parsed.month - 1]} de {parsed.year}"


def fmt_datetime(value):
    if not value:
        return "—"
    try:
        parsed = datetime.fromisoformat(str(value))
    except ValueError:
        return str(value)
    # Os carimbos gravados no banco (CURRENT_TIMESTAMP do SQLite/Turso, ou
    # datetime.now(timezone.utc) explícito) são sempre em UTC — só na
    # exibição é que convertemos para o horário de Brasília (UTC-3, sem
    # horário de verão desde 2019), sem alterar o que fica armazenado.
    return (parsed - timedelta(hours=3)).strftime("%d/%m/%Y %H:%M")


def responsive_cards(items):
    cards = []
    for label, value, note, color in items:
        text_value = str(value)
        length_class = "long" if len(text_value) > 34 else "medium" if len(text_value) > 22 else ""
        cards.append(
            f'<div class="dash-card {color}"><div class="label">{escape(str(label))}</div>'
            f'<div class="value {length_class}">{escape(text_value)}</div>'
            f'<div class="note">{escape(str(note))}</div></div>'
        )
    st.markdown(f'<div class="dashboard-grid">{"".join(cards)}</div>', unsafe_allow_html=True)


def ranking_cards(contracts):
    cards = []
    for position, (_, row) in enumerate(contracts.iterrows(), start=1):
        client = escape(str(row.get("client") or "Contratante não informado"))
        number = escape(str(row.get("contract_number") or "Contrato sem número"))
        category = escape(str(row.get("category") or "Sem modalidade"))
        instrument = escape(str(row.get("current_instrument") or "Contrato"))
        current_value = escape(brl(row.get("current_value")))
        remaining = escape(brl(row.get("Remanescente")))
        cards.append(
            f'<article class="ranking-card">'
            f'<div class="ranking-head"><div class="ranking-position">{position}</div>'
            f'<div><div class="ranking-title">{client}</div>'
            f'<div class="ranking-contract">Contrato {number}</div></div></div>'
            f'<div class="ranking-values">'
            f'<div class="ranking-value"><span>Valor atual</span><strong>{current_value}</strong></div>'
            f'<div class="ranking-value"><span>Remanescente</span><strong>{remaining}</strong></div>'
            f'</div><div class="ranking-footer"><span class="ranking-pill">{category}</span>'
            f'<span class="ranking-instrument">{instrument}</span></div></article>'
        )
    st.markdown(f'<div class="ranking-grid">{"".join(cards)}</div>', unsafe_allow_html=True)


def value_bars(items, formatter=brl, variant=""):
    maximum = max((float(value or 0) for _, value in items), default=0) or 1
    rows = []
    for label, value in items:
        width = max(1, float(value or 0) / maximum * 100)
        label_text = str(label or "Não informado")
        label_class = " long" if len(label_text) > 10 else ""
        rows.append(
            f'<div class="bar-row"><div class="bar-label{label_class}">{escape(label_text)}</div>'
            f'<div class="bar-track"><div class="bar-fill" style="width:{width:.2f}%"></div></div>'
            f'<div class="bar-value">{escape(formatter(value))}</div></div>'
        )
    panel_class = f"panel {variant}".strip()
    st.markdown(
        f'<div class="{panel_class}">{"".join(rows)}</div>',
        unsafe_allow_html=True,
    )


def modern_table(data, max_height=None):
    """Renderiza tabelas de consulta com o mesmo visual nos dois temas."""
    frame = data.copy() if isinstance(data, pd.DataFrame) else pd.DataFrame(data)
    if frame.empty:
        st.caption("Nenhum registro disponível.")
        return
    badge_columns = {
        "modalidade", "status", "situação da vigência", "prioridade", "perfil",
        "ativo", "exigir 2fa", "2fa configurado", "garantia", "art",
    }
    success_terms = {"ATIVO", "ATIVA", "VIGENTE", "CONCLUÍDO", "CONCLUÍDA", "SIM", "PAGO"}
    warning_terms = {"AGUARDANDO", "PENDENTE", "MÉDIA", "ATENÇÃO", "EM ANDAMENTO"}
    danger_terms = {"ARQUIVADO", "ARQUIVADA", "VENCIDO", "VENCIDA", "NÃO", "CRÍTICA", "INATIVO"}

    def display_value(value):
        if value is None:
            return "—"
        try:
            if bool(pd.isna(value)):
                return "—"
        except (TypeError, ValueError):
            pass
        return str(value)

    def badge_class(value):
        normalized = str(value or "").strip().upper()
        if normalized in success_terms or any(term in normalized for term in {"VIGENTE", "CONCLUÍ"}):
            return "success"
        if normalized in danger_terms or any(term in normalized for term in {"VENCID", "ARQUIVAD", "CRÍTIC"}):
            return "danger"
        if normalized in warning_terms or any(term in normalized for term in {"AGUARDANDO", "PENDENTE"}):
            return "warning"
        return ""

    headers = "".join(f"<th>{escape(str(column))}</th>" for column in frame.columns)
    body_rows = []
    for _, row in frame.iterrows():
        cells = []
        for column in frame.columns:
            raw_value = row[column]
            column_name = str(column).strip().casefold()
            is_numeric = isinstance(raw_value, (int, float)) and not isinstance(
                raw_value, bool
            )
            is_money_column = (
                is_numeric
                and any(term in column_name for term in (
                    "valor", "salário", "custo", "benefício", "remanescente",
                    "patrimônio", "receita",
                ))
                and "%" not in column_name
                and "percentual" not in column_name
            )
            value = brl(raw_value) if is_money_column else display_value(raw_value)
            cell_class = ""
            content = escape(value).replace("\n", "<br>")
            if value.startswith("R$ "):
                cell_class = "cell-money"
            elif is_numeric:
                cell_class = "cell-number"
            if column_name in badge_columns and value != "—":
                content = (
                    f'<span class="cell-badge {badge_class(value)}">'
                    f"{content}</span>"
                )
            cells.append(f'<td class="{cell_class}">{content}</td>')
        body_rows.append(f"<tr>{''.join(cells)}</tr>")
    minimum_width = max(760, len(frame.columns) * 145)
    height_style = f"max-height:{int(max_height)}px;" if max_height else ""
    row_label = "registro" if len(frame) == 1 else "registros"
    st.markdown(
        f'<div class="modern-table-shell">'
        f'<div class="modern-table-scroll" style="{height_style}">'
        f'<table class="modern-table" style="min-width:{minimum_width}px">'
        f"<thead><tr>{headers}</tr></thead><tbody>{''.join(body_rows)}</tbody>"
        f"</table></div>"
        f'<div class="modern-table-meta">{len(frame)} {row_label}</div></div>',
        unsafe_allow_html=True,
    )


def load_contracts(where_clause=""):
    sql = f"""
    SELECT c.*,
      COALESCE(
        (SELECT a.value FROM amendments a
         WHERE a.contract_id=c.id AND a.value IS NOT NULL AND a.value>0
         AND NOT (
            UPPER(TRIM(COALESCE(a.ordinal,'')))
                IN ('INICIAL','CONTRATO INICIAL')
            AND UPPER(TRIM(COALESCE(a.kind,'')))
                IN ('CONTRATO','CONTRATO INICIAL')
         )
         ORDER BY a.id DESC LIMIT 1),
        NULLIF(c.current_value,0), c.original_value, 0
      ) AS effective_value,
      COALESCE(
        (SELECT a.start_date FROM amendments a
         WHERE a.contract_id=c.id AND a.start_date IS NOT NULL AND a.start_date<>''
         AND NOT (
            UPPER(TRIM(COALESCE(a.ordinal,'')))
                IN ('INICIAL','CONTRATO INICIAL')
            AND UPPER(TRIM(COALESCE(a.kind,'')))
                IN ('CONTRATO','CONTRATO INICIAL')
         )
         ORDER BY a.id DESC LIMIT 1), c.start_date
      ) AS effective_start,
      COALESCE(NULLIF(c.original_start_date,''),c.start_date) AS original_start,
      COALESCE(NULLIF(c.original_end_date,''),c.end_date) AS original_end,
      COALESCE(c.original_value,0) AS effective_original_value,
      COALESCE(
        (SELECT a.end_date FROM amendments a
         WHERE a.contract_id=c.id AND a.end_date IS NOT NULL AND a.end_date<>''
         AND NOT (
            UPPER(TRIM(COALESCE(a.ordinal,'')))
                IN ('INICIAL','CONTRATO INICIAL')
            AND UPPER(TRIM(COALESCE(a.kind,'')))
                IN ('CONTRATO','CONTRATO INICIAL')
         )
         ORDER BY a.id DESC LIMIT 1), c.end_date
      ) AS effective_end,
      COALESCE(
        (SELECT TRIM(COALESCE(a.ordinal,'') || ' ' || COALESCE(a.kind,''))
         FROM amendments a WHERE a.contract_id=c.id
         AND NOT (
            UPPER(TRIM(COALESCE(a.ordinal,'')))
                IN ('INICIAL','CONTRATO INICIAL')
            AND UPPER(TRIM(COALESCE(a.kind,'')))
                IN ('CONTRATO','CONTRATO INICIAL')
         )
         ORDER BY a.id DESC LIMIT 1),
        'CONTRATO'
      ) AS effective_instrument
    FROM contracts c {where_clause} ORDER BY c.client
    """
    result = []
    for raw in query(sql):
        item = dict(raw)
        item["registered_current_value"] = item["current_value"]
        item["registered_start_date"] = item["start_date"]
        item["registered_end_date"] = item["end_date"]
        item["current_value"] = item["effective_value"]
        item["original_start_date"] = item["original_start"]
        item["original_end_date"] = item["original_end"]
        item["original_value"] = item["effective_original_value"]
        item["current_start_date"] = item["effective_start"]
        item["current_end_date"] = item["effective_end"]
        item["start_date"] = item["original_start"]
        item["end_date"] = item["effective_end"]
        instrument = (item["effective_instrument"] or "CONTRATO").strip()
        if "INICIAL" in instrument.upper() and "CONTRATO" in instrument.upper():
            instrument = "CONTRATO"
        item["current_instrument"] = instrument.title()
        remaining_days = days_until(item["end_date"])
        if item["archived"]:
            item["lifecycle_status"] = "ARQUIVADO"
        elif remaining_days is not None and remaining_days < 0:
            item["lifecycle_status"] = "AGUARDANDO ADITIVO"
        elif remaining_days is None:
            item["lifecycle_status"] = "PRAZO NÃO INFORMADO"
        else:
            item["lifecycle_status"] = "VIGENTE"
        result.append(item)
    return result


def is_ata(contract):
    return any(
        "ATA" in str(contract.get(field) or "").upper()
        for field in ("category", "procurement_method")
    )


def load_ata_contracts(ata_id):
    rows = query(
        """SELECT ac.*,
        COALESCE(
            (SELECT a.value FROM ata_contract_amendments a
             WHERE a.ata_contract_id=ac.id AND a.value IS NOT NULL AND a.value>0
             ORDER BY a.id DESC LIMIT 1),
            NULLIF(ac.current_value,0), ac.original_value, 0
        ) effective_value,
        COALESCE(
            (SELECT a.start_date FROM ata_contract_amendments a
             WHERE a.ata_contract_id=ac.id AND a.start_date IS NOT NULL AND a.start_date<>''
             ORDER BY a.id DESC LIMIT 1), ac.start_date
        ) effective_start,
        COALESCE(
            (SELECT a.end_date FROM ata_contract_amendments a
             WHERE a.ata_contract_id=ac.id AND a.end_date IS NOT NULL AND a.end_date<>''
             ORDER BY a.id DESC LIMIT 1), ac.end_date
        ) effective_end,
        COALESCE(
            (SELECT TRIM(COALESCE(a.ordinal,'') || ' ' || COALESCE(a.kind,''))
             FROM ata_contract_amendments a WHERE a.ata_contract_id=ac.id
             ORDER BY a.id DESC LIMIT 1), 'CONTRATO DECORRENTE DA ATA'
        ) effective_instrument
        FROM ata_contracts ac WHERE ac.ata_id=? ORDER BY ac.contract_number,ac.id""",
        (ata_id,),
    )
    result = []
    for raw in rows:
        item = dict(raw)
        item["current_value"] = item["effective_value"]
        item["current_start_date"] = item["effective_start"]
        item["current_end_date"] = item["effective_end"]
        item["current_instrument"] = str(item["effective_instrument"] or "").title()
        result.append(item)
    return result


def expand_backlog_with_ata_children(backlog_df, source_contracts, start_year, years=6):
    """Insere, só nesta exportação em Excel, uma linha para cada contrato
    decorrente de cada ATA presente no backlog — o PDF continua mostrando
    apenas a ATA "mãe", sem os decorrentes.

    O Item de cada decorrente usa o item da própria ATA como prefixo (ex.:
    ATA no item 11 → decorrentes 11-1, 11-2, 11-3...) e herda o centro de
    custo da ATA, já que decorrentes não têm centro de custo próprio — é
    o mesmo processo/contrato-mãe. `source_contracts` precisa estar na
    MESMA ordem usada para gerar `backlog_df` (backlog_rows já preserva a
    ordem de entrada), para casar item a item com o contrato de origem."""
    if backlog_df.empty:
        return backlog_df
    year_columns = [str(y) for y in range(start_year, start_year + years)]
    expanded_rows = []
    for source, (_, backlog_row) in zip(source_contracts, backlog_df.iterrows()):
        expanded_rows.append(backlog_row.to_dict())
        if not is_ata(source):
            continue
        children = load_ata_contracts(source["id"])
        for index, child in enumerate(children, start=1):
            child_value = float(child["current_value"] or 0)
            child_start = child.get("start_date")
            child_end = child.get("current_end_date")
            child_row = {
                "Item": f"{backlog_row['Item']}-{index}",
                "Centro de custo": backlog_row["Centro de custo"],
                "Contratante": child.get("client"),
                "Contrato": child.get("contract_number"),
                "Início": child_start,
                "Fim": child_end,
                "Valor atual": child_value,
                "Instrumento vigente": child.get("current_instrument") or "Contrato Decorrente Da Ata",
                "Status": child.get("status"),
                "Modalidade": source.get("category"),
                "Responsável": child.get("responsible_name") or source.get("manager_name"),
            }
            for year in year_columns:
                child_row[year] = annual_allocation(child_start, child_end, child_value, int(year))
            child_row["Remanescente total"] = remaining_value(child_start, child_end, child_value)
            expanded_rows.append(child_row)
    return pd.DataFrame(expanded_rows)


def days_until(value):
    if not value:
        return None
    try:
        return (date.fromisoformat(str(value)[:10]) - today_brt()).days
    except ValueError:
        return None


def human_remaining(value):
    return humanize_remaining(value)


def clean(value):
    if value is None or (not isinstance(value, (list, dict)) and pd.isna(value)):
        return None
    if not isinstance(value, str) and hasattr(value, "isoformat"):
        return value.isoformat()
    return value


def portable_project_path(path_value, fallback=None):
    """Resolve caminhos antigos após a pasta da aplicação ser movida."""
    raw = str(path_value or "").strip()
    if raw:
        direct = Path(raw)
        if direct.exists():
            return direct
        normalized = Path(raw.replace("\\", "/"))
        relative = APP_DIR / normalized
        if relative.exists():
            return relative
        parts = normalized.parts
        for marker in ("uploads", "templates", "assets"):
            if marker in parts:
                candidate = APP_DIR.joinpath(*parts[parts.index(marker):])
                if candidate.exists():
                    return candidate
    if fallback is not None:
        candidate = Path(fallback)
        if candidate.exists():
            return candidate
    return Path(raw) if raw else Path()


def stored_path_value(path):
    path = Path(path)
    try:
        return str(path.relative_to(APP_DIR))
    except ValueError:
        return str(path)


BLOCKED_UPLOAD_EXTENSIONS = {
    ".bat", ".cmd", ".com", ".exe", ".hta", ".html", ".htm", ".jar",
    ".js", ".jse", ".msi", ".ps1", ".scr", ".svg", ".vbe", ".vbs",
}


def validated_upload_data(upload):
    """Bloqueia arquivos executáveis e nomes inseguros antes da persistência."""
    original_name = Path(str(upload.name or "")).name
    suffix = Path(original_name).suffix.casefold()
    if suffix in BLOCKED_UPLOAD_EXTENSIONS:
        st.error(
            f"O tipo de arquivo {suffix or 'sem extensão'} foi bloqueado por segurança. "
            "Converta o conteúdo para PDF, Word, Excel ou imagem antes de anexar."
        )
        st.stop()
    payload = bytes(upload.getbuffer())
    if len(payload) > 200 * 1024 * 1024:
        st.error("O arquivo ultrapassa o limite seguro de 200 MB.")
        st.stop()
    return original_name, payload


def save_sesmt_document(professional_id, contract_id, upload, category, title, exam_id=None, training_id=None):
    folder = UPLOAD_DIR / "sesmt" / str(professional_id)
    folder.mkdir(parents=True, exist_ok=True)
    original_name, payload = validated_upload_data(upload)
    safe_name = f"{uuid.uuid4().hex}_{safe_filename(original_name)}"
    target = folder / safe_name
    target.write_bytes(payload)
    return execute(
        """INSERT INTO documents(contract_id,sesmt_professional_id,sesmt_exam_id,sesmt_training_id,
        category,title,filename,stored_path,uploaded_by)
        VALUES(?,?,?,?,?,?,?,?,?)""",
        (
            contract_id, professional_id, exam_id, training_id,
            category, title or original_name, original_name,
            stored_path_value(target),
            st.session_state.user["id"],
        ),
    )


def sesmt_document_downloads(documents, key_prefix):
    if not documents:
        st.caption("Nenhum documento anexado.")
    for doc in documents:
        stored_name = Path(str(doc["stored_path"]).replace("\\", "/")).name
        path = portable_project_path(
            doc["stored_path"],
            UPLOAD_DIR / "sesmt" / str(doc["sesmt_professional_id"]) / stored_name,
        )
        if path.exists():
            st.download_button(
                f"Baixar · {doc['title']}", data=path.read_bytes(), file_name=doc["filename"],
                key=f"{key_prefix}_{doc['id']}",
            )
    if documents and can_delete():
        with st.container(border=True):
            st.caption("Exclusão de documento anexado")
            options = {doc["title"]: doc["id"] for doc in documents}
            chosen = st.selectbox("Documento", list(options), key=f"{key_prefix}_del_select")
            if st.button("Excluir documento selecionado", key=f"{key_prefix}_del_btn"):
                execute("DELETE FROM documents WHERE id=?", (options[chosen],))
                log_action(
                    st.session_state.user["id"], "EXCLUIR", "documento SESMT",
                    options[chosen], chosen,
                )
                st.success("Documento excluído.")
                rerun()


def save_document(
    contract_id,
    upload,
    category,
    title,
    amendment_id=None,
    union_id=None,
    art_id=None,
    cno_id=None,
    guarantee_id=None,
    guarantee_endorsement_id=None,
    ata_contract_id=None,
    ata_amendment_id=None,
):
    folder = UPLOAD_DIR / str(contract_id)
    folder.mkdir(parents=True, exist_ok=True)
    original_name, payload = validated_upload_data(upload)
    safe_name = f"{uuid.uuid4().hex}_{safe_filename(original_name)}"
    target = folder / safe_name
    target.write_bytes(payload)
    return execute(
        """INSERT INTO documents(contract_id,amendment_id,union_id,art_id,cno_id,
        guarantee_id,guarantee_endorsement_id,ata_contract_id,ata_amendment_id,
        category,title,filename,stored_path,uploaded_by)
        VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
        (
            contract_id, amendment_id, union_id, art_id, cno_id, guarantee_id,
            guarantee_endorsement_id, ata_contract_id, ata_amendment_id, category,
            title or original_name, original_name,
            stored_path_value(target),
            st.session_state.user["id"],
        ),
    )


def document_downloads(documents, key_prefix):
    if not documents:
        st.caption("Nenhum documento anexado.")
    for doc in documents:
        stored_name = Path(str(doc["stored_path"]).replace("\\", "/")).name
        path = portable_project_path(
            doc["stored_path"],
            UPLOAD_DIR / str(doc["contract_id"]) / stored_name,
        )
        if path.exists():
            st.download_button(
                f"Baixar · {doc['title']}", data=path.read_bytes(), file_name=doc["filename"],
                key=f"{key_prefix}_{doc['id']}",
            )
    if documents and can_delete():
        with st.container(border=True):
            st.caption("Exclusão de documento anexado")
            delete_options = {
                f"{doc['title']} · {doc['filename']} · código {doc['id']}": doc["id"]
                for doc in documents
            }
            delete_label = st.selectbox(
                "Documento para excluir",
                delete_options,
                key=f"{key_prefix}_delete_document_select",
            )
            confirm_delete = st.checkbox(
                "Confirmo a exclusão deste documento",
                key=f"{key_prefix}_delete_document_confirm",
            )
            if st.button(
                "Excluir documento",
                disabled=not confirm_delete,
                key=f"{key_prefix}_delete_document_button",
            ):
                document_id = delete_options[delete_label]
                document = next(doc for doc in documents if doc["id"] == document_id)
                stored_name = Path(
                    str(document["stored_path"]).replace("\\", "/")
                ).name
                source = portable_project_path(
                    document["stored_path"],
                    UPLOAD_DIR / str(document["contract_id"]) / stored_name,
                )
                if source.exists() and source.is_file():
                    trash_folder = UPLOAD_DIR.parent / "trash" / "documents"
                    trash_folder.mkdir(parents=True, exist_ok=True)
                    destination = (
                        trash_folder
                        / f"documento_{document_id}_{uuid.uuid4().hex}_{source.name}"
                    )
                    shutil.move(str(source), str(destination))
                execute("DELETE FROM documents WHERE id=?", (document_id,))
                log_action(
                    st.session_state.user["id"],
                    "EXCLUIR",
                    "documento",
                    document_id,
                    document["title"],
                )
                st.success("Documento removido. O arquivo foi enviado à pasta de recuperação.")
                rerun()


DOCUMENT_FIELD_LABELS = {
    "DESTINATARIO": "Destinatário",
    "SETOR": "Setor",
    "ORGAO": "Órgão/contratante",
    "SIGLA": "Sigla do órgão",
    "CONTRATO": "Contrato",
    "PROCESSO": "Processo",
    "ASSUNTO": "Assunto",
    "CENTRO_CUSTO": "Centro de custo",
    "OBJETO": "Objeto",
    "CORPO_TEXTO": "Corpo do documento",
    "ENGENHEIRO": "Preposto/engenheiro indicado",
    "NACIONALIDADE": "Nacionalidade",
    "TITULO": "Título/profissão",
    "CPF": "CPF",
    "CREA": "Registro profissional/CREA",
    "NOME": "Nome do outorgado",
    "PREENCHIMENTO": "Qualificação completa do outorgado",
    "PODERES": "Poderes conferidos",
    "VALIDADE": "Prazo de validade em número",
    "VALIDADE_EXTENSO": "Prazo de validade por extenso",
    "VALIDADE_DMA": "Unidade da validade",
}
LONG_DOCUMENT_FIELDS = {"OBJETO", "CORPO_TEXTO", "PREENCHIMENTO", "PODERES"}
AUTOMATIC_DOCUMENT_FIELDS = {
    "NUMERO_OFICIO", "NUMERO_CARTA", "NUMERO_PROC", "NUMERO_DOCUMENTO",
    "DATA", "DATA_EXTENSO", "RESPONSAVEL", "DADOS", "CARGO",
}


def save_company_template_upload(upload):
    folder = UPLOAD_DIR / "company_templates" / uuid.uuid4().hex
    folder.mkdir(parents=True, exist_ok=True)
    source_name = Path(upload.name).name
    original_path = folder / f"original_{safe_filename(Path(source_name).stem)}{Path(source_name).suffix.lower()}"
    original_path.write_bytes(upload.getbuffer())
    generation_path = folder / f"generation_{safe_filename(Path(source_name).stem)}.docx"
    convert_template_to_docx(original_path, generation_path)
    return original_path, generation_path


def company_document_prefill(field_name, contract, signatory, separate_acronym=True):
    contract = contract or {}
    signatory = signatory or {}
    registration = signatory.get("registration") or ""
    cpf = signatory.get("cpf") or ""
    data = " ".join(filter(None, [registration, f"CPF: {cpf}" if cpf else None]))
    agency_name, agency_acronym = agency_document_fields(contract.get("client") or "")
    values = {
        "DATA": today_brt().strftime("%d/%m/%Y"),
        "DATA_EXTENSO": date_in_words(),
        "CENTRO_CUSTO": contract.get("cost_center") or "",
        "CONTRATO": contract.get("contract_number") or "",
        "ORGAO": agency_name if separate_acronym and agency_acronym else contract.get("client") or "",
        "SIGLA": agency_acronym,
        "PROCESSO": contract.get("process_number") or "",
        "OBJETO": contract.get("object") or "",
        "ENGENHEIRO": contract.get("engineer_name") or "",
        "RESPONSAVEL": signatory.get("name") or "",
        "DADOS": data,
        "CARGO": signatory.get("title") or "",
        "NACIONALIDADE": "brasileiro(a)",
        "TITULO": "Engenheiro(a)",
    }
    return values.get(field_name, "")


def professional_footer():
    st.markdown(
        f"""
        <footer class="app-footer">
            <strong>Sistema de Gestão Contratual ENGEMIL</strong><br>
            Versão {APP_VERSION} {APP_STAGE} · Atualização {APP_RELEASE_DATE}<br>
            Concepção e desenvolvimento por <strong>Rodrigo de Sousa da Silva</strong><br>
            <span class="developer-title">Engenheiro de Software</span> ·
            CREA-DF nº 36849/D-DF · RNP nº 0724248897<br>
            © {today_brt().year} · Aplicação de apoio à gestão, controle e rastreabilidade contratual
        </footer>
        """,
        unsafe_allow_html=True,
    )


def require_login():
    login_logo = LOGO_LIGHT_PATH if st.session_state.ui_theme == "Escuro" else LOGO_DARK_PATH
    if "pending_2fa_user_id" in st.session_state and "user" not in st.session_state:
        user = get_user(st.session_state.pending_2fa_user_id)
        if not user:
            st.session_state.clear()
            rerun()
        if login_logo.exists():
            st.image(str(login_logo), width=260)
        st.title("Verificação em duas etapas")
        st.caption("Informe o código de 6 dígitos exibido no seu aplicativo Authenticator.")
        with st.form("totp_login"):
            token = st.text_input("Código de segurança", max_chars=6)
            if st.form_submit_button("Confirmar", width="stretch"):
                if verify_totp(user["totp_secret"], token):
                    del st.session_state.pending_2fa_user_id
                    start_authenticated_session(user)
                    log_action(user["id"], "LOGIN 2FA", "usuário", user["id"])
                    rerun()
                st.error("Código inválido ou expirado.")
        if st.button("Voltar"):
            _clear_auth_query_param()
            st.session_state.clear()
            rerun()
        professional_footer()
        st.stop()
    if "user" not in st.session_state:
        if login_logo.exists():
            st.image(str(login_logo), width=280)
        st.title("Gestão de Contratos")
        st.caption(
            f"Acesso restrito a usuários autorizados · Versão {APP_VERSION} {APP_STAGE}"
        )
        auth_notice = st.session_state.pop("auth_notice", None)
        if auth_notice:
            st.warning(auth_notice)
        with st.form("login"):
            email = st.text_input("E-mail")
            password = st.text_input("Senha", type="password")
            submitted = st.form_submit_button("Entrar", width="stretch")
        if submitted:
            user = authenticate(email, password)
            if user:
                execute(
                    "UPDATE users SET last_page='Visão geral' WHERE id=?",
                    (user["id"],),
                )
                user = get_user(user["id"])
                if user["require_2fa"] and user["totp_enabled"]:
                    st.session_state.pending_2fa_user_id = user["id"]
                else:
                    start_authenticated_session(user)
                    log_action(user["id"], "LOGIN", "usuário", user["id"])
                rerun()
            st.error("E-mail ou senha inválidos.")
        professional_footer()
        st.stop()


def has_permission(module, action="can_view"):
    current = st.session_state.user
    if current["role"] == "admin":
        return True
    allowed_actions = {"can_view", "can_create", "can_edit", "can_delete"}
    if action not in allowed_actions:
        return False
    rows = query(
        f"SELECT {action} allowed FROM user_permissions WHERE user_id=? AND module=?",
        (current["id"], module),
    )
    if rows:
        return bool(rows[0]["allowed"])
    if action == "can_view":
        return True
    if action == "can_create":
        if module == "sesmt" and current["role"] == "sesmt":
            return True
        return current["role"] in {"operador", "gestor", "engenheiro"}
    if action == "can_edit":
        if module == "sesmt" and current["role"] == "sesmt":
            return True
        return current["role"] in {"gestor", "engenheiro"}
    return False


def can_create():
    return has_permission(
        st.session_state.get("current_module", "contract_detail"),
        "can_create",
    )


def can_edit():
    return has_permission(st.session_state.get("current_module", "contract_detail"), "can_edit")


def can_delete():
    return has_permission(st.session_state.get("current_module", "contract_detail"), "can_delete")


def contract_selector(label="Contrato"):
    rows = query("SELECT id,cost_center,client,contract_number FROM contracts ORDER BY client")
    options = {
        f"{r['cost_center']} · {r['client']} · {r['contract_number'] or 's/n'}": r["id"] for r in rows
    }
    if not options:
        st.info("Importe ou cadastre um contrato primeiro.")
        return None
    selected = st.selectbox(label, options)
    return options[selected]


def open_contract_review(contract_id, issue_labels):
    """Abre a ficha correta a partir do painel de conferência do dashboard."""
    st.session_state["detail_contract_id"] = int(contract_id)
    st.session_state["detail_review_fields"] = list(issue_labels)
    st.session_state["detail_scope"] = "Ativos"
    st.session_state.pop("_detail_target_applied", None)
    st.session_state["navigation_page"] = "Ficha do contrato"


def open_contract_guarantees(contract_id):
    """Abre a ficha indicada pelo painel global de garantias."""
    st.session_state["detail_contract_id"] = int(contract_id)
    st.session_state["detail_review_fields"] = []
    st.session_state["detail_scope"] = "Ativos"
    st.session_state.pop("_detail_target_applied", None)
    st.session_state["navigation_page"] = "Ficha do contrato"


def open_precontract_ficha(contract_id):
    """Abre a ficha de um pré-contrato a partir da página Pré-contratos.

    Usa o escopo "Todos" porque um pré-contrato (formalized=0) não aparece
    no escopo padrão "Ativos" da ficha."""
    st.session_state["detail_contract_id"] = int(contract_id)
    st.session_state["detail_review_fields"] = []
    st.session_state["detail_scope"] = "Todos"
    st.session_state.pop("_detail_target_applied", None)
    st.session_state["navigation_page"] = "Ficha do contrato"


def page_dashboard():
    st.title("Visão Geral")
    st.caption(
        f"Somente contratos vigentes · Atualizado em {fmt_date_long(today_brt())}, "
        f"às {now_brt().strftime('%H:%M')}. Contratos encerrados deixam de compor os indicadores."
    )
    portfolio = pd.DataFrame(load_contracts("WHERE c.archived=0 AND c.formalized=1"))
    if portfolio.empty:
        st.info("Não há contratos ativos na carteira.")
        return
    portfolio["days"] = portfolio["end_date"].apply(days_until)
    contracts = portfolio[portfolio["days"].apply(lambda value: value is not None and value >= 0)].copy()
    if contracts.empty:
        st.info(
            "Nenhum contrato possui vigência válida na data de hoje. Contratos vencidos permanecem "
            "disponíveis na tela Contratos durante o prazo de 30 dias para eventual aditivo."
        )
        return
    contracts["Remanescente"] = contracts.apply(
        lambda r: remaining_value(r["start_date"], r["end_date"], r["current_value"]), axis=1
    )
    expiring = contracts["days"].apply(lambda x: x is not None and 0 <= x <= 90).sum()
    total_value = contracts["current_value"].fillna(0).sum()
    total_remaining = contracts["Remanescente"].sum()
    responsive_cards([
        ("Contratos vigentes", f"{len(contracts):,}".replace(",", "."), "Vigência válida hoje", "blue"),
        ("Valor atual da carteira", brl(total_value), "Últimos instrumentos cadastrados", "green"),
        ("Remanescente estimado", brl(total_remaining), f"Calculado em {fmt_date_long(today_brt())}", "amber"),
        ("Vencimentos em 90 dias", str(int(expiring)), "Contratos próximos do fim", "red" if expiring else "green"),
    ])

    chart_col1, chart_col2 = st.columns(2)
    with chart_col1:
        st.markdown("##### Valor vigente por centro de custo")
        by_cost_center = (
            contracts.groupby("cost_center")["current_value"]
            .sum()
            .reset_index()
            .sort_values("current_value", ascending=False)
            .head(10)
        )
        if not by_cost_center.empty:
            cost_center_chart = (
                alt.Chart(by_cost_center)
                .mark_bar(color=f"#{BURGUNDY_HEX}", cornerRadiusEnd=3)
                .encode(
                    x=alt.X("current_value:Q", title="Valor vigente (R$)", axis=alt.Axis(format="~s")),
                    y=alt.Y("cost_center:N", title=None, sort="-x"),
                    tooltip=[
                        alt.Tooltip("cost_center:N", title="Centro de custo"),
                        alt.Tooltip("current_value:Q", title="Valor vigente", format=",.2f"),
                    ],
                )
                .properties(height=300)
            )
            st.altair_chart(cost_center_chart, width="stretch")
        else:
            st.caption("Sem dados suficientes para este gráfico.")
    with chart_col2:
        st.markdown("##### Valor vencendo por mês (próximos 12 meses)")
        horizon_start = today_brt().replace(day=1)
        month_labels, month_starts = [], []
        cursor_month = horizon_start
        for _ in range(12):
            month_labels.append(f"{cursor_month.month:02d}/{cursor_month.year}")
            month_starts.append(cursor_month)
            cursor_month = date(
                cursor_month.year + (1 if cursor_month.month == 12 else 0),
                1 if cursor_month.month == 12 else cursor_month.month + 1,
                1,
            )
        month_totals = {label: 0.0 for label in month_labels}
        for _, contract_row in contracts.iterrows():
            end = _date_value(contract_row.get("end_date"))
            if not end:
                continue
            label = f"{end.month:02d}/{end.year}"
            if label in month_totals:
                month_totals[label] += float(contract_row.get("current_value") or 0)
        expiring_by_month = pd.DataFrame({
            "Mês": month_labels,
            "Valor vencendo": [month_totals[label] for label in month_labels],
        })
        expiring_chart = (
            alt.Chart(expiring_by_month)
            .mark_bar(color=f"#{BURGUNDY_HEX}", cornerRadiusTopLeft=3, cornerRadiusTopRight=3)
            .encode(
                x=alt.X("Mês:N", title=None, sort=None),
                y=alt.Y("Valor vencendo:Q", title="Valor vencendo (R$)", axis=alt.Axis(format="~s")),
                tooltip=[
                    alt.Tooltip("Mês:N"),
                    alt.Tooltip("Valor vencendo:Q", format=",.2f"),
                ],
            )
            .properties(height=300)
        )
        st.altair_chart(expiring_chart, width="stretch")
    review_rows = []
    for _, contract_row in contracts.iterrows():
        issues = contract_review_issues(contract_row)
        if issues:
            review_rows.append((contract_row, issues))
    if review_rows:
        st.session_state.pop("data_review_success_notice", None)
        st.warning(
            f"{len(review_rows)} cadastro(s) vigente(s) precisam de conferência. "
            "Use o controle abaixo para identificar o contrato, o campo pendente e abrir a ficha."
        )
        show_reviews = st.toggle(
            f"🔎 EXIBIR PENDÊNCIAS E ABRIR FICHAS ({len(review_rows)})",
            key="dashboard_show_contract_reviews",
            help="Ative para visualizar cada pendência e acessar diretamente a ficha do contrato.",
        )
        if show_reviews:
            for contract_row, issues in review_rows:
                issue_html = "".join(
                    f'<div class="data-review-issue"><span class="data-review-dot">!</span>'
                    f'<span><strong>{escape(issue["label"])}</strong>: '
                    f'{escape(issue["reason"])}.<br>{escape(issue["action"])}</span></div>'
                    for issue in issues
                )
                st.markdown(
                    f'<div class="data-review-card">'
                    f'<div class="data-review-title">'
                    f'{escape(str(contract_row.get("client") or "Contratante não informado"))}'
                    f'</div><div class="data-review-meta">'
                    f'Contrato {escape(str(contract_row.get("contract_number") or "s/n"))}'
                    f' · Centro de custo {escape(str(contract_row.get("cost_center") or "não informado"))}'
                    f'</div>{issue_html}</div>',
                    unsafe_allow_html=True,
                )
                issue_labels = [issue["label"] for issue in issues]
                st.button(
                    "Abrir ficha para corrigir",
                    key=f"review_contract_{int(contract_row['id'])}",
                    on_click=open_contract_review,
                    args=(int(contract_row["id"]), issue_labels),
                    type="primary",
                )
        else:
            st.caption(
                "Ative o controle acima para exibir os detalhes da conferência."
            )
    else:
        review_notice = st.session_state.pop("data_review_success_notice", None)
        if review_notice:
            temporary_success(
                "Conferência cadastral concluída: os contratos vigentes possuem responsável "
                "administrativo, prazo final e valor atual informados."
            )
    guarantee_portfolio = []
    for contract_row in contracts.to_dict("records"):
        for guarantee in load_contract_guarantees(
            int(contract_row["id"]), contract_row.get("current_end_date")
        ):
            guarantee["contract_client"] = contract_row.get("client")
            guarantee["contract_number"] = contract_row.get("contract_number")
            guarantee["cost_center"] = contract_row.get("cost_center")
            guarantee_portfolio.append(guarantee)
    if guarantee_portfolio:
        st.subheader("Garantias e seguros da carteira")
        guarantee_expiring = [
            item for item in guarantee_portfolio
            if days_to_expiry(item.get("end_date")) is not None
            and 0 <= days_to_expiry(item.get("end_date")) <= 60
        ]
        guarantee_pending = [
            item for item in guarantee_portfolio
            if item["issues"]
            or item.get("request_status") not in {"ACEITA", "DISPENSADA", "CANCELADA"}
        ]
        responsive_cards([
            ("Registros vigentes", str(len(guarantee_portfolio)), "Garantias e seguros de contratos ativos", "blue"),
            (
                "Documentação recebida",
                str(sum(
                    1 for item in guarantee_portfolio
                    if item.get("request_status") in {"RECEBIDA", "EM ANÁLISE", "ACEITA"}
                )),
                "Registros recebidos, em análise ou aceitos",
                "green",
            ),
            ("Vencimentos em 60 dias", str(len(guarantee_expiring)), "Necessitam análise de renovação/endosso", "red" if guarantee_expiring else "green"),
            ("Pendências de conferência", str(len(guarantee_pending)), "Apólice, vigência, documento ou análise", "amber" if guarantee_pending else "green"),
        ])
        if guarantee_pending:
            with st.expander(
                f"🔎 Exibir garantias e seguros para conferência ({len(guarantee_pending)})"
            ):
                for item in guarantee_pending:
                    reasons = item["issues"] or [
                        f"situação atual: {item.get('request_status') or 'não informada'}"
                    ]
                    st.markdown(
                        f"**{item.get('cost_center') or 'Sem centro de custo'} · "
                        f"{item.get('contract_client') or 'Contratante não informado'}**  \n"
                        f"{item.get('display_type') or 'Garantia'} · "
                        f"{item.get('instrument_reference')} · "
                        f"{'; '.join(reasons)}."
                    )
                    st.button(
                        "Abrir ficha e revisar garantia",
                        key=f"dashboard_guarantee_{item['id']}",
                        on_click=open_contract_guarantees,
                        args=(int(item["contract_id"]),),
                    )
    left, right = st.columns(2)
    summary = (
        contracts.groupby("category", dropna=False)
        .agg(Contratos=("id", "count"), Valor=("current_value", "sum"))
        .reset_index()
        .rename(columns={"category": "Modalidade"})
    )
    with left:
        st.subheader("Valor por modalidade")
        value_bars(list(summary[["Modalidade", "Valor"]].itertuples(index=False, name=None)))
    with right:
        st.subheader("Quantidade por modalidade")
        value_bars(
            list(summary[["Modalidade", "Contratos"]].itertuples(index=False, name=None)),
            formatter=lambda value: f"{int(value)} contrato(s)",
        )
    start_year = today_brt().year
    annual = pd.DataFrame(backlog_rows(contracts.to_dict("records"), start_year, 6))
    year_columns = [str(y) for y in range(start_year, start_year + 6)]
    st.subheader("Remanescente previsto ano a ano")
    value_bars(
        [(column, annual[column].sum()) for column in year_columns],
        variant="annual-bars",
    )
    st.subheader("Top 5 contratos mais vantajosos")
    st.caption(
        "Critério: maior valor remanescente ainda disponível para faturamento, considerando a "
        "vigência e o instrumento atual."
    )
    top_five = contracts.sort_values("Remanescente", ascending=False).head(5)
    ranking_cards(top_five)


def page_contracts():
    st.title("Contratos — Backlog")
    st.caption(
        "Visão consolidada da carteira. Contratos vencidos aguardam até 30 dias por eventual "
        "prorrogação antes do arquivamento automático."
    )
    if AUTO_ARCHIVED_IDS:
        st.info(
            f"{len(AUTO_ARCHIVED_IDS)} contrato(s) foram arquivados automaticamente nesta execução "
            "por permanecerem vencidos por 30 dias sem novo aditivo."
        )
    if can_edit():
        with st.expander("Responsáveis por providências iniciais (TOTVS, garantia e ART)"):
            st.caption(
                "Sempre que um contrato novo é cadastrado (contrato, contrato decorrente "
                "de ATA, ou a própria ATA), ou um aditivo/apostilamento tem seu documento "
                "anexado, o sistema monta um único e-mail listando as providências "
                "pendentes (mencionando o nome de cada responsável na mensagem) para o(s) "
                "e-mail(is) de grupo cadastrados abaixo. Um contrato/contrato decorrente "
                "recém-cadastrado sempre pede a ativação no TOTVS como primeiro item (não "
                "há como checar isso automaticamente, então é pedida de novo em cada "
                "cadastro); garantia e ART entram na lista só quando ainda não há registro "
                "vinculado ao instrumento. Um responsável marcado para \"envio individual\" "
                "também recebe cópia no próprio e-mail — assim como o engenheiro e o "
                "responsável administrativo cadastrados na ficha do contrato, quando "
                "preenchidos."
            )
            task_labels = {"TOTVS": "Ativação no TOTVS", "GARANTIA": "Garantia contratual", "ART": "ART"}
            responsibles = [
                dict(row) for row in query(
                    "SELECT * FROM contract_task_responsibles ORDER BY task_type,active DESC,responsible_name"
                )
            ]
            if responsibles:
                modern_table(pd.DataFrame([{
                    "Providência": task_labels.get(row["task_type"], row["task_type"]),
                    "Responsável": row["responsible_name"],
                    "E-mail": row["responsible_email"],
                    "Envio individual": "SIM" if row["notify_individually"] else "NÃO",
                    "Status": "ATIVO" if row["active"] else "INATIVO",
                } for row in responsibles]))
                remove_options = {
                    f"{task_labels.get(r['task_type'], r['task_type'])} · {r['responsible_name']} · {r['responsible_email']}": r["id"]
                    for r in responsibles
                }
                rc1, rc2, rc3 = st.columns([3, 1, 1])
                remove_label = rc1.selectbox(
                    "Registro para ajustar", remove_options,
                    key="contract_task_responsible_target",
                )
                target_id = remove_options[remove_label]
                target_row = next(r for r in responsibles if r["id"] == target_id)
                with rc2:
                    st.write("")
                    st.write("")
                    if st.button(
                        "Pausar" if target_row["active"] else "Reativar",
                        key="toggle_contract_task_responsible",
                    ):
                        execute(
                            "UPDATE contract_task_responsibles SET active=? WHERE id=?",
                            (0 if target_row["active"] else 1, target_id),
                        )
                        rerun()
                with rc3:
                    st.write("")
                    st.write("")
                    if st.button(
                        "Não enviar individual" if target_row["notify_individually"] else "Enviar individual",
                        key="toggle_contract_task_individual",
                    ):
                        execute(
                            "UPDATE contract_task_responsibles SET notify_individually=? WHERE id=?",
                            (0 if target_row["notify_individually"] else 1, target_id),
                        )
                        rerun()
                if st.button("Remover definitivamente", key="delete_contract_task_responsible"):
                    execute("DELETE FROM contract_task_responsibles WHERE id=?", (target_id,))
                    log_action(user["id"], "REMOVER", "responsável de providência contratual", target_id, remove_label)
                    st.success("Registro removido.")
                    rerun()
            else:
                st.info("Nenhum responsável cadastrado ainda.")
            with st.form("new_contract_task_responsible", clear_on_submit=True):
                new_task_type = st.selectbox("Providência", list(task_labels), format_func=lambda k: task_labels[k])
                new_responsible_name = st.text_input("Nome do responsável")
                new_responsible_email = st.text_input("E-mail do responsável")
                new_notify_individually = st.checkbox(
                    "Também enviar uma cópia individual do e-mail para este responsável",
                    value=False,
                )
                if st.form_submit_button("Adicionar"):
                    normalized_email = new_responsible_email.strip().lower()
                    if not new_responsible_name.strip():
                        st.error("Informe o nome do responsável.")
                    elif not re.fullmatch(r"[^\s@]+@[^\s@]+\.[^\s@]+", normalized_email):
                        st.error("Informe um endereço de e-mail válido.")
                    else:
                        execute(
                            """INSERT INTO contract_task_responsibles(
                            task_type,responsible_name,responsible_email,notify_individually)
                            VALUES(?,?,?,?)""",
                            (
                                new_task_type, new_responsible_name.strip(), normalized_email,
                                1 if new_notify_individually else 0,
                            ),
                        )
                        log_action(
                            user["id"], "CADASTRAR", "responsável de providência contratual",
                            None, f"{new_task_type}: {new_responsible_name.strip()}",
                        )
                        st.success("Responsável cadastrado.")
                        rerun()
            st.divider()
            st.markdown("###### E-mail(is) de grupo para providências iniciais")
            st.caption(
                "É para este(s) e-mail(is) — normalmente uma caixa compartilhada com vários "
                "gestores — que o aviso consolidado de garantia/ART é enviado."
            )
            group_recipients = [
                dict(row) for row in query(
                    "SELECT * FROM contract_task_group_recipients ORDER BY active DESC,email"
                )
            ]
            if group_recipients:
                modern_table(pd.DataFrame([{
                    "E-mail": row["email"],
                    "Status": "ATIVO" if row["active"] else "INATIVO",
                } for row in group_recipients]))
                group_remove_options = {row["email"]: row["id"] for row in group_recipients}
                gc1, gc2 = st.columns([3, 1])
                group_remove_label = gc1.selectbox(
                    "E-mail de grupo para pausar/reativar ou remover", group_remove_options,
                    key="contract_task_group_recipient_target",
                )
                group_target_id = group_remove_options[group_remove_label]
                group_target_row = next(r for r in group_recipients if r["id"] == group_target_id)
                with gc2:
                    st.write("")
                    st.write("")
                    if st.button(
                        "Pausar" if group_target_row["active"] else "Reativar",
                        key="toggle_contract_task_group_recipient",
                    ):
                        execute(
                            "UPDATE contract_task_group_recipients SET active=? WHERE id=?",
                            (0 if group_target_row["active"] else 1, group_target_id),
                        )
                        rerun()
                if st.button(
                    "Remover este e-mail de grupo definitivamente",
                    key="delete_contract_task_group_recipient",
                ):
                    execute(
                        "DELETE FROM contract_task_group_recipients WHERE id=?", (group_target_id,)
                    )
                    log_action(
                        user["id"], "REMOVER", "e-mail de grupo de providências contratuais",
                        group_target_id, group_remove_label,
                    )
                    st.success("E-mail de grupo removido.")
                    rerun()
            else:
                st.info("Nenhum e-mail de grupo cadastrado ainda.")
            with st.form("new_contract_task_group_recipient", clear_on_submit=True):
                new_group_email = st.text_input("Adicionar e-mail de grupo")
                if st.form_submit_button("Adicionar e-mail de grupo"):
                    normalized_group_email = new_group_email.strip().lower()
                    if not re.fullmatch(r"[^\s@]+@[^\s@]+\.[^\s@]+", normalized_group_email):
                        st.error("Informe um endereço de e-mail válido.")
                    else:
                        try:
                            execute(
                                "INSERT INTO contract_task_group_recipients(email) VALUES(?)",
                                (normalized_group_email,),
                            )
                            log_action(
                                user["id"], "CADASTRAR", "e-mail de grupo de providências contratuais",
                                None, normalized_group_email,
                            )
                            st.success("E-mail de grupo cadastrado.")
                            rerun()
                        except Exception:
                            st.error("Este e-mail já está cadastrado.")
    scope = st.radio("Exibir", ["Ativos", "Arquivados", "Todos"], horizontal=True)
    where = {
        "Ativos": "WHERE c.archived=0 AND c.formalized=1",
        "Arquivados": "WHERE c.archived=1", "Todos": "",
    }[scope]
    rows = load_contracts(where)
    search = st.text_input("Pesquisar por órgão, contrato, processo, objeto ou centro de custo")
    if search:
        s = search.casefold()
        rows = [r for r in rows if s in " ".join(str(v or "") for v in r.values()).casefold()]
    if not rows:
        st.info("Nenhum contrato encontrado.")
        return
    start_year = st.number_input("Primeiro ano da projeção", min_value=2020, max_value=2100, value=today_brt().year)
    backlog = pd.DataFrame(backlog_rows(rows, int(start_year), 6))
    backlog.insert(
        backlog.columns.get_loc("Fim") + 1,
        "Prazo restante",
        backlog["Fim"].map(human_remaining),
    )
    currency_columns = ["Valor atual", *[str(y) for y in range(int(start_year), int(start_year) + 6)], "Remanescente total"]
    display = backlog.copy()
    for column in currency_columns:
        display[column] = display[column].map(brl)
    display["Início"] = display["Início"].map(fmt_date_long)
    display["Fim"] = display["Fim"].map(fmt_date_long)
    lifecycle_by_cost = {row["cost_center"]: row["lifecycle_status"] for row in rows}
    display["Situação da vigência"] = display["Centro de custo"].map(lifecycle_by_cost)
    modern_table(display, max_height=560)
    totals = backlog[currency_columns].sum()
    responsive_cards([
        (
            "Total da carteira",
            brl(totals["Valor atual"]),
            f"{len(backlog)} contrato(s) no filtro atual",
            "blue",
        ),
        (
            "Remanescente total",
            brl(totals["Remanescente total"]),
            "Projeção calculada até o fim das vigências",
            "green",
        ),
    ])
    excel_backlog = expand_backlog_with_ata_children(backlog, rows, int(start_year))
    st.download_button(
        "Exportar backlog em Excel",
        data=workbook_bytes({"Contratos": excel_backlog}),
        file_name=f"backlog_contratos_{today_brt().isoformat()}.xlsx",
        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    )
    backlog_pdf_export(backlog, f"contracts_{scope}_{int(start_year)}", contracts=rows)


def _date_value(value):
    if not value:
        return None
    if isinstance(value, date):
        return value
    try:
        return date.fromisoformat(str(value)[:10])
    except ValueError:
        return None


def guarantee_instrument_options(contract_id):
    options = {
        "Contrato inicial": {
            "instrument_scope": "CONTRATO INICIAL",
            "amendment_id": None,
            "ata_contract_id": None,
            "ata_amendment_id": None,
        }
    }
    for row in query(
        "SELECT id,ordinal,kind FROM amendments WHERE contract_id=? ORDER BY id",
        (contract_id,),
    ):
        label = " ".join(filter(None, [str(row["ordinal"] or "").strip(), str(row["kind"] or "").strip()]))
        options[f"Instrumento · {label or 'Sem identificação'}"] = {
            "instrument_scope": "ADITIVO / INSTRUMENTO",
            "amendment_id": row["id"],
            "ata_contract_id": None,
            "ata_amendment_id": None,
        }
    for ata in query(
        "SELECT id,contract_number,client FROM ata_contracts WHERE ata_id=? ORDER BY id",
        (contract_id,),
    ):
        ata_label = " · ".join(filter(None, [ata["contract_number"], ata["client"]]))
        options[f"Contrato da ATA · {ata_label}"] = {
            "instrument_scope": "CONTRATO DECORRENTE DA ATA",
            "amendment_id": None,
            "ata_contract_id": ata["id"],
            "ata_amendment_id": None,
        }
        for amendment in query(
            "SELECT id,ordinal,kind FROM ata_contract_amendments WHERE ata_contract_id=? ORDER BY id",
            (ata["id"],),
        ):
            amendment_label = " ".join(filter(None, [
                str(amendment["ordinal"] or "").strip(),
                str(amendment["kind"] or "").strip(),
            ]))
            options[f"Aditivo da ATA · {ata_label} · {amendment_label}"] = {
                "instrument_scope": "ADITIVO DE CONTRATO DA ATA",
                "amendment_id": None,
                "ata_contract_id": ata["id"],
                "ata_amendment_id": amendment["id"],
            }
    return options


def _selected_guarantee_instrument(options, item):
    for label, reference in options.items():
        if (
            reference["amendment_id"] == item.get("amendment_id")
            and reference["ata_contract_id"] == item.get("ata_contract_id")
            and reference["ata_amendment_id"] == item.get("ata_amendment_id")
            and reference["instrument_scope"] == item.get("instrument_scope")
        ):
            return label
    return next(iter(options))


def load_contract_guarantees(contract_id, contract_end_date=None):
    rows = query(
        """SELECT g.*,a.ordinal amendment_ordinal,a.kind amendment_kind,
        ac.contract_number ata_contract_number,ac.client ata_contract_client,
        aa.ordinal ata_amendment_ordinal,aa.kind ata_amendment_kind,
        (SELECT COUNT(*) FROM documents d WHERE d.guarantee_id=g.id) document_count,
        (SELECT COUNT(*) FROM guarantee_coverages cv WHERE cv.guarantee_id=g.id) coverage_count,
        (SELECT COUNT(*) FROM guarantee_endorsements ge WHERE ge.guarantee_id=g.id) endorsement_count
        FROM contract_guarantees g
        LEFT JOIN amendments a ON a.id=g.amendment_id
        LEFT JOIN ata_contracts ac ON ac.id=g.ata_contract_id
        LEFT JOIN ata_contract_amendments aa ON aa.id=g.ata_amendment_id
        WHERE g.contract_id=? ORDER BY g.end_date,g.id""",
        (contract_id,),
    )
    result = []
    for raw in rows:
        item = dict(raw)
        if item.get("ata_amendment_id"):
            reference = " ".join(filter(None, [
                f"Contrato ATA {item.get('ata_contract_number') or ''}".strip(),
                str(item.get("ata_amendment_ordinal") or "").strip(),
                str(item.get("ata_amendment_kind") or "").strip(),
            ]))
        elif item.get("ata_contract_id"):
            reference = " · ".join(filter(None, [
                f"Contrato ATA {item.get('ata_contract_number') or ''}".strip(),
                item.get("ata_contract_client"),
            ]))
        elif item.get("amendment_id"):
            reference = " ".join(filter(None, [
                str(item.get("amendment_ordinal") or "").strip(),
                str(item.get("amendment_kind") or "").strip(),
            ]))
        else:
            reference = "Contrato inicial"
        item["instrument_reference"] = reference
        item["display_type"] = (
            item.get("custom_type")
            if str(item.get("guarantee_type") or "").upper() == "OUTRO"
            else item.get("guarantee_type")
        )
        item["operational_status"] = operational_status(item)
        item["issues"] = guarantee_issues(item, contract_end_date)
        if (
            str(item.get("request_status") or "").upper()
            in {"RECEBIDA", "EM ANÁLISE", "ACEITA"}
            and not item.get("document_count")
        ):
            item["issues"].append("documento informado como recebido, mas sem arquivo anexado")
        result.append(item)
    return result


def guarantee_form(form_key, instrument_options, values=None, submit_label="Salvar garantia"):
    values = dict(values or {})
    with st.form(form_key):
        first, second, third = st.columns(3)
        type_options = list(GUARANTEE_TYPES)
        current_type = str(values.get("guarantee_type") or "GARANTIA CONTRATUAL")
        guarantee_type = first.selectbox(
            "Tipo de garantia/seguro",
            type_options,
            index=_option_index(type_options, current_type),
        )
        custom_type = second.text_input(
            "Nome quando o tipo for Outro",
            value=str(values.get("custom_type") or ""),
        )
        instrument_label = third.selectbox(
            "Instrumento/contrato relacionado",
            list(instrument_options),
            index=_option_index(
                list(instrument_options),
                _selected_guarantee_instrument(instrument_options, values),
            ),
        )
        first, second = st.columns(2)
        modality_options = list(GUARANTEE_MODALITIES)
        current_modality = str(values.get("modality") or "SEGURO-GARANTIA")
        modality = first.selectbox(
            "Modalidade/documento",
            modality_options,
            index=_option_index(modality_options, current_modality),
        )
        legal_basis = second.text_input(
            "Fundamento/referência da exigência",
            value=str(
                values.get("legal_basis")
                or default_legal_basis(current_type)
            ),
            help="Ex.: cláusula do edital/contrato ou dispositivo da Lei nº 14.133/2021.",
        )
        method_options = ("PERCENTUAL_BASE", "VALOR_INFORMADO")
        current_method = str(
            values.get("calculation_method") or "PERCENTUAL_BASE"
        ).upper()
        if current_method not in method_options:
            current_method = "VALOR_INFORMADO"
        method = st.selectbox(
            "Forma de apuração do valor exigido",
            list(method_options),
            index=_option_index(
                list(method_options), current_method,
            ),
            format_func=lambda option: CALCULATION_LABELS[option],
        )
        c1, c2, c3 = st.columns(3)
        calculation_base = currency_input(
            c1, "Base contratual", values.get("calculation_base", 0), f"{form_key}_base"
        )
        percentage = c2.number_input(
            "Percentual exigido (%)",
            min_value=0.0,
            max_value=100.0,
            value=float(values.get("percentage") or 0),
            step=0.01,
            format="%.4f",
        )
        informed_amount = currency_input(
            c3, "Valor exigido", values.get("required_amount", 0), f"{form_key}_required"
        )
        c1, c2, c3 = st.columns(3)
        provider_name = c1.text_input(
            "Seguradora/banco/emissor", value=str(values.get("provider_name") or "")
        )
        broker_name = c2.text_input(
            "Corretora/intermediário", value=str(values.get("broker_name") or "")
        )
        policy_number = c3.text_input(
            "Número da apólice/garantia", value=str(values.get("policy_number") or "")
        )
        c1, c2, c3 = st.columns(3)
        susep_registration = c1.text_input(
            "Registro SUSEP/controle", value=str(values.get("susep_registration") or "")
        )
        insured_name = c2.text_input(
            "Segurado/beneficiário", value=str(values.get("insured_name") or "")
        )
        co_insured_name = c3.text_input(
            "Cossegurado(s)", value=str(values.get("co_insured_name") or "")
        )
        c1, c2, c3, c4 = st.columns(4)
        issue_date = c1.date_input(
            "Emissão", value=_date_value(values.get("issue_date")), format="DD/MM/YYYY"
        )
        start_date = c2.date_input(
            "Início da vigência", value=_date_value(values.get("start_date")), format="DD/MM/YYYY"
        )
        end_date = c3.date_input(
            "Fim da vigência", value=_date_value(values.get("end_date")), format="DD/MM/YYYY"
        )
        payment_due_date = c4.date_input(
            "Vencimento do prêmio", value=_date_value(values.get("payment_due_date")),
            format="DD/MM/YYYY",
        )
        premium_value = currency_input(
            st, "Prêmio total", values.get("premium_value", 0), f"{form_key}_premium"
        )
        request_status = st.selectbox(
            "Situação da solicitação e análise",
            list(REQUEST_STATUSES),
            index=_option_index(
                list(REQUEST_STATUSES), str(values.get("request_status") or "A SOLICITAR")
            ),
        )
        c1, c2, c3, c4 = st.columns(4)
        request_date = c1.date_input(
            "Solicitada em", value=_date_value(values.get("request_date")), format="DD/MM/YYYY"
        )
        request_due_date = c2.date_input(
            "Prazo para apresentação", value=_date_value(values.get("request_due_date")),
            format="DD/MM/YYYY",
        )
        received_date = c3.date_input(
            "Recebida em", value=_date_value(values.get("received_date")), format="DD/MM/YYYY"
        )
        approval_date = c4.date_input(
            "Aceita/aprovada em", value=_date_value(values.get("approval_date")),
            format="DD/MM/YYYY",
        )
        c1, c2, c3 = st.columns(3)
        responsible_name = c1.text_input(
            "Responsável pelo controle", value=str(values.get("responsible_name") or "")
        )
        responsible_email = c2.text_input(
            "E-mail para alertas", value=str(values.get("responsible_email") or "")
        )
        copy_emails = c3.text_input(
            "Cópias/grupo de e-mails", value=str(values.get("copy_emails") or "")
        )
        notification_enabled = st.checkbox(
            "Enviar alertas automáticos de vigência em 60, 30 e 15 dias",
            value=bool(values.get("notification_enabled", 1)),
        )
        object_description = st.text_area(
            "Objeto/obrigações cobertas", value=str(values.get("object_description") or "")
        )
        notes = st.text_area("Observações", value=str(values.get("notes") or ""))
        submitted = st.form_submit_button(submit_label, type="primary")
    if not submitted:
        return False, None
    try:
        monetary = {
            "calculation_base": parse_brl_input(calculation_base),
            "informed_amount": parse_brl_input(informed_amount),
            "premium_value": parse_brl_input(premium_value),
        }
    except ValueError:
        st.error("Revise os valores monetários e use o padrão brasileiro, por exemplo R$ 47.460,49.")
        return True, None
    required_amount = calculate_required_amount(
        method,
        calculation_base=monetary["calculation_base"],
        percentage=percentage,
        informed_amount=monetary["informed_amount"],
    )
    reference = instrument_options[instrument_label]
    payload = {
        **reference,
        "guarantee_type": guarantee_type,
        "custom_type": custom_type.strip() or None,
        "modality": modality,
        "legal_basis": legal_basis.strip() or default_legal_basis(guarantee_type),
        "calculation_method": method,
        "calculation_base": monetary["calculation_base"],
        "percentage": percentage,
        "estimated_budget": float(values.get("estimated_budget") or 0),
        "proposal_value": float(values.get("proposal_value") or 0),
        "required_amount": required_amount,
        "guaranteed_amount": required_amount,
        "provider_name": provider_name.strip() or None,
        "broker_name": broker_name.strip() or None,
        "policy_number": policy_number.strip() or None,
        "susep_registration": susep_registration.strip() or None,
        "insured_name": insured_name.strip() or None,
        "co_insured_name": co_insured_name.strip() or None,
        "object_description": object_description.strip() or None,
        "issue_date": clean(issue_date),
        "start_date": clean(start_date),
        "end_date": clean(end_date),
        "premium_value": monetary["premium_value"],
        "payment_due_date": clean(payment_due_date),
        "request_status": request_status,
        "request_date": clean(request_date),
        "request_due_date": clean(request_due_date),
        "received_date": clean(received_date),
        "approval_date": clean(approval_date),
        "responsible_name": responsible_name.strip() or None,
        "responsible_email": responsible_email.strip() or None,
        "copy_emails": copy_emails.strip() or None,
        "notification_enabled": int(notification_enabled),
        "notes": notes.strip() or None,
    }
    if guarantee_type == "OUTRO" and not payload["custom_type"]:
        st.error("Informe o nome do seguro ou garantia selecionado como Outro.")
        return True, None
    if start_date and end_date and end_date < start_date:
        st.error("O fim da vigência não pode ser anterior ao início.")
        return True, None
    return True, payload


GUARANTEE_DB_FIELDS = (
    "amendment_id", "ata_contract_id", "ata_amendment_id", "guarantee_type",
    "custom_type", "instrument_scope", "modality", "legal_basis",
    "calculation_method", "calculation_base", "percentage", "estimated_budget",
    "proposal_value", "required_amount", "guaranteed_amount", "provider_name",
    "broker_name", "policy_number", "susep_registration", "insured_name",
    "co_insured_name", "object_description", "issue_date", "start_date", "end_date",
    "premium_value", "payment_due_date", "request_status", "request_date",
    "request_due_date", "received_date", "approval_date", "responsible_name",
    "responsible_email", "copy_emails", "notification_enabled", "notes",
)


def insert_guarantee(contract_id, payload):
    fields = ("contract_id", *GUARANTEE_DB_FIELDS)
    placeholders = ",".join("?" for _ in fields)
    return execute(
        f"INSERT INTO contract_guarantees({','.join(fields)}) VALUES({placeholders})",
        (contract_id, *(payload.get(field) for field in GUARANTEE_DB_FIELDS)),
    )


def update_guarantee(guarantee_id, contract_id, payload):
    assignments = ",".join(f"{field}=?" for field in GUARANTEE_DB_FIELDS)
    execute(
        f"UPDATE contract_guarantees SET {assignments},updated_at=CURRENT_TIMESTAMP "
        "WHERE id=? AND contract_id=?",
        (*(payload.get(field) for field in GUARANTEE_DB_FIELDS), guarantee_id, contract_id),
    )


def load_contract_budget_dates(contract_id):
    return [
        dict(row) for row in query(
            """SELECT * FROM contract_budget_dates
            WHERE contract_id=? ORDER BY reference_date,id""",
            (contract_id,),
        )
    ]


def render_budget_dates_editor(contract_id):
    budget_dates = load_contract_budget_dates(contract_id)
    st.markdown("#### Datas do orçamento")
    st.caption(
        "Registre separadamente o orçamento inicial e eventuais novas referências "
        "orçamentárias dos instrumentos posteriores."
    )
    if budget_dates:
        modern_table(pd.DataFrame([{
            "Código": item["id"],
            "Data do orçamento": fmt_date(item["reference_date"]),
            "Referência": item["description"],
            "Observações": item["notes"],
        } for item in budget_dates]))
    else:
        st.info("Nenhuma data de orçamento cadastrada.")

    if can_create():
        with st.form(f"new_budget_date_{contract_id}", clear_on_submit=True):
            c1, c2 = st.columns(2)
            reference_date = c1.date_input(
                "Data do orçamento *", value=None, format="DD/MM/YYYY"
            )
            description = c2.text_input(
                "Referência",
                placeholder="Ex.: orçamento inicial, 2º termo aditivo ou nova licitação",
            )
            notes = st.text_area("Observações da data-base do orçamento")
            add_budget_date = st.form_submit_button("Adicionar data do orçamento")
        if add_budget_date:
            if not reference_date:
                st.error("Informe a data do orçamento.")
            else:
                budget_date_id = execute(
                    """INSERT INTO contract_budget_dates(
                    contract_id,reference_date,description,notes) VALUES(?,?,?,?)""",
                    (
                        contract_id,
                        reference_date.isoformat(),
                        description.strip() or None,
                        notes.strip() or None,
                    ),
                )
                log_action(
                    st.session_state.user["id"], "CRIAR", "data do orçamento",
                    budget_date_id, fmt_date(reference_date.isoformat()),
                )
                st.success("Data do orçamento adicionada.")
                rerun()

    if budget_dates and can_edit():
        with st.expander("Editar data do orçamento"):
            budget_options = {
                f"{fmt_date(item['reference_date'])} · {item['description'] or 'Sem referência'}": item
                for item in budget_dates
            }
            selected_budget_label = st.selectbox(
                "Registro para editar", list(budget_options),
                key=f"budget_edit_select_{contract_id}",
            )
            selected_budget = budget_options[selected_budget_label]
            with st.form(f"edit_budget_date_{selected_budget['id']}"):
                c1, c2 = st.columns(2)
                edit_reference_date = c1.date_input(
                    "Data do orçamento *",
                    value=_date_value(selected_budget.get("reference_date")),
                    format="DD/MM/YYYY",
                )
                edit_description = c2.text_input(
                    "Referência", selected_budget.get("description") or ""
                )
                edit_notes = st.text_area(
                    "Observações", selected_budget.get("notes") or ""
                )
                save_budget_date = st.form_submit_button("Salvar data do orçamento")
            if save_budget_date:
                if not edit_reference_date:
                    st.error("Informe a data do orçamento.")
                else:
                    execute(
                        """UPDATE contract_budget_dates SET reference_date=?,description=?,
                        notes=?,updated_at=CURRENT_TIMESTAMP WHERE id=? AND contract_id=?""",
                        (
                            edit_reference_date.isoformat(),
                            edit_description.strip() or None,
                            edit_notes.strip() or None,
                            selected_budget["id"], contract_id,
                        ),
                    )
                    log_action(
                        st.session_state.user["id"], "EDITAR", "data do orçamento",
                        selected_budget["id"], fmt_date(edit_reference_date.isoformat()),
                    )
                    st.success("Data do orçamento atualizada.")
                    rerun()

    if budget_dates and can_delete():
        delete_options = {
            f"{fmt_date(item['reference_date'])} · {item['description'] or 'Sem referência'}": item["id"]
            for item in budget_dates
        }
        selected_delete = st.selectbox(
            "Data do orçamento para excluir", list(delete_options),
            key=f"budget_delete_select_{contract_id}",
        )
        confirm_delete = st.checkbox(
            "Confirmo a exclusão desta data do orçamento",
            key=f"budget_delete_confirm_{contract_id}",
        )
        if st.button(
            "Excluir data do orçamento",
            disabled=not confirm_delete,
            key=f"budget_delete_button_{contract_id}",
        ):
            budget_date_id = delete_options[selected_delete]
            execute(
                "DELETE FROM contract_budget_dates WHERE id=? AND contract_id=?",
                (budget_date_id, contract_id),
            )
            log_action(
                st.session_state.user["id"], "EXCLUIR", "data do orçamento",
                budget_date_id, selected_delete,
            )
            st.success("Data do orçamento excluída.")
            rerun()


def render_guarantees_tab(contract_id, contract, effective_end_date):
    instrument_options = guarantee_instrument_options(contract_id)
    guarantees = load_contract_guarantees(contract_id, effective_end_date)
    today = today_brt()
    pending_documents = sum(
        1 for item in guarantees
        if item["request_status"] not in {"DISPENSADA", "CANCELADA", "ACEITA"}
        or not item["document_count"]
    )
    expiring = sum(
        1 for item in guarantees
        if (days_to_expiry(item.get("end_date"), today) is not None)
        and 0 <= days_to_expiry(item.get("end_date"), today) <= 60
    )
    issues = [(item, issue) for item in guarantees for issue in item["issues"]]
    responsive_cards([
        ("Garantias e seguros", str(len(guarantees)), "Registros vinculados ao contrato", "blue"),
        ("Documentos pendentes", str(pending_documents), "Solicitação, recebimento ou aceite", "amber" if pending_documents else "green"),
        ("Vencimentos em 60 dias", str(expiring), "Apólices e garantias próximas do fim", "red" if expiring else "green"),
        ("Pontos para conferência", str(len(issues)), "Apólice, vigência e documentação", "red" if issues else "green"),
    ])
    if issues:
        with st.expander(f"⚠ Exibir pontos para conferência ({len(issues)})", expanded=True):
            for item, issue in issues:
                st.warning(
                    f"{item['display_type'] or 'Garantia'} · {item['instrument_reference']}: {issue}."
                )
    if guarantees:
        table = pd.DataFrame([{
            "Tipo": item["display_type"],
            "Instrumento": item["instrument_reference"],
            "Modalidade": item["modality"],
            "Situação": item["operational_status"],
            "Apólice/garantia": item["policy_number"],
            "Valor exigido": brl(item["required_amount"]),
            "Início": fmt_date(item["start_date"]),
            "Fim": fmt_date(item["end_date"]),
            "Prazo restante": human_remaining(item["end_date"]),
            "Documentos": item["document_count"],
        } for item in guarantees])
        modern_table(table, max_height=440)
    else:
        st.info("Nenhuma garantia ou seguro cadastrado para este contrato.")

    if can_create():
        with st.expander("Cadastrar garantia ou seguro", expanded=not guarantees):
            submitted, payload = guarantee_form(
                f"new_guarantee_{contract_id}",
                instrument_options,
                {
                    "calculation_base": contract.get("current_value") or contract.get("original_value"),
                    "responsible_name": contract.get("engineer_name") or contract.get("manager_name"),
                    "responsible_email": contract.get("engineer_email") or contract.get("manager_email"),
                    "copy_emails": contract.get("manager_email")
                    if contract.get("engineer_email") != contract.get("manager_email") else "",
                },
                "Cadastrar garantia/seguro",
            )
            if submitted and payload:
                guarantee_id = insert_guarantee(contract_id, payload)
                log_action(
                    st.session_state.user["id"], "CRIAR", "garantia/seguro",
                    guarantee_id, payload["guarantee_type"],
                )
                st.success("Garantia/seguro cadastrado. Agora anexe a apólice ou documento recebido.")
                rerun()

    for item in guarantees:
        title = (
            f"{item['display_type'] or 'Garantia'} · {item['instrument_reference']} · "
            f"{item['operational_status']}"
        )
        with st.expander(title):
            details, coverage_tab, endorsement_tab, document_tab = st.tabs(
                ["Dados e edição", "Coberturas e franquias", "Endossos e renovações", "Documentos"]
            )
            with details:
                responsive_cards([
                    ("Valor exigido", brl(item["required_amount"]), CALCULATION_LABELS.get(item["calculation_method"], item["calculation_method"]), "blue"),
                    ("Vigência", f"{fmt_date(item['start_date'])} a {fmt_date(item['end_date'])}", human_remaining(item["end_date"]), "amber"),
                    ("Documento", item["policy_number"] or "Não informado", item["provider_name"] or "Emissor não informado", "blue"),
                    ("Situação", item["operational_status"], item["request_status"] or "Não informada", "green" if item["operational_status"] == "VIGENTE" else "amber"),
                ])
                if can_edit():
                    submitted, payload = guarantee_form(
                        f"edit_guarantee_{item['id']}", instrument_options, item,
                        "Salvar alterações da garantia",
                    )
                    if submitted and payload:
                        update_guarantee(item["id"], contract_id, payload)
                        log_action(
                            st.session_state.user["id"], "EDITAR", "garantia/seguro",
                            item["id"], payload["guarantee_type"],
                        )
                        st.success("Garantia/seguro atualizado.")
                        rerun()
                else:
                    st.write(f"**Fundamento:** {item['legal_basis'] or 'Não informado'}")
                    st.write(f"**Registro SUSEP/controle:** {item['susep_registration'] or 'Não informado'}")
                    st.write(f"**Objeto coberto:** {item['object_description'] or 'Não informado'}")

            with coverage_tab:
                coverages = [dict(row) for row in query(
                    "SELECT * FROM guarantee_coverages WHERE guarantee_id=? ORDER BY id",
                    (item["id"],),
                )]
                modern_table(pd.DataFrame([{
                    "Código": row["id"], "Cobertura": row["coverage_name"],
                    "LMI": brl(row["insured_limit"]), "Início": fmt_date(row["start_date"]),
                    "Fim": fmt_date(row["end_date"]), "Franquia/POS": row["deductible"],
                    "Observações": row["notes"],
                } for row in coverages]))
                if can_create():
                    with st.form(f"new_coverage_{item['id']}", clear_on_submit=True):
                        c1, c2 = st.columns(2)
                        coverage_name = c1.text_input("Cobertura")
                        insured_limit = currency_input(c2, "Limite máximo de indenização (LMI)", 0, f"coverage_limit_{item['id']}")
                        c1, c2 = st.columns(2)
                        coverage_start = c1.date_input("Início", value=None, format="DD/MM/YYYY")
                        coverage_end = c2.date_input("Fim", value=None, format="DD/MM/YYYY")
                        deductible = st.text_input("Franquia ou participação obrigatória (POS)")
                        coverage_notes = st.text_area("Observações da cobertura")
                        add_coverage = st.form_submit_button("Adicionar cobertura")
                    if add_coverage:
                        if not coverage_name.strip():
                            st.error("Informe o nome da cobertura.")
                        elif coverage_start and coverage_end and coverage_end < coverage_start:
                            st.error("O fim da cobertura não pode ser anterior ao início.")
                        else:
                            try:
                                coverage_value = parse_brl_input(insured_limit)
                            except ValueError:
                                st.error("Informe o LMI no padrão brasileiro.")
                            else:
                                coverage_id = execute(
                                    """INSERT INTO guarantee_coverages(
                                    guarantee_id,coverage_name,insured_limit,start_date,end_date,
                                    deductible,notes) VALUES(?,?,?,?,?,?,?)""",
                                    (item["id"], coverage_name.strip(), coverage_value,
                                     clean(coverage_start), clean(coverage_end), deductible, coverage_notes),
                                )
                                log_action(st.session_state.user["id"], "CRIAR", "cobertura de seguro", coverage_id, coverage_name)
                                rerun()
                if coverages and can_delete():
                    delete_options = {f"{row['coverage_name']} · código {row['id']}": row["id"] for row in coverages}
                    selected = st.selectbox("Cobertura para excluir", delete_options, key=f"delete_coverage_select_{item['id']}")
                    confirm = st.checkbox("Confirmo a exclusão da cobertura", key=f"delete_coverage_confirm_{item['id']}")
                    if st.button("Excluir cobertura", disabled=not confirm, key=f"delete_coverage_button_{item['id']}"):
                        coverage_id = delete_options[selected]
                        execute("DELETE FROM guarantee_coverages WHERE id=? AND guarantee_id=?", (coverage_id, item["id"]))
                        log_action(st.session_state.user["id"], "EXCLUIR", "cobertura de seguro", coverage_id)
                        rerun()

            with endorsement_tab:
                endorsements = [dict(row) for row in query(
                    "SELECT * FROM guarantee_endorsements WHERE guarantee_id=? ORDER BY id",
                    (item["id"],),
                )]
                modern_table(pd.DataFrame([{
                    "Código": row["id"], "Movimento": row["movement_type"],
                    "Número": row["endorsement_number"], "Emissão": fmt_date(row["issue_date"]),
                    "Novo fim": fmt_date(row["new_end_date"]),
                    "Situação": row["request_status"], "Descrição": row["description"],
                } for row in endorsements]))
                if can_create():
                    with st.form(f"new_endorsement_{item['id']}", clear_on_submit=True):
                        c1, c2, c3 = st.columns(3)
                        movement_type = c1.selectbox("Tipo de movimento", ["ENDOSSO", "RENOVAÇÃO", "SUBSTITUIÇÃO", "CANCELAMENTO", "OUTRO"])
                        endorsement_number = c2.text_input("Número do endosso/documento")
                        endorsement_status = c3.selectbox("Situação", list(REQUEST_STATUSES))
                        endorsement_description = st.text_area("Descrição/alteração contratual atendida")
                        c1, c2, c3 = st.columns(3)
                        endorsement_issue = c1.date_input("Emissão", value=None, format="DD/MM/YYYY")
                        previous_end = c2.date_input("Fim anterior", value=_date_value(item.get("end_date")), format="DD/MM/YYYY")
                        new_end = c3.date_input("Novo fim", value=None, format="DD/MM/YYYY")
                        premium_adjustment = currency_input(
                            st, "Ajuste de prêmio", 0,
                            f"endorsement_premium_{item['id']}",
                        )
                        request_date = st.date_input("Solicitado em", value=None, format="DD/MM/YYYY")
                        received_date = st.date_input("Recebido em", value=None, format="DD/MM/YYYY")
                        endorsement_notes = st.text_area("Observações do endosso")
                        add_endorsement = st.form_submit_button("Adicionar movimentação/endosso")
                    if add_endorsement:
                        try:
                            premium_value = parse_brl_input(premium_adjustment)
                        except ValueError:
                            st.error("Revise os valores do endosso no padrão brasileiro.")
                        else:
                            endorsement_id = execute(
                                """INSERT INTO guarantee_endorsements(
                                guarantee_id,endorsement_number,movement_type,description,issue_date,
                                previous_end_date,new_end_date,previous_amount,new_amount,premium_adjustment,
                                request_status,request_date,received_date,notes)
                                VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                                (item["id"], endorsement_number, movement_type, endorsement_description,
                                 clean(endorsement_issue), clean(previous_end), clean(new_end), 0,
                                 0, premium_value, endorsement_status, clean(request_date),
                                 clean(received_date), endorsement_notes),
                            )
                            if new_end:
                                execute(
                                    """UPDATE contract_guarantees SET
                                    end_date=COALESCE(?,end_date),
                                    updated_at=CURRENT_TIMESTAMP WHERE id=?""",
                                    (clean(new_end), item["id"]),
                                )
                            log_action(st.session_state.user["id"], "CRIAR", "endosso de garantia", endorsement_id, endorsement_number)
                            rerun()
                if endorsements and can_delete():
                    delete_options = {
                        f"{row['movement_type']} {row['endorsement_number'] or ''} · código {row['id']}": row["id"]
                        for row in endorsements
                    }
                    selected = st.selectbox("Movimentação para excluir", delete_options, key=f"delete_endorsement_select_{item['id']}")
                    confirm = st.checkbox("Confirmo a exclusão da movimentação", key=f"delete_endorsement_confirm_{item['id']}")
                    if st.button("Excluir movimentação", disabled=not confirm, key=f"delete_endorsement_button_{item['id']}"):
                        endorsement_id = delete_options[selected]
                        linked_docs = query("SELECT id FROM documents WHERE guarantee_endorsement_id=?", (endorsement_id,))
                        if linked_docs:
                            st.error("Exclua primeiro os documentos vinculados a esta movimentação.")
                        else:
                            execute("DELETE FROM guarantee_endorsements WHERE id=? AND guarantee_id=?", (endorsement_id, item["id"]))
                            log_action(st.session_state.user["id"], "EXCLUIR", "endosso de garantia", endorsement_id)
                            rerun()

            with document_tab:
                docs = [dict(row) for row in query(
                    "SELECT * FROM documents WHERE guarantee_id=? ORDER BY uploaded_at DESC,id DESC",
                    (item["id"],),
                )]
                document_downloads(docs, f"guarantee_{item['id']}")
                endorsements = [dict(row) for row in query(
                    "SELECT * FROM guarantee_endorsements WHERE guarantee_id=? ORDER BY id",
                    (item["id"],),
                )]
                if can_create():
                    target_options = {"Apólice/garantia principal": None}
                    target_options.update({
                        f"{row['movement_type']} · {row['endorsement_number'] or 'sem número'}": row["id"]
                        for row in endorsements
                    })
                    with st.form(f"upload_guarantee_{item['id']}", clear_on_submit=True):
                        document_target = st.selectbox("Vincular documento a", target_options)
                        document_title = st.text_input("Título do documento")
                        guarantee_upload = st.file_uploader("Apólice, garantia, endosso ou comprovante")
                        upload_submitted = st.form_submit_button("Anexar documento")
                    if upload_submitted and guarantee_upload:
                        document_id = save_document(
                            contract_id, guarantee_upload, "GARANTIA / SEGURO", document_title,
                            guarantee_id=item["id"],
                            guarantee_endorsement_id=target_options[document_target],
                        )
                        log_action(st.session_state.user["id"], "ANEXAR", "documento de garantia", document_id, guarantee_upload.name)
                        st.success("Documento anexado à garantia.")
                        rerun()

            if can_delete():
                st.divider()
                confirm = st.checkbox(
                    "Confirmo a exclusão definitiva deste cadastro de garantia/seguro",
                    key=f"delete_guarantee_confirm_{item['id']}",
                )
                if st.button(
                    "Excluir garantia/seguro",
                    disabled=not confirm,
                    key=f"delete_guarantee_button_{item['id']}",
                ):
                    linked_docs = query("SELECT id FROM documents WHERE guarantee_id=?", (item["id"],))
                    if linked_docs:
                        st.error("Exclua primeiro os documentos vinculados para preservar a rastreabilidade.")
                    else:
                        execute("DELETE FROM contract_guarantees WHERE id=? AND contract_id=?", (item["id"], contract_id))
                        log_action(st.session_state.user["id"], "EXCLUIR", "garantia/seguro", item["id"], item["display_type"])
                        st.success("Cadastro de garantia/seguro excluído.")
                        rerun()


EMPLOYEE_COLUMN_KEYWORDS = {
    "full_name": ["nome", "funcionário", "funcionario", "colaborador", "empregado"],
    "role_title": ["cargo", "função", "funcao", "ocupação", "ocupacao"],
    "cost_center": ["centro de custo", "centro custo", "cc", "cost center"],
    "cpf": ["cpf"],
    "admission_date": ["admissão", "admissao", "data de admissão", "data admissao"],
    "base_salary": ["salário", "salario", "salário-base", "salario base", "remuneração", "remuneracao"],
}


def suggest_employee_column_mapping(columns):
    """Tenta reconhecer, pelo nome do cabeçalho da planilha, qual coluna
    corresponde a cada campo — só uma sugestão inicial, o usuário sempre
    confirma antes de importar."""
    guess = {}
    for field, keywords in EMPLOYEE_COLUMN_KEYWORDS.items():
        match = next(
            (col for col in columns if any(kw in str(col).strip().casefold() for kw in keywords)),
            "(não usar)",
        )
        guess[field] = match
    return guess


def build_employee_import_preview(
    sheet_df, contract_cost_center, col_name, col_role, col_cost_center, col_cpf, col_admission, col_salary,
):
    """Monta as linhas prontas para importação a partir da planilha colada,
    filtrando pelo centro de custo do contrato atual quando a planilha tiver
    essa coluna. Datas e valores em formatos variados (texto, número, data
    do Excel) são tratados com tolerância, já que a origem é uma planilha
    de outro sistema, não controlada por nós."""
    rows = []
    skipped_other_cc = 0
    target_cc = str(contract_cost_center or "").strip().casefold()
    for _, source_row in sheet_df.iterrows():
        name_value = source_row.get(col_name)
        if pd.isna(name_value) or not str(name_value).strip():
            continue
        if col_cost_center != "(não usar)":
            row_cc = str(source_row.get(col_cost_center) or "").strip().casefold()
            if row_cc and target_cc and row_cc != target_cc:
                skipped_other_cc += 1
                continue
        admission_value = None
        if col_admission != "(não usar)":
            raw_admission = source_row.get(col_admission)
            if pd.notna(raw_admission):
                try:
                    admission_value = pd.to_datetime(raw_admission).date().isoformat()
                except (ValueError, TypeError):
                    admission_value = None
        salary_value = None
        if col_salary != "(não usar)":
            raw_salary = source_row.get(col_salary)
            if pd.notna(raw_salary):
                try:
                    salary_value = float(
                        str(raw_salary).replace("R$", "").replace(".", "").replace(",", ".").strip()
                    ) if isinstance(raw_salary, str) else float(raw_salary)
                except ValueError:
                    salary_value = None
        rows.append({
            "Nome": str(name_value).strip(),
            "Cargo": str(source_row.get(col_role) or "").strip() if col_role != "(não usar)" else "",
            "CPF": str(source_row.get(col_cpf) or "").strip() if col_cpf != "(não usar)" else "",
            "Admissão": admission_value,
            "Salário-base": salary_value,
        })
    return rows, skipped_other_cc


def page_contract_detail():
    st.title("Ficha do Contrato")
    scope = st.radio("Carteira", ["Ativos", "Arquivados", "Todos"], horizontal=True, key="detail_scope")
    where = {
        "Ativos": "WHERE c.archived=0 AND c.formalized=1",
        "Arquivados": "WHERE c.archived=1", "Todos": "",
    }[scope]
    rows = load_contracts(where)
    if not rows:
        st.info("Nenhum contrato disponível.")
        return
    if not rows:
        return
    options = {
        f"{r['cost_center']} · {r['client']} · {r['contract_number'] or 's/n'}": r["id"] for r in rows
    }
    labels = list(options)
    target_id = st.session_state.get("detail_contract_id")
    target_label = next(
        (label for label, contract_id in options.items() if contract_id == target_id),
        None,
    )
    if target_label and st.session_state.get("_detail_target_applied") != target_id:
        st.session_state["contract_detail_selector"] = target_label
        st.session_state["_detail_target_applied"] = target_id
    if st.session_state.get("contract_detail_selector") not in options:
        st.session_state["contract_detail_selector"] = labels[0]
    selected_label = st.selectbox(
        "Abrir ficha do contrato",
        labels,
        key="contract_detail_selector",
    )
    cid = options[selected_label]
    if cid == target_id and st.session_state.get("detail_review_fields"):
        pending_text = ", ".join(st.session_state["detail_review_fields"])
        st.info(
            f"Ficha aberta pelo painel de conferência. Revise na aba Editar: {pending_text}."
        )
    display_contract = next(r for r in rows if r["id"] == cid)
    contract = dict(query("SELECT * FROM contracts WHERE id=?", (cid,))[0])
    st.divider()
    st.header(f"{contract['cost_center']} — {contract['client']}")
    if contract["archived"]:
        st.markdown(
            '<div class="archive-banner"><strong>Contrato arquivado.</strong> A ficha continua '
            "editável. Ao cadastrar um aditivo com nova vigência válida, o contrato será reativado "
            "automaticamente.</div>",
            unsafe_allow_html=True,
        )
    elif display_contract["lifecycle_status"] == "AGUARDANDO ADITIVO":
        st.markdown(
            '<div class="archive-banner"><strong>Vigência encerrada, aguardando possível aditivo.</strong> '
            "O registro será arquivado automaticamente após 30 dias sem prorrogação.</div>",
            unsafe_allow_html=True,
        )
    cdays = days_until(display_contract["end_date"])
    responsive_cards([
        ("Contrato", contract["contract_number"] or "Não informado", contract["cost_center"], "blue"),
        ("Processo", contract.get("process_number") or "Não informado", contract["cost_center"], "blue"),
        ("Valor original", brl(display_contract["original_value"]), "Contrato inicial", "blue"),
        ("Início original", fmt_date_long(display_contract["original_start_date"]), "Contrato inicial", "blue"),
        ("Fim original", fmt_date_long(display_contract["original_end_date"]), "Contrato inicial", "blue"),
        ("Instrumento vigente", display_contract["current_instrument"], "Último registro contratual", "blue"),
        ("Valor vigente", brl(display_contract["current_value"]), display_contract["current_instrument"], "green"),
        ("Início da vigência atual", fmt_date_long(display_contract["current_start_date"]), display_contract["current_instrument"], "amber"),
        ("Fim da vigência atual", fmt_date_long(display_contract["current_end_date"]), display_contract["current_instrument"], "amber"),
        ("Prazo restante", human_remaining(display_contract["current_end_date"]), "Atualização diária", "red" if cdays is not None and cdays < 90 else "green"),
        (
            "Regime de faturamento",
            BDI_REGIME_LABELS.get(
                contract.get("tax_regime") or "NÃO DEFINIDO",
                contract.get("tax_regime") or "Não definido",
            ),
            "Oneração/desoneração para conferência financeira",
            "green" if contract.get("tax_regime") in {"ONERADO", "DESONERADO"} else "red",
        ),
    ])
    tab_names = ["Resumo", "Aditivos", "Garantias e seguros", "BDI"]
    if is_ata(contract):
        tab_names.append("Contratos decorrentes da ATA")
    tab_names.extend([
        "Sindicatos e datas-base", "Equipe e cargos", "Prazos e obrigações",
        "ARTs", "CNO", "Editar",
    ])
    tabs = dict(zip(tab_names, st.tabs(tab_names)))
    with tabs["Resumo"]:
        st.markdown(
            f'<div class="contract-object"><strong>Objeto:</strong> '
            f'{escape(contract["object"] or "Não informado")}</div>',
            unsafe_allow_html=True,
        )
        x, y = st.columns(2)
        x.write(f"**Engenheiro responsável:** {contract['engineer_name'] or 'Não definido'}")
        x.write(f"**Responsável administrativo:** {contract['manager_name'] or 'Não definido'}")
        team_total = query(
            "SELECT COALESCE(SUM(quantity),0) total FROM contract_positions WHERE contract_id=?", (cid,)
        )[0]["total"]
        union_total = query("SELECT COUNT(*) total FROM contract_unions WHERE contract_id=?", (cid,))[0]["total"]
        budget_dates = load_contract_budget_dates(cid)
        x.write(f"**Equipe cadastrada:** {team_total or contract['employee_count'] or 0} empregados")
        y.write(f"**Sindicatos/CCT cadastrados:** {union_total}")
        y.write(f"**Próxima repactuação geral:** {fmt_date(contract['repactuation_date'])}")
        y.write(
            "**Data(s) do orçamento:** "
            + (
                "; ".join(
                    f"{fmt_date(item['reference_date'])}"
                    + (f" — {item['description']}" if item.get("description") else "")
                    for item in budget_dates
                )
                if budget_dates else "Não informada"
            )
        )
        st.info(contract["observations"] or "Sem observações registradas.")
        st.markdown("#### Exportar ficha contratual")
        contract_document_exports(cid, "detail")
        st.markdown("#### Documentos gerais do contrato")
        general_docs = [dict(r) for r in query(
            """SELECT * FROM documents WHERE contract_id=? AND amendment_id IS NULL
            AND union_id IS NULL AND art_id IS NULL AND cno_id IS NULL
            AND guarantee_id IS NULL AND guarantee_endorsement_id IS NULL
            AND ata_contract_id IS NULL
            AND ata_amendment_id IS NULL ORDER BY uploaded_at DESC""", (cid,)
        )]
        document_downloads(general_docs, f"general_{cid}")
        if can_create():
            with st.form("upload_general_document", clear_on_submit=True):
                general_category = st.selectbox(
                    "Categoria", ["CONTRATO", "SEGURO", "ATESTADO", "PLANILHA", "OFÍCIO", "OUTRO"]
                )
                general_title = st.text_input("Título do documento")
                general_upload = st.file_uploader("Arquivo geral")
                if st.form_submit_button("Anexar documento geral") and general_upload:
                    did = save_document(cid, general_upload, general_category, general_title)
                    log_action(user["id"], "ANEXAR", "documento", did, general_upload.name)
                    st.success("Documento anexado ao resumo.")
                    rerun()
    with tabs["Aditivos"]:
        amendments = contract_amendments_with_arts(cid)
        amendment_columns = [
            "id", "ordinal", "kind", "description", "value", "start_date", "end_date",
            "duration_months", "guarantee_status", "art_status", "notes",
        ]
        amendment_df = pd.DataFrame(amendments)
        if amendments and can_edit():
            amendment_edit_df = amendment_df[amendment_columns].copy()
            amendment_edit_df["value"] = amendment_edit_df["value"].map(brl)
            for column in ("start_date", "end_date"):
                amendment_edit_df[column] = pd.to_datetime(
                    amendment_edit_df[column], errors="coerce"
                ).dt.date
            amendment_edit_df["duration_months"] = amendment_edit_df.apply(
                lambda row: contract_duration_months(row["start_date"], row["end_date"]),
                axis=1,
            )
            edited_amendments = st.data_editor(
                amendment_edit_df, width="stretch", hide_index=True,
                disabled=["id", "duration_months", "guarantee_status", "art_status"], key="edit_amendments",
                column_config={
                    "id": st.column_config.NumberColumn("Código"),
                    "ordinal": st.column_config.TextColumn("Ordem"),
                    "kind": st.column_config.TextColumn("Instrumento"),
                    "description": st.column_config.TextColumn("Descrição", width="large"),
                    "value": st.column_config.TextColumn(
                        "Valor vigente",
                        help="Informe no padrão brasileiro, por exemplo: R$ 22.763.546,65.",
                    ),
                    "start_date": st.column_config.DateColumn("Início", format="DD/MM/YYYY"),
                    "end_date": st.column_config.DateColumn("Fim", format="DD/MM/YYYY"),
                    "duration_months": st.column_config.NumberColumn("Meses"),
                    "guarantee_status": st.column_config.TextColumn(
                        "Garantias vinculadas",
                        help="Campo automático, alimentado pela aba Garantias e seguros.",
                    ),
                    "art_status": st.column_config.TextColumn(
                        "ARTs vinculadas",
                        help="Campo automático, alimentado pelos vínculos cadastrados na aba ARTs.",
                    ),
                    "notes": st.column_config.TextColumn("Observações", width="large"),
                },
            )
            st.caption(
                "Os valores podem ser digitados com ou sem “R$” e são exibidos no padrão "
                "brasileiro. As colunas Garantias e ARTs vinculadas são atualizadas "
                "automaticamente pelas respectivas abas."
            )
            if st.button("Salvar alterações dos aditivos"):
                invalid_periods = [
                    int(row["id"]) for _, row in edited_amendments.iterrows()
                    if clean(row["start_date"]) and clean(row["end_date"])
                    and contract_duration_months(
                        clean(row["start_date"]), clean(row["end_date"])
                    ) is None
                ]
                invalid_values = []
                for _, row in edited_amendments.iterrows():
                    try:
                        parse_brazilian_number(row["value"], 0)
                    except ValueError:
                        invalid_values.append(int(row["id"]))
                if invalid_periods:
                    st.error(
                        "A data final não pode ser anterior à data inicial. "
                        f"Revise o(s) registro(s): {invalid_periods}."
                    )
                elif invalid_values:
                    st.error(
                        "Informe os valores no padrão brasileiro. "
                        f"Revise o(s) registro(s): {invalid_values}."
                    )
                else:
                    for _, row in edited_amendments.iterrows():
                        duration_months = contract_duration_months(
                            clean(row["start_date"]), clean(row["end_date"])
                        )
                        execute(
                            """UPDATE amendments SET ordinal=?,kind=?,description=?,value=?,
                            start_date=?,end_date=?,duration_months=?,
                            notes=? WHERE id=? AND contract_id=?""",
                            (
                                clean(row["ordinal"]), clean(row["kind"]),
                                clean(row["description"]),
                                parse_brazilian_number(row["value"], 0),
                                clean(row["start_date"]), clean(row["end_date"]),
                                duration_months, clean(row["notes"]),
                                int(row["id"]), cid,
                            ),
                        )
                    refresh_contract_lifecycle(cid)
                    log_action(user["id"], "EDITAR", "aditivos", cid)
                    st.success("Aditivos atualizados.")
                    rerun()
        else:
            amendment_display = pd.DataFrame([{
                "Ordem": a["ordinal"], "Instrumento": str(a["kind"] or "").title(),
                "Descrição": a["description"], "Valor vigente": brl(a["value"]),
                "Início": fmt_date(a["start_date"]), "Fim": fmt_date(a["end_date"]),
                "Meses": a["duration_months"], "Garantia": a["guarantee_status"],
                "ART": a["art_status"], "Observações": a["notes"],
            } for a in amendments])
            modern_table(amendment_display)
        if can_create():
            with st.form("new_amendment", clear_on_submit=True):
                col1, col2, col3 = st.columns(3)
                ordinal = col1.text_input("Número/ordem", placeholder="3º")
                kind_option = col2.selectbox(
                    "Tipo",
                    [
                        "TERMO ADITIVO",
                        "TERMO DE APOSTILAMENTO",
                        "CONTRATO",
                        "OUTRO (INFORMAR ABAIXO)",
                    ],
                )
                value = col3.number_input("Valor atualizado", min_value=0.0, format="%.2f")
                custom_kind = st.text_input(
                    "Nome do instrumento quando o tipo for “Outro”",
                    placeholder="Ex.: Termo de Rerratificação, Ordem de Serviço ou Distrato",
                )
                start, end = st.columns(2)
                start_date = start.date_input("Início", value=None, format="DD/MM/YYYY")
                end_date = end.date_input("Fim", value=None, format="DD/MM/YYYY")
                calculated_duration = contract_duration_months(start_date, end_date)
                if calculated_duration is not None:
                    st.caption(
                        f"Vigência calculada automaticamente: {calculated_duration} "
                        f"mês{'es' if calculated_duration != 1 else ''} completo(s)."
                    )
                description = st.text_area("Objeto e alterações relevantes")
                notes = st.text_area("Observações")
                if st.form_submit_button("Adicionar aditivo"):
                    kind = (
                        custom_kind.strip()
                        if kind_option == "OUTRO (INFORMAR ABAIXO)"
                        else kind_option
                    )
                    if not kind:
                        st.error("Informe o nome do instrumento selecionado como “Outro”.")
                    elif start_date and end_date and end_date < start_date:
                        st.error("A data final não pode ser anterior à data inicial.")
                    else:
                        aid = execute(
                            """INSERT INTO amendments(
                            contract_id,ordinal,kind,description,value,start_date,end_date,
                            duration_months,notes)
                            VALUES(?,?,?,?,?,?,?,?,?)""",
                            (
                                cid, ordinal, kind, description, value,
                                start_date.isoformat() if start_date else None,
                                end_date.isoformat() if end_date else None,
                                calculated_duration, notes,
                            ),
                        )
                        lifecycle = refresh_contract_lifecycle(cid)
                        log_action(st.session_state.user["id"], "CRIAR", "aditivo", aid, ordinal)
                        st.success(
                            "Instrumento registrado."
                            + (
                                " O contrato foi reativado pela nova vigência."
                                if lifecycle == "ATIVO" else ""
                            )
                        )
                        rerun()
        st.markdown("#### Documentos dos instrumentos")
        for amendment in amendments:
            label = f"{amendment['ordinal'] or ''} {amendment['kind'] or 'Instrumento'}".strip().title()
            with st.expander(
                f"{label} · {brl(amendment['value'])} · "
                f"{fmt_date(amendment['start_date'])} a {fmt_date(amendment['end_date'])}"
            ):
                st.write(amendment["description"] or "Sem descrição.")
                docs = [dict(r) for r in query(
                    "SELECT * FROM documents WHERE amendment_id=? ORDER BY uploaded_at DESC",
                    (amendment["id"],),
                )]
                document_downloads(docs, f"amendment_{amendment['id']}")
        if can_create() and amendments:
            amendment_options = {
                f"{a['ordinal'] or ''} {a['kind'] or 'Instrumento'}".strip().title(): a["id"]
                for a in amendments
            }
            with st.form("upload_amendment_document", clear_on_submit=True):
                amendment_label = st.selectbox("Instrumento relacionado", amendment_options)
                document_title = st.text_input("Título do documento")
                amendment_upload = st.file_uploader("Documento do contrato/aditivo/apostilamento")
                if st.form_submit_button("Anexar ao instrumento") and amendment_upload:
                    selected_amendment_id = amendment_options[amendment_label]
                    did = save_document(
                        cid, amendment_upload, "INSTRUMENTO CONTRATUAL", document_title,
                        amendment_id=selected_amendment_id,
                    )
                    log_action(user["id"], "ANEXAR", "documento", did, amendment_upload.name)
                    selected_amendment = next(
                        a for a in amendments if a["id"] == selected_amendment_id
                    )
                    notified = notify_contract_task_needs(
                        contract_id=cid, amendment_id=selected_amendment_id,
                        kind_label=selected_amendment.get("kind"),
                        ordinal=selected_amendment.get("ordinal"),
                        cost_center=contract["cost_center"], client=contract["client"],
                        contract_number=contract["contract_number"],
                        document_bytes=amendment_upload.getvalue(),
                        document_filename=amendment_upload.name,
                        extra_recipients=[contract.get("engineer_email"), contract.get("manager_email")],
                    )
                    success_message = "Documento vinculado ao instrumento."
                    if notified:
                        success_message += (
                            f" Aviso de providências enviado para {len(notified)} responsável(is)."
                        )
                    st.success(success_message)
                    rerun()
        if can_delete() and amendments:
            with st.expander("Excluir instrumento contratual"):
                amendment_delete_options = {
                    (
                        f"{a['ordinal'] or ''} {a['kind'] or 'Instrumento'}".strip().title()
                        + (
                            f" · {a.get('linked_art_count', 0)} ART(s) vinculada(s)"
                            if a.get("linked_art_count") else ""
                        )
                        + (
                            f" · {a.get('linked_guarantee_count', 0)} garantia(s) vinculada(s)"
                            if a.get("linked_guarantee_count") else ""
                        )
                    ): a["id"]
                    for a in amendments
                }
                amendment_to_delete = st.selectbox(
                    "Instrumento para excluir", amendment_delete_options
                )
                confirm_amendment_delete = st.checkbox(
                    "Confirmo a exclusão do instrumento selecionado",
                    key=f"confirm_amendment_delete_{cid}",
                )
                if st.button(
                    "Excluir instrumento",
                    disabled=not confirm_amendment_delete,
                    key=f"delete_amendment_{cid}",
                ):
                    amendment_id = amendment_delete_options[amendment_to_delete]
                    linked_guarantees = query(
                        "SELECT id FROM contract_guarantees WHERE amendment_id=?",
                        (amendment_id,),
                    )
                    if linked_guarantees:
                        st.error(
                            "Este instrumento possui garantia/seguro vinculado. "
                            "Reassocie ou exclua a garantia antes de excluir o instrumento."
                        )
                    else:
                        execute(
                            """UPDATE arts SET amendment_id=NULL,
                            instrument_scope='NÃO DEFINIDO' WHERE amendment_id=?""",
                            (amendment_id,),
                        )
                        execute("DELETE FROM amendments WHERE id=? AND contract_id=?", (amendment_id, cid))
                        refresh_contract_lifecycle(cid)
                        log_action(
                            user["id"], "EXCLUIR", "aditivo", amendment_id, amendment_to_delete
                        )
                        st.success("Instrumento excluído.")
                        rerun()
    with tabs["Garantias e seguros"]:
        render_guarantees_tab(cid, contract, display_contract["current_end_date"])
    with tabs["BDI"]:
        st.markdown("#### Custos Indiretos, Tributos e Lucro — BDI")
        st.caption(
            "Cadastre um ou vários BDIs e identifique a aplicação de cada composição, "
            "como mão de obra, materiais ou serviços. Os percentuais são recalculados "
            "automaticamente a partir das parcelas informadas."
        )
        contract_regime_options = ["NÃO DEFINIDO", "ONERADO", "DESONERADO"]
        contract_regime = str(contract.get("tax_regime") or "NÃO DEFINIDO")
        if can_edit():
            regime_column, action_column = st.columns([3, 1])
            selected_contract_regime = regime_column.selectbox(
                "Regime de faturamento do contrato",
                contract_regime_options,
                index=_option_index(contract_regime_options, contract_regime),
                format_func=lambda option: BDI_REGIME_LABELS[option],
                key=f"contract_tax_regime_{cid}",
                help=(
                    "Indicação operacional para conferência do faturamento. "
                    "As alíquotas continuam sendo definidas em cada BDI."
                ),
            )
            if action_column.button(
                "Salvar regime",
                key=f"save_contract_tax_regime_{cid}",
                width="stretch",
            ):
                execute(
                    """UPDATE contracts SET tax_regime=?,updated_at=CURRENT_TIMESTAMP
                    WHERE id=?""",
                    (selected_contract_regime, cid),
                )
                log_action(
                    user["id"], "EDITAR", "regime de faturamento", cid,
                    selected_contract_regime,
                )
                st.success("Regime de faturamento atualizado.")
                rerun()
            effective_contract_regime = selected_contract_regime
        else:
            effective_contract_regime = contract_regime

        if effective_contract_regime == "NÃO DEFINIDO":
            st.warning(
                "O regime de faturamento ainda não foi definido. Informe se o contrato "
                "é onerado ou desonerado antes de encaminhar a composição ao financeiro."
            )
        else:
            st.info(
                f"Regime indicado para o faturamento: "
                f"**{BDI_REGIME_LABELS[effective_contract_regime]}**. "
                "Confira as alíquotas aplicáveis em cada composição."
            )

        bdis = load_contract_bdis(cid, effective_contract_regime)
        if not bdis:
            st.info("Nenhuma composição de BDI foi cadastrada para este contrato.")
        for bdi in bdis:
            title = (
                f"{bdi['name']} — {bdi['reference_name']} · "
                f"{fmt_percent(bdi['calculated_percentage'])}"
            )
            with st.expander(title):
                responsive_cards([
                    (
                        "BDI calculado",
                        fmt_percent(bdi["calculated_percentage"]),
                        BDI_METHOD_LABELS.get(
                            bdi["calculation_method"], bdi["calculation_method"]
                        ),
                        "green",
                    ),
                    (
                        "Tributos",
                        fmt_percent(bdi["tax_total"]),
                        "PIS + COFINS + ISS + CPRB + outros",
                        "amber",
                    ),
                    (
                        "Regime",
                        BDI_REGIME_LABELS.get(
                            bdi["effective_tax_regime"], bdi["effective_tax_regime"]
                        ),
                        "Regime aplicado a esta composição",
                        "blue",
                    ),
                ])
                if bdi["calculation_error"]:
                    st.error(bdi["calculation_error"])
                if bdi["calculation_method"] == "SOMA_DIRETA":
                    component_rows = [
                        {"Parcela": "Custos indiretos", "Percentual": fmt_percent(bdi["indirect_costs"], 4)},
                        {"Parcela": "Lucro", "Percentual": fmt_percent(bdi["profit"], 4)},
                    ]
                else:
                    component_rows = [
                        {"Parcela": "Administração central — AC", "Percentual": fmt_percent(bdi["central_administration"], 4)},
                        {"Parcela": "Seguros — S", "Percentual": fmt_percent(bdi["insurance"], 4)},
                        {"Parcela": "Riscos — R", "Percentual": fmt_percent(bdi["risks"], 4)},
                        {"Parcela": "Garantias — G", "Percentual": fmt_percent(bdi["guarantees"], 4)},
                        {"Parcela": "Outros custos indiretos", "Percentual": fmt_percent(bdi["other_indirect_costs"], 4)},
                        {"Parcela": "Subtotal AC + S + R + G + outros", "Percentual": fmt_percent(bdi["composed_indirect_total"], 4)},
                        {"Parcela": "Despesas financeiras — DF", "Percentual": fmt_percent(bdi["financial_expenses"], 4)},
                        {"Parcela": "Lucro — L", "Percentual": fmt_percent(bdi["profit"], 4)},
                    ]
                component_rows.extend([
                    {"Parcela": "PIS", "Percentual": fmt_percent(bdi["pis"], 4)},
                    {"Parcela": "COFINS", "Percentual": fmt_percent(bdi["cofins"], 4)},
                    {"Parcela": "ISS", "Percentual": fmt_percent(bdi["iss"], 4)},
                    {"Parcela": "CPRB", "Percentual": fmt_percent(bdi["cprb"], 4)},
                    {"Parcela": "Outros tributos", "Percentual": fmt_percent(bdi["other_taxes"], 4)},
                    {"Parcela": "Total dos tributos — T", "Percentual": fmt_percent(bdi["tax_total"], 4)},
                ])
                modern_table(pd.DataFrame(component_rows), max_height=520)
                if bdi["notes"]:
                    st.write(f"**Observações:** {bdi['notes']}")
                if (
                    bdi["effective_tax_regime"] == "ONERADO"
                    and float(bdi["cprb"] or 0) > 0
                ):
                    st.warning(
                        "Esta composição está indicada como onerada e possui CPRB. "
                        "Confirme a parametrização antes do faturamento."
                    )
                if (
                    bdi["effective_tax_regime"] == "DESONERADO"
                    and float(bdi["cprb"] or 0) == 0
                ):
                    st.warning(
                        "Esta composição está indicada como desonerada e não possui CPRB. "
                        "Confirme se a alíquota zero é intencional."
                    )

        if can_create():
            with st.expander("Cadastrar novo BDI", expanded=not bdis):
                new_bdi, new_bdi_error = bdi_input_fields(
                    f"new_bdi_{cid}", contract_regime=effective_contract_regime
                )
                if st.button(
                    "Salvar novo BDI",
                    type="primary",
                    disabled=bool(new_bdi_error),
                    key=f"save_new_bdi_{cid}",
                ):
                    if not new_bdi["name"] or not new_bdi["reference_name"]:
                        st.error("Informe a identificação e a referência/aplicação do BDI.")
                    else:
                        placeholders = ",".join("?" for _ in BDI_DB_FIELDS)
                        bdi_id = execute(
                            f"""INSERT INTO contract_bdis(
                            contract_id,{','.join(BDI_DB_FIELDS)})
                            VALUES(?,{placeholders})""",
                            (cid,) + tuple(new_bdi[field] for field in BDI_DB_FIELDS),
                        )
                        log_action(
                            user["id"], "CRIAR", "BDI", bdi_id,
                            f"{new_bdi['name']} — {new_bdi['reference_name']}",
                        )
                        st.success("Composição de BDI cadastrada.")
                        rerun()

        if can_edit() and bdis:
            with st.expander("Editar BDI cadastrado"):
                edit_options = {
                    f"{item['name']} — {item['reference_name']}": item["id"]
                    for item in bdis
                }
                edit_label = st.selectbox(
                    "Composição para editar",
                    edit_options,
                    key=f"select_bdi_edit_{cid}",
                )
                edit_id = edit_options[edit_label]
                selected_bdi = next(item for item in bdis if item["id"] == edit_id)
                edited_bdi, edited_bdi_error = bdi_input_fields(
                    f"edit_bdi_{cid}_{edit_id}",
                    selected_bdi,
                    effective_contract_regime,
                )
                if st.button(
                    "Salvar alterações do BDI",
                    type="primary",
                    disabled=bool(edited_bdi_error),
                    key=f"save_bdi_edit_{cid}_{edit_id}",
                ):
                    if not edited_bdi["name"] or not edited_bdi["reference_name"]:
                        st.error("Informe a identificação e a referência/aplicação do BDI.")
                    else:
                        assignments = ",".join(
                            f"{field}=?" for field in BDI_DB_FIELDS
                        )
                        execute(
                            f"""UPDATE contract_bdis SET {assignments},
                            updated_at=CURRENT_TIMESTAMP WHERE id=? AND contract_id=?""",
                            tuple(edited_bdi[field] for field in BDI_DB_FIELDS)
                            + (edit_id, cid),
                        )
                        log_action(
                            user["id"], "EDITAR", "BDI", edit_id,
                            f"{edited_bdi['name']} — {edited_bdi['reference_name']}",
                        )
                        st.success("Composição de BDI atualizada.")
                        rerun()

        if can_delete() and bdis:
            with st.expander("Excluir BDI cadastrado"):
                delete_options = {
                    f"{item['name']} — {item['reference_name']}": item["id"]
                    for item in bdis
                }
                delete_label = st.selectbox(
                    "Composição para excluir",
                    delete_options,
                    key=f"select_bdi_delete_{cid}",
                )
                confirm_bdi_delete = st.checkbox(
                    "Confirmo a exclusão desta composição de BDI",
                    key=f"confirm_bdi_delete_{cid}",
                )
                if st.button(
                    "Excluir BDI",
                    disabled=not confirm_bdi_delete,
                    key=f"delete_bdi_{cid}",
                ):
                    bdi_id = delete_options[delete_label]
                    execute(
                        "DELETE FROM contract_bdis WHERE id=? AND contract_id=?",
                        (bdi_id, cid),
                    )
                    log_action(
                        user["id"], "EXCLUIR", "BDI", bdi_id, delete_label
                    )
                    st.success("Composição de BDI excluída.")
                    rerun()
    if is_ata(contract):
        with tabs["Contratos decorrentes da ATA"]:
            st.markdown("#### Contratos decorrentes da Ata de Registro de Preços")
            st.caption(
                "Cadastre aqui cada contrato formalizado com base nesta ATA. Os aditivos desses "
                "contratos permanecem nesta mesma área, sem criar fichas separadas."
            )
            ata_contracts = load_ata_contracts(cid)
            if ata_contracts:
                ata_display = pd.DataFrame([{
                    "Contrato": item["contract_number"],
                    "Contratante": item["client"] or contract["client"],
                    "Processo": item["process_number"],
                    "Início original": fmt_date(item["start_date"]),
                    "Fim original": fmt_date(item["end_date"]),
                    "Valor original": brl(item["original_value"]),
                    "Instrumento vigente": item["current_instrument"],
                    "Início vigente": fmt_date(item["current_start_date"]),
                    "Fim vigente": fmt_date(item["current_end_date"]),
                    "Valor vigente": brl(item["current_value"]),
                    "Status": item["status"],
                } for item in ata_contracts])
                modern_table(ata_display)
                ata_options = {
                    f"{item['contract_number']} · {item['client'] or contract['client']}": item["id"]
                    for item in ata_contracts
                }
                ata_label = st.selectbox("Gerenciar contrato decorrente", ata_options)
                ata_contract_id = ata_options[ata_label]
                ata_contract = next(item for item in ata_contracts if item["id"] == ata_contract_id)
                responsive_cards([
                    (
                        "Contrato decorrente",
                        ata_contract["contract_number"],
                        ata_contract["process_number"] or "Processo não informado",
                        "blue",
                    ),
                    (
                        "Valor vigente",
                        brl(ata_contract["current_value"]),
                        ata_contract["current_instrument"],
                        "green",
                    ),
                    (
                        "Vigência atual",
                        f"{fmt_date(ata_contract['current_start_date'])} a "
                        f"{fmt_date(ata_contract['current_end_date'])}",
                        human_remaining(ata_contract["current_end_date"]),
                        "amber",
                    ),
                ])
                if can_edit():
                    with st.expander("Editar dados do contrato decorrente"):
                        with st.form(f"edit_ata_contract_{ata_contract_id}"):
                            c1, c2, c3 = st.columns(3)
                            ata_number = c1.text_input(
                                "Número do contrato *", ata_contract["contract_number"] or ""
                            )
                            ata_process = c2.text_input(
                                "Processo/ordem de fornecimento", ata_contract["process_number"] or ""
                            )
                            ata_status = c3.selectbox(
                                "Status",
                                ["ATIVO", "SUSPENSO", "ENCERRADO", "CANCELADO", "OUTRO"],
                                index=(
                                    ["ATIVO", "SUSPENSO", "ENCERRADO", "CANCELADO", "OUTRO"].index(
                                        ata_contract["status"]
                                    )
                                    if ata_contract["status"] in
                                    ["ATIVO", "SUSPENSO", "ENCERRADO", "CANCELADO", "OUTRO"]
                                    else 4
                                ),
                            )
                            ata_client = st.text_input(
                                "Contratante", ata_contract["client"] or contract["client"] or ""
                            )
                            ata_object = st.text_area("Objeto", ata_contract["object"] or "")
                            c1, c2, c3 = st.columns(3)
                            ata_signature = c1.date_input(
                                "Assinatura",
                                value=date.fromisoformat(ata_contract["signature_date"])
                                if ata_contract["signature_date"] else None,
                                format="DD/MM/YYYY",
                            )
                            ata_start = c2.date_input(
                                "Início original",
                                value=date.fromisoformat(ata_contract["start_date"])
                                if ata_contract["start_date"] else None,
                                format="DD/MM/YYYY",
                            )
                            ata_end = c3.date_input(
                                "Fim original",
                                value=date.fromisoformat(ata_contract["end_date"])
                                if ata_contract["end_date"] else None,
                                format="DD/MM/YYYY",
                            )
                            c1, c2 = st.columns(2)
                            ata_original_value = c1.number_input(
                                "Valor original", min_value=0.0,
                                value=float(ata_contract["original_value"] or 0), format="%.2f",
                            )
                            ata_current_value = c2.number_input(
                                "Valor atual", min_value=0.0,
                                value=float(ata_contract["current_value"] or 0), format="%.2f",
                            )
                            c1, c2 = st.columns(2)
                            ata_responsible = c1.text_input(
                                "Responsável", ata_contract["responsible_name"] or ""
                            )
                            ata_email = c2.text_input(
                                "E-mail do responsável", ata_contract["responsible_email"] or ""
                            )
                            ata_notes = st.text_area("Observações", ata_contract["notes"] or "")
                            if st.form_submit_button("Salvar contrato decorrente"):
                                execute(
                                    """UPDATE ata_contracts SET contract_number=?,process_number=?,
                                    client=?,object=?,signature_date=?,start_date=?,end_date=?,
                                    original_value=?,current_value=?,status=?,responsible_name=?,
                                    responsible_email=?,notes=?,updated_at=CURRENT_TIMESTAMP WHERE id=? AND ata_id=?""",
                                    (
                                        ata_number, ata_process,
                                        normalize_agency_name(ata_client), ata_object,
                                        ata_signature.isoformat() if ata_signature else None,
                                        ata_start.isoformat() if ata_start else None,
                                        ata_end.isoformat() if ata_end else None,
                                        ata_original_value, ata_current_value, ata_status,
                                        ata_responsible, ata_email, ata_notes, ata_contract_id, cid,
                                    ),
                                )
                                log_action(
                                    user["id"], "EDITAR", "contrato decorrente de ATA",
                                    ata_contract_id, ata_number,
                                )
                                st.success("Contrato decorrente atualizado.")
                                rerun()
                st.markdown("##### Aditivos do contrato decorrente")
                ata_amendments = [dict(row) for row in query(
                    """SELECT * FROM ata_contract_amendments WHERE ata_contract_id=?
                    ORDER BY id""",
                    (ata_contract_id,),
                )]
                ata_guarantees_by_amendment = {}
                for guarantee_row in query(
                    """SELECT id,ata_amendment_id,guarantee_type,custom_type,
                    request_status,end_date,required_amount,guaranteed_amount
                    FROM contract_guarantees
                    WHERE ata_contract_id=? AND ata_amendment_id IS NOT NULL
                    ORDER BY id""",
                    (ata_contract_id,),
                ):
                    guarantee_item = dict(guarantee_row)
                    ata_guarantees_by_amendment.setdefault(
                        int(guarantee_item["ata_amendment_id"]), []
                    ).append(guarantee_item)
                for ata_amendment in ata_amendments:
                    linked_guarantees = ata_guarantees_by_amendment.get(
                        int(ata_amendment["id"]), []
                    )
                    ata_amendment["linked_guarantee_count"] = len(linked_guarantees)
                    if linked_guarantees:
                        ata_amendment["guarantee_status"] = " · ".join(
                            (
                                f"{guarantee_item.get('custom_type') or guarantee_item.get('guarantee_type')}: "
                                f"{operational_status(guarantee_item)}"
                                + (
                                    f" até {fmt_date(guarantee_item.get('end_date'))}"
                                    if guarantee_item.get("end_date") else ""
                                )
                            )
                            for guarantee_item in linked_guarantees
                        )
                    else:
                        ata_amendment["guarantee_status"] = "Sem garantia vinculada"
                ata_amendment_columns = [
                    "id", "ordinal", "kind", "description", "value", "start_date", "end_date",
                    "duration_months", "guarantee_status", "art_status", "notes",
                ]
                if ata_amendments and can_edit():
                    ata_amendment_df = pd.DataFrame(ata_amendments)[ata_amendment_columns].copy()
                    ata_amendment_df["value"] = ata_amendment_df["value"].map(brl)
                    for column in ("start_date", "end_date"):
                        ata_amendment_df[column] = pd.to_datetime(
                            ata_amendment_df[column], errors="coerce"
                        ).dt.date
                    ata_amendment_df["duration_months"] = ata_amendment_df.apply(
                        lambda row: contract_duration_months(
                            row["start_date"], row["end_date"]
                        ),
                        axis=1,
                    )
                    edited_ata_amendments = st.data_editor(
                        ata_amendment_df, width="stretch", hide_index=True,
                        disabled=["id", "duration_months", "guarantee_status"],
                        key=f"edit_ata_amendments_{ata_contract_id}",
                        column_config={
                            "id": st.column_config.NumberColumn("Código"),
                            "ordinal": st.column_config.TextColumn("Ordem"),
                            "kind": st.column_config.TextColumn("Instrumento"),
                            "description": st.column_config.TextColumn("Descrição", width="large"),
                            "value": st.column_config.TextColumn(
                                "Valor vigente",
                                help="Informe no padrão brasileiro, por exemplo: R$ 22.763.546,65.",
                            ),
                            "start_date": st.column_config.DateColumn("Início", format="DD/MM/YYYY"),
                            "end_date": st.column_config.DateColumn("Fim", format="DD/MM/YYYY"),
                            "duration_months": st.column_config.NumberColumn("Meses"),
                            "guarantee_status": st.column_config.TextColumn(
                                "Garantias vinculadas",
                                help="Campo automático da aba Garantias e seguros.",
                            ),
                            "art_status": st.column_config.TextColumn("ART"),
                            "notes": st.column_config.TextColumn("Observações", width="large"),
                        },
                    )
                    if st.button(
                        "Salvar aditivos do contrato decorrente",
                        key=f"save_ata_amendments_{ata_contract_id}",
                    ):
                        invalid_periods = [
                            int(row["id"]) for _, row in edited_ata_amendments.iterrows()
                            if clean(row["start_date"]) and clean(row["end_date"])
                            and contract_duration_months(
                                clean(row["start_date"]), clean(row["end_date"])
                            ) is None
                        ]
                        invalid_values = []
                        for _, row in edited_ata_amendments.iterrows():
                            try:
                                parse_brazilian_number(row["value"], 0)
                            except ValueError:
                                invalid_values.append(int(row["id"]))
                        if invalid_periods:
                            st.error(
                                "A data final não pode ser anterior à data inicial. "
                                f"Revise o(s) registro(s): {invalid_periods}."
                            )
                        elif invalid_values:
                            st.error(
                                "Informe os valores no padrão brasileiro. "
                                f"Revise o(s) registro(s): {invalid_values}."
                            )
                        else:
                            for _, row in edited_ata_amendments.iterrows():
                                duration_months = contract_duration_months(
                                    clean(row["start_date"]), clean(row["end_date"])
                                )
                                execute(
                                    """UPDATE ata_contract_amendments SET ordinal=?,kind=?,
                                    description=?,value=?,start_date=?,end_date=?,
                                    duration_months=?,art_status=?,notes=?
                                    WHERE id=? AND ata_contract_id=?""",
                                    (
                                        clean(row["ordinal"]), clean(row["kind"]),
                                        clean(row["description"]),
                                        parse_brazilian_number(row["value"], 0),
                                        clean(row["start_date"]), clean(row["end_date"]),
                                        duration_months, clean(row["art_status"]),
                                        clean(row["notes"]),
                                        int(row["id"]), ata_contract_id,
                                    ),
                                )
                            log_action(
                                user["id"], "EDITAR", "aditivos de contrato da ATA",
                                ata_contract_id,
                            )
                            st.success("Aditivos atualizados.")
                            rerun()
                else:
                    ata_amendment_display = pd.DataFrame([{
                        "Ordem": row["ordinal"],
                        "Instrumento": str(row["kind"] or "").title(),
                        "Descrição": row["description"],
                        "Valor vigente": brl(row["value"]),
                        "Início": fmt_date(row["start_date"]),
                        "Fim": fmt_date(row["end_date"]),
                        "Meses": row["duration_months"],
                        "Garantia": row["guarantee_status"],
                        "ART": row["art_status"],
                        "Observações": row["notes"],
                    } for row in ata_amendments])
                    modern_table(ata_amendment_display)
                if can_create():
                    with st.form(f"new_ata_amendment_{ata_contract_id}", clear_on_submit=True):
                        c1, c2, c3 = st.columns(3)
                        ata_ordinal = c1.text_input("Número/ordem", placeholder="1º")
                        ata_kind = c2.selectbox(
                            "Tipo",
                            [
                                "TERMO ADITIVO",
                                "TERMO DE APOSTILAMENTO",
                                "OUTRO (INFORMAR ABAIXO)",
                            ],
                            key=f"ata_kind_{ata_contract_id}",
                        )
                        ata_amendment_value = c3.number_input(
                            "Valor atualizado", min_value=0.0, format="%.2f"
                        )
                        ata_custom_kind = st.text_input(
                            "Nome do instrumento quando o tipo for “Outro”",
                            placeholder="Ex.: Termo de Rerratificação ou Ordem de Serviço",
                            key=f"ata_custom_kind_{ata_contract_id}",
                        )
                        c1, c2 = st.columns(2)
                        ata_amendment_start = c1.date_input(
                            "Início", value=None, format="DD/MM/YYYY"
                        )
                        ata_amendment_end = c2.date_input(
                            "Fim", value=None, format="DD/MM/YYYY"
                        )
                        ata_calculated_duration = contract_duration_months(
                            ata_amendment_start, ata_amendment_end
                        )
                        if ata_calculated_duration is not None:
                            st.caption(
                                f"Vigência calculada automaticamente: "
                                f"{ata_calculated_duration} mês(es) completo(s)."
                            )
                        ata_description = st.text_area("Objeto e alterações relevantes")
                        ata_amendment_notes = st.text_area("Observações do aditivo")
                        ata_amendment_upload = st.file_uploader(
                            "Documento do aditivo/apostilamento (opcional)",
                            help="Se anexado agora, já fica salvo na ficha do contrato "
                            "decorrente e é enviado por e-mail junto com o aviso de "
                            "providências (garantia contratual e ART), quando houver "
                            "responsável cadastrado para isso.",
                            key=f"ata_amendment_upload_{ata_contract_id}",
                        )
                        if st.form_submit_button("Adicionar aditivo ao contrato decorrente"):
                            resolved_ata_kind = (
                                ata_custom_kind.strip()
                                if ata_kind == "OUTRO (INFORMAR ABAIXO)"
                                else ata_kind
                            )
                            if not resolved_ata_kind:
                                st.error("Informe o nome do instrumento selecionado como “Outro”.")
                            elif (
                                ata_amendment_start and ata_amendment_end
                                and ata_amendment_end < ata_amendment_start
                            ):
                                st.error(
                                    "A data final não pode ser anterior à data inicial."
                                )
                            else:
                                new_ata_amendment_id = execute(
                                    """INSERT INTO ata_contract_amendments(
                                    ata_contract_id,ordinal,kind,description,value,start_date,end_date,
                                    duration_months,notes)
                                    VALUES(?,?,?,?,?,?,?,?,?)""",
                                    (
                                        ata_contract_id, ata_ordinal, resolved_ata_kind,
                                        ata_description, ata_amendment_value,
                                        ata_amendment_start.isoformat()
                                        if ata_amendment_start else None,
                                        ata_amendment_end.isoformat()
                                        if ata_amendment_end else None,
                                        ata_calculated_duration,
                                        ata_amendment_notes,
                                    ),
                                )
                                log_action(
                                    user["id"], "CRIAR", "aditivo de contrato da ATA",
                                    new_ata_amendment_id, ata_ordinal,
                                )
                                ata_amendment_doc_bytes = ata_amendment_doc_filename = None
                                if ata_amendment_upload:
                                    save_document(
                                        cid, ata_amendment_upload, "INSTRUMENTO CONTRATUAL",
                                        f"{ata_ordinal} {resolved_ata_kind}".strip(),
                                        ata_contract_id=ata_contract_id,
                                        ata_amendment_id=new_ata_amendment_id,
                                    )
                                    ata_amendment_doc_bytes = ata_amendment_upload.getvalue()
                                    ata_amendment_doc_filename = ata_amendment_upload.name
                                notified = notify_contract_task_needs(
                                    ata_contract_id=ata_contract_id,
                                    ata_amendment_id=new_ata_amendment_id,
                                    ata_number=contract["contract_number"],
                                    kind_label=resolved_ata_kind, ordinal=ata_ordinal,
                                    cost_center=contract["cost_center"],
                                    client=ata_contract["client"] or contract["client"],
                                    contract_number=ata_contract["contract_number"],
                                    document_bytes=ata_amendment_doc_bytes,
                                    document_filename=ata_amendment_doc_filename,
                                    extra_recipients=[
                                        contract.get("engineer_email"), contract.get("manager_email"),
                                    ],
                                )
                                success_message = "Instrumento do contrato decorrente registrado."
                                if notified:
                                    success_message += (
                                        f" Aviso de providências enviado para "
                                        f"{len(notified)} responsável(is)."
                                    )
                                st.success(success_message)
                                rerun()
                st.markdown("##### Documentos do contrato decorrente e de seus aditivos")
                ata_contract_docs = [dict(row) for row in query(
                    """SELECT * FROM documents WHERE ata_contract_id=?
                    AND ata_amendment_id IS NULL ORDER BY uploaded_at DESC""",
                    (ata_contract_id,),
                )]
                document_downloads(ata_contract_docs, f"ata_contract_{ata_contract_id}")
                for ata_amendment in ata_amendments:
                    with st.expander(
                        f"{ata_amendment['ordinal'] or ''} "
                        f"{str(ata_amendment['kind'] or 'Instrumento').title()} · "
                        f"{fmt_date(ata_amendment['end_date'])}"
                    ):
                        ata_amendment_docs = [dict(row) for row in query(
                            "SELECT * FROM documents WHERE ata_amendment_id=? ORDER BY uploaded_at DESC",
                            (ata_amendment["id"],),
                        )]
                        document_downloads(
                            ata_amendment_docs, f"ata_amendment_{ata_amendment['id']}"
                        )
                if can_create():
                    ata_document_targets = {"Contrato decorrente": (ata_contract_id, None)}
                    ata_document_targets.update({
                        f"{row['ordinal'] or ''} {row['kind'] or 'Instrumento'}".strip().title():
                        (ata_contract_id, row["id"])
                        for row in ata_amendments
                    })
                    with st.form(f"upload_ata_document_{ata_contract_id}", clear_on_submit=True):
                        ata_document_target = st.selectbox(
                            "Vincular documento a", ata_document_targets
                        )
                        ata_document_title = st.text_input("Título do documento")
                        ata_document_upload = st.file_uploader("Arquivo do contrato/aditivo")
                        if st.form_submit_button("Anexar documento") and ata_document_upload:
                            target_contract_id, target_amendment_id = ata_document_targets[
                                ata_document_target
                            ]
                            did = save_document(
                                cid, ata_document_upload, "CONTRATO DECORRENTE DE ATA",
                                ata_document_title, ata_contract_id=target_contract_id,
                                ata_amendment_id=target_amendment_id,
                            )
                            log_action(
                                user["id"], "ANEXAR", "documento de contrato da ATA",
                                did, ata_document_upload.name,
                            )
                            st.success("Documento anexado.")
                            rerun()
                if can_delete():
                    if ata_amendments:
                        with st.expander("Excluir aditivo do contrato decorrente"):
                            ata_amendment_delete_options = {
                                f"{row['ordinal'] or ''} {row['kind'] or 'Instrumento'}".strip().title():
                                row["id"] for row in ata_amendments
                            }
                            ata_amendment_to_delete = st.selectbox(
                                "Aditivo para excluir",
                                ata_amendment_delete_options,
                                key=f"ata_amendment_delete_{ata_contract_id}",
                            )
                            confirm_ata_amendment_delete = st.checkbox(
                                "Confirmo a exclusão deste aditivo",
                                key=f"confirm_ata_amendment_delete_{ata_contract_id}",
                            )
                            if st.button(
                                "Excluir aditivo do contrato decorrente",
                                disabled=not confirm_ata_amendment_delete,
                                key=f"delete_ata_amendment_{ata_contract_id}",
                            ):
                                ata_amendment_id = ata_amendment_delete_options[
                                    ata_amendment_to_delete
                                ]
                                linked_guarantees = query(
                                    "SELECT id FROM contract_guarantees WHERE ata_amendment_id=?",
                                    (ata_amendment_id,),
                                )
                                if linked_guarantees:
                                    st.error(
                                        "Este aditivo possui garantia/seguro vinculado. "
                                        "Reassocie ou exclua a garantia antes de excluir o aditivo."
                                    )
                                else:
                                    execute(
                                        "UPDATE documents SET ata_amendment_id=NULL WHERE ata_amendment_id=?",
                                        (ata_amendment_id,),
                                    )
                                    execute(
                                        """DELETE FROM ata_contract_amendments
                                        WHERE id=? AND ata_contract_id=?""",
                                        (ata_amendment_id, ata_contract_id),
                                    )
                                    log_action(
                                        user["id"], "EXCLUIR", "aditivo de contrato da ATA",
                                        ata_amendment_id, ata_amendment_to_delete,
                                    )
                                    st.success("Aditivo excluído.")
                                    rerun()
                    st.divider()
                    confirm_ata_delete = st.checkbox(
                        "Confirmo a exclusão deste contrato decorrente e de seus aditivos",
                        key=f"confirm_ata_delete_{ata_contract_id}",
                    )
                    if st.button(
                        "Excluir contrato decorrente",
                        disabled=not confirm_ata_delete,
                        key=f"delete_ata_contract_{ata_contract_id}",
                    ):
                        linked_guarantees = query(
                            "SELECT id FROM contract_guarantees WHERE ata_contract_id=?",
                            (ata_contract_id,),
                        )
                        if linked_guarantees:
                            st.error(
                                "Este contrato decorrente possui garantia/seguro vinculado. "
                                "Reassocie ou exclua a garantia antes de excluir o contrato."
                            )
                        else:
                            execute(
                                """UPDATE documents SET ata_contract_id=NULL,ata_amendment_id=NULL
                                WHERE ata_contract_id=?""",
                                (ata_contract_id,),
                            )
                            execute("DELETE FROM ata_contracts WHERE id=? AND ata_id=?", (ata_contract_id, cid))
                            log_action(
                                user["id"], "EXCLUIR", "contrato decorrente de ATA",
                                ata_contract_id, ata_contract["contract_number"],
                            )
                            st.success("Contrato decorrente excluído.")
                            rerun()
            else:
                st.info("Nenhum contrato decorrente foi cadastrado para esta ATA.")
            if can_create():
                with st.expander("Cadastrar novo contrato decorrente", expanded=not ata_contracts):
                    with st.form("new_ata_contract", clear_on_submit=True):
                        c1, c2 = st.columns(2)
                        new_ata_number = c1.text_input("Número do contrato *")
                        new_ata_process = c2.text_input("Processo/ordem de fornecimento")
                        new_ata_client = st.text_input(
                            "Contratante", value=contract["client"] or ""
                        )
                        new_ata_object = st.text_area("Objeto do contrato decorrente")
                        c1, c2, c3 = st.columns(3)
                        new_ata_signature = c1.date_input(
                            "Assinatura", value=None, format="DD/MM/YYYY"
                        )
                        new_ata_start = c2.date_input(
                            "Início", value=None, format="DD/MM/YYYY"
                        )
                        new_ata_end = c3.date_input(
                            "Fim", value=None, format="DD/MM/YYYY"
                        )
                        c1, c2 = st.columns(2)
                        new_ata_original_value = c1.number_input(
                            "Valor original", min_value=0.0, format="%.2f",
                            help="Sem aditivos, este também será o valor atual.",
                        )
                        c2.metric(
                            "Valor atual inicial",
                            brl(new_ata_original_value),
                            help="O valor atual será alterado somente por instrumento posterior.",
                        )
                        new_ata_current_value = new_ata_original_value
                        c1, c2 = st.columns(2)
                        new_ata_responsible = c1.text_input("Responsável")
                        new_ata_email = c2.text_input("E-mail do responsável")
                        new_ata_notes = st.text_area("Observações")
                        new_ata_document_upload = st.file_uploader(
                            "Documento do contrato decorrente assinado (opcional)",
                            help="Se anexado agora, já fica salvo na ficha do contrato "
                            "decorrente e é enviado por e-mail junto com o aviso de "
                            "providências iniciais (garantia contratual e ART), quando "
                            "houver responsável cadastrado para isso.",
                        )
                        if st.form_submit_button("Cadastrar contrato decorrente", width="stretch"):
                            if not new_ata_number.strip():
                                st.error("Informe o número do contrato decorrente.")
                            else:
                                new_ata_contract_id = execute(
                                    """INSERT INTO ata_contracts(
                                    ata_id,contract_number,process_number,client,object,signature_date,
                                    start_date,end_date,original_value,current_value,responsible_name,
                                    responsible_email,notes) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                                    (
                                        cid, new_ata_number, new_ata_process,
                                        normalize_agency_name(new_ata_client),
                                        new_ata_object,
                                        new_ata_signature.isoformat() if new_ata_signature else None,
                                        new_ata_start.isoformat() if new_ata_start else None,
                                        new_ata_end.isoformat() if new_ata_end else None,
                                        new_ata_original_value, new_ata_current_value,
                                        new_ata_responsible, new_ata_email, new_ata_notes,
                                    ),
                                )
                                log_action(
                                    user["id"], "CRIAR", "contrato decorrente de ATA",
                                    new_ata_contract_id, new_ata_number,
                                )
                                ata_document_bytes = ata_document_filename = None
                                if new_ata_document_upload:
                                    save_document(
                                        cid, new_ata_document_upload, "CONTRATO",
                                        "Contrato decorrente assinado",
                                        ata_contract_id=new_ata_contract_id,
                                    )
                                    ata_document_bytes = new_ata_document_upload.getvalue()
                                    ata_document_filename = new_ata_document_upload.name
                                notified = notify_contract_task_needs(
                                    ata_contract_id=new_ata_contract_id, ata_amendment_id=None,
                                    ata_number=contract["contract_number"],
                                    kind_label="CONTRATO", ordinal=None,
                                    cost_center=contract["cost_center"],
                                    client=normalize_agency_name(new_ata_client),
                                    contract_number=new_ata_number.strip(),
                                    document_bytes=ata_document_bytes,
                                    document_filename=ata_document_filename,
                                    extra_recipients=[
                                        contract.get("engineer_email"), contract.get("manager_email"),
                                    ],
                                )
                                success_message = "Contrato decorrente cadastrado."
                                if notified:
                                    success_message += (
                                        f" Aviso de providências iniciais enviado para "
                                        f"{len(notified)} responsável(is)."
                                    )
                                st.success(success_message)
                                rerun()
    with tabs["Sindicatos e datas-base"]:
        unions = [dict(r) for r in query(
            "SELECT * FROM contract_unions WHERE contract_id=? ORDER BY base_month,union_name", (cid,)
        )]
        union_instruments = [dict(r) for r in query(
            "SELECT id,ordinal,kind FROM amendments WHERE contract_id=? ORDER BY id", (cid,)
        )]
        union_instrument_labels = {
            a["id"]: f"{a['ordinal'] or ''} {a['kind'] or 'Instrumento'}".strip().title()
            for a in union_instruments
        }
        union_columns = [
            "id", "union_name", "collective_agreement", "category_name", "base_month",
            "base_date", "next_repactuation", "amendment_id", "notes",
        ]
        if unions and can_edit():
            union_edit_df = pd.DataFrame(unions)[union_columns].copy()
            for column in ("base_date", "next_repactuation"):
                union_edit_df[column] = pd.to_datetime(union_edit_df[column], errors="coerce").dt.date
            edited_unions = st.data_editor(
                union_edit_df, width="stretch", hide_index=True,
                disabled=["id"], key="edit_unions",
                column_config={
                    "id": st.column_config.NumberColumn("Código"),
                    "union_name": st.column_config.TextColumn("Sindicato", width="large"),
                    "collective_agreement": st.column_config.TextColumn("CCT/Instrumento coletivo"),
                    "category_name": st.column_config.TextColumn("Categoria"),
                    "base_month": st.column_config.NumberColumn("Mês da data-base"),
                    "base_date": st.column_config.DateColumn("Data-base", format="DD/MM/YYYY"),
                    "next_repactuation": st.column_config.DateColumn("Próxima repactuação", format="DD/MM/YYYY"),
                    "amendment_id": st.column_config.SelectboxColumn(
                        "Instrumento de referência",
                        options=[None, *union_instrument_labels.keys()],
                        format_func=lambda value: union_instrument_labels.get(value, "Contrato geral"),
                    ),
                    "notes": st.column_config.TextColumn("Observações", width="large"),
                },
            )
            if st.button("Salvar alterações dos sindicatos"):
                for _, row in edited_unions.iterrows():
                    execute(
                        """UPDATE contract_unions SET union_name=?,collective_agreement=?,category_name=?,
                        base_month=?,base_date=?,next_repactuation=?,amendment_id=?,notes=?
                        WHERE id=? AND contract_id=?""",
                        tuple(clean(row[c]) for c in union_columns[1:]) + (int(row["id"]), cid),
                    )
                log_action(user["id"], "EDITAR", "sindicatos", cid)
                st.success("Sindicatos e datas-base atualizados.")
                rerun()
        else:
            union_display = pd.DataFrame([{
                "Sindicato": u["union_name"], "CCT/Instrumento coletivo": u["collective_agreement"],
                "Categoria": u["category_name"], "Mês da data-base": u["base_month"],
                "Data-base": fmt_date(u["base_date"]),
                "Próxima repactuação": fmt_date(u["next_repactuation"]),
                "Instrumento de referência": union_instrument_labels.get(u["amendment_id"], "Contrato geral"),
                "Observações": u["notes"],
            } for u in unions])
            modern_table(union_display)
        if can_create():
            with st.form("new_union", clear_on_submit=True):
                c1, c2 = st.columns(2)
                union_name = c1.text_input("Sindicato *")
                cct = c2.text_input("CCT/Instrumento coletivo")
                c1, c2, c3 = st.columns(3)
                category_name = c1.text_input("Categoria abrangida")
                base_month = c2.number_input("Mês da data-base", min_value=1, max_value=12, value=1)
                next_repactuation = c3.date_input(
                    "Próxima repactuação", value=None, format="DD/MM/YYYY"
                )
                instrument_options = {"Contrato geral": None, **{
                    label: instrument_id for instrument_id, label in union_instrument_labels.items()
                }}
                instrument_label = st.selectbox("Instrumento contratual de referência", instrument_options)
                notes = st.text_area("Observações sobre a CCT/data-base")
                if st.form_submit_button("Adicionar sindicato/data-base"):
                    if union_name.strip():
                        uid = execute(
                            """INSERT INTO contract_unions(contract_id,amendment_id,union_name,
                            collective_agreement,category_name,base_month,next_repactuation,notes)
                            VALUES(?,?,?,?,?,?,?,?)""",
                            (cid, instrument_options[instrument_label], union_name, cct, category_name,
                             base_month, next_repactuation.isoformat() if next_repactuation else None, notes),
                        )
                        log_action(user["id"], "CRIAR", "sindicato", uid, union_name)
                        st.success("Sindicato e data-base adicionados.")
                        rerun()
                    st.error("Informe o sindicato.")
        if unions and can_delete():
            delete_union_options = {
                f"{u['union_name']} · {u['collective_agreement'] or 'sem CCT'}": u["id"]
                for u in unions
            }
            delete_union_label = st.selectbox(
                "Remover registro de sindicato",
                delete_union_options,
            )
            confirm_union = st.checkbox("Confirmo a remoção deste registro", key="confirm_union")
            if st.button("Remover sindicato/data-base", disabled=not confirm_union):
                delete_union_id = delete_union_options[delete_union_label]
                execute("DELETE FROM contract_unions WHERE id=?", (delete_union_id,))
                log_action(
                    user["id"], "EXCLUIR", "sindicato", delete_union_id,
                    delete_union_label,
                )
                st.success("Registro de sindicato/data-base removido.")
                rerun()
        st.markdown("#### Documentos das convenções e sindicatos")
        for union in unions:
            with st.expander(
                f"{union['union_name']} · {union['collective_agreement'] or 'CCT não informada'} · "
                f"{union_instrument_labels.get(union['amendment_id'], 'Contrato geral')} · "
                f"Repactuação: {fmt_date(union['next_repactuation'])}"
            ):
                docs = [dict(r) for r in query(
                    "SELECT * FROM documents WHERE union_id=? ORDER BY uploaded_at DESC", (union["id"],)
                )]
                document_downloads(docs, f"union_{union['id']}")
        if can_create() and unions:
            union_document_options = {
                f"{u['union_name']} · {u['collective_agreement'] or 'sem CCT'}": u["id"] for u in unions
            }
            with st.form("upload_union_document", clear_on_submit=True):
                union_document_label = st.selectbox("Sindicato/CCT relacionado", union_document_options)
                union_document_title = st.text_input("Título do documento")
                union_upload = st.file_uploader("Documento da CCT/sindicato")
                if st.form_submit_button("Anexar à CCT") and union_upload:
                    did = save_document(
                        cid, union_upload, "CCT/SINDICATO", union_document_title,
                        union_id=union_document_options[union_document_label],
                    )
                    log_action(user["id"], "ANEXAR", "documento", did, union_upload.name)
                    st.success("Documento vinculado ao sindicato/CCT.")
                    rerun()
    with tabs["Equipe e cargos"]:
        st.markdown("#### Parâmetros de cálculo")
        labor_rows = [dict(r) for r in query("SELECT * FROM labor_parameters ORDER BY year DESC")]
        labor_map = {r["year"]: float(r["minimum_wage"] or 0) for r in labor_rows}
        current_year = today_brt().year
        current_minimum = labor_map.get(current_year, 0)
        c1, c2 = st.columns(2)
        c1.write(f"**Ano-base da insalubridade:** {current_year}")
        c2.metric("Salário mínimo parametrizado", brl(current_minimum))
        if can_edit():
            with st.expander("Atualizar salário mínimo anual"):
                parameter_year = st.number_input(
                    "Ano", min_value=2000, max_value=2100, value=current_year, key="labor_year"
                )
                parameter_value = st.number_input(
                    "Salário mínimo", min_value=0.0,
                    value=float(labor_map.get(parameter_year, 0)), format="%.2f", key="labor_value",
                )
                if st.button("Salvar parâmetro trabalhista"):
                    execute(
                        """INSERT INTO labor_parameters(year,minimum_wage) VALUES(?,?)
                        ON CONFLICT(year) DO UPDATE SET minimum_wage=excluded.minimum_wage,
                        updated_at=CURRENT_TIMESTAMP""",
                        (parameter_year, parameter_value),
                    )
                    st.success("Salário mínimo atualizado.")
                    rerun()
        positions = [dict(r) for r in query(
            """SELECT p.*,u.union_name FROM contract_positions p
            LEFT JOIN contract_unions u ON u.id=p.union_id
            WHERE p.contract_id=? ORDER BY p.title""", (cid,)
        )]
        if positions:
            zero_salary_positions = [
                position for position in positions
                if float(position.get("base_salary") or 0) <= 0
            ]
            if zero_salary_positions:
                st.warning(
                    f"{len(zero_salary_positions)} cargo(s) estão com salário-base zerado. "
                    "Os valores antigos não podem ser reconstruídos automaticamente; revise-os "
                    "na grade abaixo e clique em “Salvar alterações da equipe”."
                )
            positions_df = pd.DataFrame(positions)
            benefit_totals = {
                r["position_id"]: float(r["total"] or 0) for r in query(
                    """SELECT position_id,SUM(monthly_value) total FROM position_benefits
                    GROUP BY position_id"""
                )
            }
            positions_df["Periculosidade (R$)"] = (
                positions_df["base_salary"] * positions_df["hazard_percent"].fillna(0) / 100
            )
            positions_df["Base insalubridade"] = positions_df["unhealthy_base_year"].apply(
                lambda year: labor_map.get(int(year), 0) if pd.notna(year) else current_minimum
            )
            positions_df["Insalubridade (R$)"] = (
                positions_df["Base insalubridade"] * positions_df["unhealthy_percent"].fillna(0) / 100
            )
            positions_df["Benefícios (R$)"] = positions_df["id"].map(benefit_totals).fillna(0)
            positions_df["Custo por empregado"] = (
                positions_df["base_salary"] + positions_df["Periculosidade (R$)"]
                + positions_df["Insalubridade (R$)"] + positions_df["Benefícios (R$)"]
            )
            positions_df["Custo mensal da equipe"] = positions_df["quantity"] * positions_df["Custo por empregado"]
            position_columns = [
                "id", "title", "quantity", "base_salary", "hazard_percent",
                "unhealthy_percent", "unhealthy_base_year", "notes",
            ]
            if can_edit():
                position_edit_df = positions_df[position_columns].copy()
                position_edit_df["base_salary"] = position_edit_df["base_salary"].map(brl)
                edited_positions = st.data_editor(
                    position_edit_df, width="stretch", hide_index=True,
                    disabled=["id"], key="edit_positions",
                    column_config={
                        "id": st.column_config.NumberColumn("Código"),
                        "title": st.column_config.TextColumn("Cargo/função", width="large"),
                        "quantity": st.column_config.NumberColumn("Quantidade"),
                        "base_salary": st.column_config.TextColumn(
                            "Salário-base",
                            help="Informe no padrão brasileiro, por exemplo: R$ 4.250,00.",
                        ),
                        "hazard_percent": st.column_config.NumberColumn("Periculosidade (%)", format="%.2f%%"),
                        "unhealthy_percent": st.column_config.NumberColumn("Insalubridade (%)", format="%.2f%%"),
                        "unhealthy_base_year": st.column_config.NumberColumn("Ano-base insalubridade"),
                        "notes": st.column_config.TextColumn("Observações", width="large"),
                    },
                )
                if st.button("Salvar alterações da equipe"):
                    try:
                        for _, row in edited_positions.iterrows():
                            execute(
                                """UPDATE contract_positions SET title=?,quantity=?,base_salary=?,
                                hazard_percent=?,unhealthy_percent=?,unhealthy_base_year=?,notes=?
                                WHERE id=? AND contract_id=?""",
                                (
                                    clean(row["title"]), clean(row["quantity"]),
                                    parse_brazilian_number(row["base_salary"], 0),
                                    clean(row["hazard_percent"]),
                                    clean(row["unhealthy_percent"]),
                                    clean(row["unhealthy_base_year"]), clean(row["notes"]),
                                    int(row["id"]), cid,
                                ),
                            )
                    except ValueError:
                        st.error(
                            "Revise o salário-base. Use o padrão brasileiro, por exemplo: "
                            "R$ 4.250,00."
                        )
                    else:
                        log_action(user["id"], "EDITAR", "equipe", cid)
                        st.success("Equipe atualizada.")
                        rerun()
                calculation_display = positions_df[[
                    "title", "quantity", "base_salary", "hazard_percent", "Periculosidade (R$)",
                    "unhealthy_percent", "Base insalubridade", "Insalubridade (R$)",
                    "Benefícios (R$)", "Custo por empregado", "Custo mensal da equipe",
                ]].copy()
                calculation_display.columns = [
                    "Cargo", "Quantidade", "Salário-base", "Periculosidade (%)", "Periculosidade (R$)",
                    "Insalubridade (%)", "Base da insalubridade", "Insalubridade (R$)",
                    "Benefícios", "Custo por empregado", "Custo mensal da equipe",
                ]
                for column in [
                    "Salário-base", "Periculosidade (R$)", "Base da insalubridade",
                    "Insalubridade (R$)", "Benefícios", "Custo por empregado", "Custo mensal da equipe",
                ]:
                    calculation_display[column] = calculation_display[column].map(brl)
                modern_table(calculation_display)
            else:
                display_positions = positions_df[[
                    "title", "quantity", "base_salary", "hazard_percent", "Periculosidade (R$)",
                    "unhealthy_percent", "Base insalubridade", "Insalubridade (R$)",
                    "Benefícios (R$)", "Custo por empregado", "Custo mensal da equipe",
                ]].copy()
                display_positions.columns = [
                    "Cargo", "Quantidade", "Salário-base", "Periculosidade (%)", "Periculosidade (R$)",
                    "Insalubridade (%)", "Base da insalubridade", "Insalubridade (R$)",
                    "Benefícios", "Custo por empregado", "Custo mensal da equipe",
                ]
                for column in [
                    "Salário-base", "Periculosidade (R$)", "Base da insalubridade",
                    "Insalubridade (R$)", "Benefícios", "Custo por empregado", "Custo mensal da equipe",
                ]:
                    display_positions[column] = display_positions[column].map(brl)
                modern_table(display_positions)
            responsive_cards([
                (
                    "Custo mensal estimado da equipe",
                    brl(positions_df["Custo mensal da equipe"].sum()),
                    "Salários, adicionais e benefícios cadastrados",
                    "green",
                )
            ])
            st.markdown("#### Benefícios por cargo")
            for position in positions:
                benefits_for_position = [dict(r) for r in query(
                    "SELECT * FROM position_benefits WHERE position_id=? ORDER BY benefit_type",
                    (position["id"],),
                )]
                with st.expander(f"{position['title']} · {position['quantity']} empregado(s)"):
                    if benefits_for_position:
                        benefit_display = pd.DataFrame([{
                            "Benefício": b["benefit_type"],
                            "Descrição": b["description"],
                            "Valor mensal por empregado": brl(b["monthly_value"]),
                        } for b in benefits_for_position])
                        modern_table(benefit_display)
                    else:
                        st.caption("Nenhum benefício detalhado.")
        else:
            st.info("Nenhum cargo cadastrado.")
        if can_create():
            unions_now = [dict(r) for r in query(
                "SELECT id,union_name,collective_agreement FROM contract_unions WHERE contract_id=?", (cid,)
            )]
            union_options = {"Sem vinculação": None, **{
                f"{u['union_name']} · {u['collective_agreement'] or 'sem CCT'}": u["id"] for u in unions_now
            }}
            with st.form("new_position", clear_on_submit=True):
                c1, c2 = st.columns(2)
                title = c1.text_input("Cargo/função *")
                quantity = c2.number_input("Quantidade", min_value=1, value=1)
                c1, c2, c3 = st.columns(3)
                salary = c1.number_input("Salário-base", min_value=0.0, format="%.2f")
                hazard_percent = c2.number_input("Periculosidade (%)", min_value=0.0, max_value=100.0)
                unhealthy_percent = c3.number_input("Insalubridade (%)", min_value=0.0, max_value=100.0)
                c1, c2, c3 = st.columns(3)
                unhealthy_year = c1.number_input(
                    "Ano-base da insalubridade", min_value=2000, max_value=2100, value=current_year
                )
                union_label = c3.selectbox("Sindicato/CCT vinculado", union_options)
                notes = st.text_area("Observações do cargo")
                if st.form_submit_button("Adicionar cargo"):
                    if title.strip():
                        pid = execute(
                            """INSERT INTO contract_positions(contract_id,title,quantity,base_salary,
                            hazard_percent,unhealthy_percent,unhealthy_base_year,union_id,notes)
                            VALUES(?,?,?,?,?,?,?,?,?)""",
                            (cid, title, quantity, salary, hazard_percent, unhealthy_percent,
                             unhealthy_year, union_options[union_label], notes),
                        )
                        log_action(user["id"], "CRIAR", "cargo", pid, title)
                        st.success("Cargo adicionado.")
                        rerun()
                    st.error("Informe o cargo.")
            positions_now = [dict(r) for r in query(
                "SELECT id,title FROM contract_positions WHERE contract_id=? ORDER BY title", (cid,)
            )]
            if positions_now:
                position_options = {p["title"]: p["id"] for p in positions_now}
                with st.form("new_benefit", clear_on_submit=True):
                    position_label = st.selectbox("Cargo relacionado", position_options)
                    c1, c2 = st.columns(2)
                    benefit_type = c1.selectbox(
                        "Tipo de benefício",
                        ["PLANO DE SAÚDE", "PLANO ODONTOLÓGICO", "SEGURO DE VIDA",
                         "VALE-ALIMENTAÇÃO", "VALE-REFEIÇÃO", "AUXÍLIO-CRECHE", "OUTRO"],
                    )
                    benefit_value = c2.number_input("Valor mensal por empregado", min_value=0.0, format="%.2f")
                    benefit_description = st.text_area("Descrição e regras do benefício")
                    if st.form_submit_button("Adicionar benefício"):
                        execute(
                            """INSERT INTO position_benefits(position_id,benefit_type,description,monthly_value)
                            VALUES(?,?,?,?)""",
                            (position_options[position_label], benefit_type, benefit_description, benefit_value),
                        )
                        st.success("Benefício vinculado ao cargo.")
                        rerun()
        if can_delete():
            all_benefits = [dict(r) for r in query(
                """SELECT b.id,b.benefit_type,b.description,b.monthly_value,p.title
                FROM position_benefits b JOIN contract_positions p ON p.id=b.position_id
                WHERE p.contract_id=? ORDER BY p.title,b.benefit_type""", (cid,)
            )]
            if all_benefits:
                benefit_delete_options = {
                    f"{b['title']} · {b['benefit_type']} · {brl(b['monthly_value'])}": b["id"]
                    for b in all_benefits
                }
                benefit_delete_label = st.selectbox(
                    "Benefício para remover", benefit_delete_options
                )
                confirm_benefit_delete = st.checkbox(
                    "Confirmo a remoção do benefício", key="confirm_benefit_delete"
                )
                if st.button("Remover benefício", disabled=not confirm_benefit_delete):
                    benefit_id = benefit_delete_options[benefit_delete_label]
                    execute("DELETE FROM position_benefits WHERE id=?", (benefit_id,))
                    log_action(
                        user["id"], "EXCLUIR", "benefício", benefit_id,
                        benefit_delete_label,
                    )
                    st.success("Benefício removido.")
                    rerun()
            if positions:
                delete_position_options = {
                    f"{p['title']} · {p['quantity']} empregado(s)": p["id"]
                    for p in positions
                }
                delete_position_label = st.selectbox(
                    "Remover cargo",
                    delete_position_options,
                )
                confirm_position = st.checkbox(
                    "Confirmo a remoção deste cargo", key="confirm_position"
                )
                if st.button("Remover cargo", disabled=not confirm_position):
                    delete_position_id = delete_position_options[delete_position_label]
                    execute(
                        "DELETE FROM contract_positions WHERE id=? AND contract_id=?",
                        (delete_position_id, cid),
                    )
                    log_action(
                        user["id"], "EXCLUIR", "cargo", delete_position_id,
                        delete_position_label,
                    )
                    st.success("Cargo e seus benefícios vinculados foram removidos.")
                    rerun()

        st.divider()
        st.markdown("#### Funcionários nominais (relação de pessoas por centro de custo)")
        st.caption(
            "Diferente da tabela de cargos acima (que é um planejamento por quantidade, ex.: "
            "\"Servente — 5 vagas\"), esta seção guarda o nome de cada pessoa alocada neste "
            "contrato — para conferência com o RH e para outras telas (como o SESMT) "
            "reconhecerem automaticamente quem já está na equipe, sem redigitar."
        )
        employees = [dict(r) for r in query(
            "SELECT * FROM contract_employees WHERE contract_id=? ORDER BY full_name", (cid,)
        )]
        if employees:
            employees_df = pd.DataFrame([
                {
                    "Nome": e["full_name"], "Cargo": e["role_title"] or "—",
                    "CPF": e["cpf"] or "—",
                    "Admissão": fmt_date(e["admission_date"]) if e["admission_date"] else "—",
                    "Salário-base": brl(e["base_salary"]) if e["base_salary"] else "—",
                    "Status": e["status"], "Origem": e["source"],
                }
                for e in employees
            ])
            modern_table(employees_df, max_height=320)
        else:
            st.info("Nenhum funcionário nominal cadastrado ainda neste contrato.")

        if can_create():
            with st.expander("Importar planilha do RH (Excel)", expanded=not employees):
                st.caption(
                    "Envie a planilha como o RH exportar (não precisa reformatar) — o sistema "
                    "reconhece as colunas pelo nome do cabeçalho, mas você confirma o mapeamento "
                    "antes de importar. A planilha em si NÃO é salva no sistema, só os dados "
                    "reconhecidos. Se a planilha tiver uma coluna de centro de custo, só as "
                    "linhas correspondentes ao centro de custo "
                    f"**{contract['cost_center']}** deste contrato serão importadas; sem essa "
                    "coluna, todas as linhas são consideradas deste contrato."
                )
                uploaded_sheet = st.file_uploader(
                    "Planilha (.xlsx ou .csv)", type=["xlsx", "xls", "csv"], key=f"employee_sheet_{cid}",
                )
                if uploaded_sheet is not None:
                    try:
                        sheet_df = (
                            pd.read_csv(uploaded_sheet) if uploaded_sheet.name.lower().endswith(".csv")
                            else pd.read_excel(uploaded_sheet)
                        )
                    except Exception as error:
                        st.error(f"Não consegui ler essa planilha: {error}")
                        sheet_df = None
                    if sheet_df is not None and not sheet_df.empty:
                        st.caption(f"{len(sheet_df)} linha(s) encontrada(s). Confirme o que é cada coluna:")
                        columns_available = ["(não usar)"] + list(sheet_df.columns)
                        auto_guess = suggest_employee_column_mapping(sheet_df.columns)
                        m1, m2, m3 = st.columns(3)
                        col_name = m1.selectbox(
                            "Coluna do nome *", columns_available,
                            index=columns_available.index(auto_guess.get("full_name", "(não usar)")),
                            key=f"map_name_{cid}",
                        )
                        col_role = m2.selectbox(
                            "Coluna do cargo", columns_available,
                            index=columns_available.index(auto_guess.get("role_title", "(não usar)")),
                            key=f"map_role_{cid}",
                        )
                        col_cost_center = m3.selectbox(
                            "Coluna do centro de custo (opcional)", columns_available,
                            index=columns_available.index(auto_guess.get("cost_center", "(não usar)")),
                            key=f"map_cc_{cid}",
                        )
                        m1, m2, m3 = st.columns(3)
                        col_cpf = m1.selectbox(
                            "Coluna do CPF (opcional)", columns_available,
                            index=columns_available.index(auto_guess.get("cpf", "(não usar)")),
                            key=f"map_cpf_{cid}",
                        )
                        col_admission = m2.selectbox(
                            "Coluna da admissão (opcional)", columns_available,
                            index=columns_available.index(auto_guess.get("admission_date", "(não usar)")),
                            key=f"map_admission_{cid}",
                        )
                        col_salary = m3.selectbox(
                            "Coluna do salário-base (opcional)", columns_available,
                            index=columns_available.index(auto_guess.get("base_salary", "(não usar)")),
                            key=f"map_salary_{cid}",
                        )
                        if col_name != "(não usar)":
                            preview_rows, skipped_other_cc = build_employee_import_preview(
                                sheet_df, contract["cost_center"],
                                col_name, col_role, col_cost_center, col_cpf, col_admission, col_salary,
                            )
                            st.caption(
                                f"{len(preview_rows)} linha(s) serão importadas para este contrato"
                                + (f" — {skipped_other_cc} linha(s) de outro centro de custo foram "
                                   "ignoradas." if skipped_other_cc else ".")
                            )
                            if preview_rows:
                                st.dataframe(pd.DataFrame(preview_rows).head(20), width="stretch")
                                if st.button("Confirmar importação", key=f"confirm_import_{cid}"):
                                    for row in preview_rows:
                                        execute(
                                            """INSERT INTO contract_employees(
                                            contract_id,full_name,role_title,cpf,admission_date,
                                            base_salary,source,created_by)
                                            VALUES(?,?,?,?,?,?,?,?)""",
                                            (
                                                cid, row["Nome"], row.get("Cargo") or None,
                                                row.get("CPF") or None, row.get("Admissão") or None,
                                                row.get("Salário-base") or None,
                                                "IMPORTADO", user["id"],
                                            ),
                                        )
                                    log_action(
                                        user["id"], "IMPORTAR", "funcionários nominais",
                                        cid, f"{len(preview_rows)} linha(s)",
                                    )
                                    st.success(f"{len(preview_rows)} funcionário(s) importado(s).")
                                    rerun()
                        else:
                            st.warning("Selecione ao menos a coluna do nome para continuar.")

            with st.expander("Cadastrar funcionário manualmente"):
                with st.form(f"new_employee_{cid}", clear_on_submit=True):
                    ne1, ne2 = st.columns(2)
                    new_employee_name = ne1.text_input("Nome completo *")
                    new_employee_role = ne2.text_input("Cargo/função")
                    ne1, ne2, ne3 = st.columns(3)
                    new_employee_cpf = ne1.text_input("CPF")
                    new_employee_admission = ne2.date_input(
                        "Admissão", value=None, format="DD/MM/YYYY", key=f"new_emp_admission_{cid}",
                    )
                    new_employee_salary = ne3.number_input("Salário-base", min_value=0.0, format="%.2f")
                    if st.form_submit_button("Cadastrar funcionário"):
                        if not new_employee_name.strip():
                            st.error("Informe o nome completo.")
                        else:
                            execute(
                                """INSERT INTO contract_employees(
                                contract_id,full_name,role_title,cpf,admission_date,base_salary,
                                source,created_by) VALUES(?,?,?,?,?,?,?,?)""",
                                (
                                    cid, new_employee_name.strip(), new_employee_role.strip() or None,
                                    new_employee_cpf.strip() or None,
                                    new_employee_admission.isoformat() if new_employee_admission else None,
                                    new_employee_salary or None, "MANUAL", user["id"],
                                ),
                            )
                            log_action(
                                user["id"], "CADASTRAR", "funcionário nominal", cid, new_employee_name,
                            )
                            st.success("Funcionário cadastrado.")
                            rerun()
            if employees:
                with st.expander("Excluir funcionário"):
                    delete_employee_options = {e["full_name"]: e["id"] for e in employees}
                    delete_employee_label = st.selectbox(
                        "Funcionário", list(delete_employee_options), key=f"delete_employee_select_{cid}",
                    )
                    if st.button("Excluir funcionário selecionado", key=f"delete_employee_btn_{cid}"):
                        execute(
                            "DELETE FROM contract_employees WHERE id=? AND contract_id=?",
                            (delete_employee_options[delete_employee_label], cid),
                        )
                        log_action(
                            user["id"], "EXCLUIR", "funcionário nominal",
                            delete_employee_options[delete_employee_label], delete_employee_label,
                        )
                        st.success("Funcionário removido.")
                        rerun()

    with tabs["Prazos e obrigações"]:
        obligation_notice = st.session_state.pop("obligation_email_notice", None)
        if obligation_notice:
            notice_ok, notice_message = obligation_notice
            (st.success if notice_ok else st.warning)(notice_message)
        obligations = [dict(r) for r in query(
            "SELECT * FROM obligations WHERE contract_id=? ORDER BY due_date", (cid,)
        )]
        today_iso = today_brt().isoformat()
        pending_obligations = [
            row for row in obligations
            if str(row["status"] or "").upper() not in
            {"CONCLUÍDA", "CONCLUIDA", "CANCELADA", "CANCELADO"}
        ]
        overdue_obligations = [
            row for row in pending_obligations
            if row["due_date"] and str(row["due_date"])[:10] < today_iso
        ]
        email_obligations = [
            row for row in pending_obligations
            if row["notification_enabled"] and row["responsible_email"]
        ]
        responsive_cards([
            (
                "Obrigações pendentes",
                len(pending_obligations),
                "Itens que ainda exigem acompanhamento",
                "amber",
            ),
            (
                "Prazos vencidos",
                len(overdue_obligations),
                "Continuam recebendo cobranças até a conclusão",
                "red",
            ),
            (
                "Alertas por e-mail",
                len(email_obligations),
                "Obrigações ativas com destinatário configurado",
                "green",
            ),
        ])
        current_end = display_contract.get("current_end_date")
        current_days = days_until(current_end)
        if not contract["engineer_email"]:
            st.warning(
                "Os alertas automáticos de encerramento não poderão ser enviados: "
                "informe o e-mail do engenheiro responsável na aba Editar."
            )
        elif current_days is not None and 0 <= current_days <= 30:
            next_alert = (
                "A confirmação de 15 dias será enviada nesta janela."
                if current_days <= 15
                else "O primeiro aviso de 30 dias será enviado nesta janela."
            )
            st.info(
                f"Vigência atual: {human_remaining(current_end)}. {next_alert} "
                f"Destinatário: {contract['engineer_email']}."
            )
        expiry_notifications = [dict(row) for row in query(
            """SELECT event_type,event_date,recipient,sent_at
            FROM notification_log
            WHERE reference_id=?
            AND event_type IN (
                'CONTRATO_VENCIMENTO_30_DIAS',
                'CONTRATO_VENCIMENTO_15_DIAS'
            )
            ORDER BY sent_at DESC""",
            (cid,),
        )]
        if expiry_notifications:
            with st.expander("Histórico dos alertas de encerramento"):
                modern_table(pd.DataFrame([{
                    "Alerta": (
                        "30 dias"
                        if row["event_type"].endswith("30_DIAS")
                        else "15 dias"
                    ),
                    "Fim da vigência": fmt_date(row["event_date"]),
                    "Destinatário": row["recipient"],
                    "Enviado em": fmt_datetime(row["sent_at"]),
                } for row in expiry_notifications]))
        email_status = smtp_status()
        with st.expander("Configuração e teste dos alertas por e-mail"):
            if email_status["configured"]:
                st.success(
                    f"Canal configurado para envio por {email_status['sender']} via "
                    f"{email_status['host']}:{email_status['port']} "
                    f"({email_status['security']})."
                )
                st.caption(
                    f"Origem: {email_status['source']}. A configuração é relida em "
                    "cada atualização, teste e envio automático."
                )
                st.caption(
                    "O agendador diário processa obrigações, repactuações, avisos de "
                    "encerramento dos contratos aos 30 e 15 dias e vencimentos de "
                    "garantias/seguros aos 60, 30 e 15 dias."
                )
                if email_status["default_cc"]:
                    st.caption(
                        f"Cópia global configurada: {email_status['default_cc']}"
                    )
                for smtp_warning in email_status["warnings"]:
                    st.warning(smtp_warning)
            else:
                st.warning(
                    "SMTP ainda não configurado. Os prazos serão registrados, mas os e-mails "
                    "só serão enviados após preencher o arquivo configuracao_email.bat."
                )
                st.caption(
                    f"Origem consultada: {email_status['source']}. Campos pendentes: "
                    + ", ".join(email_status["missing"])
                )
            if user["role"] == "admin":
                test_recipient = st.text_input(
                    "Destinatário do teste",
                    value=(
                        contract["engineer_email"]
                        or contract["manager_email"]
                        or user["email"]
                        or ""
                    ),
                    key=f"smtp_test_recipient_{cid}",
                )
                if st.button(
                    "Enviar e-mail de teste",
                    key=f"smtp_test_button_{cid}",
                    disabled=not email_status["configured"],
                ):
                    ok, message = send_test_email(test_recipient)
                    if ok:
                        log_action(
                            user["id"],
                            "TESTAR E-MAIL",
                            "configuração SMTP",
                            cid,
                            test_recipient,
                        )
                    (st.success if ok else st.error)(message)
        obligation_columns = [
            "id", "title", "category", "due_date", "recurrence", "responsible_name",
            "responsible_email", "copy_emails", "priority", "status", "advance_days",
            "notification_enabled", "reminder_frequency_days", "notes",
        ]
        if obligations and can_edit():
            obligation_edit_df = pd.DataFrame(obligations)[obligation_columns].copy()
            obligation_edit_df["due_date"] = pd.to_datetime(
                obligation_edit_df["due_date"], errors="coerce"
            ).dt.date
            edited_obligations = st.data_editor(
                obligation_edit_df, width="stretch", hide_index=True,
                disabled=["id"], key="edit_obligations",
                column_config={
                    "id": st.column_config.NumberColumn("Código"),
                    "title": st.column_config.TextColumn("Obrigação/prazo", width="large"),
                    "category": st.column_config.TextColumn("Categoria"),
                    "due_date": st.column_config.DateColumn("Vencimento", format="DD/MM/YYYY"),
                    "recurrence": st.column_config.TextColumn("Recorrência"),
                    "responsible_name": st.column_config.TextColumn("Responsável"),
                    "responsible_email": st.column_config.TextColumn("E-mail principal"),
                    "copy_emails": st.column_config.TextColumn(
                        "E-mails em cópia/grupo", width="large"
                    ),
                    "priority": st.column_config.SelectboxColumn(
                        "Prioridade", options=["BAIXA", "MÉDIA", "ALTA", "CRÍTICA"]
                    ),
                    "status": st.column_config.SelectboxColumn(
                        "Status",
                        options=[
                            "PENDENTE", "EM ANDAMENTO", "VENCIDA", "CONCLUÍDA", "CANCELADA",
                        ],
                    ),
                    "advance_days": st.column_config.NumberColumn("Antecedência (dias)"),
                    "notification_enabled": st.column_config.CheckboxColumn("Alertas ativos"),
                    "reminder_frequency_days": st.column_config.NumberColumn(
                        "Cobrar a cada (dias)", min_value=1
                    ),
                    "notes": st.column_config.TextColumn("Orientações", width="large"),
                },
            )
            if st.button("Salvar alterações dos prazos"):
                for _, row in edited_obligations.iterrows():
                    execute(
                        """UPDATE obligations SET title=?,category=?,due_date=?,recurrence=?,
                        responsible_name=?,responsible_email=?,copy_emails=?,priority=?,status=?,
                        advance_days=?,notification_enabled=?,reminder_frequency_days=?,notes=?
                        WHERE id=? AND contract_id=?""",
                        tuple(clean(row[c]) for c in obligation_columns[1:]) + (int(row["id"]), cid),
                    )
                log_action(user["id"], "EDITAR", "obrigações", cid)
                st.success("Prazos e obrigações atualizados.")
                rerun()
        else:
            obligation_display = pd.DataFrame([{
                "Obrigação/prazo": row["title"],
                "Categoria": row["category"],
                "Vencimento": fmt_date(row["due_date"]),
                "Recorrência": row["recurrence"],
                "Responsável": row["responsible_name"],
                "E-mail principal": row["responsible_email"],
                "Cópia/grupo": row["copy_emails"],
                "Prioridade": row["priority"],
                "Status": row["status"],
                "Antecedência": f"{row['advance_days'] or 0} dias",
                "Alertas": "ATIVOS" if row["notification_enabled"] else "DESATIVADOS",
                "Frequência de cobrança": f"{row['reminder_frequency_days'] or 7} dias",
                "Cobranças enviadas": row["reminder_count"] or 0,
                "Última cobrança": fmt_datetime(row["last_reminder_at"]),
                "Orientações": row["notes"],
            } for row in obligations])
            modern_table(obligation_display)
        if can_create():
            with st.form("new_obligation", clear_on_submit=True):
                title = st.text_input("Obrigação/prazo")
                c1, c2, c3 = st.columns(3)
                category = c1.selectbox(
                    "Categoria",
                    ["ADMINISTRATIVA", "TÉCNICA", "FATURAMENTO", "REPACTUAÇÃO",
                     "GARANTIA", "ART", "OUTRA"],
                )
                due = c2.date_input(
                    "Vencimento", value=today_brt() + timedelta(days=30),
                    format="DD/MM/YYYY",
                )
                priority = c3.selectbox("Prioridade", ["BAIXA", "MÉDIA", "ALTA", "CRÍTICA"], index=1)
                c1, c2 = st.columns(2)
                responsible_name = c1.text_input(
                    "Responsável",
                    value=contract["engineer_name"] or contract["manager_name"] or "",
                )
                responsible_email = c2.text_input(
                    "E-mail principal",
                    value=contract["engineer_email"] or contract["manager_email"] or "",
                )
                default_copy = (
                    contract["manager_email"]
                    if responsible_email == (contract["engineer_email"] or "")
                    else contract["engineer_email"]
                )
                copy_emails = st.text_input(
                    "E-mails em cópia ou grupo",
                    value=default_copy or "",
                    help="Separe vários endereços por vírgula ou ponto e vírgula.",
                )
                c1, c2, c3 = st.columns(3)
                recurrence = c1.selectbox(
                    "Recorrência da obrigação",
                    ["ÚNICA", "SEMANAL", "MENSAL", "TRIMESTRAL", "ANUAL", "OUTRA"],
                )
                advance_days = c2.number_input(
                    "Iniciar alertas com antecedência de (dias)",
                    min_value=0,
                    max_value=365,
                    value=30,
                )
                reminder_frequency = c3.number_input(
                    "Repetir cobrança a cada (dias)",
                    min_value=1,
                    max_value=90,
                    value=7,
                )
                notes = st.text_area("Orientações e comprovações necessárias")
                notification_enabled = st.checkbox(
                    "Manter alertas e cobranças automáticas ativos até a conclusão",
                    value=True,
                )
                notify = st.checkbox("Enviar o primeiro e-mail imediatamente após salvar")
                if st.form_submit_button("Registrar obrigação"):
                    if not title.strip():
                        st.error("Informe o nome da obrigação ou do prazo.")
                    else:
                        oid = execute(
                            """INSERT INTO obligations(
                            contract_id,title,category,due_date,recurrence,responsible_name,
                            responsible_email,copy_emails,priority,advance_days,
                            notification_enabled,reminder_frequency_days,notes)
                            VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                            (
                                cid, title, category, due.isoformat(), recurrence,
                                responsible_name, responsible_email, copy_emails, priority,
                                advance_days, int(notification_enabled), reminder_frequency, notes,
                            ),
                        )
                        log_action(
                            st.session_state.user["id"], "CRIAR", "obrigação", oid, title
                        )
                        if notify and responsible_email:
                            ok, message = send_obligation_alert(oid, force=True)
                            st.session_state.obligation_email_notice = (ok, message)
                        elif notification_enabled and not responsible_email:
                            st.session_state.obligation_email_notice = (
                                False,
                                "Obrigação registrada, mas os alertas não serão enviados até "
                                "que um e-mail principal seja informado.",
                            )
                        else:
                            st.session_state.obligation_email_notice = (
                                True,
                                "Obrigação registrada e incluída no controle de prazos.",
                            )
                        rerun()
        if obligations and can_edit():
            st.markdown("#### Reenvio manual de cobrança")
            reminder_options = {
                f"{row['title']} · {fmt_date(row['due_date'])} · {row['status']}": row["id"]
                for row in obligations
                if str(row["status"] or "").upper()
                not in {"CONCLUÍDA", "CONCLUIDA", "CANCELADA", "CANCELADO"}
            }
            if reminder_options:
                reminder_label = st.selectbox(
                    "Obrigação para cobrar agora",
                    reminder_options,
                    key=f"manual_obligation_reminder_{cid}",
                )
                if st.button(
                    "Enviar cobrança agora",
                    key=f"send_manual_obligation_reminder_{cid}",
                ):
                    ok, message = send_obligation_alert(
                        reminder_options[reminder_label], force=True
                    )
                    if ok:
                        log_action(
                            user["id"], "ENVIAR COBRANÇA", "obrigação",
                            reminder_options[reminder_label], reminder_label,
                        )
                    st.session_state.obligation_email_notice = (ok, message)
                    rerun()
        if obligations and can_delete():
            obligation_delete_options = {
                f"{row['title']} · {fmt_date(row['due_date'])}": row["id"]
                for row in obligations
            }
            obligation_to_delete = st.selectbox(
                "Obrigação para excluir", obligation_delete_options
            )
            confirm_obligation_delete = st.checkbox(
                "Confirmo a exclusão desta obrigação",
                key=f"confirm_obligation_delete_{cid}",
            )
            if st.button(
                "Excluir obrigação",
                disabled=not confirm_obligation_delete,
                key=f"delete_obligation_{cid}",
            ):
                obligation_id = obligation_delete_options[obligation_to_delete]
                execute("DELETE FROM obligations WHERE id=? AND contract_id=?", (obligation_id, cid))
                log_action(
                    user["id"], "EXCLUIR", "obrigação", obligation_id, obligation_to_delete
                )
                st.success("Obrigação excluída.")
                rerun()
    with tabs["ARTs"]:
        art_amendments = contract_amendments_with_arts(cid)
        initial_instrument_label = (
            f"Contrato inicial · {contract.get('contract_number') or contract.get('cost_center')}"
        )
        art_instrument_options = {
            "Selecione o instrumento contratual": ("NÃO DEFINIDO", None, None, None),
            initial_instrument_label: ("CONTRATO_INICIAL", None, None, None),
        }
        for amendment in art_amendments:
            art_instrument_options[
                f"{amendment_instrument_label(amendment)} · código {amendment['id']}"
            ] = ("ADITIVO", int(amendment["id"]), None, None)
        for ata in query(
            "SELECT id,contract_number,client FROM ata_contracts WHERE ata_id=? ORDER BY id",
            (cid,),
        ):
            ata_label = " · ".join(filter(None, [ata["contract_number"], ata["client"]]))
            art_instrument_options[
                f"Contrato da ATA · {ata_label}"
            ] = ("CONTRATO DECORRENTE DA ATA", None, int(ata["id"]), None)
            for amendment in query(
                "SELECT id,ordinal,kind FROM ata_contract_amendments WHERE ata_contract_id=? ORDER BY id",
                (ata["id"],),
            ):
                amendment_label = " ".join(filter(None, [
                    str(amendment["ordinal"] or "").strip(),
                    str(amendment["kind"] or "").strip(),
                ])) or f"Instrumento {amendment['id']}"
                art_instrument_options[
                    f"Aditivo da ATA · {ata_label} · {amendment_label}"
                ] = ("ADITIVO DE CONTRATO DA ATA", None, int(ata["id"]), int(amendment["id"]))
        arts = organize_art_rows(query(
            """SELECT ar.*,a.ordinal amendment_ordinal,a.kind amendment_kind,
            atc.contract_number ata_contract_number, atc.client ata_client,
            ataa.ordinal ata_amendment_ordinal, ataa.kind ata_amendment_kind
            FROM arts ar
            LEFT JOIN amendments a ON a.id=ar.amendment_id
            LEFT JOIN ata_contracts atc ON atc.id=ar.ata_contract_id
            LEFT JOIN ata_contract_amendments ataa ON ataa.id=ar.ata_amendment_id
            WHERE ar.contract_id=? ORDER BY ar.id""",
            (cid,),
        ))
        company_art_profiles = professional_profiles(query(
            "SELECT * FROM arts ORDER BY id"
        ))
        if arts:
            st.caption(
                f"{len(arts)} ART(s) organizadas por "
                f"{len(professional_profiles(arts))} profissional(is), na ordem do primeiro cadastro."
            )
            art_display = pd.DataFrame([{
                "Profissional": art["professional_display_name"],
                "Título profissional": art.get("professional_title"),
                "Registro profissional": art["professional_registration"],
                "Número da ART": art["art_number"],
                "Instrumento contratual": art_instrument_reference(art),
                "Emissão": fmt_date(art["issue_date"]),
                "Término": fmt_date(art["end_date"]),
                "Status": art["status"],
                "Descrição": art["description"],
            } for art in arts])
            modern_table(art_display)
            unlinked_arts = [
                art for art in arts
                if str(art.get("instrument_scope") or "").upper() == "NÃO DEFINIDO"
            ]
            if unlinked_arts:
                st.warning(
                    f"{len(unlinked_arts)} ART(s) antiga(s) ainda não possuem instrumento "
                    "contratual definido. Use “Editar ART cadastrada” para concluir o vínculo."
                )
            for art in arts:
                with st.expander(
                    f"{art['professional_display_name']} · ART {art['art_number']} · "
                    f"{art_instrument_reference(art)}"
                ):
                    st.write(art["description"] or "Sem descrição.")
                    docs = [dict(r) for r in query(
                        "SELECT * FROM documents WHERE art_id=? ORDER BY uploaded_at DESC", (art["id"],)
                    )]
                    document_downloads(docs, f"art_{art['id']}")
        else:
            st.info("Nenhuma ART cadastrada.")
        if can_create() or can_edit():
            profile_options = {"Cadastrar novo profissional": None}
            for profile in company_art_profiles:
                label = " · ".join(filter(None, [
                    profile.get("professional_name"),
                    profile.get("professional_title"),
                    profile.get("professional_registration"),
                ]))
                profile_options[label] = profile
            selected_profile_label = st.selectbox(
                "Profissional da ART",
                list(profile_options),
                key=f"art_professional_profile_{cid}",
                help=(
                    "Selecione um profissional já cadastrado para preencher automaticamente "
                    "nome, título e registro, ou escolha cadastrar um novo profissional."
                ),
            )
            selected_profile = profile_options[selected_profile_label]
            profile_token = (
                selected_profile.get("key") if selected_profile else "NOVO_PROFISSIONAL"
            )
            with st.form(f"new_art_{cid}_{profile_token}", clear_on_submit=True):
                selected_instrument_label = st.selectbox(
                    "Instrumento contratual de referência *",
                    list(art_instrument_options),
                    help=(
                        "Selecione o contrato inicial ou o aditivo ao qual a ART pertence. "
                        "O vínculo preencherá automaticamente a coluna ARTs vinculadas em Aditivos."
                    ),
                )
                c1, c2 = st.columns(2)
                professional_name = c1.text_input(
                    "Nome do profissional *",
                    value=(selected_profile or {}).get("professional_name", ""),
                )
                professional_title = c2.text_input(
                    "Título profissional",
                    value=(selected_profile or {}).get("professional_title", ""),
                    placeholder="Ex.: Engenheiro Civil, Arquiteto ou Engenheiro Eletricista",
                )
                c1, c2 = st.columns(2)
                professional_registration = c1.text_input(
                    "Registro profissional",
                    value=(selected_profile or {}).get("professional_registration", ""),
                )
                art_number = c2.text_input("Número da ART *")
                c1, c2, c3 = st.columns(3)
                issue_date = c1.date_input(
                    "Data de emissão", value=None, format="DD/MM/YYYY"
                )
                art_end_date = c2.date_input(
                    "Data de término", value=None, format="DD/MM/YYYY"
                )
                art_status = c3.selectbox("Status", ["ATIVA", "BAIXADA", "SUBSTITUÍDA", "CANCELADA"])
                art_description = st.text_area("Objeto/descrição da ART")
                art_notes = st.text_area("Observações")
                if st.form_submit_button(
                    "Cadastrar ART", disabled=not can_create()
                ):
                    instrument_scope, amendment_id, ata_contract_id, ata_amendment_id = (
                        art_instrument_options[selected_instrument_label]
                    )
                    if (
                        issue_date and art_end_date
                        and art_end_date < issue_date
                    ):
                        st.error("A data de término não pode ser anterior à emissão.")
                    elif instrument_scope == "NÃO DEFINIDO":
                        st.error("Selecione o instrumento contratual de referência da ART.")
                    elif any(
                        art_number_key(item.get("art_number")) == art_number_key(art_number)
                        for item in arts
                    ):
                        st.error("Este número de ART já está cadastrado neste contrato.")
                    elif professional_name.strip() and art_number.strip():
                        art_id = execute(
                            """INSERT INTO arts(contract_id,amendment_id,ata_contract_id,ata_amendment_id,
                            instrument_scope,professional_name,professional_title,
                            professional_registration,art_number,issue_date,end_date,status,
                            description,notes) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                            (
                             cid, amendment_id, ata_contract_id, ata_amendment_id, instrument_scope,
                             professional_name, professional_title,
                             professional_registration, art_number,
                             issue_date.isoformat() if issue_date else None,
                             art_end_date.isoformat() if art_end_date else None,
                             art_status, art_description, art_notes),
                        )
                        log_action(
                            user["id"], "CRIAR", "ART", art_id,
                            f"{art_number} · {selected_instrument_label}",
                        )
                        st.success("ART cadastrada.")
                        rerun()
                    else:
                        st.error("Informe o profissional e o número da ART.")
            if arts:
                art_options = {
                    f"{a['professional_display_name']} · ART {a['art_number']}": a["id"]
                    for a in arts
                }
                with st.expander("Editar ART cadastrada"):
                    art_edit_label = st.selectbox(
                        "ART para editar", art_options, key=f"art_edit_select_{cid}"
                    )
                    art_edit = next(
                        item for item in arts if item["id"] == art_options[art_edit_label]
                    )
                    with st.form(f"edit_art_{art_edit['id']}"):
                        current_scope = str(
                            art_edit.get("instrument_scope") or "NÃO DEFINIDO"
                        ).upper()
                        current_amendment_id = art_edit.get("amendment_id")
                        current_ata_contract_id = art_edit.get("ata_contract_id")
                        current_ata_amendment_id = art_edit.get("ata_amendment_id")
                        current_instrument_label = next(
                            (
                                label for label, (scope, amendment_id, ata_contract_id, ata_amendment_id)
                                in art_instrument_options.items()
                                if scope == current_scope
                                and amendment_id == current_amendment_id
                                and ata_contract_id == current_ata_contract_id
                                and ata_amendment_id == current_ata_amendment_id
                            ),
                            "Selecione o instrumento contratual",
                        )
                        edit_instrument_label = st.selectbox(
                            "Instrumento contratual de referência *",
                            list(art_instrument_options),
                            index=list(art_instrument_options).index(
                                current_instrument_label
                            ),
                            key=f"edit_art_instrument_{art_edit['id']}",
                            help=(
                                "A alteração é refletida automaticamente na coluna "
                                "ARTs vinculadas da aba Aditivos."
                            ),
                        )
                        c1, c2 = st.columns(2)
                        edit_professional_name = c1.text_input(
                            "Profissional *", art_edit["professional_name"] or ""
                        )
                        edit_professional_title = c2.text_input(
                            "Título profissional", art_edit.get("professional_title") or ""
                        )
                        c1, c2 = st.columns(2)
                        edit_registration = c1.text_input(
                            "Registro profissional",
                            art_edit["professional_registration"] or "",
                        )
                        edit_art_number = c2.text_input(
                            "Número da ART *", art_edit["art_number"] or ""
                        )
                        c1, c2, c3 = st.columns(3)
                        edit_issue_date = c1.date_input(
                            "Data de emissão",
                            value=date.fromisoformat(art_edit["issue_date"])
                            if art_edit["issue_date"] else None,
                            format="DD/MM/YYYY",
                        )
                        edit_end_date = c2.date_input(
                            "Data de término",
                            value=date.fromisoformat(art_edit["end_date"])
                            if art_edit["end_date"] else None,
                            format="DD/MM/YYYY",
                        )
                        edit_status = c3.selectbox(
                            "Status",
                            ["ATIVA", "BAIXADA", "SUBSTITUÍDA", "CANCELADA"],
                            index=_option_index(
                                ["ATIVA", "BAIXADA", "SUBSTITUÍDA", "CANCELADA"],
                                art_edit["status"] or "ATIVA",
                            ),
                        )
                        edit_description = st.text_area(
                            "Objeto/descrição da ART", art_edit["description"] or ""
                        )
                        edit_notes = st.text_area(
                            "Observações", art_edit["notes"] or ""
                        )
                        if st.form_submit_button(
                            "Salvar alterações da ART", disabled=not can_edit()
                        ):
                            edit_instrument_scope, edit_amendment_id, edit_ata_contract_id, edit_ata_amendment_id = (
                                art_instrument_options[edit_instrument_label]
                            )
                            if (
                                edit_issue_date and edit_end_date
                                and edit_end_date < edit_issue_date
                            ):
                                st.error(
                                    "A data de término não pode ser anterior à emissão."
                                )
                            elif edit_instrument_scope == "NÃO DEFINIDO":
                                st.error(
                                    "Selecione o instrumento contratual de referência da ART."
                                )
                            elif any(
                                item["id"] != art_edit["id"]
                                and art_number_key(item.get("art_number"))
                                == art_number_key(edit_art_number)
                                for item in arts
                            ):
                                st.error("Este número de ART já está cadastrado neste contrato.")
                            elif edit_professional_name.strip() and edit_art_number.strip():
                                execute(
                                    """UPDATE arts SET amendment_id=?,ata_contract_id=?,ata_amendment_id=?,
                                    instrument_scope=?,
                                    professional_name=?,professional_title=?,
                                    professional_registration=?,art_number=?,issue_date=?,end_date=?,
                                    status=?,description=?,notes=? WHERE id=? AND contract_id=?""",
                                    (
                                        edit_amendment_id, edit_ata_contract_id, edit_ata_amendment_id,
                                        edit_instrument_scope,
                                        edit_professional_name, edit_professional_title,
                                        edit_registration, edit_art_number,
                                        edit_issue_date.isoformat() if edit_issue_date else None,
                                        edit_end_date.isoformat() if edit_end_date else None,
                                        edit_status, edit_description, edit_notes,
                                        art_edit["id"], cid,
                                    ),
                                )
                                log_action(
                                    user["id"], "EDITAR", "ART", art_edit["id"],
                                    f"{edit_art_number} · {edit_instrument_label}",
                                )
                                st.success("ART atualizada.")
                                rerun()
                            else:
                                st.error("Informe o profissional e o número da ART.")
                with st.form("upload_art_document", clear_on_submit=True):
                    art_label = st.selectbox("ART relacionada", art_options)
                    art_document_title = st.text_input("Título do documento", value="Documento da ART")
                    art_upload = st.file_uploader("Arquivo da ART")
                    if st.form_submit_button(
                        "Anexar documento à ART", disabled=not can_create()
                    ) and art_upload:
                        did = save_document(
                            cid, art_upload, "ART", art_document_title,
                            art_id=art_options[art_label],
                        )
                        log_action(user["id"], "ANEXAR", "documento", did, art_upload.name)
                        st.success("Documento vinculado à ART.")
                        rerun()
        if arts and can_delete():
            art_delete_options = {
                f"{row['professional_display_name']} · ART {row['art_number']}": row["id"]
                for row in arts
            }
            art_to_delete = st.selectbox("ART para excluir", art_delete_options)
            confirm_art_delete = st.checkbox(
                "Confirmo a exclusão desta ART", key=f"confirm_art_delete_{cid}"
            )
            if st.button(
                "Excluir ART",
                disabled=not confirm_art_delete,
                key=f"delete_art_{cid}",
            ):
                art_id = art_delete_options[art_to_delete]
                execute("DELETE FROM arts WHERE id=? AND contract_id=?", (art_id, cid))
                log_action(user["id"], "EXCLUIR", "ART", art_id, art_to_delete)
                st.success("ART excluída. Seus arquivos permanecem no histórico do contrato.")
                rerun()
    with tabs["CNO"]:
        st.markdown("#### Cadastro Nacional de Obras — CNO")
        cno_status_options = {
            "A definir": None,
            "Sim — CNO obrigatório": 1,
            "Não — CNO não aplicável": 0,
        }
        current_cno_required = display_contract.get("cno_required")
        current_cno_label = next(
            (
                label for label, value in cno_status_options.items()
                if value == current_cno_required
            ),
            "A definir",
        )
        selected_cno_label = st.radio(
            "Este contrato exige inscrição no CNO?",
            list(cno_status_options),
            index=list(cno_status_options).index(current_cno_label),
            horizontal=True,
            key=f"cno_required_{cid}",
            disabled=not can_edit(),
        )
        selected_cno_required = cno_status_options[selected_cno_label]
        if can_edit() and selected_cno_required != current_cno_required:
            if st.button(
                "Salvar definição do CNO",
                key=f"save_cno_required_{cid}",
                type="primary",
            ):
                execute(
                    """UPDATE contracts SET cno_required=?,updated_at=CURRENT_TIMESTAMP
                    WHERE id=?""",
                    (selected_cno_required, cid),
                )
                log_action(
                    user["id"], "EDITAR", "exigência de CNO", cid,
                    selected_cno_label,
                )
                st.success("Definição do CNO atualizada.")
                rerun()
        cno_required = current_cno_required == 1
        if current_cno_required == 0:
            st.success(
                "CNO marcado como não aplicável. Os campos de cadastramento e anexos "
                "permanecem recolhidos para evitar lançamentos indevidos."
            )
        elif current_cno_required is None:
            st.info(
                "Defina se o CNO é obrigatório. Os campos de preenchimento serão "
                "liberados somente após selecionar “Sim”."
            )
        ata_cno_mode = is_ata(display_contract)
        ata_cno_contracts = load_ata_contracts(cid) if ata_cno_mode else []
        ata_cno_labels = {
            int(item["id"]): " · ".join(filter(None, [
                f"Contrato {item.get('contract_number') or 's/n'}",
                item.get("client"),
            ]))
            for item in ata_cno_contracts
        }
        if cno_required and ata_cno_mode:
            st.caption(
                "Cada CNO da ata deve ser associado ao respectivo contrato decorrente, "
                "mantendo a rastreabilidade mesmo quando a ata gerar vários contratos."
            )
            if not ata_cno_contracts:
                st.warning(
                    "Cadastre primeiro ao menos um contrato na aba "
                    "“Contratos decorrentes da ATA” para vinculá-lo ao CNO."
                )
        elif cno_required:
            st.caption(
                "Registre uma ou mais inscrições vinculadas ao contrato, com as datas de "
                "cadastro e de início da responsabilidade e a respectiva área de atuação."
            )
        cnos = [dict(row) for row in query(
            """SELECT n.*,ac.contract_number ata_contract_number,
            ac.client ata_contract_client
            FROM contract_cnos n
            LEFT JOIN ata_contracts ac ON ac.id=n.ata_contract_id
            WHERE n.contract_id=? ORDER BY n.registration_date,n.id""",
            (cid,),
        )]
        if cnos:
            cno_display_rows = []
            for item in cnos:
                display_row = {
                    "Número de inscrição": item["registration_number"],
                    "Data de cadastramento": fmt_date(item["registration_date"]),
                    "Início da responsabilidade": fmt_date(
                        item["responsibility_start_date"]
                    ),
                    "Área de atuação da obra": item["work_area"],
                    "Observações": item["notes"],
                }
                if ata_cno_mode:
                    display_row["Contrato decorrente da ATA"] = (
                        ata_cno_labels.get(item.get("ata_contract_id"))
                        or "Não associado — revisar"
                    )
                cno_display_rows.append(display_row)
            cno_display = pd.DataFrame(cno_display_rows)
            modern_table(cno_display)
            for item in cnos:
                cno_context = (
                    f" · {ata_cno_labels.get(item.get('ata_contract_id'), 'sem contrato associado')}"
                    if ata_cno_mode else ""
                )
                with st.expander(
                    f"CNO {item['registration_number']}{cno_context} · documentos"
                ):
                    docs = [dict(row) for row in query(
                        "SELECT * FROM documents WHERE cno_id=? ORDER BY uploaded_at DESC",
                        (item["id"],),
                    )]
                    document_downloads(docs, f"cno_{item['id']}")
        elif cno_required:
            st.info("Nenhum CNO cadastrado para este contrato.")
        elif cnos:
            st.warning(
                "Existem registros históricos de CNO preservados. Para editar, anexar ou "
                "excluir, altere a definição acima para “Sim”."
            )
        if cno_required and (can_edit() or can_create()):
            if cnos:
                cno_columns = [
                    "id", "registration_number", "registration_date",
                    "responsibility_start_date", "work_area", "notes",
                ]
                cno_edit_df = pd.DataFrame(cnos)[cno_columns].copy()
                if ata_cno_mode:
                    cno_edit_df.insert(
                        2,
                        "ata_contract_reference",
                        [
                            ata_cno_labels.get(
                                item.get("ata_contract_id"),
                                "Não associado — revisar",
                            )
                            for item in cnos
                        ],
                    )
                for column in ("registration_date", "responsibility_start_date"):
                    cno_edit_df[column] = pd.to_datetime(
                        cno_edit_df[column], errors="coerce"
                    ).dt.date
                edited_cnos = st.data_editor(
                    cno_edit_df,
                    width="stretch",
                    hide_index=True,
                    disabled=["id"] if can_edit() else list(cno_edit_df.columns),
                    key=f"edit_cnos_{cid}",
                    column_config={
                        "id": st.column_config.NumberColumn("Código"),
                        "registration_number": st.column_config.TextColumn(
                            "Número de inscrição", required=True
                        ),
                        "ata_contract_reference": st.column_config.SelectboxColumn(
                            "Contrato decorrente da ATA",
                            options=list(ata_cno_labels.values()),
                            required=True,
                            width="large",
                        ),
                        "registration_date": st.column_config.DateColumn(
                            "Data de cadastramento", format="DD/MM/YYYY"
                        ),
                        "responsibility_start_date": st.column_config.DateColumn(
                            "Início da responsabilidade", format="DD/MM/YYYY"
                        ),
                        "work_area": st.column_config.TextColumn(
                            "Área de atuação da obra", width="large"
                        ),
                        "notes": st.column_config.TextColumn(
                            "Observações", width="large"
                        ),
                    },
                )
                if can_edit() and st.button("Salvar alterações dos CNOs"):
                    ata_id_by_label = {
                        label: ata_id for ata_id, label in ata_cno_labels.items()
                    }
                    invalid_ata_link = False
                    for _, row in edited_cnos.iterrows():
                        registration_number = str(
                            clean(row["registration_number"]) or ""
                        ).strip()
                        if not registration_number:
                            continue
                        ata_contract_id = None
                        if ata_cno_mode:
                            ata_contract_id = ata_id_by_label.get(
                                clean(row.get("ata_contract_reference"))
                            )
                            if not ata_contract_id:
                                invalid_ata_link = True
                                continue
                        execute(
                            """UPDATE contract_cnos SET registration_number=?,
                            registration_date=?,responsibility_start_date=?,work_area=?,
                            notes=?,ata_contract_id=?,updated_at=CURRENT_TIMESTAMP
                            WHERE id=? AND contract_id=?""",
                            (
                                registration_number,
                                clean(row["registration_date"]),
                                clean(row["responsibility_start_date"]),
                                clean(row["work_area"]),
                                clean(row["notes"]),
                                ata_contract_id,
                                int(row["id"]),
                                cid,
                            ),
                        )
                    if invalid_ata_link:
                        st.error(
                            "Selecione o contrato decorrente da ATA em todos os CNOs."
                        )
                    else:
                        log_action(user["id"], "EDITAR", "CNOs", cid)
                        st.success("Registros de CNO atualizados.")
                        rerun()
            with st.form("new_cno", clear_on_submit=True):
                selected_ata_contract_id = None
                if ata_cno_mode:
                    new_ata_options = {
                        "Selecione o contrato decorrente": None,
                        **{
                            label: ata_id
                            for ata_id, label in ata_cno_labels.items()
                        },
                    }
                    selected_ata_label = st.selectbox(
                        "Contrato decorrente da ATA *",
                        list(new_ata_options),
                    )
                    selected_ata_contract_id = new_ata_options[selected_ata_label]
                c1, c2, c3 = st.columns(3)
                cno_number = c1.text_input("Número de inscrição da obra *")
                cno_registration_date = c2.date_input(
                    "Data de cadastramento", value=None, format="DD/MM/YYYY"
                )
                cno_responsibility_start = c3.date_input(
                    "Início da responsabilidade", value=None, format="DD/MM/YYYY"
                )
                cno_work_area = st.text_area(
                    "Área de atuação da obra",
                    placeholder="Ex.: manutenção predial, reforma, instalações elétricas.",
                )
                cno_notes = st.text_area("Observações do CNO")
                if st.form_submit_button(
                    "Cadastrar CNO", disabled=not can_create()
                ):
                    if ata_cno_mode and not selected_ata_contract_id:
                        st.error(
                            "Selecione o contrato decorrente da ATA ao qual o CNO pertence."
                        )
                    elif cno_number.strip():
                        duplicate = query(
                            """SELECT id FROM contract_cnos
                            WHERE contract_id=? AND registration_number=? COLLATE NOCASE""",
                            (cid, cno_number.strip()),
                        )
                        if duplicate:
                            st.error("Este número de CNO já está cadastrado neste contrato.")
                        else:
                            cno_id = execute(
                                """INSERT INTO contract_cnos(
                                contract_id,ata_contract_id,registration_number,registration_date,
                                responsibility_start_date,work_area,notes)
                                VALUES(?,?,?,?,?,?,?)""",
                                (
                                    cid, selected_ata_contract_id, cno_number.strip(),
                                    cno_registration_date.isoformat()
                                    if cno_registration_date else None,
                                    cno_responsibility_start.isoformat()
                                    if cno_responsibility_start else None,
                                    cno_work_area, cno_notes,
                                ),
                            )
                            log_action(user["id"], "CRIAR", "CNO", cno_id, cno_number)
                            st.success("CNO cadastrado.")
                            rerun()
                    else:
                        st.error("Informe o número de inscrição da obra.")
            if cnos:
                cno_options = {
                    f"CNO {item['registration_number']}": item["id"] for item in cnos
                }
                with st.form("upload_cno_document", clear_on_submit=True):
                    cno_label = st.selectbox("CNO relacionado", cno_options)
                    cno_document_title = st.text_input(
                        "Título do documento", value="Comprovante do CNO"
                    )
                    cno_upload = st.file_uploader("Arquivo do CNO")
                    if st.form_submit_button(
                        "Anexar documento ao CNO", disabled=not can_create()
                    ) and cno_upload:
                        document_id = save_document(
                            cid, cno_upload, "CNO", cno_document_title,
                            cno_id=cno_options[cno_label],
                        )
                        log_action(
                            user["id"], "ANEXAR", "documento", document_id,
                            cno_upload.name,
                        )
                        st.success("Documento vinculado ao CNO.")
                        rerun()
        if cno_required and cnos and can_delete():
            cno_delete_options = {
                f"CNO {item['registration_number']}": item["id"] for item in cnos
            }
            cno_to_delete = st.selectbox(
                "CNO para excluir", cno_delete_options, key=f"delete_cno_select_{cid}"
            )
            confirm_cno_delete = st.checkbox(
                "Confirmo a exclusão deste CNO", key=f"confirm_cno_delete_{cid}"
            )
            if st.button(
                "Excluir CNO",
                disabled=not confirm_cno_delete,
                key=f"delete_cno_{cid}",
            ):
                cno_id = cno_delete_options[cno_to_delete]
                execute("UPDATE documents SET cno_id=NULL WHERE cno_id=?", (cno_id,))
                execute(
                    "DELETE FROM contract_cnos WHERE id=? AND contract_id=?",
                    (cno_id, cid),
                )
                log_action(user["id"], "EXCLUIR", "CNO", cno_id, cno_to_delete)
                st.success("CNO excluído; os documentos permanecem no histórico do contrato.")
                rerun()
    with tabs["Editar"]:
        if not can_edit():
            st.info("Seu perfil possui acesso somente para consulta.")
        else:
            with st.form("edit_contract"):
                c1, c2, c3 = st.columns(3)
                cost_center = c1.text_input("Centro de custo", contract["cost_center"] or "")
                contract_number = c2.text_input("Número do contrato", contract["contract_number"] or "")
                category = c3.selectbox(
                    "Modalidade", ["MANUTENÇÃO", "OBRA", "REFORMA", "ATA", "CONSÓRCIO", "OUTRO"],
                    index=["MANUTENÇÃO", "OBRA", "REFORMA", "ATA", "CONSÓRCIO", "OUTRO"].index(
                        contract["category"] if contract["category"] in
                        ["MANUTENÇÃO", "OBRA", "REFORMA", "ATA", "CONSÓRCIO", "OUTRO"] else "OUTRO"
                    ),
                )
                client = st.text_input("Órgão/contratante", contract["client"] or "")
                object_text = st.text_area("Objeto", contract["object"] or "")
                c1, c2, c3 = st.columns(3)
                bid_number = c1.text_input("Edital/licitação", contract["bid_number"] or "")
                process_number = c2.text_input(
                    "Número do processo", contract.get("process_number") or "",
                    help="Número do processo administrativo/licitatório de origem do contrato.",
                )
                uasg = c3.text_input("UASG", contract["uasg"] or "")
                procurement_method = st.text_input(
                    "Modalidade da licitação", contract["procurement_method"] or ""
                )
                c1, c2, c3 = st.columns(3)
                signature = c1.date_input(
                    "Assinatura",
                    value=date.fromisoformat(contract["signature_date"])
                    if contract["signature_date"] else None,
                    format="DD/MM/YYYY",
                )
                start = c2.date_input(
                    "Início da vigência",
                    value=date.fromisoformat(contract["start_date"])
                    if contract["start_date"] else None,
                    format="DD/MM/YYYY",
                )
                end = c3.date_input(
                    "Fim da vigência",
                    value=date.fromisoformat(contract["end_date"])
                    if contract["end_date"] else None,
                    format="DD/MM/YYYY",
                )
                c1, c2, c3 = st.columns(3)
                original_value_text = currency_input(
                    c1, "Valor original", contract["original_value"], f"edit_original_value_{cid}"
                )
                current_value_text = currency_input(
                    c2, "Valor atual", contract["current_value"], f"edit_current_value_{cid}"
                )
                status = c3.selectbox(
                    "Status", ["ATIVO", "SUSPENSO", "ENCERRADO", "EM TRANSIÇÃO", "OUTRO"],
                    index=["ATIVO", "SUSPENSO", "ENCERRADO", "EM TRANSIÇÃO", "OUTRO"].index(
                        contract["status"] if contract["status"] in
                        ["ATIVO", "SUSPENSO", "ENCERRADO", "EM TRANSIÇÃO", "OUTRO"] else "OUTRO"
                    ),
                )
                tax_regime = st.selectbox(
                    "Regime de faturamento",
                    ["NÃO DEFINIDO", "ONERADO", "DESONERADO"],
                    index=_option_index(
                        ["NÃO DEFINIDO", "ONERADO", "DESONERADO"],
                        str(contract.get("tax_regime") or "NÃO DEFINIDO"),
                    ),
                    format_func=lambda option: BDI_REGIME_LABELS[option],
                )
                c1, c2 = st.columns(2)
                engineer_name = c1.text_input("Engenheiro responsável", contract["engineer_name"] or "")
                engineer_email = c2.text_input("E-mail do engenheiro", contract["engineer_email"] or "")
                manager_name = c1.text_input("Responsável administrativo", contract["manager_name"] or "")
                manager_email = c2.text_input("E-mail administrativo", contract["manager_email"] or "")
                c1, c2 = st.columns(2)
                repactuation = c1.date_input(
                    "Próxima repactuação",
                    value=date.fromisoformat(contract["repactuation_date"])
                    if contract["repactuation_date"] else None,
                    format="DD/MM/YYYY",
                )
                c2.info(
                    "Vigências de garantias e seguros são controladas na aba dedicada."
                )
                observations = st.text_area("Observações gerais", contract["observations"] or "")
                if st.form_submit_button("Salvar alterações"):
                    try:
                        original_value = parse_brl_input(original_value_text)
                        current_value = parse_brl_input(current_value_text)
                    except ValueError:
                        st.error("Informe os valores no padrão brasileiro, por exemplo: R$ 18.740.995,83.")
                    else:
                        newly_formalized = not contract["formalized"] and bool(contract_number.strip())
                        formalized = 1 if (contract["formalized"] or contract_number.strip()) else 0
                        execute(
                            """UPDATE contracts SET cost_center=?,contract_number=?,category=?,client=?,object=?,
                            bid_number=?,process_number=?,uasg=?,procurement_method=?,signature_date=?,start_date=?,end_date=?,
                            original_value=?,current_value=?,status=?,tax_regime=?,manager_name=?,manager_email=?,
                            engineer_name=?,engineer_email=?,repactuation_date=?,
                            observations=?,formalized=?,updated_at=CURRENT_TIMESTAMP WHERE id=?""",
                            (
                             cost_center, contract_number, category,
                             normalize_agency_name(client), object_text, bid_number, process_number, uasg,
                             procurement_method, signature.isoformat() if signature else None,
                             start.isoformat() if start else None, end.isoformat() if end else None,
                             original_value, current_value, status, tax_regime,
                             manager_name, manager_email,
                             engineer_name, engineer_email,
                             repactuation.isoformat() if repactuation else None,
                             observations, formalized, cid),
                        )
                        refresh_contract_lifecycle(cid)
                        log_action(
                            st.session_state.user["id"], "EDITAR", "contrato", cid,
                            contract["cost_center"],
                        )
                        st.session_state["data_review_success_notice"] = True
                        if newly_formalized:
                            st.success("Contrato formalizado e incluído na carteira.")
                        else:
                            st.success("Contrato atualizado.")
                        rerun()
            render_budget_dates_editor(cid)
            st.divider()
            if contract["archived"]:
                if st.button("Restaurar contrato para a carteira ativa"):
                    execute(
                        "UPDATE contracts SET archived=0,archived_at=NULL,archived_by=NULL,status='ATIVO' WHERE id=?",
                        (cid,),
                    )
                    log_action(user["id"], "RESTAURAR", "contrato", cid, contract["cost_center"])
                    st.success("Contrato restaurado.")
                    rerun()
            else:
                confirm = st.checkbox("Confirmo que o contrato foi encerrado e deve ser arquivado")
                if st.button("Arquivar contrato finalizado", disabled=not confirm):
                    execute(
                        """UPDATE contracts SET archived=1,archived_at=CURRENT_TIMESTAMP,
                        archived_by=?,status='ENCERRADO' WHERE id=?""",
                        (user["id"], cid),
                    )
                    log_action(user["id"], "ARQUIVAR", "contrato", cid, contract["cost_center"])
                    st.success("Contrato arquivado. O histórico e os arquivos foram preservados.")
                    rerun()
        if can_delete():
            st.divider()
            st.error(
                "Zona de exclusão autorizada: remove definitivamente o contrato e os "
                "registros vinculados."
            )
            delete_confirmation = st.text_input(
                f"Digite o centro de custo {contract['cost_center']} para confirmar a exclusão",
                key=f"delete_contract_{cid}",
            )
            if st.button(
                "Excluir contrato definitivamente",
                disabled=delete_confirmation.strip() != str(contract["cost_center"]).strip(),
            ):
                source_folder = UPLOAD_DIR / str(cid)
                if source_folder.exists():
                    trash_folder = UPLOAD_DIR.parent / "trash"
                    trash_folder.mkdir(parents=True, exist_ok=True)
                    shutil.move(
                        str(source_folder),
                        str(trash_folder / f"contrato_{cid}_{uuid.uuid4().hex}"),
                    )
                execute("DELETE FROM contracts WHERE id=?", (cid,))
                log_action(
                    user["id"], "EXCLUIR DEFINITIVAMENTE", "contrato", cid,
                    contract["cost_center"],
                )
                st.success(
                    "Contrato excluído. Os arquivos foram movidos para a pasta de recuperação trash."
                )
                rerun()


CONTRACT_CATEGORY_BY_COST_CENTER_CODE = {
    "01": "OUTRO",
    "02": "MANUTENÇÃO",
    "03": "OBRA",
    "04": "REFORMA",
    "05": "ATA",
    "06": "CONSÓRCIO",
}
COST_CENTER_CODE_BY_CATEGORY = {
    category: code for code, category in CONTRACT_CATEGORY_BY_COST_CENTER_CODE.items()
}


def suggested_category_from_cost_center(cost_center):
    """Sugere a Modalidade a partir do padrão do centro de custo da
    empresa (XX.YY.ZZZZZ, onde YY define a modalidade — ex.: 01.02.00176
    é MANUTENÇÃO). Mesma regra da planilha de referência do RH/financeiro
    — devolve None quando o padrão não é reconhecido, para nunca travar
    um centro de custo em formato diferente."""
    code = (cost_center or "")[3:5]
    return CONTRACT_CATEGORY_BY_COST_CENTER_CODE.get(code)


def next_cost_center_for_category(category):
    """Gera o próximo centro de custo disponível para a modalidade
    escolhida, seguindo o padrão fixo 01.YY.ZZZZZ (YY = código da
    modalidade, ZZZZZ = sequência com 5 dígitos). Considera TODOS os
    centros de custo já usados com aquele código — inclusive os ainda não
    formalizados — para nunca repetir um número já reservado."""
    code = COST_CENTER_CODE_BY_CATEGORY.get(category, "01")
    rows = query(
        "SELECT cost_center FROM contracts WHERE substr(cost_center,4,2)=?", (code,)
    )
    max_seq = 0
    for row in rows:
        match = re.match(r"^01\.\d{2}\.(\d+)$", str(row["cost_center"] or "").strip())
        if match:
            max_seq = max(max_seq, int(match.group(1)))
    return f"01.{code}.{max_seq + 1:05d}"


def load_known_contract_people():
    """Consolida nomes e e-mails de engenheiros responsáveis e
    responsáveis administrativos já usados em contratos anteriores —
    mesmo espírito dos perfis de profissionais de ART: à medida que
    novos nomes são digitados ao cadastrar um contrato, eles já ficam
    disponíveis como sugestão nos próximos cadastros, sem precisar de
    uma tela separada de cadastro de engenheiros."""
    rows = query(
        """SELECT engineer_name AS name, engineer_email AS email FROM contracts
        WHERE engineer_name IS NOT NULL AND TRIM(engineer_name) != ''
        UNION
        SELECT manager_name AS name, manager_email AS email FROM contracts
        WHERE manager_name IS NOT NULL AND TRIM(manager_name) != ''"""
    )
    people = {}
    for row in rows:
        name = (row["name"] or "").strip()
        if not name:
            continue
        key = name.upper()
        if key not in people or (row["email"] and not people[key]["email"]):
            people[key] = {"name": name, "email": (row["email"] or "").strip()}
    return sorted(people.values(), key=lambda p: p["name"])


def page_new_contract():
    st.title("Novo contrato")
    st.caption("Cadastre o contrato, seus responsáveis, sindicatos, datas-base e composição inicial da equipe.")
    if not can_create():
        st.info(
            "Seu perfil pode consultar a carteira, mas não possui permissão de "
            "lançamento para cadastrar novos contratos."
        )
        return
    with st.expander("Como funciona o centro de custo automático", expanded=False):
        st.caption(
            "O centro de custo segue o padrão 01.YY.ZZZZZ, em que YY define a modalidade: "
            "01 → Outro, 02 → Manutenção, 03 → Obra, 04 → Reforma, 05 → ATA, 06 → Consórcio. "
            "Ao escolher a modalidade abaixo, o centro de custo já é gerado automaticamente, "
            "seguindo a sequência existente para aquele código — normalmente antes mesmo de o "
            "contrato ser assinado, quando ainda não há número de contrato. Marque \"digitar "
            "manualmente\" só se este caso não seguir o padrão."
        )
    category_options = ["MANUTENÇÃO", "OBRA", "REFORMA", "ATA", "CONSÓRCIO", "OUTRO"]
    manual_cost_center = st.checkbox(
        "Digitar centro de custo manualmente (em vez de gerar automaticamente pela modalidade)",
        key="new_contract_manual_cc",
    )
    cc1, cc2 = st.columns(2)
    if manual_cost_center:
        cost_center = cc1.text_input("Centro de custo *", key="new_contract_cost_center")
        suggested_category = suggested_category_from_cost_center(cost_center)
        category = cc2.selectbox(
            "Modalidade", category_options,
            index=category_options.index(suggested_category) if suggested_category in category_options else 0,
            key=f"new_contract_category_{re.sub(r'[^0-9]', '', cost_center)[:5] or 'manual'}",
            help="Sugerida automaticamente a partir do centro de custo digitado ao lado — "
            "pode ser trocada manualmente a qualquer momento.",
        )
    else:
        category = cc1.selectbox("Modalidade", category_options, key="new_contract_category_auto")
        cost_center = next_cost_center_for_category(category)
        cc2.text_input(
            "Centro de custo (gerado automaticamente)", value=cost_center, disabled=True,
            key=f"new_contract_cost_center_display_{category}",
        )

    known_people = load_known_contract_people()
    people_options = {"Cadastrar novo": None}
    people_options.update({f"{p['name']} · {p['email'] or 's/ e-mail'}": p for p in known_people})
    ep1, ep2 = st.columns(2)
    engineer_pick_label = ep1.selectbox(
        "Engenheiro responsável — selecionar já cadastrado", list(people_options),
        key="new_contract_engineer_pick",
        help="Escolha um nome já usado em outro contrato para preencher o e-mail sozinho, ou "
        "\"Cadastrar novo\" para digitar um engenheiro que ainda não está na lista — a partir "
        "daí ele já fica disponível para os próximos contratos.",
    )
    if people_options[engineer_pick_label] and st.session_state.get("new_contract_engineer_applied") != engineer_pick_label:
        st.session_state["new_contract_engineer_name"] = people_options[engineer_pick_label]["name"]
        st.session_state["new_contract_engineer_email"] = people_options[engineer_pick_label]["email"]
        st.session_state["new_contract_engineer_applied"] = engineer_pick_label
        rerun()
    manager_pick_label = ep2.selectbox(
        "Responsável administrativo — selecionar já cadastrado", list(people_options),
        key="new_contract_manager_pick",
        help="Mesma lista de pessoas já usadas em outros contratos, para o responsável "
        "administrativo (pode ser a mesma pessoa do engenheiro, ou não).",
    )
    if people_options[manager_pick_label] and st.session_state.get("new_contract_manager_applied") != manager_pick_label:
        st.session_state["new_contract_manager_name"] = people_options[manager_pick_label]["name"]
        st.session_state["new_contract_manager_email"] = people_options[manager_pick_label]["email"]
        st.session_state["new_contract_manager_applied"] = manager_pick_label
        rerun()

    procurement_method = selectbox_with_custom_option(
        "Modalidade da licitação", BID_MODALITIES, "new_contract_procurement_method",
        help="Mesma lista de modalidades da Lei 14.133/2021 usada no menu Licitações, com "
        "espaço para digitar uma modalidade diferente.",
    )

    with st.expander("BDI (opcional)", expanded=False):
        st.caption(
            "Mesma composição usada na aba BDI da ficha do contrato — preenchendo aqui, "
            "já sai calculada e detalhada (por item) no e-mail de anúncio. Deixe a "
            "identificação em branco para não cadastrar nenhum BDI agora; dá para "
            "cadastrar mais de um depois, na própria ficha."
        )
        new_contract_bdi, new_contract_bdi_error = bdi_input_fields("new_contract_bdi")

    with st.form("new_contract"):
        c1, c2 = st.columns(2)
        contract_number = c1.text_input(
            "Número do contrato",
            help="Pode ficar em branco quando o centro de custo é reservado antes da "
            "assinatura — o contrato fica como pré-contrato (fora da carteira) até o "
            "número ser preenchido aqui ou na Ficha do Contrato.",
        )
        client = c2.text_input("Órgão/contratante *")
        object_text = st.text_area("Objeto")
        object_identifier = st.text_input(
            "Identificação do objeto (para o assunto do e-mail)",
            placeholder="Ex.: VRF, Manutenção Predial, Obra de Restauro",
            help="Um termo curto que identifique o tipo de objeto — usado no assunto do "
            "e-mail de anúncio e dos avisos de providências deste contrato.",
        )
        c1, c2 = st.columns(2)
        bid_number = c1.text_input("Edital/licitação", help="Número do certame (pregão eletrônico etc.).")
        process_number = c2.text_input(
            "Número do processo",
            help="Número do processo administrativo/licitatório de origem do contrato.",
        )
        uasg = st.text_input("UASG")
        c1, c2, c3 = st.columns(3)
        signature = c1.date_input("Assinatura", value=None, format="DD/MM/YYYY")
        start = c2.date_input("Início da vigência", value=None, format="DD/MM/YYYY")
        end = c3.date_input("Fim da vigência", value=None, format="DD/MM/YYYY")
        c1, c2, c3 = st.columns(3)
        original_value = c1.number_input(
            "Valor original", min_value=0.0, format="%.2f",
            help="No cadastro inicial, este valor também será utilizado como valor atual.",
        )
        c2.metric(
            "Valor atual inicial",
            brl(original_value),
            help="Sem aditivos, o valor vigente é automaticamente igual ao valor original.",
        )
        current_value = original_value
        budget_date = c3.date_input(
            "Data do orçamento", value=None, format="DD/MM/YYYY"
        )
        tax_regime = st.selectbox(
            "Regime de faturamento",
            ["NÃO DEFINIDO", "ONERADO", "DESONERADO"],
            format_func=lambda option: BDI_REGIME_LABELS[option],
        )
        c1, c2 = st.columns(2)
        engineer_name = c1.text_input("Engenheiro responsável", key="new_contract_engineer_name")
        engineer_email = c2.text_input("E-mail do engenheiro", key="new_contract_engineer_email")
        manager_name = c1.text_input("Responsável administrativo", key="new_contract_manager_name")
        manager_email = c2.text_input("E-mail do responsável", key="new_contract_manager_email")
        c1, c2 = st.columns(2)
        repactuation = c1.date_input(
            "Próxima repactuação geral", value=None, format="DD/MM/YYYY"
        )
        budget_description = c2.text_input(
            "Referência da data do orçamento",
            placeholder="Ex.: orçamento contratual inicial",
        )
        st.markdown("#### Garantia (opcional)")
        st.caption(
            "Preenchendo aqui, o valor exigido de garantia já sai calculado — e continua "
            "editável depois na aba Garantias e seguros da ficha do contrato."
        )
        c1, c2 = st.columns(2)
        guarantee_percent = c1.number_input(
            "Garantia contratual (%)", min_value=0.0, max_value=100.0, format="%.2f",
            help="Percentual aplicado sobre o valor do contrato (campo \"Valor original\" acima).",
        )
        additional_guarantee_applies = c2.checkbox(
            "Exige garantia adicional (obras/serviços de engenharia)",
            help="Lei nº 14.133/2021, art. 59, § 5º — deixe desmarcado quando não se aplicar; "
            "o sistema já registra a dispensa com a base legal correspondente.",
        )
        additional_guarantee_estimated = st.number_input(
            "Valor estimado da licitação (para a garantia adicional)", min_value=0.0, format="%.2f",
            help="Só é usado quando a garantia adicional acima está marcada — o valor exigido "
            "é a diferença entre o estimado e o valor do contrato.",
        )
        st.markdown("#### Anexos do certame (opcional)")
        c1, c2 = st.columns(2)
        edital_upload = c1.file_uploader("Edital")
        tr_upload = c2.file_uploader("Termo de Referência")
        c1, c2 = st.columns(2)
        spreadsheet_upload = c1.file_uploader("Planilha")
        proposal_upload = c2.file_uploader("Proposta homologada")
        st.markdown("#### Sindicatos e datas-base iniciais")
        union_rows = st.data_editor(
            pd.DataFrame(columns=[
                "Sindicato", "CCT", "Categoria", "Mês data-base", "Próxima repactuação", "Observações"
            ]),
            num_rows="dynamic", width="stretch", hide_index=True, key="new_contract_unions",
        )
        st.markdown("#### Equipe e cargos iniciais")
        position_rows = st.data_editor(
            pd.DataFrame({
                "Cargo": pd.Series(dtype="str"),
                "Quantidade": pd.Series(dtype="int64"),
                "Salário-base": pd.Series(dtype="str"),
                "Periculosidade (%)": pd.Series(dtype="float64"),
                "Insalubridade (%)": pd.Series(dtype="float64"),
                "Ano-base insalubridade": pd.Series(dtype="int64"),
                "Sindicato": pd.Series(dtype="str"),
            }),
            num_rows="dynamic", width="stretch", hide_index=True, key="new_contract_positions",
            column_config={
                "Cargo": st.column_config.TextColumn("Cargo/função", required=True),
                "Quantidade": st.column_config.NumberColumn(
                    "Quantidade", min_value=1, step=1, default=1
                ),
                "Salário-base": st.column_config.TextColumn(
                    "Salário-base",
                    default="R$ 0,00",
                    help="Informe no padrão brasileiro, por exemplo: R$ 4.250,00.",
                ),
                "Periculosidade (%)": st.column_config.NumberColumn(
                    "Periculosidade (%)", min_value=0.0, max_value=100.0, step=0.01
                ),
                "Insalubridade (%)": st.column_config.NumberColumn(
                    "Insalubridade (%)", min_value=0.0, max_value=100.0, step=0.01
                ),
                "Ano-base insalubridade": st.column_config.NumberColumn(
                    "Ano-base insalubridade", min_value=2000, max_value=2100, step=1
                ),
                "Sindicato": st.column_config.TextColumn("Sindicato"),
            },
        )
        observations = st.text_area("Observações")
        contract_document_upload = st.file_uploader(
            "Documento do contrato assinado (opcional)",
            help="Se anexado agora, já fica salvo na ficha do contrato e é enviado por "
            "e-mail junto com o aviso de providências iniciais (garantia contratual e "
            "ART), quando houver responsável cadastrado para isso.",
        )
        if st.form_submit_button("Cadastrar contrato", width="stretch"):
            if not cost_center.strip() or not client.strip():
                st.error("Preencha centro de custo e contratante.")
            else:
                formalized = 1 if contract_number.strip() else 0
                try:
                    cid = execute(
                        """INSERT INTO contracts(cost_center,client,contract_number,category,object,
                        object_identifier,bid_number,
                        process_number,uasg,procurement_method,signature_date,start_date,end_date,original_value,current_value,
                        manager_name,manager_email,engineer_name,engineer_email,
                        repactuation_date,observations,tax_regime,formalized,status)
                        VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,'ATIVO')""",
                        (
                         cost_center.strip(), normalize_agency_name(client),
                         contract_number.strip() or None, category, object_text,
                         object_identifier.strip() or None,
                         bid_number, process_number, uasg, procurement_method,
                         signature.isoformat() if signature else None, start.isoformat() if start else None,
                         end.isoformat() if end else None, original_value, current_value,
                         manager_name, manager_email, engineer_name, engineer_email,
                         repactuation.isoformat() if repactuation else None,
                         observations, tax_regime, formalized),
                    )
                    if budget_date:
                        execute(
                            """INSERT INTO contract_budget_dates(
                            contract_id,reference_date,description) VALUES(?,?,?)""",
                            (
                                cid, budget_date.isoformat(),
                                budget_description.strip() or "Orçamento contratual inicial",
                            ),
                        )
                    union_ids = {}
                    for _, row in union_rows.fillna("").iterrows():
                        union_name = str(row.get("Sindicato", "")).strip()
                        if not union_name:
                            continue
                        try:
                            base_month = int(float(row.get("Mês data-base") or 0)) or None
                        except (TypeError, ValueError):
                            base_month = None
                        uid = execute(
                            """INSERT INTO contract_unions(contract_id,union_name,collective_agreement,
                            category_name,base_month,next_repactuation,notes) VALUES(?,?,?,?,?,?,?)""",
                            (cid, union_name, str(row.get("CCT", "")), str(row.get("Categoria", "")),
                             base_month, str(row.get("Próxima repactuação", "")) or None,
                             str(row.get("Observações", ""))),
                        )
                        union_ids[union_name.casefold()] = uid
                    for _, row in position_rows.fillna("").iterrows():
                        title = str(row.get("Cargo", "")).strip()
                        if not title:
                            continue
                        def numeric(name, default=0):
                            try:
                                return parse_brazilian_number(row.get(name), default)
                            except ValueError:
                                return default
                        union_id = union_ids.get(str(row.get("Sindicato", "")).strip().casefold())
                        execute(
                            """INSERT INTO contract_positions(contract_id,title,quantity,base_salary,
                            hazard_percent,unhealthy_percent,unhealthy_base_year,union_id)
                            VALUES(?,?,?,?,?,?,?,?)""",
                            (cid, title, int(numeric("Quantidade", 1)), numeric("Salário-base"),
                             numeric("Periculosidade (%)"), numeric("Insalubridade (%)"),
                             int(numeric("Ano-base insalubridade", today_brt().year)), union_id),
                        )
                    log_action(user["id"], "CRIAR", "contrato", cid, cost_center)
                    if guarantee_percent > 0 or additional_guarantee_applies:
                        required_amount = calculate_required_amount(
                            "PERCENTUAL_BASE", calculation_base=original_value,
                            percentage=guarantee_percent,
                        )
                        execute(
                            """INSERT INTO contract_guarantees(
                            contract_id,guarantee_type,instrument_scope,legal_basis,
                            calculation_method,calculation_base,percentage,required_amount)
                            VALUES(?,?,?,?,?,?,?,?)""",
                            (
                                cid, "GARANTIA CONTRATUAL", "CONTRATO INICIAL",
                                default_legal_basis("GARANTIA CONTRATUAL"),
                                "PERCENTUAL_BASE", original_value, guarantee_percent,
                                required_amount,
                            ),
                        )
                        if additional_guarantee_applies:
                            additional_required = calculate_required_amount(
                                "GARANTIA_ADICIONAL", estimated_budget=additional_guarantee_estimated,
                                proposal_value=original_value,
                            )
                            execute(
                                """INSERT INTO contract_guarantees(
                                contract_id,guarantee_type,instrument_scope,legal_basis,
                                calculation_method,estimated_budget,proposal_value,required_amount)
                                VALUES(?,?,?,?,?,?,?,?)""",
                                (
                                    cid, "GARANTIA ADICIONAL", "CONTRATO INICIAL",
                                    default_legal_basis("GARANTIA ADICIONAL"),
                                    "GARANTIA_ADICIONAL", additional_guarantee_estimated,
                                    original_value, additional_required,
                                ),
                            )
                        else:
                            execute(
                                """INSERT INTO contract_guarantees(
                                contract_id,guarantee_type,instrument_scope,legal_basis,
                                calculation_method,request_status,notes)
                                VALUES(?,?,?,?,?,?,?)""",
                                (
                                    cid, "GARANTIA ADICIONAL", "CONTRATO INICIAL",
                                    default_legal_basis("GARANTIA ADICIONAL"),
                                    "GARANTIA_ADICIONAL", "DISPENSADA",
                                    "Não se aplica a este contrato.",
                                ),
                            )
                    if (
                        not new_contract_bdi_error
                        and new_contract_bdi.get("name")
                        and new_contract_bdi.get("reference_name")
                    ):
                        bdi_placeholders = ",".join("?" for _ in BDI_DB_FIELDS)
                        execute(
                            f"""INSERT INTO contract_bdis(contract_id,{','.join(BDI_DB_FIELDS)})
                            VALUES(?,{bdi_placeholders})""",
                            (cid,) + tuple(new_contract_bdi[field] for field in BDI_DB_FIELDS),
                        )
                    for upload, doc_category, doc_title in (
                        (edital_upload, "EDITAL", "Edital"),
                        (tr_upload, "TERMO DE REFERÊNCIA", "Termo de Referência"),
                        (spreadsheet_upload, "PLANILHA", "Planilha"),
                        (proposal_upload, "PROPOSTA HOMOLOGADA", "Proposta homologada"),
                    ):
                        if upload:
                            save_document(cid, upload, doc_category, doc_title)
                    document_bytes = document_filename = None
                    if contract_document_upload:
                        save_document(
                            cid, contract_document_upload, "CONTRATO",
                            "Contrato assinado",
                        )
                        document_bytes = contract_document_upload.getvalue()
                        document_filename = contract_document_upload.name
                    notified = []
                    if formalized:
                        if category == "ATA":
                            # A ATA em si não gera garantia contratual nem ART — isso só
                            # passa a valer para os contratos decorrentes dela, quando
                            # forem cadastrados e assinados (fluxo normal, mais abaixo).
                            notified = notify_ata_registration(
                                cost_center=cost_center.strip(),
                                client=normalize_agency_name(client),
                                contract_number=contract_number.strip(),
                                extra_recipients=[engineer_email, manager_email],
                            )
                        else:
                            notified = notify_contract_task_needs(
                                contract_id=cid, amendment_id=None, kind_label="CONTRATO",
                                ordinal=None, cost_center=cost_center.strip(),
                                client=normalize_agency_name(client), contract_number=contract_number.strip(),
                                document_bytes=document_bytes, document_filename=document_filename,
                                extra_recipients=[engineer_email, manager_email],
                            )
                    for reset_key in (
                        "new_contract_engineer_pick", "new_contract_manager_pick",
                        "new_contract_engineer_applied", "new_contract_manager_applied",
                        "new_contract_engineer_name", "new_contract_engineer_email",
                        "new_contract_manager_name", "new_contract_manager_email",
                        "new_contract_cost_center",
                        "new_contract_procurement_method_select", "new_contract_procurement_method_custom",
                    ):
                        st.session_state.pop(reset_key, None)
                    if formalized:
                        success_message = "Contrato, sindicatos e equipe cadastrados. Complete os demais dados na Ficha do Contrato."
                        if notified and category == "ATA":
                            success_message += (
                                f" Aviso de novo centro de custo de ATA enviado para "
                                f"{len(notified)} destinatário(s) (sem cobrança de garantia/ART "
                                "neste momento)."
                            )
                        elif notified:
                            success_message += (
                                f" Aviso de providências iniciais enviado para "
                                f"{len(notified)} responsável(is)."
                            )
                    else:
                        success_message = (
                            f"Centro de custo {cost_center.strip()} reservado como pré-contrato "
                            "(fora da carteira até o número do contrato ser preenchido). Vá em "
                            "\"Pré-contratos\" para revisar e enviar o e-mail de anúncio."
                        )
                    st.success(success_message)
                except Exception:
                    st.error("Não foi possível cadastrar. Verifique se o centro de custo já existe.")


def page_precontracts():
    st.title("Pré-contratos")
    st.caption(
        "Centros de custo já reservados, aguardando a formalização do contrato (número do "
        "contrato ainda não preenchido). Ficam fora da carteira ativa até serem formalizados "
        "— preencha o número na Ficha do Contrato para incluí-los na carteira."
    )
    if can_edit():
        with st.expander("E-mails de anúncio (destinatários fixos)"):
            st.caption(
                "Lista reaproveitada em todos os envios do e-mail de anúncio de contrato "
                "vencido — cadastre uma vez e vá incluindo novos endereços conforme necessário."
            )
            recipients = [
                dict(row) for row in query(
                    "SELECT * FROM new_contract_announcement_recipients ORDER BY active DESC,email"
                )
            ]
            if recipients:
                modern_table(pd.DataFrame([{
                    "E-mail": row["email"],
                    "Status": "ATIVO" if row["active"] else "INATIVO",
                } for row in recipients]))
                remove_options = {row["email"]: row["id"] for row in recipients}
                rc1, rc2 = st.columns([3, 1])
                remove_label = rc1.selectbox(
                    "E-mail para pausar/reativar ou remover", remove_options,
                    key="announcement_recipient_target",
                )
                target_id = remove_options[remove_label]
                target_row = next(r for r in recipients if r["id"] == target_id)
                with rc2:
                    st.write("")
                    st.write("")
                    if st.button(
                        "Pausar" if target_row["active"] else "Reativar",
                        key="toggle_announcement_recipient",
                    ):
                        execute(
                            "UPDATE new_contract_announcement_recipients SET active=? WHERE id=?",
                            (0 if target_row["active"] else 1, target_id),
                        )
                        rerun()
                if st.button("Remover este e-mail definitivamente", key="delete_announcement_recipient"):
                    execute(
                        "DELETE FROM new_contract_announcement_recipients WHERE id=?", (target_id,)
                    )
                    log_action(
                        user["id"], "REMOVER", "destinatário de anúncio de contrato",
                        target_id, remove_label,
                    )
                    st.success("E-mail removido.")
                    rerun()
            else:
                st.info("Nenhum e-mail cadastrado ainda.")
            with st.form("new_announcement_recipient", clear_on_submit=True):
                new_email = st.text_input("Adicionar e-mail")
                if st.form_submit_button("Adicionar"):
                    normalized = new_email.strip().lower()
                    if not re.fullmatch(r"[^\s@]+@[^\s@]+\.[^\s@]+", normalized):
                        st.error("Informe um endereço de e-mail válido.")
                    else:
                        try:
                            execute(
                                "INSERT INTO new_contract_announcement_recipients(email) VALUES(?)",
                                (normalized,),
                            )
                            log_action(
                                user["id"], "CADASTRAR", "destinatário de anúncio de contrato",
                                None, normalized,
                            )
                            st.success("E-mail cadastrado.")
                            rerun()
                        except Exception:
                            st.error("Este e-mail já está cadastrado.")

    precontracts = load_contracts("WHERE c.formalized=0")
    if not precontracts:
        st.info("Nenhum pré-contrato pendente no momento.")
        return

    for item in precontracts:
        with st.container(border=True):
            st.markdown(f"##### {item['cost_center']} · {item['client']}")
            cols = st.columns(4)
            cols[0].metric("Modalidade", item["category"] or "—")
            cols[1].metric("Identificação", item.get("object_identifier") or "—")
            cols[2].metric("Criado em", fmt_date(item.get("created_at")))
            with cols[3]:
                st.write("")
                st.button(
                    "Abrir ficha", key=f"open_precontract_{item['id']}",
                    on_click=open_precontract_ficha, args=(item["id"],),
                )
            if item.get("object"):
                st.caption(item["object"])
            if not can_edit():
                continue
            with st.expander("Preparar e-mail de anúncio"):
                subject, body, html_body = build_announcement_email(item["id"])
                edited_subject = st.text_input(
                    "Assunto", value=subject, key=f"announcement_subject_{item['id']}",
                )
                edited_body = st.text_area(
                    "Corpo do e-mail (texto simples)", value=body, height=240,
                    key=f"announcement_body_{item['id']}",
                    help="É este texto que fica editável antes do envio. A tabela de "
                    "garantia e BDI abaixo é só uma prévia de como sai formatada no "
                    "e-mail (calculada a partir dos dados cadastrados) — para corrigir "
                    "algum número dela, ajuste na aba Garantias ou BDI da ficha do "
                    "contrato e reabra este e-mail.",
                )
                has_guarantee = query(
                    "SELECT 1 FROM contract_guarantees WHERE contract_id=? AND amendment_id IS NULL "
                    "AND ata_contract_id IS NULL LIMIT 1",
                    (item["id"],),
                )
                has_bdi = query(
                    "SELECT 1 FROM contract_bdis WHERE contract_id=? LIMIT 1", (item["id"],)
                )
                if not has_guarantee and not has_bdi:
                    st.warning(
                        "Nenhuma garantia contratual/adicional ou composição de BDI cadastrada "
                        "para este pré-contrato — a seção \"Informações adicionais\" vai sair "
                        "vazia no e-mail. Se for o caso, cadastre pela aba Garantias ou BDI na "
                        "Ficha do Contrato (botão \"Abrir ficha\" acima) e volte aqui para "
                        "reabrir o e-mail com os dados atualizados."
                    )
                st.caption("Prévia da tabela de garantia e BDI (como chega no e-mail):")
                st.markdown(html_body, unsafe_allow_html=True)
                attachments_available = announcement_attachments_available(item["id"])
                selected_attachments = []
                if attachments_available:
                    for doc in attachments_available:
                        stored_name = Path(str(doc["stored_path"]).replace("\\", "/")).name
                        doc_path = portable_project_path(
                            doc["stored_path"], UPLOAD_DIR / str(doc["contract_id"]) / stored_name,
                        )
                        doc["_size_bytes"] = doc_path.stat().st_size if doc_path.exists() else 0
                    attachment_options = {
                        f"{doc['title']} · {doc['filename']} "
                        f"({doc['_size_bytes'] / (1024 * 1024):.1f} MB)": doc
                        for doc in attachments_available
                    }
                    picked = st.multiselect(
                        "Anexos do certame para incluir neste envio", list(attachment_options),
                        default=list(attachment_options),
                        key=f"announcement_attachments_{item['id']}",
                        help="Desmarcar aqui só afeta este envio — o arquivo continua salvo no "
                        "pré-contrato. Para removê-lo definitivamente, use \"Excluir anexo do "
                        "certame\" logo abaixo.",
                    )
                    selected_attachments = [attachment_options[label] for label in picked]
                    selected_size_mb = sum(
                        doc["_size_bytes"] for doc in selected_attachments
                    ) / (1024 * 1024)
                    limit_mb = MAX_ATTACHMENTS_BYTES / (1024 * 1024)
                    if selected_size_mb > limit_mb:
                        st.error(
                            f"Anexos selecionados somam {selected_size_mb:.1f} MB, acima "
                            f"do limite de {limit_mb:.0f} MB — o servidor de e-mail rejeita "
                            "mensagens muito grandes. Desmarque ou exclua algum anexo antes de "
                            "enviar (mais de um anexo é compactado em .zip automaticamente, "
                            "mas isso raramente reduz arquivos que já são PDF/imagem)."
                        )
                    elif selected_attachments:
                        st.caption(f"Anexos selecionados: {selected_size_mb:.1f} MB no total.")
                    with st.expander("Baixar ou excluir anexo do certame"):
                        document_downloads(
                            attachments_available, key_prefix=f"precontract_announcement_{item['id']}"
                        )
                else:
                    st.caption("Nenhum anexo do certame salvo para este pré-contrato.")
                active_recipients = [
                    row["email"] for row in query(
                        "SELECT email FROM new_contract_announcement_recipients WHERE active=1 ORDER BY email"
                    )
                ]
                if not active_recipients:
                    st.warning("Cadastre ao menos um e-mail de anúncio acima antes de enviar.")
                announcement_cc = [item.get("engineer_email"), item.get("manager_email")]
                if any(announcement_cc):
                    st.caption(
                        "Recebem cópia automaticamente: "
                        + ", ".join(email for email in announcement_cc if email)
                    )
                if st.button(
                    "Enviar e-mail de anúncio", key=f"send_announcement_{item['id']}",
                    disabled=not active_recipients,
                ):
                    attachment_payload = []
                    for doc in selected_attachments:
                        stored_name = Path(str(doc["stored_path"]).replace("\\", "/")).name
                        doc_path = portable_project_path(
                            doc["stored_path"], UPLOAD_DIR / str(doc["contract_id"]) / stored_name,
                        )
                        if doc_path.exists():
                            attachment_payload.append((doc["filename"], doc_path.read_bytes()))
                    if len(attachment_payload) > 1:
                        zip_buffer = BytesIO()
                        with zipfile.ZipFile(zip_buffer, "w", zipfile.ZIP_DEFLATED) as zf:
                            for filename, content in attachment_payload:
                                zf.writestr(filename, content)
                        attachment_payload = [("Anexos_do_certame.zip", zip_buffer.getvalue())]
                    ok, message = send_email(
                        active_recipients, edited_subject, edited_body,
                        cc=announcement_cc, html_body=html_body,
                        attachments=attachment_payload or None,
                    )
                    if ok:
                        log_action(
                            user["id"], "ENVIAR", "e-mail de anúncio de contrato",
                            item["id"], item["cost_center"],
                        )
                        st.success(message)
                    else:
                        st.error(message)


def page_import():
    st.title("Importar planilha")
    if not (can_create() and can_edit()):
        st.info(
            "A importação altera registros existentes e exige permissões de "
            "lançamento e modificação."
        )
        return
    st.write("A importação atualiza os contratos pelo centro de custo e não altera o arquivo Excel.")
    upload = st.file_uploader("Planilha de análise crítica", type=["xlsx"])
    replace = st.checkbox("Substituir os aditivos já importados pelos dados do Excel")
    if st.button("Importar", disabled=not upload):
        temp = Path("/tmp") / f"{uuid.uuid4().hex}.xlsx"
        temp.write_bytes(upload.getbuffer())
        with st.spinner("Lendo contratos e aditivos..."):
            result = import_workbook(temp, replace)
        temp.unlink(missing_ok=True)
        st.success(f"{result['contracts']} contratos processados e {result['amendments']} aditivos incluídos.")


def indices_data():
    contracts = [
        contract for contract in load_contracts("WHERE c.archived=0 AND c.formalized=1")
        if days_until(contract["end_date"]) is not None and days_until(contract["end_date"]) >= 0
    ]
    params = dict(query("SELECT * FROM financial_parameters WHERE id=1")[0])
    total = sum(float(c["current_value"] or 0) for c in contracts)
    remnant = sum(remaining_value(c["start_date"], c["end_date"], c["current_value"]) for c in contracts)
    equity = float(params["equity_value"] or 0)
    revenue = float(params["gross_revenue"] or 0)
    return {
        **params,
        "total_contracts": total,
        "total_remaining": remnant,
        "equity_contract_index": equity * 12 / total if total else 0,
        "equity_remaining_index": equity * 12 / remnant if remnant else 0,
        "contracts_revenue_variation": (revenue - total) / revenue if revenue else 0,
    }


def page_indices():
    st.title("Índices e Declaração de Contratos")
    st.caption(
        "Cálculos equivalentes à aba ÍNDICES e declaração no papel timbrado da ENGEMIL, "
        "atualizados pela carteira ativa."
    )
    data = indices_data()
    responsive_cards([
        (
            "Valor total dos contratos",
            brl(data["total_contracts"]),
            "Somatório integral da carteira vigente",
            "blue",
        ),
        (
            "Remanescente",
            brl(data["total_remaining"]),
            "Saldo estimado dos contratos vigentes",
            "green",
        ),
        (
            "PL × 12 / Contratos",
            f"{data['equity_contract_index']:.2f}",
            "Resultado mínimo esperado: 1,00",
            "amber",
        ),
        (
            "PL × 12 / Remanescente",
            f"{data['equity_remaining_index']:.2f}",
            "Resultado mínimo esperado: 1,00",
            "amber",
        ),
    ])
    if data["equity_contract_index"] >= 1:
        st.success("O índice sobre o valor total dos contratos é igual ou superior a 1,00.")
    else:
        st.error("O índice sobre o valor total dos contratos está inferior a 1,00.")
    if data["equity_remaining_index"] >= 1:
        st.success("O índice sobre o remanescente dos contratos é igual ou superior a 1,00.")
    else:
        st.error("O índice sobre o remanescente dos contratos está inferior a 1,00.")
    st.subheader("Parâmetros contábeis")
    if can_edit():
        with st.form("financial_parameters"):
            year = st.number_input("Ano de referência", min_value=2000, max_value=2100, value=data["reference_year"])
            c1, c2 = st.columns(2)
            equity_text = currency_input(
                c1,
                "Patrimônio líquido",
                data["equity_value"],
                "financial_equity_brl",
            )
            revenue_text = currency_input(
                c2,
                "Receita bruta",
                data["gross_revenue"],
                "financial_revenue_brl",
            )
            justification = st.text_area(
                "Justificativa que constará na declaração",
                data.get("justification_text") or (
                    f"A divergência entre os valores apresentados na Demonstração do Resultado "
                    f"do Exercício encerrada em 31 de dezembro de {data['reference_year']} e a "
                    "relação de contratos decorre da diferença nos critérios e períodos de "
                    "reconhecimento das receitas. A DRE contempla as receitas efetivamente "
                    "reconhecidas no exercício, enquanto a relação inclui todos os contratos "
                    "vigentes, com faturamentos distribuídos em exercícios presentes e futuros."
                ),
                height=160,
            )
            notes = st.text_area("Observações internas (não aparecem na declaração)", data["notes"] or "")
            st.markdown("##### Responsável pela assinatura")
            c1, c2 = st.columns(2)
            signatory_name = c1.text_input("Nome", data.get("signatory_name") or "")
            signatory_registration = c2.text_input(
                "Registro profissional", data.get("signatory_registration") or ""
            )
            c1, c2 = st.columns(2)
            signatory_cpf = c1.text_input("CPF", data.get("signatory_cpf") or "")
            signatory_title = c2.text_input("Cargo/função", data.get("signatory_title") or "")
            if st.form_submit_button("Atualizar parâmetros"):
                try:
                    equity = parse_brl_input(equity_text)
                    revenue = parse_brl_input(revenue_text)
                except ValueError:
                    st.error(
                        "Informe patrimônio e receita no padrão brasileiro, por exemplo: "
                        "R$ 139.259.969,94."
                    )
                else:
                    execute(
                        """UPDATE financial_parameters SET
                        reference_year=?,equity_value=?,gross_revenue=?,
                        justification_text=?,notes=?,signatory_name=?,signatory_registration=?,
                        signatory_cpf=?,signatory_title=?,updated_at=CURRENT_TIMESTAMP WHERE id=1""",
                        (
                            year, equity, revenue, justification, notes, signatory_name,
                            signatory_registration, signatory_cpf, signatory_title,
                        ),
                    )
                    log_action(user["id"], "EDITAR", "índices", 1, str(year))
                    st.session_state.pop("indices_official_pdf", None)
                    st.success("Parâmetros atualizados.")
                    rerun()
    st.subheader("Relação que será incluída na declaração")
    contracts = [
        contract for contract in load_contracts("WHERE c.archived=0 AND c.formalized=1")
        if days_until(contract["end_date"]) is not None and days_until(contract["end_date"]) >= 0
    ]
    declaration_contracts = []
    indices_pdf_rows = []
    preview_rows = []
    for item, contract in enumerate(contracts, start=1):
        row = dict(contract)
        row["remaining_value"] = remaining_value(
            row["start_date"], row["end_date"], row["current_value"]
        )
        declaration_contracts.append(row)
        indices_pdf_rows.append({
            "Item": item,
            "Centro de custo": row["cost_center"],
            "Contratante": row["client"],
            "Contrato": row["contract_number"],
            "Início": row["start_date"],
            "Fim": row["end_date"],
            "Valor atual": row["current_value"],
            "Instrumento vigente": row["current_instrument"],
            "Remanescente total": row["remaining_value"],
        })
        preview_rows.append({
            "Item": item,
            "Contratante": row["client"],
            "Contrato": row["contract_number"],
            "Início original": fmt_date(row["start_date"]),
            "Fim vigente": fmt_date(row["end_date"]),
            "Valor atual": brl(row["current_value"]),
            "Instrumento vigente": row["current_instrument"],
            "Remanescente": brl(row["remaining_value"]),
        })
    modern_table(pd.DataFrame(preview_rows), max_height=520)
    st.write(
        f"**Variação entre contratos e receita bruta:** {data['contracts_revenue_variation']:.2%}. "
        "A justificativa editável acima será apresentada no documento."
    )
    st.caption(
        "O PDF oficial será gerado em A4 vertical: relação de contratos na primeira "
        "página e fórmulas, justificativa e assinatura na segunda página."
    )
    signatory_ready = bool(str(data.get("signatory_name") or "").strip())
    if not signatory_ready:
        st.warning("Informe o responsável pela assinatura antes de gerar a declaração.")
    if st.button(
        "Gerar declaração oficial de Índices em PDF",
        type="primary",
        width="stretch",
        disabled=not signatory_ready,
    ):
        ordered_indices_rows = sort_backlog_rows(
            indices_pdf_rows,
            "cost_center_asc",
        )
        with st.spinner("Gerando a declaração oficial em PDF..."):
            st.session_state.indices_official_pdf = generate_indices_pdf(
                ordered_indices_rows,
                data,
            )
        log_action(
            user["id"], "GERAR EXPORTAÇÃO", "declaração de índices", None,
            f"{len(ordered_indices_rows)} contrato(s) · PDF oficial · 2 páginas",
        )
        st.success("Declaração gerada com a padronização oficial.")
    indices_pdf = st.session_state.get("indices_official_pdf")
    if indices_pdf:
        st.download_button(
            "Baixar declaração oficial de Índices em PDF",
            indices_pdf,
            file_name=(
                "Declaracao_Indices_ENGEMIL_"
                f"{today_brt().strftime('%Y-%m-%d')}.pdf"
            ),
            mime="application/pdf",
            width="stretch",
        )


def page_company_documents():
    st.title("Documentos padrões da empresa")
    st.caption(
        "Gere ofícios, cartas de preposto, procurações e novos modelos padronizados, "
        "com vínculo ao contrato e histórico de encaminhamento."
    )
    generate_tab, history_tab, templates_tab = st.tabs(
        ["Gerar documento", "Histórico e encaminhamento", "Modelos e assinaturas"]
    )
    with generate_tab:
        templates = [dict(row) for row in query(
            "SELECT * FROM company_document_templates WHERE active=1 ORDER BY document_type,name"
        )]
        if not templates:
            st.info("Nenhum modelo ativo. O administrador deve cadastrar um modelo primeiro.")
        elif not can_create():
            st.info("Seu perfil possui acesso ao histórico, mas não está autorizado a gerar documentos.")
        else:
            template_options = {
                f"{row['name']} · {row['document_type'].replace('_', ' ').title()}": row["id"]
                for row in templates
            }
            template_label = st.selectbox("Modelo do documento", template_options)
            template = next(row for row in templates if row["id"] == template_options[template_label])
            all_contracts = load_contracts("")
            contract_options = {"Sem vínculo contratual": None}
            contract_options.update({
                f"{row['cost_center']} · {row['client']} · {row['contract_number'] or 's/n'}": row["id"]
                for row in all_contracts
            })
            contract_label = st.selectbox("Vincular ao contrato", contract_options)
            contract_id = contract_options[contract_label]
            contract = next((row for row in all_contracts if row["id"] == contract_id), {})
            signatories = [dict(row) for row in query(
                "SELECT * FROM company_signatories WHERE active=1 ORDER BY name"
            )]
            if not signatories:
                st.warning("Cadastre ao menos um responsável pela assinatura.")
                signatory = {}
            else:
                signatory_options = {row["name"]: row["id"] for row in signatories}
                signatory_label = st.selectbox("Responsável pela assinatura", signatory_options)
                signatory = next(
                    row for row in signatories if row["id"] == signatory_options[signatory_label]
                )
            generation_path = resolve_project_path(template["generation_path"])
            try:
                placeholders = extract_placeholders(generation_path)
            except Exception as error:
                placeholders = []
                st.error(f"Não foi possível ler o modelo: {error}")
            st.caption(
                f"{len(placeholders)} campo(s) identificado(s) no modelo. Os dados do contrato "
                "foram preenchidos automaticamente e permanecem editáveis antes da geração."
            )
            with st.form(f"generate_company_document_{template['id']}_{contract_id}"):
                values = {}
                for placeholder in placeholders:
                    field_name = placeholder[2:-2]
                    if field_name in AUTOMATIC_DOCUMENT_FIELDS:
                        continue
                    label = DOCUMENT_FIELD_LABELS.get(
                        field_name, field_name.replace("_", " ").capitalize()
                    )
                    default = company_document_prefill(
                        field_name,
                        contract,
                        signatory,
                        separate_acronym="{{SIGLA}}" in placeholders,
                    )
                    widget_key = (
                        f"document_field_{template['id']}_{contract_id}_{field_name}"
                    )
                    if field_name in LONG_DOCUMENT_FIELDS:
                        values[field_name] = st.text_area(
                            label, value=default, height=150, key=widget_key
                        )
                    else:
                        values[field_name] = st.text_input(
                            label, value=default, key=widget_key
                        )
                internal_notes = st.text_area(
                    "Observações internas e registro do encaminhamento",
                    key=f"document_notes_{template['id']}_{contract_id}",
                )
                submitted = st.form_submit_button(
                    "Gerar documento em Word", type="primary", width="stretch"
                )
            if submitted:
                if not signatory:
                    st.error("Selecione ou cadastre um responsável pela assinatura.")
                else:
                    try:
                        sequence = next_document_sequence(
                            template["document_type"], today_brt().year
                        )
                        document_number = format_document_number(
                            template["document_type"],
                            sequence,
                            values.get("CONTRATO") or contract.get("contract_number") or "",
                            (
                                extract_agency_acronym(contract.get("client") or "")
                                or extract_agency_acronym(
                                    f"Órgão - {values.get('SIGLA') or ''}"
                                )
                            ),
                        )
                        signature_data = company_document_prefill(
                            "DADOS", contract, signatory
                        )
                        replacements = {
                            **values,
                            "NUMERO_OFICIO": document_number,
                            "NUMERO_CARTA": document_number,
                            "NUMERO_PROC": document_number,
                            "NUMERO_DOCUMENTO": document_number,
                            "DATA": today_brt().strftime("%d/%m/%Y"),
                            "DATA_EXTENSO": date_in_words(),
                            "RESPONSAVEL": signatory.get("name") or "",
                            "DADOS": signature_data,
                            "CARGO": signatory.get("title") or "",
                        }
                        destination = (
                            UPLOAD_DIR / "company_documents" / str(today_brt().year)
                            / uuid.uuid4().hex
                        )
                        destination.mkdir(parents=True, exist_ok=True)
                        output_name = f"{safe_filename(document_number)}.docx"
                        docx_path = generate_document(
                            generation_path, destination / output_name, replacements
                        )
                        generated_id = execute(
                            """INSERT INTO generated_company_documents(
                            template_id,contract_id,document_number,recipient,subject,status,
                            docx_filename,docx_path,fields_json,created_by,notes)
                            VALUES(?,?,?,?,?,'GERADO',?,?,?,?,?)""",
                            (
                                template["id"], contract_id, document_number,
                                values.get("DESTINATARIO") or values.get("ORGAO") or contract.get("client"),
                                values.get("ASSUNTO") or template["name"],
                                docx_path.name, stored_path_value(docx_path),
                                json.dumps(replacements, ensure_ascii=False),
                                user["id"], internal_notes,
                            ),
                        )
                        log_action(
                            user["id"], "GERAR", "documento padrão", generated_id,
                            document_number,
                        )
                        st.success(f"Documento {document_number} gerado e registrado no histórico.")
                        st.download_button(
                            "Baixar Word",
                            docx_path.read_bytes(),
                            file_name=docx_path.name,
                            mime="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
                            width="stretch",
                        )
                    except Exception as error:
                        st.error(f"Não foi possível gerar o documento: {error}")
    with history_tab:
        history = [dict(row) for row in query(
            """SELECT g.*,t.name template_name,c.cost_center,c.client,u.name created_by_name
            FROM generated_company_documents g
            LEFT JOIN company_document_templates t ON t.id=g.template_id
            LEFT JOIN contracts c ON c.id=g.contract_id
            LEFT JOIN users u ON u.id=g.created_by
            ORDER BY g.id DESC"""
        )]
        if not history:
            st.info("Nenhum documento foi gerado pelo sistema.")
        else:
            history_display = pd.DataFrame([{
                "Número": row["document_number"],
                "Modelo": row["template_name"] or "Modelo removido",
                "Contrato/C.C.": row["cost_center"] or "Sem vínculo",
                "Órgão/destinatário": row["recipient"] or row["client"] or "Não informado",
                "Assunto": row["subject"],
                "Status": row["status"],
                "Gerado por": row["created_by_name"] or "Usuário removido",
                "Gerado em": fmt_datetime(row["created_at"]),
                "Encaminhado em": fmt_date(row["sent_at"]),
            } for row in history])
            modern_table(history_display, max_height=520)
            history_options = {
                f"{row['document_number']} · {row['status']}": row["id"] for row in history
            }
            history_label = st.selectbox("Abrir registro", history_options)
            selected = next(
                row for row in history if row["id"] == history_options[history_label]
            )
            docx_path = portable_project_path(selected["docx_path"])
            if not docx_path.exists() and selected.get("docx_filename"):
                matches = list(
                    (UPLOAD_DIR / "company_documents").rglob(
                        selected["docx_filename"]
                    )
                )
                docx_path = matches[0] if matches else docx_path
            if docx_path.exists():
                st.download_button(
                    "Baixar Word registrado",
                    docx_path.read_bytes(),
                    file_name=selected["docx_filename"],
                    width="stretch",
                )
            if can_edit():
                with st.form(f"update_generated_document_{selected['id']}"):
                    status_options = ["GERADO", "EM REVISÃO", "APROVADO", "ENCAMINHADO", "CANCELADO"]
                    status = st.selectbox(
                        "Status do documento",
                        status_options,
                        index=status_options.index(selected["status"])
                        if selected["status"] in status_options else 0,
                    )
                    current_sent_date = (
                        date.fromisoformat(str(selected["sent_at"])[:10])
                        if selected["sent_at"] else None
                    )
                    sent_date = st.date_input(
                        "Data de encaminhamento ao órgão",
                        value=current_sent_date,
                        format="DD/MM/YYYY",
                    )
                    trace_notes = st.text_area(
                        "Observações e protocolo de encaminhamento",
                        value=selected["notes"] or "",
                    )
                    if st.form_submit_button("Atualizar rastreabilidade"):
                        execute(
                            """UPDATE generated_company_documents
                            SET status=?,sent_at=?,notes=? WHERE id=?""",
                            (
                                status,
                                sent_date.isoformat() if sent_date else None,
                                trace_notes,
                                selected["id"],
                            ),
                        )
                        log_action(
                            user["id"], "ATUALIZAR RASTREABILIDADE", "documento padrão",
                            selected["id"], status,
                        )
                        st.success("Histórico do documento atualizado.")
                        rerun()
    with templates_tab:
        templates = [dict(row) for row in query(
            "SELECT * FROM company_document_templates ORDER BY active DESC,document_type,name"
        )]
        template_display = pd.DataFrame([{
            "Modelo": row["name"],
            "Tipo": row["document_type"].replace("_", " ").title(),
            "Descrição": row["description"],
            "Arquivo Word": row["generation_filename"],
            "Modelo VBA": row["original_filename"],
            "Status": "ATIVO" if row["active"] else "INATIVO",
            "Atualizado em": fmt_datetime(row["updated_at"]),
        } for row in templates])
        modern_table(template_display)
        if templates:
            template_options = {row["name"]: row["id"] for row in templates}
            template_label = st.selectbox("Modelo para consultar", template_options)
            selected_template = next(
                row for row in templates if row["id"] == template_options[template_label]
            )
            left, right = st.columns(2)
            original_path = resolve_project_path(selected_template["original_path"])
            generation_path = resolve_project_path(selected_template["generation_path"])
            if original_path.exists():
                left.download_button(
                    "Baixar modelo original/VBA",
                    original_path.read_bytes(),
                    file_name=selected_template["original_filename"],
                    width="stretch",
                )
            if generation_path.exists():
                right.download_button(
                    "Baixar modelo DOCX de geração",
                    generation_path.read_bytes(),
                    file_name=selected_template["generation_filename"],
                    width="stretch",
                )
            if user["role"] == "admin":
                with st.expander("Editar ou substituir este modelo"):
                    with st.form(f"edit_company_template_{selected_template['id']}"):
                        edited_name = st.text_input("Nome", selected_template["name"])
                        edited_type = st.selectbox(
                            "Tipo",
                            ["OFICIO", "CARTA_PREPOSTO", "PROCURACAO", "DIVERSO"],
                            index=["OFICIO", "CARTA_PREPOSTO", "PROCURACAO", "DIVERSO"].index(
                                selected_template["document_type"]
                                if selected_template["document_type"] in
                                ["OFICIO", "CARTA_PREPOSTO", "PROCURACAO", "DIVERSO"]
                                else "DIVERSO"
                            ),
                        )
                        edited_description = st.text_area(
                            "Descrição", selected_template["description"] or ""
                        )
                        edited_active = st.checkbox(
                            "Modelo ativo", value=bool(selected_template["active"])
                        )
                        replacement_upload = st.file_uploader(
                            "Novo arquivo, se desejar substituir",
                            type=["docx", "dotm", "dotx"],
                            key=f"replace_template_file_{selected_template['id']}",
                        )
                        if st.form_submit_button("Salvar modelo"):
                            original_filename = selected_template["original_filename"]
                            original_path_value = selected_template["original_path"]
                            generation_filename = selected_template["generation_filename"]
                            generation_path_value = selected_template["generation_path"]
                            if replacement_upload:
                                new_original, new_generation = save_company_template_upload(
                                    replacement_upload
                                )
                                original_filename = Path(replacement_upload.name).name
                                original_path_value = stored_path_value(new_original)
                                generation_filename = new_generation.name
                                generation_path_value = stored_path_value(new_generation)
                            execute(
                                """UPDATE company_document_templates SET name=?,document_type=?,
                                description=?,original_filename=?,original_path=?,generation_filename=?,
                                generation_path=?,active=?,updated_at=CURRENT_TIMESTAMP WHERE id=?""",
                                (
                                    edited_name, edited_type, edited_description,
                                    original_filename, original_path_value,
                                    generation_filename, generation_path_value,
                                    int(edited_active), selected_template["id"],
                                ),
                            )
                            log_action(
                                user["id"], "EDITAR", "modelo de documento",
                                selected_template["id"], edited_name,
                            )
                            st.success("Modelo atualizado.")
                            rerun()
        if user["role"] == "admin":
            with st.expander("Cadastrar novo modelo de documento"):
                st.caption(
                    "Use marcadores no Word como {{ORGAO}}, {{CONTRATO}}, {{ASSUNTO}}, "
                    "{{CORPO_TEXTO}}, {{RESPONSAVEL}}, {{DADOS}} e {{CARGO}}."
                )
                with st.form("new_company_template", clear_on_submit=True):
                    new_name = st.text_input("Nome do modelo")
                    new_type = st.selectbox(
                        "Tipo", ["DIVERSO", "OFICIO", "CARTA_PREPOSTO", "PROCURACAO"]
                    )
                    new_description = st.text_area("Descrição e finalidade")
                    new_upload = st.file_uploader(
                        "Modelo Word", type=["docx", "dotm", "dotx"]
                    )
                    if st.form_submit_button("Cadastrar modelo"):
                        if not new_name.strip() or not new_upload:
                            st.error("Informe o nome e selecione o arquivo Word.")
                        else:
                            try:
                                original_path, generation_path = save_company_template_upload(
                                    new_upload
                                )
                                template_id = execute(
                                    """INSERT INTO company_document_templates(
                                    name,document_type,description,original_filename,original_path,
                                    generation_filename,generation_path,created_by)
                                    VALUES(?,?,?,?,?,?,?,?)""",
                                    (
                                        new_name.strip(), new_type, new_description,
                                        Path(new_upload.name).name,
                                        stored_path_value(original_path),
                                        generation_path.name,
                                        stored_path_value(generation_path), user["id"],
                                    ),
                                )
                                log_action(
                                    user["id"], "CRIAR", "modelo de documento",
                                    template_id, new_name,
                                )
                                st.success("Novo modelo cadastrado.")
                                rerun()
                            except Exception as error:
                                st.error(f"Não foi possível cadastrar o modelo: {error}")
        st.subheader("Responsáveis pelas assinaturas")
        signatories = [dict(row) for row in query(
            "SELECT * FROM company_signatories ORDER BY active DESC,name"
        )]
        modern_table(pd.DataFrame([{
            "Nome": row["name"],
            "Registro": row["registration"],
            "CPF": row["cpf"],
            "Cargo/função": row["title"],
            "Status": "ATIVO" if row["active"] else "INATIVO",
        } for row in signatories]))
        if user["role"] == "admin" and signatories:
            signatory_options = {row["name"]: row["id"] for row in signatories}
            signatory_label = st.selectbox(
                "Responsável para editar", signatory_options,
                key="edit_company_signatory",
            )
            selected_signatory = next(
                row for row in signatories
                if row["id"] == signatory_options[signatory_label]
            )
            with st.form(f"edit_signatory_{selected_signatory['id']}"):
                signatory_name = st.text_input("Nome", selected_signatory["name"])
                c1, c2 = st.columns(2)
                signatory_registration = c1.text_input(
                    "Registro profissional", selected_signatory["registration"] or ""
                )
                signatory_cpf = c2.text_input("CPF", selected_signatory["cpf"] or "")
                signatory_title = st.text_input(
                    "Cargo/função", selected_signatory["title"] or ""
                )
                signatory_active = st.checkbox(
                    "Responsável ativo", value=bool(selected_signatory["active"])
                )
                if st.form_submit_button("Atualizar responsável"):
                    execute(
                        """UPDATE company_signatories SET name=?,registration=?,cpf=?,title=?,
                        active=?,updated_at=CURRENT_TIMESTAMP WHERE id=?""",
                        (
                            signatory_name, signatory_registration, signatory_cpf,
                            signatory_title, int(signatory_active), selected_signatory["id"],
                        ),
                    )
                    log_action(
                        user["id"], "EDITAR", "responsável de assinatura",
                        selected_signatory["id"], signatory_name,
                    )
                    st.success("Responsável atualizado.")
                    rerun()
        if user["role"] == "admin":
            with st.expander("Cadastrar novo responsável"):
                with st.form("new_company_signatory", clear_on_submit=True):
                    new_signatory_name = st.text_input("Nome completo")
                    c1, c2 = st.columns(2)
                    new_signatory_registration = c1.text_input("Registro profissional")
                    new_signatory_cpf = c2.text_input("CPF")
                    new_signatory_title = st.text_input("Cargo/função")
                    if st.form_submit_button("Cadastrar responsável"):
                        if not new_signatory_name.strip():
                            st.error("Informe o nome do responsável.")
                        else:
                            try:
                                signatory_id = execute(
                                    """INSERT INTO company_signatories(
                                    name,registration,cpf,title) VALUES(?,?,?,?)""",
                                    (
                                        new_signatory_name.strip(),
                                        new_signatory_registration,
                                        new_signatory_cpf,
                                        new_signatory_title,
                                    ),
                                )
                                log_action(
                                    user["id"], "CRIAR", "responsável de assinatura",
                                    signatory_id, new_signatory_name,
                                )
                                st.success("Responsável cadastrado.")
                                rerun()
                            except Exception:
                                st.error("Já existe um responsável com esse nome.")


def detail_export_sheets(contract_id):
    contract_row = dict(query(
        "SELECT * FROM contracts WHERE id=?", (contract_id,)
    )[0])
    contract_row.pop("adjustment_index", None)
    contract_row.pop("guarantee_end_date", None)
    contract = pd.DataFrame([contract_row])
    bdi_rows = load_contract_bdis(
        contract_id, contract_row.get("tax_regime") or "NÃO DEFINIDO"
    )
    sheets = {
        "Ficha": contract,
        "Aditivos": pd.DataFrame(contract_amendments_with_arts(contract_id)),
        "Garantias e seguros": pd.DataFrame([{
            "Código": row["id"],
            "Tipo": row["custom_type"] or row["guarantee_type"],
            "Modalidade": row["modality"],
            "Instrumento": row["instrument_scope"],
            "Fundamento": row["legal_basis"],
            "Valor exigido": row["required_amount"],
            "Emissor": row["provider_name"],
            "Corretora": row["broker_name"],
            "Apólice/garantia": row["policy_number"],
            "SUSEP/controle": row["susep_registration"],
            "Emissão": row["issue_date"],
            "Início": row["start_date"],
            "Fim": row["end_date"],
            "Prêmio": row["premium_value"],
            "Situação": row["request_status"],
            "Responsável": row["responsible_name"],
            "E-mail": row["responsible_email"],
            "Observações": row["notes"],
        } for row in (
            dict(r) for r in query(
                "SELECT * FROM contract_guarantees WHERE contract_id=? ORDER BY id",
                (contract_id,),
            )
        )]),
        "Coberturas de seguros": pd.DataFrame([dict(r) for r in query(
            """SELECT cv.*,g.guarantee_type,g.policy_number
            FROM guarantee_coverages cv
            JOIN contract_guarantees g ON g.id=cv.guarantee_id
            WHERE g.contract_id=? ORDER BY g.id,cv.id""",
            (contract_id,),
        )]),
        "Endossos de garantias": pd.DataFrame([{
            key: value for key, value in dict(r).items()
            if key not in {"previous_amount", "new_amount"}
        } for r in query(
            """SELECT ge.*,g.guarantee_type,g.policy_number
            FROM guarantee_endorsements ge
            JOIN contract_guarantees g ON g.id=ge.guarantee_id
            WHERE g.contract_id=? ORDER BY g.id,ge.id""",
            (contract_id,),
        )]),
        "Datas do orçamento": pd.DataFrame(load_contract_budget_dates(contract_id)),
        "BDI": pd.DataFrame([{
            "BDI": item["name"],
            "Referência": item["reference_name"],
            "Regime": item["effective_tax_regime"],
            "Método": BDI_METHOD_LABELS.get(
                item["calculation_method"], item["calculation_method"]
            ),
            "Arredondamento": BDI_ROUNDING_LABELS.get(
                item["rounding_method"], item["rounding_method"]
            ),
            "Custos indiretos": item["indirect_costs"],
            "Administração central": item["central_administration"],
            "Seguros": item["insurance"],
            "Riscos": item["risks"],
            "Garantias": item["guarantees"],
            "Outros custos indiretos": item["other_indirect_costs"],
            "Despesas financeiras": item["financial_expenses"],
            "Lucro": item["profit"],
            "PIS": item["pis"],
            "COFINS": item["cofins"],
            "ISS": item["iss"],
            "CPRB": item["cprb"],
            "Outros tributos": item["other_taxes"],
            "Total dos tributos": item["tax_total"],
            "BDI calculado": item["calculated_percentage"],
            "Observações": item["notes"],
        } for item in bdi_rows]),
        "Sindicatos": pd.DataFrame([dict(r) for r in query(
            "SELECT * FROM contract_unions WHERE contract_id=? ORDER BY id", (contract_id,)
        )]),
        "Equipe": pd.DataFrame([dict(r) for r in query(
            "SELECT * FROM contract_positions WHERE contract_id=? ORDER BY id", (contract_id,)
        )]),
        "Benefícios": pd.DataFrame([dict(r) for r in query(
            """SELECT b.*,p.title cargo FROM position_benefits b
            JOIN contract_positions p ON p.id=b.position_id
            WHERE p.contract_id=? ORDER BY p.title,b.benefit_type""", (contract_id,)
        )]),
        "Obrigações": pd.DataFrame([dict(r) for r in query(
            "SELECT * FROM obligations WHERE contract_id=? ORDER BY due_date", (contract_id,)
        )]),
        "ARTs": pd.DataFrame([{
            **item,
            "professional_name": item.get("professional_display_name")
            or item.get("professional_name"),
            "instrument_reference": art_instrument_reference(item),
        } for item in organize_art_rows(query(
                """SELECT ar.*,a.ordinal amendment_ordinal,a.kind amendment_kind,
                atc.contract_number ata_contract_number, atc.client ata_client,
                ataa.ordinal ata_amendment_ordinal, ataa.kind ata_amendment_kind
                FROM arts ar
                LEFT JOIN amendments a ON a.id=ar.amendment_id
                LEFT JOIN ata_contracts atc ON atc.id=ar.ata_contract_id
                LEFT JOIN ata_contract_amendments ataa ON ataa.id=ar.ata_amendment_id
                WHERE ar.contract_id=? ORDER BY ar.id""",
                (contract_id,),
            ))]),
        "CNO": pd.DataFrame([dict(r) for r in query(
            """SELECT n.*,ac.contract_number ata_contract_number,
            ac.client ata_contract_client
            FROM contract_cnos n
            LEFT JOIN ata_contracts ac ON ac.id=n.ata_contract_id
            WHERE n.contract_id=? ORDER BY n.registration_date,n.id""",
            (contract_id,),
        )]),
        "Documentos": pd.DataFrame([dict(r) for r in query(
            "SELECT id,category,title,filename,uploaded_at FROM documents WHERE contract_id=? ORDER BY id",
            (contract_id,),
        )]),
        "Documentos padronizados": pd.DataFrame([dict(r) for r in query(
            """SELECT g.document_number numero,t.name modelo,g.recipient destinatario,
            g.subject assunto,g.status,g.docx_filename arquivo_word,
            u.name gerado_por,g.created_at gerado_em,g.sent_at encaminhado_em,g.notes observacoes
            FROM generated_company_documents g
            LEFT JOIN company_document_templates t ON t.id=g.template_id
            LEFT JOIN users u ON u.id=g.created_by
            WHERE g.contract_id=? ORDER BY g.id""",
            (contract_id,),
        )]),
    }
    ata_contract_rows = [dict(r) for r in query(
        "SELECT * FROM ata_contracts WHERE ata_id=? ORDER BY contract_number,id", (contract_id,)
    )]
    if ata_contract_rows:
        sheets["Contratos da ATA"] = pd.DataFrame(ata_contract_rows)
        sheets["Aditivos Contratos ATA"] = pd.DataFrame([dict(r) for r in query(
            """SELECT a.*,c.contract_number FROM ata_contract_amendments a
            JOIN ata_contracts c ON c.id=a.ata_contract_id
            WHERE c.ata_id=? ORDER BY c.contract_number,a.id""",
            (contract_id,),
        )])
    return sheets


def contract_report_payload(contract_id):
    contract = dict(query("SELECT * FROM contracts WHERE id=?", (contract_id,))[0])
    effective = next(
        item for item in load_contracts("") if int(item["id"]) == int(contract_id)
    )
    effective = dict(effective)
    effective["remaining_value"] = remaining_value(
        effective["start_date"],
        effective["end_date"],
        effective["current_value"],
    )
    amendments = contract_amendments_with_arts(contract_id)
    guarantees = load_contract_guarantees(
        contract_id, effective.get("current_end_date") or effective.get("end_date")
    )
    for guarantee in guarantees:
        guarantee["coverages"] = [dict(row) for row in query(
            "SELECT * FROM guarantee_coverages WHERE guarantee_id=? ORDER BY id",
            (guarantee["id"],),
        )]
        guarantee["endorsements"] = [dict(row) for row in query(
            "SELECT * FROM guarantee_endorsements WHERE guarantee_id=? ORDER BY id",
            (guarantee["id"],),
        )]
    guarantee_names = {
        item["id"]: " · ".join(filter(None, [
            item.get("display_type"), item.get("policy_number"),
        ]))
        for item in guarantees
    }
    endorsement_names = {
        endorsement["id"]: " · ".join(filter(None, [
            guarantee_names.get(guarantee["id"]),
            endorsement.get("movement_type"), endorsement.get("endorsement_number"),
        ]))
        for guarantee in guarantees
        for endorsement in guarantee["endorsements"]
    }
    bdis = load_contract_bdis(
        contract_id, contract.get("tax_regime") or "NÃO DEFINIDO"
    )
    amendment_names = {
        row["id"]: " ".join(
            str(part).strip() for part in (row.get("ordinal"), row.get("kind")) if part
        )
        for row in amendments
    }
    unions = []
    for raw in query(
        """SELECT u.*,a.ordinal amendment_ordinal,a.kind amendment_kind
        FROM contract_unions u LEFT JOIN amendments a ON a.id=u.amendment_id
        WHERE u.contract_id=? ORDER BY u.id""",
        (contract_id,),
    ):
        item = dict(raw)
        item["instrument_reference"] = " ".join(filter(None, [
            str(item.get("amendment_ordinal") or "").strip(),
            str(item.get("amendment_kind") or "").strip(),
        ])).strip() or "Contrato inicial"
        unions.append(item)
    union_names = {
        item["id"]: " · ".join(filter(None, [
            item.get("union_name"), item.get("collective_agreement"),
        ]))
        for item in unions
    }
    positions = []
    for raw in query(
        "SELECT * FROM contract_positions WHERE contract_id=? ORDER BY title,id",
        (contract_id,),
    ):
        item = dict(raw)
        item["union_reference"] = union_names.get(item.get("union_id"), "")
        item["benefits"] = [
            dict(row) for row in query(
                "SELECT * FROM position_benefits WHERE position_id=? ORDER BY benefit_type,id",
                (item["id"],),
            )
        ]
        positions.append(item)
    obligations = [
        dict(row) for row in query(
            "SELECT * FROM obligations WHERE contract_id=? ORDER BY due_date,id",
            (contract_id,),
        )
    ]
    budget_dates = load_contract_budget_dates(contract_id)
    arts = organize_art_rows(query(
        """SELECT ar.*,a.ordinal amendment_ordinal,a.kind amendment_kind,
        atc.contract_number ata_contract_number, atc.client ata_client,
        ataa.ordinal ata_amendment_ordinal, ataa.kind ata_amendment_kind
        FROM arts ar
        LEFT JOIN amendments a ON a.id=ar.amendment_id
        LEFT JOIN ata_contracts atc ON atc.id=ar.ata_contract_id
        LEFT JOIN ata_contract_amendments ataa ON ataa.id=ar.ata_amendment_id
        WHERE ar.contract_id=? ORDER BY ar.id""",
        (contract_id,),
    ))
    for item in arts:
        item["instrument_reference"] = art_instrument_reference(item)
    art_names = {item["id"]: item.get("art_number") for item in arts}
    cnos = [
        dict(row) for row in query(
            """SELECT n.*,ac.contract_number ata_contract_number,
            ac.client ata_contract_client
            FROM contract_cnos n
            LEFT JOIN ata_contracts ac ON ac.id=n.ata_contract_id
            WHERE n.contract_id=? ORDER BY n.registration_date,n.id""",
            (contract_id,),
        )
    ]
    for item in cnos:
        item["ata_contract_reference"] = " · ".join(filter(None, [
            (
                f"Contrato {item.get('ata_contract_number')}"
                if item.get("ata_contract_number") else ""
            ),
            item.get("ata_contract_client"),
        ]))
    cno_names = {item["id"]: item.get("registration_number") for item in cnos}
    ata_contracts = []
    ata_contract_names = {}
    ata_amendment_names = {}
    for raw in query(
        "SELECT * FROM ata_contracts WHERE ata_id=? ORDER BY contract_number,id",
        (contract_id,),
    ):
        item = dict(raw)
        ata_contract_names[item["id"]] = item.get("contract_number")
        item["amendments"] = [
            dict(row) for row in query(
                "SELECT * FROM ata_contract_amendments WHERE ata_contract_id=? ORDER BY id",
                (item["id"],),
            )
        ]
        for amendment in item["amendments"]:
            ata_amendment_names[amendment["id"]] = " ".join(filter(None, [
                item.get("contract_number"),
                str(amendment.get("ordinal") or "").strip(),
                str(amendment.get("kind") or "").strip(),
            ])).strip()
        ata_contracts.append(item)
    documents = []
    for raw in query(
        "SELECT * FROM documents WHERE contract_id=? ORDER BY uploaded_at,id",
        (contract_id,),
    ):
        item = dict(raw)
        if item.get("guarantee_endorsement_id"):
            association = endorsement_names.get(
                item["guarantee_endorsement_id"], "Endosso/renovação de garantia"
            )
        elif item.get("guarantee_id"):
            association = guarantee_names.get(
                item["guarantee_id"], "Garantia/seguro contratual"
            )
        elif item.get("amendment_id"):
            association = amendment_names.get(item["amendment_id"], "Instrumento contratual")
        elif item.get("union_id"):
            association = union_names.get(item["union_id"], "Sindicato/CCT")
        elif item.get("art_id"):
            association = f"ART {art_names.get(item['art_id'], '')}".strip()
        elif item.get("cno_id"):
            association = f"CNO {cno_names.get(item['cno_id'], '')}".strip()
        elif item.get("ata_amendment_id"):
            association = ata_amendment_names.get(
                item["ata_amendment_id"], "Aditivo de contrato decorrente da ATA"
            )
        elif item.get("ata_contract_id"):
            association = (
                f"Contrato decorrente da ATA "
                f"{ata_contract_names.get(item['ata_contract_id'], '')}"
            ).strip()
        else:
            association = "Resumo do contrato"
        item["association"] = association
        documents.append(item)
    generated_documents = [
        dict(row) for row in query(
            """SELECT g.*,t.name template_name,u.name created_by_name
            FROM generated_company_documents g
            LEFT JOIN company_document_templates t ON t.id=g.template_id
            LEFT JOIN users u ON u.id=g.created_by
            WHERE g.contract_id=? ORDER BY g.created_at,g.id""",
            (contract_id,),
        )
    ]
    return {
        "contract": contract,
        "effective": effective,
        "amendments": amendments,
        "guarantees": guarantees,
        "bdis": bdis,
        "ata_contracts": ata_contracts,
        "unions": unions,
        "positions": positions,
        "obligations": obligations,
        "budget_dates": budget_dates,
        "arts": arts,
        "cnos": cnos,
        "documents": documents,
        "generated_documents": generated_documents,
    }


def contract_document_exports(contract_id, key_prefix):
    session_key = f"{key_prefix}_contract_files_{contract_id}"
    if st.button(
        "Preparar ficha completa em Word",
        key=f"{key_prefix}_prepare_contract_{contract_id}",
        type="primary",
    ):
        with st.spinner("Organizando todas as informações da ficha contratual..."):
            payload = contract_report_payload(contract_id)
            docx_bytes = generate_contract_dossier(payload)
            contract = payload["contract"]
            stem = f"Ficha_Contratual_{contract.get('cost_center') or contract_id}"
            st.session_state[session_key] = {
                "docx": docx_bytes,
                "stem": safe_filename(stem),
            }
            log_action(
                user["id"], "GERAR EXPORTAÇÃO", "ficha contratual", contract_id, stem
            )
    files = st.session_state.get(session_key)
    if not files:
        st.caption(
            "O relatório reúne todas as abas preenchidas, omite campos em branco e mantém o "
            "papel timbrado em A4 vertical."
        )
        return
    st.download_button(
        "Baixar ficha em Word",
        files["docx"],
        file_name=f"{files['stem']}.docx",
        mime="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        key=f"{key_prefix}_download_contract_docx_{contract_id}",
        width="stretch",
    )


def backlog_pdf_export(backlog, key_prefix, contracts=None):
    official_columns = [
        "Item",
        "Centro de custo",
        "Contratante",
        "Contrato",
        "Início",
        "Fim",
        "Valor atual",
        "Instrumento vigente",
        "Remanescente total",
    ]
    official_backlog = backlog.reindex(columns=official_columns)
    controls = st.columns(2)
    sort_label = controls[0].selectbox(
        "Ordenar o Backlog por",
        list(BACKLOG_SORT_OPTIONS),
        key=f"{key_prefix}_backlog_sort",
    )
    sort_criterion = BACKLOG_SORT_OPTIONS[sort_label]
    signatories = [
        dict(row) for row in query(
            "SELECT * FROM company_signatories WHERE active=1 ORDER BY name"
        )
    ]
    signatory_options = {
        f"{row['name']} · {row['title'] or 'Sem cargo informado'}": row["id"]
        for row in signatories
    }
    signatory_label = controls[1].selectbox(
        "Responsável pela assinatura",
        list(signatory_options) or ["Nenhum responsável ativo"],
        key=f"{key_prefix}_backlog_signatory",
        disabled=not signatory_options,
    )
    signatory_id = signatory_options.get(signatory_label)
    signatory = next(
        (row for row in signatories if row["id"] == signatory_id),
        {},
    )
    if user["role"] == "admin":
        with st.expander("Cadastrar outro diretor, gestor ou responsável pela assinatura"):
            st.caption(
                "O responsável ficará disponível no Backlog e nos demais documentos "
                "padronizados da empresa."
            )
            with st.form(
                f"{key_prefix}_new_backlog_signatory",
                clear_on_submit=True,
            ):
                new_signatory_name = st.text_input(
                    "Nome completo *",
                    key=f"{key_prefix}_backlog_signatory_name",
                )
                c1, c2 = st.columns(2)
                new_signatory_title = c1.text_input(
                    "Cargo/função *",
                    key=f"{key_prefix}_backlog_signatory_title",
                )
                new_signatory_registration = c2.text_input(
                    "Registro profissional",
                    key=f"{key_prefix}_backlog_signatory_registration",
                )
                new_signatory_cpf = st.text_input(
                    "CPF",
                    key=f"{key_prefix}_backlog_signatory_cpf",
                )
                if st.form_submit_button("Cadastrar responsável"):
                    normalized_name = new_signatory_name.strip()
                    if not normalized_name or not new_signatory_title.strip():
                        st.error("Informe o nome completo e o cargo/função.")
                    elif query(
                        "SELECT id FROM company_signatories WHERE name=? COLLATE NOCASE",
                        (normalized_name,),
                    ):
                        st.error("Já existe um responsável cadastrado com este nome.")
                    else:
                        new_signatory_id = execute(
                            """INSERT INTO company_signatories(
                            name,registration,cpf,title,active)
                            VALUES(?,?,?,?,1)""",
                            (
                                normalized_name,
                                new_signatory_registration.strip(),
                                new_signatory_cpf.strip(),
                                new_signatory_title.strip(),
                            ),
                        )
                        log_action(
                            user["id"], "CRIAR", "responsável de assinatura",
                            new_signatory_id, normalized_name,
                        )
                        st.success("Responsável cadastrado e liberado para seleção.")
                        rerun()
    session_key = f"{key_prefix}_backlog_pdf"
    st.caption(
        "PDF oficial: Item, Centro de custo, Contratante, Contrato, Vigência inicial e final, "
        "Valor atual, Instrumento vigente e Remanescente total. As projeções anuais não são "
        "incluídas neste relatório."
    )
    if signatory:
        professional_data = " · ".join(
            value for value in (
                signatory.get("title"),
                signatory.get("registration"),
                f"CPF {signatory.get('cpf')}" if signatory.get("cpf") else "",
            )
            if value
        )
        st.caption(
            f"Assinatura selecionada: {signatory['name']}"
            f"{' · ' + professional_data if professional_data else ''}."
        )
    else:
        st.error(
            "Não há responsável ativo para assinatura. Cadastre ou ative um responsável "
            "em Documentos padrões."
        )
    if st.button(
        "Gerar Backlog oficial em PDF — modelo Análise Crítica",
        key=f"{key_prefix}_prepare_backlog_pdf",
        type="primary",
        disabled=not signatory,
    ):
        with st.spinner("Gerando o PDF oficial do Backlog ENGEMIL..."):
            ordered_rows = sort_backlog_rows(
                official_backlog.to_dict("records"),
                sort_criterion,
            )
            report_pdf = generate_backlog_pdf(
                ordered_rows,
                signatory=signatory,
                sort_label=sort_label,
                overview_summary=(
                    build_contract_overview_summary(
                        contracts,
                        total_remaining_value=official_backlog["Remanescente total"].sum(),
                    )
                    if contracts is not None else None
                ),
            )
            st.session_state[session_key] = {
                "pdf": report_pdf,
                "sort_criterion": sort_criterion,
                "signatory_id": signatory_id,
            }
            log_action(
                user["id"], "GERAR EXPORTAÇÃO", "backlog", None,
                f"{len(official_backlog)} contrato(s) · PDF oficial · "
                f"{sort_label} · assinatura: {signatory['name']}",
            )
    result = st.session_state.get(session_key)
    if not result:
        return
    if (
        result.get("sort_criterion") != sort_criterion
        or result.get("signatory_id") != signatory_id
    ):
        st.info(
            "A ordenação ou o responsável foi alterado. Gere o PDF novamente "
            "para atualizar o arquivo."
        )
        return
    st.download_button(
        "Baixar Backlog oficial em PDF",
        result["pdf"],
        file_name=f"Backlog_ENGEMIL_{today_brt().isoformat()}.pdf",
        mime="application/pdf",
        key=f"{key_prefix}_download_backlog_pdf",
    )


def load_bid_processes(where_clause=""):
    sql = f"SELECT * FROM bid_processes {where_clause} ORDER BY COALESCE(dispute_date, created_at) ASC"
    return [dict(row) for row in query(sql)]


def load_bid_lots(bid_process_id):
    return [
        dict(row) for row in query(
            "SELECT * FROM bid_lots WHERE bid_process_id=? ORDER BY id ASC",
            (bid_process_id,),
        )
    ]


def load_bid_lots_by_process():
    """Carrega todos os grupos/itens de todas as licitações de uma vez só
    (uma consulta), organizados por licitação — usado para não precisar
    de uma consulta separada por linha ao montar os indicadores e a
    listagem geral de licitações."""
    by_process = {}
    for row in query("SELECT * FROM bid_lots ORDER BY bid_process_id, id"):
        by_process.setdefault(row["bid_process_id"], []).append(dict(row))
    return by_process


def load_bid_lot_items(bid_lot_id):
    return [
        dict(row) for row in query(
            "SELECT * FROM bid_lot_items WHERE bid_lot_id=? ORDER BY id ASC",
            (bid_lot_id,),
        )
    ]


def recompute_bid_lot_totals(bid_lot_id):
    """Depois de salvar os itens de um grupo/item (quantidade × valor
    unitário de cada linha, como no exemplo do Compras.gov.br), soma tudo
    e atualiza o valor estimado e o valor ofertado (nosso lance) do
    grupo/item — a classificação sempre usa esse total, nunca os valores
    unitários de cada item isoladamente."""
    items = load_bid_lot_items(bid_lot_id)
    if not items:
        return
    total_estimated = sum(float(it["quantity"] or 0) * float(it["estimated_unit_value"] or 0) for it in items)
    offered_items = [it for it in items if it.get("offered_unit_value") is not None]
    total_offered = (
        sum(float(it["quantity"] or 0) * float(it["offered_unit_value"] or 0) for it in offered_items)
        if offered_items else None
    )
    discount = None
    if total_offered and total_estimated:
        discount = (1 - total_offered / total_estimated) * 100
    execute(
        """UPDATE bid_lots SET estimated_value=?,our_bid_value=?,our_discount_percent=?,
        item_count=?,updated_at=CURRENT_TIMESTAMP WHERE id=?""",
        (total_estimated, total_offered, discount, len(items), bid_lot_id),
    )


def format_discount_display(value):
    """Formata um percentual de desconto para exibição: quando o valor
    ficou ACIMA do estimado (percentual negativo), mostra com uma seta
    ▲ para deixar isso óbvio, em vez de um sinal de menos fácil de
    passar despercebido — mesmo padrão já usado na imagem de
    classificação e no relatório em PDF."""
    if value is None:
        return "—"
    if value < 0:
        return f"▲ {abs(value):.2f}%".replace(".", ",")
    return f"{value:.2f}%".replace(".", ",")


def format_discount_display(value):
    """Formata um percentual de desconto para exibição: quando o valor
    ficou ACIMA do estimado (percentual negativo), mostra com uma seta
    ▲ para deixar isso óbvio, em vez de um sinal de menos fácil de
    passar despercebido — mesmo padrão já usado na imagem de
    classificação e no relatório em PDF."""
    if value is None:
        return "—"
    if value < 0:
        return f"▲ {abs(value):.2f}%".replace(".", ",")
    return f"{value:.2f}%".replace(".", ",")


def format_estimated_value_for_pdf(aggregate):
    """Mesma lógica de format_estimated_value_display, mas em texto puro
    (sem emoji) — a fonte padrão usada no PDF não tem o glifo do cadeado
    e renderizaria um quadrado preto no lugar dele."""
    if aggregate.get("is_confidential"):
        registered_value = aggregate.get("estimated_value")
        if registered_value:
            return f"SIGILOSO\n{brl(registered_value)} (cadastrado)"
        return "SIGILOSO — sem valor cadastrado"
    return aggregate.get("estimated_value")


def load_bid_rankings(bid_process_id, bid_lot_id=None):
    if bid_lot_id:
        sql = "SELECT * FROM bid_rankings WHERE bid_lot_id=? ORDER BY seq ASC, id ASC"
        params = (bid_lot_id,)
    else:
        sql = "SELECT * FROM bid_rankings WHERE bid_process_id=? AND bid_lot_id IS NULL ORDER BY seq ASC, id ASC"
        params = (bid_process_id,)
    return [dict(row) for row in query(sql, params)]


def delete_bid_rankings(bid_process_id, bid_lot_id=None):
    if bid_lot_id:
        execute("DELETE FROM bid_rankings WHERE bid_lot_id=?", (bid_lot_id,))
    else:
        execute(
            "DELETE FROM bid_rankings WHERE bid_process_id=? AND bid_lot_id IS NULL",
            (bid_process_id,),
        )


def apply_engemil_ranking_to_process(bid_process_id, rows, bid_lot_id=None):
    """Depois de salvar a classificação, localiza a linha da ENGEMIL (por
    CNPJ ou nome) e já preenche automaticamente — na aba Resumo e edição
    (licitação sem grupos/itens) ou no grupo/item correspondente (aba
    Grupos/Itens) — o nosso lance final, o desconto e a posição de
    classificação, sem precisar digitar de novo o que acabou de ser
    colado/editado."""
    engemil_row = next((row for row in rows if row.get("is_engemil")), None)
    if not engemil_row:
        return
    if bid_lot_id:
        execute(
            """UPDATE bid_lots SET our_bid_value=?,our_discount_percent=?,our_ranking=?,
            updated_at=CURRENT_TIMESTAMP WHERE id=?""",
            (
                engemil_row.get("final_bid_value"),
                engemil_row.get("discount_percent"),
                engemil_row.get("seq"),
                bid_lot_id,
            ),
        )
    else:
        execute(
            """UPDATE bid_processes SET our_bid_value=?,our_discount_percent=?,our_ranking=?,
            updated_at=CURRENT_TIMESTAMP WHERE id=?""",
            (
                engemil_row.get("final_bid_value"),
                engemil_row.get("discount_percent"),
                engemil_row.get("seq"),
                bid_process_id,
            ),
        )


def bid_status_color(status):
    return {
        "EM ANDAMENTO": "amber",
        "HOMOLOGADA - VENCEDORA": "green",
        "HOMOLOGADA - NÃO VENCEDORA": "red",
        "DESERTA / FRACASSADA": "red",
        "SUSPENSA": "amber",
        "REVOGADA / CANCELADA": "red",
    }.get(status, "blue")


_RANKING_SEGMENT_BADGE_PATTERN = re.compile(r"(OE|ME|EPP|MEI)\*?", re.IGNORECASE)
_RANKING_SEGMENT_BADGE_WORDS = {
    "OUTRAS EMPRESAS", "OUTRA EMPRESA", "MICRO-EMPRESA", "MICROEMPRESA",
    "MICRO EMPRESA", "PEQUENA EMPRESA", "EMPRESA DE PEQUENO PORTE",
    "GRANDE EMPRESA", "COOPERATIVA", "ME/EPP",
}
_RANKING_DATETIME_PATTERN = re.compile(
    r"\d{2}/\d{2}/\d{4}(\s+\d{2}:\d{2}:\d{2}(:\d{1,3})?)?"
)


def _is_ranking_segment_badge(token):
    """Reconhece o selo de porte/segmento da empresa (coluna 'Segmento'),
    tanto na forma abreviada (OE*, ME*, EPP*, MEI*) quanto por extenso
    (Outras Empresas, Micro-Empresa etc., como no Pregão Online do Banco
    do Brasil) — não faz parte do nome da empresa."""
    cleaned = re.sub(r"\s+", " ", token.strip()).upper()
    return bool(_RANKING_SEGMENT_BADGE_PATTERN.fullmatch(cleaned)) or cleaned in _RANKING_SEGMENT_BADGE_WORDS


def _ranking_situation_from_token(token):
    """Reconhece um token de situação dentro de uma coluna 'Situação' (ex.:
    Licitações-e e Pregão Online do Banco do Brasil: Classificado,
    Desclassificado, Arrematante, Entregue, Inabilitado, Desistente etc.),
    retornando a situação padronizada — ou None se o token não for isso."""
    cleaned = token.strip().upper()
    if "DESCLASSIFICAD" in cleaned:
        return "DESCLASSIFICADA"
    if "INABILITAD" in cleaned:
        return "INABILITADA"
    if "DESISTEN" in cleaned:
        return "DESISTENTE"
    if cleaned in {
        "ARREMATANTE", "CLASSIFICADO", "CLASSIFICADA", "HABILITADO", "HABILITADA",
        "ENTREGUE", "ACEITO", "ACEITA",
    }:
        return "CLASSIFICADA"
    return None


def parse_pasted_ranking(text):
    """Reconhece linhas de classificação coladas de um portal (Compras.gov.br,
    PNCP, Portal de Compras Públicas, Licitações-e do Banco do Brasil etc.)
    ou de uma planilha. Aceita colunas separadas por tabulação (padrão ao
    colar de uma tabela web) ou por 2+ espaços (padrão ao colar texto
    alinhado). Reconhece cada valor pelo formato (CNPJ, percentual, valor
    monetário, situação, selo de porte da empresa, data/hora do lance) em
    vez de depender de uma ordem fixa de colunas, para funcionar com
    layouts diferentes."""
    rows = []
    cnpj_pattern = re.compile(r"^\d{2}\.?\d{3}\.?\d{3}/?\d{4}-?\d{2}$")
    for raw_line in text.strip().splitlines():
        line = raw_line.strip()
        if not line:
            continue
        parts = re.split(r"\t+", line) if "\t" in line else re.split(r"\s{2,}", line)
        parts = [p.strip() for p in parts if p.strip()]
        if len(parts) < 2:
            continue
        if any(p.strip().upper() == "PARTICIPANTE" for p in parts):
            continue
        seq = None
        cnpj = None
        bid_value = None
        discount = None
        situation = None
        remaining = []
        for part in parts:
            if seq is None and re.fullmatch(r"\d{1,4}º?", part):
                seq = int(re.sub(r"\D", "", part))
                continue
            if cnpj is None and cnpj_pattern.fullmatch(part):
                cnpj = re.sub(r"\D", "", part)
                continue
            if _is_ranking_segment_badge(part):
                continue
            if _RANKING_DATETIME_PATTERN.fullmatch(part):
                continue
            if situation is None:
                token_situation = _ranking_situation_from_token(part)
                if token_situation:
                    situation = token_situation
                    continue
            if "%" in part:
                try:
                    discount = float(part.replace("%", "").strip().replace(".", "").replace(",", "."))
                except ValueError:
                    pass
                continue
            if bid_value is None and (
                "R$" in part or re.fullmatch(r"\d{1,3}(\.\d{3})*,\d{2}", part)
            ):
                try:
                    bid_value = parse_brazilian_number(part)
                    continue
                except ValueError:
                    pass
            remaining.append(part)
        company = " ".join(remaining).strip()
        if not company or company.upper() in {"SEQ", "EMPRESAS", "EMPRESA"}:
            continue
        row_data = {
            "seq": seq,
            "company_name": company,
            "company_cnpj": cnpj,
            "final_bid_value": bid_value,
            "discount_percent": discount,
        }
        if situation:
            row_data["situation"] = situation
        rows.append(row_data)
    for index, row in enumerate(rows):
        if row["seq"] is None:
            row["seq"] = index + 1
    return rows


BRAZILIAN_UF_CODES = {
    "AC", "AL", "AP", "AM", "BA", "CE", "DF", "ES", "GO", "MA", "MT", "MS",
    "MG", "PA", "PB", "PR", "PE", "PI", "RJ", "RN", "RS", "RO", "RR", "SC",
    "SP", "SE", "TO",
}


def _is_ranking_badge_line(line):
    """Identifica linhas de 'selo' ou de status do certame que aparecem
    entre o CNPJ e o nome da empresa em algumas telas de resultado do
    Compras.gov.br (ME/EPP, Equidade de gênero, Programa de integridade,
    Aceita, Habilitada etc.) — não fazem parte do nome da empresa e devem
    ser ignoradas. Bug real corrigido nesta versão: a palavra "Aceita" (um
    status de proposta, não um nome de empresa) estava sendo interpretada
    como se fosse a primeira colocada. Esta lista cobre os status mais
    comuns do portal — status novos que ainda não estejam aqui podem
    continuar entrando incorretamente como nome; se isso acontecer, é só
    avisar para incluirmos aqui."""
    cleaned = line.strip().strip("~").strip().upper()
    if "EQUIDADE DE G" in cleaned:  # cobre "GÊNERO"/"GENERO"
        return True
    if "PROGRAMA DE INTEGRIDADE" in cleaned:
        return True
    if cleaned in {"ME/EPP", "ME", "EPP", "MICROEMPRESA", "MEI"}:
        return True
    known_status_words = {
        "ACEITA", "ACEITO", "ACEITA PROVISORIAMENTE", "HABILITADA", "HABILITADO",
        "CONVOCADA", "CONVOCADO", "RECUSADA", "RECUSADO", "CANCELADA", "CANCELADO",
        "RECLASSIFICADA", "RECLASSIFICADO", "EM ANÁLISE", "EM ANALISE",
        "EM NEGOCIAÇÃO", "EM NEGOCIACAO", "NEGOCIAÇÃO", "NEGOCIACAO",
        "EMPATADA", "EMPATE", "EMPATADO", "AGUARDANDO JULGAMENTO",
        "AGUARDANDO ACEITAÇÃO", "AGUARDANDO ACEITACAO", "AGUARDANDO ENVIO DE ANEXO",
        "PROVISORIAMENTE VENCEDORA", "PROVISORIAMENTE VENCEDOR", "VENCEDORA", "VENCEDOR",
        "EM DISPUTA", "EM ANDAMENTO", "JULGADO", "JULGADO E HABILITADO",
    }
    if cleaned in known_status_words:
        return True
    # Cobre combinações desses mesmos status (ex.: "Aceita e habilitada",
    # "Julgado e habilitado (aberto para recursos)") — se, depois de tirar
    # os conectivos e o texto entre parênteses, tudo que sobra são status
    # conhecidos, a linha inteira é um selo, não um nome de empresa.
    without_parens = re.sub(r"\([^)]*\)", "", cleaned).strip()
    tokens = [t.strip() for t in re.split(r"\s+E\s+|/", without_parens) if t.strip()]
    return bool(tokens) and all(token in known_status_words for token in tokens)


def _ranking_situation_from_line(line):
    """Reconhece uma linha que indica a situação da empresa no certame
    (Desclassificada, Inabilitada, Desistente etc.), retornando a situação
    padronizada — ou None se a linha não for esse tipo de marcação. Bug
    corrigido nesta versão: antes, essa linha não era reconhecida e acabava
    virando parte do nome da empresa (ex.: a imagem saía com 'DESCLASSIFICADA'
    no lugar do nome)."""
    cleaned = line.strip().strip("~").strip().upper()
    if "DESCLASSIFICAD" in cleaned:
        return "DESCLASSIFICADA"
    if "INABILITAD" in cleaned:
        return "INABILITADA"
    if "DESISTEN" in cleaned:
        return "DESISTENTE"
    return None


_VALUE_WITH_PERCENT_PATTERN = re.compile(
    r"(?P<value>R\$\s*[\d.,]+)\s*(?:\(\s*(?P<percent>[\d.,]+)\s*%\s*\))?"
)


def parse_pasted_ranking_cards(text):
    """Reconhece o formato 'em cartões' de algumas telas de resultado do
    Compras.gov.br: um bloco de várias linhas por empresa, começando pelo
    CNPJ, com selos e situação opcionais, nome, UF e um conjunto de
    rótulos seguidos dos respectivos valores, na mesma ordem — por
    exemplo 'Valor ofertado (unitário)' / 'Valor negociado (unitário)',
    ou, em certames por técnica e preço (julgamento "Técnica e Preço",
    comum em Concorrência da Lei 14.133/2021), 'Nota técnica e preço' /
    'Valor ofertado (unitário)' / 'Valor negociado (unitário)'.

    A pontuação técnica (não é um valor em R$) é sempre ignorada para
    fins de classificação — o valor considerado é sempre o negociado,
    quando existir (diferente de "-"), senão o ofertado. Quando o
    rótulo indica valor "(unitário)", o valor extraído é multiplicado
    pela quantidade informada da licitação para chegar ao valor global
    — necessário porque o valor estimado cadastrado é sempre o total."""
    lines = [line.strip() for line in text.strip().splitlines() if line.strip()]
    cnpj_pattern = re.compile(r"^\d{2}\.\d{3}\.\d{3}/\d{4}-\d{2}$")
    block_starts = [index for index, line in enumerate(lines) if cnpj_pattern.fullmatch(line)]
    rows = []
    for position, start in enumerate(block_starts):
        end = block_starts[position + 1] if position + 1 < len(block_starts) else len(lines)
        block = lines[start + 1:end]
        cnpj = re.sub(r"\D", "", lines[start])
        situation = "CLASSIFICADA"
        content = []
        is_unit_value = False
        for line in block:
            found_situation = _ranking_situation_from_line(line)
            if found_situation:
                situation = found_situation
                continue
            if _is_ranking_badge_line(line):
                continue
            if "unit" in line.lower() and ("valor ofertado" in line.lower() or "valor negociado" in line.lower()):
                is_unit_value = True
            content.append(line)
        uf = None
        uf_index = None
        for index, line in enumerate(content):
            if len(line) == 2 and line.upper() in BRAZILIAN_UF_CODES:
                uf = line.upper()
                uf_index = index
                break
        if uf_index is not None:
            company = " ".join(content[:uf_index]).strip()
            remainder = content[uf_index + 1:]
        else:
            company = content[0].strip() if content else ""
            remainder = content[1:]

        # Os rótulos (ex.: "Nota técnica e preço", "Valor ofertado
        # (unitário)", "Valor negociado (unitário)") vêm todos primeiro,
        # seguidos pelos valores correspondentes na MESMA ordem — por
        # isso associamos cada rótulo ao valor na mesma posição, em vez
        # de simplesmente pegar "o primeiro valor sobrando", que
        # confundia a pontuação técnica com um valor em R$.
        label_kinds = []
        for line in remainder:
            lowered = line.lower()
            if "nota técnica" in lowered or "nota tecnica" in lowered:
                label_kinds.append("tecnica")
            elif "valor negociado" in lowered:
                label_kinds.append("negociado")
            elif "valor ofertado" in lowered:
                label_kinds.append("ofertado")
            else:
                break
        value_lines = remainder[len(label_kinds):len(label_kinds) * 2]

        parsed_values = {}
        technical_score = None
        for kind, value_line in zip(label_kinds, value_lines):
            if value_line == "-":
                continue
            if kind == "tecnica":
                try:
                    technical_score = float(
                        value_line.replace("R$", "").strip().replace(".", "").replace(",", ".")
                    )
                except ValueError:
                    technical_score = None
                continue
            match = _VALUE_WITH_PERCENT_PATTERN.search(value_line)
            if not match:
                continue
            try:
                parsed_values[kind] = (
                    parse_brazilian_number(match.group("value")),
                    match.group("percent"),
                )
            except ValueError:
                continue

        bid_value = None
        parsed_percent = None
        if "negociado" in parsed_values:
            bid_value, raw_percent = parsed_values["negociado"]
        elif "ofertado" in parsed_values:
            bid_value, raw_percent = parsed_values["ofertado"]
        else:
            raw_percent = None
        if raw_percent:
            try:
                parsed_percent = float(raw_percent.replace(",", "."))
            except ValueError:
                parsed_percent = None

        if not company:
            continue
        rows.append({
            "seq": position + 1,
            "company_name": company,
            "company_cnpj": cnpj,
            "final_bid_value": bid_value,
            "is_unit_value": is_unit_value,
            "parsed_discount_percent": parsed_percent,
            "situation": situation,
            "uf": uf,
            "technical_score": technical_score,
        })
    return rows


def parse_pasted_ranking_auto(text, estimated_value=None, quantity=None, is_confidential=False):
    """Detecta automaticamente o formato colado (linha única por empresa —
    inclusive o quadro do Licitações-e do Banco do Brasil, com colunas de
    segmento/porte e situação — vs. o formato em cartões do Compras.gov.br),
    converte valores unitários em globais quando necessário, recalcula o
    desconto a partir do valor estimado da licitação (com o percentual
    eventualmente colado servindo apenas de reserva, quando não há valor
    estimado cadastrado) e identifica a ENGEMIL automaticamente. A lista
    final é ordenada por valor de lance (do menor para o maior), com as
    empresas desclassificadas/inabilitadas/desistentes sempre no fim
    (também por valor), renumerando a sequência de 1 em diante. Quando a
    licitação é sigilosa (is_confidential=True), o desconto nunca é
    calculado — o valor estimado cadastrado é só uma referência interna,
    não uma base de comparação oficial válida até o órgão divulgar o valor
    de verdade."""
    lowered = text.lower()
    if "valor ofertado" in lowered or "valor negociado" in lowered:
        rows = parse_pasted_ranking_cards(text)
    else:
        rows = parse_pasted_ranking(text)
        for row in rows:
            row.setdefault("situation", "CLASSIFICADA")
            row.setdefault("is_unit_value", False)
            row.setdefault("technical_score", None)
            row["parsed_discount_percent"] = row.get("discount_percent")

    for row in rows:
        final_value = row.get("final_bid_value")
        if final_value and row.get("is_unit_value") and quantity:
            final_value = final_value * float(quantity)
        row["final_bid_value"] = final_value
        if is_confidential:
            row["discount_percent"] = None
        elif final_value and estimated_value:
            row["discount_percent"] = (1 - final_value / float(estimated_value)) * 100
        elif row.get("parsed_discount_percent") is not None:
            row["discount_percent"] = row["parsed_discount_percent"]
        else:
            row["discount_percent"] = None
        row["is_engemil"] = bool(
            row.get("company_cnpj") == COMPANY_CNPJ
            or "ENGEMIL" in row["company_name"].upper()
        )

    def _value_sort_key(row):
        value = row.get("final_bid_value")
        return (value is None, value or 0)

    classified = sorted(
        (r for r in rows if r.get("situation", "CLASSIFICADA") == "CLASSIFICADA"),
        key=_value_sort_key,
    )
    others = sorted(
        (r for r in rows if r.get("situation", "CLASSIFICADA") != "CLASSIFICADA"),
        key=_value_sort_key,
    )
    ordered = classified + others
    for index, row in enumerate(ordered):
        row["seq"] = index + 1
    return ordered


def selectbox_with_custom_option(label, options, key_prefix, current_value=None, help=None):
    """Combina uma lista de opções predefinidas com a possibilidade de
    digitar uma opção nova quando 'Outro' é escolhido — sempre com
    espaço para o portal/modalidade/modo de disputa mais incomum que
    ainda não esteja na lista. Precisa ficar FORA de um st.form para que
    o campo de texto apareça imediatamente ao escolher 'Outro', sem
    esperar o envio do formulário."""
    select_options = list(options)
    default_index = 0
    custom_default = ""
    if current_value and current_value not in select_options:
        custom_default = current_value
        outro_matches = [i for i, opt in enumerate(select_options) if opt.strip().upper() == "OUTRO"]
        default_index = outro_matches[0] if outro_matches else len(select_options) - 1
    elif current_value in select_options:
        default_index = select_options.index(current_value)
    choice = st.selectbox(label, select_options, index=default_index, key=f"{key_prefix}_select", help=help)
    if choice.strip().upper() == "OUTRO":
        custom = st.text_input(
            f"Digite: {label}", value=custom_default, key=f"{key_prefix}_custom",
        )
        return custom.strip() or "OUTRO"
    return choice


def bid_value_inputs(key_prefix, default_quantity=0.0, default_unit=0.0, default_total=0.0):
    """Campos de quantidade e valor estimado (unitário/total), com cálculo
    automático do total em tempo real. Precisam ficar FORA de qualquer
    st.form — formulários do Streamlit só recalculam ao serem enviados, e
    aqui o total precisa atualizar a cada tecla digitada, sem esperar o
    envio."""
    q1, q2 = st.columns(2)
    quantity = q1.number_input(
        "Quantidade solicitada", min_value=0.0, format="%.2f",
        value=float(default_quantity), key=f"{key_prefix}_qty",
    )
    unit_value = q2.number_input(
        "Valor estimado (unitário)", min_value=0.0, format="%.4f",
        value=float(default_unit), key=f"{key_prefix}_unit",
        help="Como aparece no edital, ex.: R$ 322,0300.",
    )
    suggested_total = quantity * unit_value
    auto_total = st.checkbox(
        "Calcular o valor total automaticamente (quantidade × valor unitário)",
        value=True, key=f"{key_prefix}_auto",
    )
    if auto_total:
        st.metric("Valor estimado (total)", brl(suggested_total))
        total_value = suggested_total
    else:
        total_value = st.number_input(
            "Valor estimado (total)", min_value=0.0, format="%.2f",
            value=float(default_total), key=f"{key_prefix}_total_manual",
            help="Preenchimento manual — desmarque a opção acima para digitar um valor "
            "diferente de quantidade × unitário.",
        )
    return quantity, unit_value, total_value


BID_LOT_TYPE_LABELS = {"GRUPO": "Grupo", "ITEM": "Item avulso"}


MONTH_NAMES_PT = {
    1: "Janeiro", 2: "Fevereiro", 3: "Março", 4: "Abril", 5: "Maio", 6: "Junho",
    7: "Julho", 8: "Agosto", 9: "Setembro", 10: "Outubro", 11: "Novembro", 12: "Dezembro",
}


def page_bids():
    st.title("Licitações")
    st.caption(
        "Acompanhamento das licitações em que a ENGEMIL está participando: "
        "valores, classificação e desdobramento para contrato."
    )
    all_processes = load_bid_processes()
    lots_by_process = load_bid_lots_by_process()
    total_open = sum(1 for p in all_processes if p["status"] == "EM ANDAMENTO")
    total_won = sum(1 for p in all_processes if p["status"] == "HOMOLOGADA - VENCEDORA")
    total_concluded = sum(1 for p in all_processes if p["status"] not in {"EM ANDAMENTO", "SUSPENSA"})
    success_rate = (total_won / total_concluded * 100) if total_concluded else 0
    open_aggregates = [
        bid_process_aggregate_values(p, lots_by_process.get(p["id"], []))
        for p in all_processes if p["status"] == "EM ANDAMENTO"
    ]
    estimated_open = sum(float(a["estimated_value"] or 0) for a in open_aggregates)
    bid_open = sum(float(a["our_bid_value"] or 0) for a in open_aggregates if a["our_bid_value"])
    responsive_cards([
        ("Em andamento", str(total_open), "Disputas abertas ou aguardando resultado", "amber"),
        ("Vencidas (homologadas)", str(total_won), f"Taxa de sucesso: {success_rate:.0f}%", "green"),
        ("Valor estimado em disputa", brl(estimated_open), "Soma dos processos em andamento", "blue"),
        ("Valor de lance em disputa", brl(bid_open), "Nossa proposta nos processos em andamento", "blue"),
    ])

    with st.expander("Consultar contratações publicadas no PNCP", expanded=False):
        st.caption(
            "Consulta pública e gratuita ao Portal Nacional de Contratações Públicas. "
            "Não traz o mapa de lances/classificação de uma disputa em andamento — apenas "
            "editais publicados e, quando já concluídos, o resultado homologado. Útil para "
            "localizar e conferir processos antes de cadastrá-los abaixo."
        )
        pc1, pc2, pc3 = st.columns(3)
        pncp_start = pc1.date_input("Publicados a partir de", value=today_brt() - timedelta(days=30))
        pncp_end = pc2.date_input("Até", value=today_brt())
        pncp_modality = pc3.selectbox(
            "Modalidade", list(PNCP_MODALIDADES), format_func=lambda code: f"{code} — {PNCP_MODALIDADES[code]}",
            index=list(PNCP_MODALIDADES).index(6),
        )
        pc4, pc5 = st.columns(2)
        pncp_uf = pc4.text_input("UF (opcional)", max_chars=2, placeholder="Ex.: DF")
        pncp_cnpj = pc5.text_input("CNPJ do órgão (opcional)", placeholder="Somente números")
        if st.button("Buscar no PNCP"):
            try:
                result = pncp_search_contratacoes(
                    pncp_start, pncp_end, pncp_modality,
                    uf=pncp_uf.strip().upper() or None,
                    cnpj_orgao=re.sub(r"\D", "", pncp_cnpj) or None,
                )
            except PncpError as error:
                st.error(str(error))
            else:
                items = result["itens"]
                if not items:
                    st.info("Nenhuma contratação encontrada para os filtros informados.")
                else:
                    st.success(f"{result['total']} contratação(ões) encontrada(s) — exibindo até 50 nesta página.")
                    preview = pd.DataFrame([
                        {
                            "Órgão": item.get("orgaoEntidade", {}).get("razaoSocial"),
                            "Objeto": item.get("objetoCompra"),
                            "Modalidade": item.get("modalidadeNome"),
                            "Valor estimado": brl(item.get("valorTotalEstimado")),
                            "Publicação": item.get("dataPublicacaoPncp"),
                            "Nº controle PNCP": item.get("numeroControlePNCP"),
                        }
                        for item in items[:50]
                    ])
                    modern_table(preview, max_height=360)

    if can_edit():
        with st.expander("Notificação diária de licitações do dia"):
            st.caption(
                "Todo dia útil às 6h50, o sistema envia um quadro com as licitações que têm "
                "disputa marcada para o dia (dia, hora, UASG, nº da licitação, órgão, "
                "escopo, estrutura, objeto e valor estimado) para os e-mails cadastrados "
                "abaixo. Sem licitação marcada para o dia, nenhum e-mail é enviado."
            )
            recipients = [
                dict(row) for row in query(
                    "SELECT * FROM bid_schedule_recipients ORDER BY active DESC,email"
                )
            ]
            if recipients:
                modern_table(pd.DataFrame([{
                    "E-mail": row["email"],
                    "Status": "ATIVO" if row["active"] else "INATIVO",
                } for row in recipients]))
                remove_options = {row["email"]: row["id"] for row in recipients}
                rc1, rc2 = st.columns([3, 1])
                remove_label = rc1.selectbox(
                    "E-mail para remover ou reativar/pausar", remove_options,
                    key="bid_schedule_recipient_target",
                )
                target_id = remove_options[remove_label]
                target_row = next(row for row in recipients if row["id"] == target_id)
                with rc2:
                    st.write("")
                    st.write("")
                    if st.button(
                        "Pausar" if target_row["active"] else "Reativar",
                        key="toggle_bid_schedule_recipient",
                    ):
                        execute(
                            "UPDATE bid_schedule_recipients SET active=? WHERE id=?",
                            (0 if target_row["active"] else 1, target_id),
                        )
                        rerun()
                if st.button("Remover este e-mail definitivamente", key="delete_bid_schedule_recipient"):
                    execute("DELETE FROM bid_schedule_recipients WHERE id=?", (target_id,))
                    log_action(user["id"], "REMOVER", "destinatário licitações do dia", target_id, remove_label)
                    st.success("E-mail removido.")
                    rerun()
            else:
                st.info("Nenhum e-mail cadastrado ainda para receber a notificação diária.")
            with st.form("new_bid_schedule_recipient", clear_on_submit=True):
                new_recipient_email = st.text_input("Adicionar e-mail")
                if st.form_submit_button("Adicionar"):
                    normalized = new_recipient_email.strip().lower()
                    if not re.fullmatch(r"[^\s@]+@[^\s@]+\.[^\s@]+", normalized):
                        st.error("Informe um endereço de e-mail válido.")
                    else:
                        try:
                            execute(
                                "INSERT INTO bid_schedule_recipients(email) VALUES(?)",
                                (normalized,),
                            )
                            log_action(user["id"], "CADASTRAR", "destinatário licitações do dia", None, normalized)
                            st.success("E-mail cadastrado.")
                            rerun()
                        except Exception:
                            st.error("Este e-mail já está cadastrado.")

    st.divider()
    st.subheader("Carteira de licitações")
    f1, f2, f3, f4 = st.columns(4)
    status_filter = f1.multiselect("Status", BID_STATUSES, default=[], placeholder="Selecione...")
    platform_filter = f2.multiselect("Plataforma", BID_PLATFORMS, default=[], placeholder="Selecione...")
    scope_filter = f3.multiselect("Escopo", BID_SCOPE_OPTIONS, default=[], placeholder="Selecione...")
    text_filter = f4.text_input("Pesquisar por órgão, processo ou objeto")

    month_keys = sorted(
        {p["dispute_date"][:7] for p in all_processes if p.get("dispute_date")}, reverse=True,
    )
    month_options = ["(Personalizado — usar as datas abaixo)"] + month_keys

    def _format_month_option(key):
        if key.startswith("("):
            return key
        year_part, month_part = key.split("-")
        return f"{MONTH_NAMES_PT[int(month_part)]}/{year_part}"

    f1, f2, f3 = st.columns([1.3, 1, 1])
    selected_month = f1.selectbox(
        "Mês do certame (atalho)", month_options, format_func=_format_month_option,
        key="bid_filter_month",
        help="Escolha um mês já cadastrado para preencher as datas de/até ao lado "
        "automaticamente — você ainda pode ajustá-las manualmente depois.",
    )
    if not selected_month.startswith("(") and st.session_state.get("bid_filter_month_applied") != selected_month:
        year_selected, month_selected = map(int, selected_month.split("-"))
        st.session_state["bid_filter_date_from"] = date(year_selected, month_selected, 1)
        st.session_state["bid_filter_date_to"] = date(
            year_selected, month_selected, calendar.monthrange(year_selected, month_selected)[1],
        )
        st.session_state["bid_filter_month_applied"] = selected_month
    date_from = f2.date_input(
        "Data da disputa — de", value=None, format="DD/MM/YYYY", key="bid_filter_date_from",
    )
    date_to = f3.date_input(
        "Data da disputa — até", value=None, format="DD/MM/YYYY", key="bid_filter_date_to",
    )
    filtered = all_processes
    if status_filter:
        filtered = [p for p in filtered if p["status"] in status_filter]
    if platform_filter:
        filtered = [p for p in filtered if p["platform"] in platform_filter]
    if scope_filter:
        filtered = [p for p in filtered if p.get("scope") in scope_filter]
    if date_from or date_to:
        def _in_date_range(process_row):
            raw_date = process_row.get("dispute_date")
            if not raw_date:
                return False
            try:
                parsed_date = date.fromisoformat(str(raw_date)[:10])
            except ValueError:
                return False
            if date_from and parsed_date < date_from:
                return False
            if date_to and parsed_date > date_to:
                return False
            return True
        filtered = [p for p in filtered if _in_date_range(p)]
    if text_filter:
        needle = text_filter.casefold()
        filtered = [
            p for p in filtered
            if needle in " ".join(str(v or "") for v in p.values()).casefold()
        ]
    if filtered:
        listing_rows = []
        for p in filtered:
            process_lots = lots_by_process.get(p["id"], [])
            aggregate = bid_process_aggregate_values(p, process_lots)
            listing_rows.append({
                "Disputa": fmt_date(p["dispute_date"]) + (f" {p['dispute_time']}" if p.get("dispute_time") else ""),
                "Nº da licitação": p.get("edital_number") or p["process_number"],
                "UASG": p.get("uasg") or "—",
                "Órgão": p["agency"],
                "Escopo": p.get("scope") or "—",
                "Estrutura": aggregate["structure_label"],
                "Plataforma": p["platform"],
                "Status": p["status"],
                "Valor estimado": format_estimated_value_display(aggregate),
                "Nosso lance": brl(aggregate["our_bid_value"]) if aggregate["our_bid_value"] else "—",
                "Desconto": format_discount_display(aggregate["our_discount_percent"]),
                "Classificação": p["our_ranking"] or "—",
            })
        listing = pd.DataFrame(listing_rows)
        modern_table(listing, max_height=420)

        with st.expander("Exportar licitações do filtro atual em PDF (A4 horizontal, 1 página)"):
            st.caption(
                "Escolha as colunas que devem aparecer no relatório. O PDF ajusta "
                "automaticamente o tamanho das linhas para caber tudo numa página só, "
                "no mesmo padrão do Backlog oficial — só pagina se isso tornar o texto "
                "ilegível."
            )
            column_labels = {
                key: label for key, (label, _, _, _) in BID_PDF_COLUMN_CATALOG.items()
            }
            default_columns = [
                key for key in [
                    "process_number", "uasg", "agency", "scope", "structure", "object",
                    "estimated_value", "our_bid_value",
                    "our_discount_percent", "status", "dispute_date",
                ]
                if key in column_labels
            ]
            selected_columns = st.multiselect(
                "Colunas do relatório", list(column_labels),
                default=default_columns, format_func=lambda key: column_labels[key],
                key="bid_pdf_columns", placeholder="Selecione...",
            )
            if st.button("Gerar PDF", key="generate_bid_pdf"):
                if not selected_columns:
                    st.error("Selecione ao menos uma coluna.")
                else:
                    active_logo = LOGO_DARK_PATH if LOGO_DARK_PATH.exists() else None
                    pdf_rows = []
                    for p in filtered:
                        aggregate = bid_process_aggregate_values(p, lots_by_process.get(p["id"], []))
                        pdf_rows.append({
                            **p,
                            "estimated_value": format_estimated_value_for_pdf(aggregate),
                            "our_bid_value": aggregate["our_bid_value"],
                            "our_discount_percent": aggregate["our_discount_percent"],
                            "structure": aggregate["structure_label"],
                        })
                    pdf_bytes = generate_bid_processes_pdf(
                        pdf_rows, selected_columns, logo_path=active_logo,
                        report_subtitle=f"{len(filtered)} licitação(ões) no filtro selecionado",
                    )
                    st.download_button(
                        "Baixar Licitações vigentes em PDF",
                        pdf_bytes,
                        file_name=f"Licitacoes_ENGEMIL_{today_brt().isoformat()}.pdf",
                        mime="application/pdf",
                        key="download_bid_pdf",
                    )
    else:
        st.info("Nenhuma licitação encontrada para os filtros atuais.")

    st.divider()
    if can_create():
        with st.expander("Cadastrar nova licitação", expanded=not all_processes):
            structure_choice = st.radio(
                "Como este certame será cadastrado?",
                [
                    "Individual (um único item para todo o certame)",
                    "Vários itens individuais (mesmo processo, cada item com sua própria "
                    "classificação, sem agrupamento)",
                    "Grupo(s) com itens (cada grupo reúne vários itens, e a classificação é "
                    "pelo valor total do grupo)",
                ],
                key="new_bid_structure",
                help="Mesma lógica do Compras.gov.br: um pregão pode ter um único item, vários "
                "itens avulsos (cada um disputado e classificado separadamente), ou ser dividido "
                "em grupos — cada grupo reúne vários itens, e embora a fase de lances seja item "
                "por item, quem vence é decidido pelo valor TOTAL do grupo inteiro, não pelos "
                "itens isolados. Escolha do mesmo jeito que o certame está estruturado no portal.",
            )
            uses_lots = not structure_choice.startswith("Individual")
            if uses_lots:
                if structure_choice.startswith("Grupo"):
                    st.session_state["new_bid_default_lot_type"] = "GRUPO"
                    st.caption(
                        "Cadastre os dados gerais abaixo. Depois de salvar, a licitação já fica "
                        "selecionada e você cadastra cada grupo na aba **Grupos/Itens** (ex.: "
                        "\"Grupo 1\", \"Grupo 2\"...) — dentro de cada grupo, adiciona os itens "
                        "que ele reúne (Item 1, Item 2...), cada um com sua quantidade e valor "
                        "estimado unitário. O valor do grupo inteiro é somado automaticamente a "
                        "partir dos itens, e é esse total que vale na classificação."
                    )
                else:
                    st.session_state["new_bid_default_lot_type"] = "ITEM"
                    st.caption(
                        "Cadastre os dados gerais abaixo. Depois de salvar, a licitação já fica "
                        "selecionada e você cadastra cada item avulso na aba **Grupos/Itens** — "
                        "cada um com sua própria quantidade, valor estimado e classificação, sem "
                        "agrupar (diferente do modo \"Grupo(s) com itens\", aqui cada item "
                        "concorre e é classificado separadamente)."
                    )
                quantity = estimated_unit_value = estimated_value = None
            else:
                st.caption("Quantidade e valores estimados (calculados automaticamente):")
                quantity, estimated_unit_value, estimated_value = bid_value_inputs("new_bid_process")

            npc1, npc2, npc3 = st.columns(3)
            platform = selectbox_with_custom_option(
                "Plataforma", BID_PLATFORMS, "new_bid_platform",
            )
            modality = selectbox_with_custom_option(
                "Modalidade da licitação", BID_MODALITIES, "new_bid_modality",
                help="Modalidades da Lei 14.133/2021, com espaço para digitar outra caso "
                "surja uma modalidade diferente.",
            )
            dispute_mode = selectbox_with_custom_option(
                "Modo de disputa", BID_DISPUTE_MODES, "new_bid_dispute_mode",
            )

            npc1, npc2 = st.columns(2)
            edital_number = npc1.text_input(
                "Edital/pregão", key="new_bid_edital_number",
                help="Junto com a UASG, é usado para detectar se este certame já foi cadastrado.",
            )
            uasg = npc2.text_input(
                "UASG", key="new_bid_uasg",
                help="Essencial para localizar o processo no Compras.gov.br/PNCP — e, junto "
                "com o Edital, para detectar duplicatas.",
            )
            duplicate_matches = []
            if edital_number.strip() and uasg.strip():
                duplicate_matches = [
                    p for p in all_processes
                    if (p.get("edital_number") or "").strip().casefold() == edital_number.strip().casefold()
                    and (p.get("uasg") or "").strip().casefold() == uasg.strip().casefold()
                ]
            confirm_duplicate = True
            if duplicate_matches:
                match_list = "; ".join(
                    f"{m['process_number']} · {m['agency']} · status: {m['status']}"
                    for m in duplicate_matches
                )
                st.warning(
                    f"⚠️ Já existe {'uma licitação cadastrada' if len(duplicate_matches) == 1 else f'{len(duplicate_matches)} licitações cadastradas'} "
                    f"com este mesmo Edital + UASG: {match_list}. Confira se não é a "
                    "mesma licitação antes de continuar — pode ser um cadastro em duplicidade."
                )
                confirm_duplicate = st.checkbox(
                    "Confirmo que não é duplicada — quero cadastrar mesmo assim (ex.: certame "
                    "republicado com o mesmo número, ou uma segunda fase do mesmo edital)",
                    key="new_bid_confirm_duplicate",
                )

            with st.form("new_bid_process", clear_on_submit=True):
                process_number = st.text_input("Número do processo *")
                st.caption(f"Edital/pregão: **{edital_number or '—'}** · UASG: **{uasg or '—'}**")
                agency = st.text_input("Órgão/contratante *")
                n1, n2 = st.columns(2)
                agency_cnpj = n1.text_input(
                    "CNPJ do órgão", placeholder="Somente números",
                    help="Digite só os números — o sistema formata sozinho ao salvar. "
                    "Preenchendo este campo, o sistema consegue verificar automaticamente "
                    "no PNCP se o processo foi homologado em favor da ENGEMIL.",
                )
                pncp_control_number = n2.text_input(
                    "Nº de controle PNCP",
                    help="Se você já souber o número de controle no PNCP, preencha aqui — "
                    "não precisa esperar terminar o cadastro para voltar e preencher depois.",
                )
                object_text = st.text_area("Objeto")
                n1, n2, n3 = st.columns(3)
                uf = n1.selectbox("UF", [""] + BID_UF_OPTIONS, format_func=lambda v: v or "—")
                scope = n2.selectbox("Escopo", BID_SCOPE_OPTIONS)
                status = n3.selectbox("Status", BID_STATUSES)
                n1, n2 = st.columns(2)
                dispute_date = n1.date_input("Data da disputa", value=None, format="DD/MM/YYYY")
                dispute_time_value = n2.time_input("Horário da disputa", value=None)
                n1, n2 = st.columns(2)
                responsible_name = n1.text_input(
                    "Responsável pelo acompanhamento", value=user.get("name") or "",
                )
                responsible_email = n2.text_input(
                    "E-mail do responsável", value=user.get("email") or "",
                )
                is_confidential = st.checkbox(
                    "Licitação sigilosa (valor estimado ainda não divulgado pelo órgão)",
                    help="Marque quando o órgão ainda não tornou público o valor estimado do "
                    "certame — comum em algumas modalidades até a fase de lances terminar. "
                    "Pode ser desmarcada a qualquer momento, assim que o valor for divulgado "
                    "(a classificação recalcula o desconto automaticamente ao salvar de novo). "
                    "O valor que você cadastrar abaixo, enquanto sigiloso, é tratado como "
                    "referência interna — não é usado para calcular desconto.",
                )
                notes = st.text_area("Observações")
                if st.form_submit_button("Cadastrar licitação", width="stretch"):
                    if not process_number.strip() or not agency.strip():
                        st.error("Preencha ao menos o número do processo e o órgão.")
                    elif status == "SUSPENSA" and not notes.strip():
                        st.error(
                            "Preencha o campo Observações explicando o motivo da suspensão — "
                            "esse texto vai junto no e-mail de licitações do dia para avisar os "
                            "gestores."
                        )
                    elif duplicate_matches and not confirm_duplicate:
                        st.error(
                            "Este Edital + UASG já está cadastrado (veja o aviso acima). Marque "
                            "a confirmação de que não é duplicada, logo acima do formulário, para "
                            "poder cadastrar mesmo assim."
                        )
                    else:
                        final_estimated_value = (
                            (estimated_value or (quantity * estimated_unit_value)) if not uses_lots else 0
                        )
                        new_id = execute(
                            """INSERT INTO bid_processes(
                            process_number,edital_number,uasg,platform,agency,agency_cnpj,uf,object,modality,
                            scope,quantity,estimated_unit_value,estimated_value,status,dispute_date,
                            dispute_time,dispute_mode,responsible_name,responsible_email,notes,
                            pncp_control_number,is_confidential,created_by)
                            VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                            (
                                process_number.strip(), edital_number.strip(), uasg.strip() or None,
                                platform,
                                normalize_agency_name(agency), re.sub(r"\D", "", agency_cnpj) or None,
                                uf or None,
                                object_text.strip(), modality, scope,
                                (quantity or None) if not uses_lots else None,
                                (estimated_unit_value or None) if not uses_lots else None,
                                final_estimated_value, status,
                                dispute_date.isoformat() if dispute_date else None,
                                dispute_time_value.strftime("%H:%M") if dispute_time_value else None,
                                dispute_mode,
                                responsible_name.strip() or None, responsible_email.strip() or None,
                                notes.strip() or None, pncp_control_number.strip() or None,
                                1 if is_confidential else 0, user["id"],
                            ),
                        )
                        log_action(user["id"], "CADASTRAR", "licitação", new_id, process_number)
                        for reset_key in (
                            "new_bid_process_qty", "new_bid_process_unit",
                            "new_bid_edital_number", "new_bid_uasg", "new_bid_confirm_duplicate",
                        ):
                            st.session_state.pop(reset_key, None)
                        st.session_state["just_created_bid_id"] = new_id
                        if uses_lots:
                            st.session_state["just_created_bid_open_lots"] = True
                        st.success("Licitação cadastrada — role a página para vê-la selecionada abaixo.")
                        rerun()

    if not filtered:
        st.info(
            "Nenhuma licitação corresponde aos filtros acima — ajuste o filtro de mês/data "
            "ou os demais filtros da Carteira de licitações para abrir uma licitação específica."
        )
        return

    st.subheader("Detalhe e classificação")
    options = {
        f"{p.get('edital_number') or p['process_number']} · UASG {p.get('uasg') or 's/n'} · {p['agency']}": p["id"]
        for p in filtered
    }
    default_label = next(
        (label for label, pid in options.items() if pid == st.session_state.get("just_created_bid_id")),
        None,
    )
    selected_label = st.selectbox(
        "Abrir licitação", list(options),
        index=list(options).index(default_label) if default_label else 0,
        help="Esta lista já respeita os filtros da Carteira de licitações acima (Status, "
        "Plataforma, Escopo, Mês do certame, datas, pesquisa por texto) — estreite os filtros "
        "para achar mais rápido uma licitação de um mês específico.",
    )
    bid_id = options[selected_label]
    process = next(p for p in filtered if p["id"] == bid_id)
    if st.session_state.pop("just_created_bid_id", None) == bid_id:
        st.success(
            "Licitação cadastrada e já selecionada abaixo. Se este certame tiver mais de um "
            "grupo ou item (ex.: \"Grupo 1 · 3 itens\"), cadastre-os agora na aba **Grupos/Itens** "
            "logo abaixo — senão, pode ir direto para a aba **Classificação**."
        )

    detail_tabs = st.tabs(["Resumo e edição", "Grupos/Itens", "Classificação", "Documentos do PNCP"])
    lots = load_bid_lots(bid_id)
    with detail_tabs[0]:
        st.write(f"**Objeto:** {process['object'] or 'Não informado'}")
        aggregate = bid_process_aggregate_values(process, lots)
        st.caption(f"Estrutura do certame: **{aggregate['structure_label']}**")
        if process.get("is_confidential"):
            st.warning(
                "🔒 Licitação sigilosa — o valor estimado ainda não foi divulgado pelo órgão. "
                "O valor abaixo é só uma referência interna, por isso o desconto não é "
                "calculado. Assim que o órgão divulgar o valor oficial, desmarque a opção "
                "\"Licitação sigilosa\" logo abaixo e salve — a classificação recalcula o "
                "desconto sozinha."
            )
        if lots:
            st.caption(
                "Os valores abaixo são a soma automática de todos os grupos/itens "
                "cadastrados na aba Grupos/Itens — o detalhamento de cada um continua lá."
            )
        d1, d2, d3 = st.columns(3)
        d1.metric(
            "Valor estimado" + (" (referência interna)" if process.get("is_confidential") else ""),
            brl(aggregate["estimated_value"]),
        )
        d2.metric("Nosso lance", brl(aggregate["our_bid_value"]) if aggregate["our_bid_value"] else "—")
        d3.metric("Desconto aplicado", format_discount_display(aggregate["our_discount_percent"]))
        if can_edit():
            st.caption("Quantidade e valores estimados (calculados automaticamente):")
            edit_quantity, edit_estimated_unit_value, edit_estimated_value_number = bid_value_inputs(
                f"edit_bid_{bid_id}",
                default_quantity=process.get("quantity") or 0,
                default_unit=process.get("estimated_unit_value") or 0,
                default_total=process.get("estimated_value") or 0,
            )
            edp1, edp2, edp3 = st.columns(3)
            with edp1:
                edit_platform = selectbox_with_custom_option(
                    "Plataforma", BID_PLATFORMS, f"edit_bid_platform_{bid_id}",
                    current_value=process["platform"],
                )
            with edp2:
                edit_modality = selectbox_with_custom_option(
                    "Modalidade da licitação", BID_MODALITIES, f"edit_bid_modality_{bid_id}",
                    current_value=process.get("modality"),
                )
            with edp3:
                edit_dispute_mode = selectbox_with_custom_option(
                    "Modo de disputa", BID_DISPUTE_MODES, f"edit_bid_dispute_mode_{bid_id}",
                    current_value=process.get("dispute_mode"),
                )
            with st.form(f"edit_bid_{bid_id}"):
                st.caption(
                    "Todos os campos abaixo podem ser completados ou corrigidos a qualquer "
                    "momento — útil quando alguma informação ficou pendente no cadastro inicial."
                )
                e1, e2, e3 = st.columns(3)
                edit_process_number = e1.text_input(
                    "Número do processo *", process["process_number"] or ""
                )
                edit_edital_number = e2.text_input(
                    "Edital/pregão", process["edital_number"] or ""
                )
                edit_uasg = e3.text_input(
                    "UASG", process.get("uasg") or "",
                    help="Essencial para localizar o processo no Compras.gov.br/PNCP.",
                )
                edit_agency = st.text_input("Órgão/contratante *", process["agency"] or "")
                edit_object = st.text_area("Objeto", process["object"] or "")
                e1, e2, e3 = st.columns(3)
                edit_uf = e1.selectbox(
                    "UF", [""] + BID_UF_OPTIONS, format_func=lambda v: v or "—",
                    index=([""] + BID_UF_OPTIONS).index(process["uf"]) if process.get("uf") in BID_UF_OPTIONS else 0,
                )
                edit_scope = e2.selectbox(
                    "Escopo", BID_SCOPE_OPTIONS,
                    index=_option_index(BID_SCOPE_OPTIONS, process.get("scope")),
                )
                edit_status = e3.selectbox(
                    "Status", BID_STATUSES, index=_option_index(BID_STATUSES, process["status"]),
                )
                e1, e2 = st.columns(2)
                edit_bid_value = currency_input(
                    e1, "Nosso lance final", process["our_bid_value"], f"bid_value_{bid_id}"
                )
                edit_ranking = e2.number_input(
                    "Classificação (posição)", min_value=0, step=1,
                    value=int(process["our_ranking"] or 0),
                )
                e1, e2 = st.columns(2)
                edit_dispute_date = e1.date_input(
                    "Data da disputa",
                    value=date.fromisoformat(process["dispute_date"][:10]) if process["dispute_date"] else None,
                    format="DD/MM/YYYY",
                )
                _existing_time = None
                if process.get("dispute_time"):
                    try:
                        _existing_time = datetime.strptime(process["dispute_time"], "%H:%M").time()
                    except ValueError:
                        _existing_time = None
                edit_dispute_time_value = e2.time_input("Horário da disputa", value=_existing_time)
                e1, e2 = st.columns(2)
                edit_responsible_name = e1.text_input(
                    "Responsável pelo acompanhamento", process["responsible_name"] or ""
                )
                edit_responsible_email = e2.text_input(
                    "E-mail do responsável", process["responsible_email"] or ""
                )
                e1, e2 = st.columns(2)
                edit_pncp = e1.text_input("Nº de controle PNCP", process["pncp_control_number"] or "")
                edit_agency_cnpj = e2.text_input(
                    "CNPJ do órgão", format_cnpj(process.get("agency_cnpj")),
                    help="Digite só os números — o sistema formata sozinho ao salvar "
                    "(XX.XXX.XXX/XXXX-XX). Necessário para a verificação automática de "
                    "homologação no PNCP, abaixo.",
                )
                edit_is_confidential = st.checkbox(
                    "Licitação sigilosa (valor estimado ainda não divulgado pelo órgão)",
                    value=bool(process.get("is_confidential")),
                    help="Desmarque assim que o órgão divulgar o valor — a classificação passa "
                    "a calcular o desconto normalmente na próxima vez que você salvá-la.",
                )
                linked_contract_options = {"Nenhum": None, **{
                    f"{c['cost_center']} · {c['contract_number'] or 's/n'}": c["id"]
                    for c in query("SELECT id,cost_center,contract_number FROM contracts WHERE archived=0")
                }}
                current_contract_label = next(
                    (label for label, cid in linked_contract_options.items() if cid == process["contract_id"]),
                    "Nenhum",
                )
                linked_label = st.selectbox(
                    "Vincular a um contrato já cadastrado",
                    list(linked_contract_options),
                    index=list(linked_contract_options).index(current_contract_label),
                )
                edit_notes = st.text_area("Observações", process["notes"] or "")
                if st.form_submit_button("Salvar alterações"):
                    try:
                        bid_value = parse_brazilian_number(edit_bid_value, default=None) if edit_bid_value.strip() else None
                    except ValueError:
                        st.error(
                            "Informe os valores no padrão brasileiro, por exemplo: R$ 15.400.330,93."
                        )
                    else:
                        if not edit_process_number.strip() or not edit_agency.strip():
                            st.error("Preencha ao menos o número do processo e o órgão.")
                        elif edit_status == "SUSPENSA" and not edit_notes.strip():
                            st.error(
                                "Preencha o campo Observações explicando o motivo da suspensão — "
                                "esse texto vai junto no e-mail de licitações do dia para avisar "
                                "os gestores."
                            )
                        else:
                            estimated_value = edit_estimated_value_number or None
                            discount = None
                            if bid_value and estimated_value:
                                discount = (1 - bid_value / estimated_value) * 100
                            if edit_is_confidential:
                                discount = None
                            execute(
                                """UPDATE bid_processes SET process_number=?,edital_number=?,uasg=?,platform=?,
                                agency=?,object=?,uf=?,modality=?,scope=?,quantity=?,estimated_unit_value=?,
                                estimated_value=?,
                                status=?,our_bid_value=?,our_discount_percent=?,
                                our_ranking=?,dispute_date=?,dispute_time=?,dispute_mode=?,
                                responsible_name=?,responsible_email=?,
                                pncp_control_number=?,agency_cnpj=?,contract_id=?,notes=?,
                                is_confidential=?,
                                updated_at=CURRENT_TIMESTAMP WHERE id=?""",
                                (
                                    edit_process_number.strip(), edit_edital_number.strip() or None,
                                    edit_uasg.strip() or None,
                                    edit_platform, normalize_agency_name(edit_agency),
                                    edit_object.strip() or None, edit_uf or None,
                                    edit_modality, edit_scope, edit_quantity or None,
                                    edit_estimated_unit_value or None,
                                    estimated_value or 0,
                                    edit_status, bid_value, discount,
                                    edit_ranking or None,
                                    edit_dispute_date.isoformat() if edit_dispute_date else None,
                                    edit_dispute_time_value.strftime("%H:%M") if edit_dispute_time_value else None,
                                    edit_dispute_mode,
                                    edit_responsible_name.strip() or None, edit_responsible_email.strip() or None,
                                    edit_pncp.strip() or None,
                                    re.sub(r"\D", "", edit_agency_cnpj) or None,
                                    linked_contract_options[linked_label],
                                    edit_notes.strip() or None, 1 if edit_is_confidential else 0, bid_id,
                                ),
                            )
                            log_action(user["id"], "EDITAR", "licitação", bid_id, edit_process_number)
                            st.success("Licitação atualizada.")
                            rerun()

        st.divider()
        st.markdown("**Verificar homologação automaticamente no PNCP**")
        st.caption(
            "Consulta os contratos publicados por ESTE órgão (usando o CNPJ acima) num "
            "período e confere se algum foi firmado com o CNPJ da ENGEMIL. Funciona apenas "
            "para processos já homologados/publicados — não detecta disputas em andamento, "
            "porque o PNCP não permite buscar por CNPJ do fornecedor, só por CNPJ do órgão."
        )
        if not process.get("agency_cnpj"):
            st.info("Preencha o CNPJ do órgão acima e salve para habilitar esta verificação.")
        else:
            vc1, vc2 = st.columns(2)
            check_start = vc1.date_input(
                "Publicados a partir de", value=today_brt() - timedelta(days=180),
                key=f"check_start_{bid_id}",
            )
            check_end = vc2.date_input("Até", value=today_brt(), key=f"check_end_{bid_id}")
            if st.button("Verificar no PNCP", key=f"check_pncp_{bid_id}"):
                try:
                    matches = pncp_check_awarded_contracts(
                        process["agency_cnpj"], check_start, check_end, cnpj_fornecedor=COMPANY_CNPJ,
                    )
                except PncpError as error:
                    st.error(str(error))
                else:
                    if not matches:
                        st.info(
                            "Nenhum contrato desse órgão, no período informado, foi encontrado "
                            "em nome da ENGEMIL. Isso pode significar que o processo ainda não "
                            "foi homologado/publicado, ou que o período não cobre a data certa."
                        )
                    else:
                        for match in matches:
                            st.success(
                                f"Contrato {match.get('numeroContratoEmpenho')} encontrado — "
                                f"valor global {brl(match.get('valorGlobal'))}, "
                                f"assinado em {match.get('dataAssinatura')}."
                            )
                            if st.button(
                                "Marcar esta licitação como vencida com estes dados",
                                key=f"apply_match_{bid_id}_{match.get('numeroControlePNCP')}",
                            ):
                                execute(
                                    """UPDATE bid_processes SET status='HOMOLOGADA - VENCEDORA',
                                    our_bid_value=?,pncp_control_number=?,updated_at=CURRENT_TIMESTAMP
                                    WHERE id=?""",
                                    (
                                        match.get("valorGlobal"),
                                        match.get("numeroControlePNCP"),
                                        bid_id,
                                    ),
                                )
                                log_action(
                                    user["id"], "EDITAR", "licitação (homologação PNCP)",
                                    bid_id, process["process_number"],
                                )
                                st.success("Licitação atualizada com os dados do PNCP.")
                                rerun()

        if can_delete():
            st.divider()
            with st.expander("Excluir esta licitação"):
                st.warning(
                    "Isso remove definitivamente esta licitação, seus grupos/itens e toda a "
                    "classificação associada. Use quando a ENGEMIL desistir de participar ou o "
                    "cadastro tiver sido feito por engano — não use para registrar uma disputa "
                    "perdida (nesse caso, mude o Status acima para refletir o resultado)."
                )
                confirm_delete_bid = st.checkbox(
                    f"Confirmo a exclusão de {process['process_number']}", key=f"confirm_delete_bid_{bid_id}",
                )
                if st.button(
                    "Excluir licitação definitivamente", disabled=not confirm_delete_bid,
                    key=f"delete_bid_{bid_id}",
                ):
                    execute("DELETE FROM bid_processes WHERE id=?", (bid_id,))
                    log_action(user["id"], "EXCLUIR", "licitação", bid_id, process["process_number"])
                    st.success("Licitação excluída.")
                    rerun()

    with detail_tabs[1]:
        st.caption(
            "Use esta aba quando o certame tiver mais de um grupo/item — por exemplo, "
            "\"Grupo 1 · 5 itens\" e \"Grupo 2 · 3 itens\" no mesmo pregão, cada um com valor "
            "estimado e classificação próprios (igual ao Compras.gov.br). Cadastre um "
            "grupo/item para cada linha do portal. Se o certame tiver um único item, não "
            "precisa cadastrar nada aqui — a classificação continua na aba ao lado, associada "
            "diretamente à licitação."
        )
        if lots:
            lots_df = pd.DataFrame([
                {
                    "Grupo/Item": lot["label"],
                    "Tipo": BID_LOT_TYPE_LABELS.get(lot.get("lot_type"), "Item avulso"),
                    "Qtd. itens": lot["item_count"] or "—",
                    "Valor est. total": brl(lot["estimated_value"]),
                    "Nosso lance": brl(lot["our_bid_value"]) if lot["our_bid_value"] else "—",
                    "Desconto": format_discount_display(lot["our_discount_percent"]),
                    "Classificação": lot["our_ranking"] or "—",
                }
                for lot in lots
            ])
            modern_table(lots_df, max_height=300)
        if can_edit():
            with st.expander(
                "Cadastrar novo grupo/item",
                expanded=not lots or st.session_state.pop("just_created_bid_open_lots", False),
            ):
                lc1, lc2 = st.columns(2)
                lot_label = lc1.text_input(
                    "Nome do grupo/item *", placeholder='Ex.: "Grupo 1" ou "Item 3 - Revestimento Piso"',
                    key=f"new_lot_label_{bid_id}",
                )
                lot_type = lc2.selectbox(
                    "Tipo", list(BID_LOT_TYPE_LABELS), format_func=lambda key: BID_LOT_TYPE_LABELS[key],
                    index=list(BID_LOT_TYPE_LABELS).index(
                        st.session_state.get("new_bid_default_lot_type", "GRUPO")
                    ),
                    key=f"new_lot_type_{bid_id}",
                    help="Grupo: reúne vários itens, e a classificação/valor é do grupo inteiro. "
                    "Item avulso: um item sozinho, fora de qualquer grupo.",
                )
                st.caption(
                    "Se souber só o valor total do grupo/item, preencha abaixo. Se preferir "
                    "detalhar item por item (como no exemplo do Compras.gov.br: LUMINÁRIA, "
                    "LÂMPADA LED etc.), deixe em 0 aqui e cadastre os itens depois de salvar — "
                    "o total passa a ser somado automaticamente a partir deles."
                )
                lot_quantity, lot_unit_value, lot_total_value = bid_value_inputs(f"new_bid_lot_{bid_id}")
                with st.form(f"new_bid_lot_{bid_id}", clear_on_submit=True):
                    lot_notes = st.text_area("Observações", key=f"lot_notes_{bid_id}")
                    if st.form_submit_button("Cadastrar grupo/item"):
                        if not lot_label.strip():
                            st.error("Dê um nome ao grupo/item.")
                        else:
                            final_total = lot_total_value or (lot_quantity * lot_unit_value)
                            new_lot_id = execute(
                                """INSERT INTO bid_lots(
                                bid_process_id,label,lot_type,quantity,estimated_unit_value,
                                estimated_value,notes) VALUES(?,?,?,?,?,?,?)""",
                                (
                                    bid_id, lot_label.strip(), lot_type,
                                    lot_quantity or None, lot_unit_value or None,
                                    final_total, lot_notes.strip() or None,
                                ),
                            )
                            log_action(user["id"], "CADASTRAR", "grupo/item de licitação", new_lot_id, lot_label)
                            for reset_key in (
                                f"new_lot_label_{bid_id}",
                                f"new_bid_lot_{bid_id}_qty", f"new_bid_lot_{bid_id}_unit",
                            ):
                                st.session_state.pop(reset_key, None)
                            st.session_state[f"open_lot_id_{bid_id}"] = new_lot_id
                            st.success(
                                "Grupo/item cadastrado. Se quiser detalhar item por item, abra "
                                "\"Editar, detalhar itens ou excluir um grupo/item\" logo abaixo."
                            )
                            rerun()
            if lots:
                with st.expander(
                    "Editar, detalhar itens ou excluir um grupo/item",
                    expanded=bool(st.session_state.get(f"open_lot_id_{bid_id}")),
                ):
                    lot_options = {lot["label"]: lot["id"] for lot in lots}
                    just_opened_lot_id = st.session_state.pop(f"open_lot_id_{bid_id}", None)
                    default_lot_label = next(
                        (label for label, lid in lot_options.items() if lid == just_opened_lot_id), None,
                    )
                    chosen_label = st.selectbox(
                        "Grupo/item", list(lot_options), key=f"edit_lot_select_{bid_id}",
                        index=list(lot_options).index(default_lot_label) if default_lot_label else 0,
                    )
                    chosen_lot = next(lot for lot in lots if lot["id"] == lot_options[chosen_label])
                    e1, e2 = st.columns(2)
                    e_label = e1.text_input(
                        "Nome do grupo/item", chosen_lot["label"], key=f"edit_lot_label_{chosen_lot['id']}",
                    )
                    e_type = e2.selectbox(
                        "Tipo", list(BID_LOT_TYPE_LABELS), format_func=lambda key: BID_LOT_TYPE_LABELS[key],
                        index=list(BID_LOT_TYPE_LABELS).index(chosen_lot.get("lot_type") or "ITEM"),
                        key=f"edit_lot_type_{chosen_lot['id']}",
                    )

                    st.markdown("##### Itens deste grupo/item (opcional — detalhamento como no portal)")
                    st.caption(
                        "Preencha uma linha por item/material, com a quantidade solicitada e o "
                        "valor unitário — igual ao exemplo do Compras.gov.br (LUMINÁRIA, LÂMPADA "
                        "LED, PLUGUE etc.). O valor estimado e o nosso valor ofertado deste "
                        "grupo/item passam a ser a soma automática destas linhas."
                    )
                    lot_items = load_bid_lot_items(chosen_lot["id"])
                    editor_nonce_key = f"lot_items_editor_nonce_{chosen_lot['id']}"
                    generated_rows_key = f"lot_items_generated_{chosen_lot['id']}"
                    st.session_state.setdefault(editor_nonce_key, 0)
                    if not lot_items:
                        gen1, gen2 = st.columns([1, 3])
                        gen_n = gen1.number_input(
                            "Gerar quantos itens?", min_value=0, max_value=50, step=1, value=0,
                            key=f"gen_item_count_{chosen_lot['id']}",
                            help='Cria linhas em branco já nomeadas "Item 1", "Item 2"... para '
                            "você só preencher quantidade e valores — do jeito mais rápido de "
                            "detalhar um grupo com vários itens.",
                        )
                        if gen2.button("Gerar linhas", key=f"gen_items_btn_{chosen_lot['id']}") and gen_n:
                            # Não é permitido reatribuir o valor de um widget já renderizado
                            # via st.session_state — em vez disso, guardamos as linhas geradas
                            # numa chave própria e damos ao data_editor uma chave nova (nonce),
                            # para o Streamlit tratá-lo como um widget "novo" e aceitar o valor
                            # inicial preenchido abaixo.
                            st.session_state[generated_rows_key] = pd.DataFrame([
                                {
                                    "Item": f"Item {i}", "Quantidade": 0.0,
                                    "Valor estimado (unitário)": 0.0,
                                    "Nosso valor ofertado (unitário)": None,
                                }
                                for i in range(1, int(gen_n) + 1)
                            ])
                            st.session_state[editor_nonce_key] += 1
                            rerun()
                    if lot_items:
                        items_df = pd.DataFrame([
                            {
                                "Item": it["item_name"], "Quantidade": it["quantity"],
                                "Valor estimado (unitário)": it["estimated_unit_value"],
                                "Nosso valor ofertado (unitário)": it["offered_unit_value"],
                            }
                            for it in lot_items
                        ])
                    elif generated_rows_key in st.session_state:
                        # Não usar .pop() aqui: o Streamlit reexecuta o script inteiro a cada
                        # interação (inclusive ao clicar em "Salvar itens" depois), então essas
                        # linhas geradas precisam continuar disponíveis em toda nova execução até
                        # os itens serem realmente salvos no banco — só então são descartadas.
                        items_df = st.session_state[generated_rows_key]
                    else:
                        items_df = pd.DataFrame(
                            columns=["Item", "Quantidade", "Valor estimado (unitário)", "Nosso valor ofertado (unitário)"]
                        )
                    edited_items = st.data_editor(
                        items_df, num_rows="dynamic", width="stretch", hide_index=True,
                        key=f"lot_items_editor_{chosen_lot['id']}_{st.session_state[editor_nonce_key]}",
                        column_config={
                            "Quantidade": st.column_config.NumberColumn("Quantidade", min_value=0.0, format="%.2f"),
                            "Valor estimado (unitário)": st.column_config.NumberColumn(
                                "Valor estimado (unitário)", min_value=0.0, format="%.4f",
                            ),
                            "Nosso valor ofertado (unitário)": st.column_config.NumberColumn(
                                "Nosso valor ofertado (unitário)", min_value=0.0, format="%.4f",
                            ),
                        },
                    )
                    live_estimated_total = 0.0
                    live_offered_total = 0.0
                    has_offered = False
                    for _, item_row in edited_items.fillna(0).iterrows():
                        item_qty = float(item_row.get("Quantidade") or 0)
                        live_estimated_total += item_qty * float(item_row.get("Valor estimado (unitário)") or 0)
                        offered_raw = item_row.get("Nosso valor ofertado (unitário)")
                        if offered_raw not in (None, 0, "0", ""):
                            has_offered = True
                            live_offered_total += item_qty * float(offered_raw or 0)
                    im1, im2 = st.columns(2)
                    im1.metric("Valor estimado do grupo/item (soma dos itens)", brl(live_estimated_total))
                    im2.metric(
                        "Nosso valor ofertado do grupo/item (soma dos itens)",
                        brl(live_offered_total) if has_offered else "—",
                    )
                    if st.button("Salvar itens deste grupo/item", key=f"save_lot_items_{chosen_lot['id']}"):
                        execute("DELETE FROM bid_lot_items WHERE bid_lot_id=?", (chosen_lot["id"],))
                        for _, item_row in edited_items.fillna("").iterrows():
                            item_name = str(item_row.get("Item", "")).strip()
                            if not item_name:
                                continue
                            offered_raw = item_row.get("Nosso valor ofertado (unitário)")
                            execute(
                                """INSERT INTO bid_lot_items(
                                bid_lot_id,item_name,quantity,estimated_unit_value,offered_unit_value)
                                VALUES(?,?,?,?,?)""",
                                (
                                    chosen_lot["id"], item_name,
                                    float(item_row.get("Quantidade") or 0),
                                    float(item_row.get("Valor estimado (unitário)") or 0),
                                    float(offered_raw) if offered_raw not in ("", None) else None,
                                ),
                            )
                        recompute_bid_lot_totals(chosen_lot["id"])
                        log_action(
                            user["id"], "EDITAR", "itens de grupo/item de licitação",
                            chosen_lot["id"], chosen_lot["label"],
                        )
                        st.session_state.pop(generated_rows_key, None)
                        st.success("Itens salvos — o valor do grupo/item foi recalculado automaticamente.")
                        rerun()

                    st.markdown("##### Valor total do grupo/item (sem detalhar por item)")
                    st.caption(
                        "Só preencha aqui se você NÃO cadastrou itens acima — se já cadastrou, o "
                        "total já é calculado sozinho a partir deles."
                    )
                    e_quantity, e_unit_value, e_total_value = bid_value_inputs(
                        f"edit_bid_lot_{chosen_lot['id']}",
                        default_quantity=chosen_lot["quantity"] or 0,
                        default_unit=chosen_lot["estimated_unit_value"] or 0,
                        default_total=chosen_lot["estimated_value"] or 0,
                    )
                    with st.form(f"edit_bid_lot_{chosen_lot['id']}"):
                        e_notes = st.text_area("Observações", chosen_lot["notes"] or "")
                        col_save, col_delete = st.columns(2)
                        if col_save.form_submit_button("Salvar alterações", width="stretch"):
                            has_items = bool(load_bid_lot_items(chosen_lot["id"]))
                            final_total = chosen_lot["estimated_value"] if has_items else (
                                e_total_value or (e_quantity * e_unit_value)
                            )
                            execute(
                                """UPDATE bid_lots SET label=?,lot_type=?,quantity=?,
                                estimated_unit_value=?,estimated_value=?,notes=?,
                                updated_at=CURRENT_TIMESTAMP WHERE id=?""",
                                (
                                    e_label.strip(), e_type,
                                    (e_quantity or None) if not has_items else chosen_lot["quantity"],
                                    (e_unit_value or None) if not has_items else chosen_lot["estimated_unit_value"],
                                    final_total, e_notes.strip() or None,
                                    chosen_lot["id"],
                                ),
                            )
                            log_action(user["id"], "EDITAR", "grupo/item de licitação", chosen_lot["id"], e_label)
                            st.success("Grupo/item atualizado.")
                            rerun()
                        if col_delete.form_submit_button(
                            "Excluir este grupo/item", width="stretch", type="secondary",
                        ):
                            execute("DELETE FROM bid_lots WHERE id=?", (chosen_lot["id"],))
                            log_action(
                                user["id"], "EXCLUIR", "grupo/item de licitação",
                                chosen_lot["id"], chosen_lot["label"],
                            )
                            st.success("Grupo/item excluído (os itens e a classificação associada também foram removidos).")
                            rerun()

    with detail_tabs[2]:
        rankings_scope_options = {"Licitação inteira (sem grupos/itens)": None}
        rankings_scope_options.update({lot["label"]: lot["id"] for lot in lots})
        if len(rankings_scope_options) > 1:
            scope_label = st.selectbox(
                "Qual grupo/item deseja classificar?", list(rankings_scope_options),
                key=f"ranking_scope_{bid_id}",
            )
        else:
            scope_label = "Licitação inteira (sem grupos/itens)"
        selected_lot_id = rankings_scope_options[scope_label]
        selected_lot = next((lot for lot in lots if lot["id"] == selected_lot_id), None) if selected_lot_id else None
        ranking_scope_estimated_value = (
            selected_lot["estimated_value"] if selected_lot else process.get("estimated_value")
        )
        ranking_scope_quantity = selected_lot["quantity"] if selected_lot else process.get("quantity")

        rankings = load_bid_rankings(bid_id, bid_lot_id=selected_lot_id)
        process_is_confidential = bool(process.get("is_confidential"))
        if process_is_confidential:
            st.warning(
                "🔒 Esta licitação está marcada como sigilosa — o desconto não será calculado "
                "até o órgão divulgar o valor estimado oficial e a opção \"Licitação sigilosa\" "
                "(aba Resumo e edição) ser desmarcada."
            )
        st.caption(
            "Cole a classificação copiada do portal (Compras.gov.br, PNCP, Portal de Compras "
            "Públicas, Licitações-e do Banco do Brasil etc.) ou edite manualmente. O desconto "
            "é sempre recalculado automaticamente a partir do valor estimado desta licitação. "
            "A linha da ENGEMIL é destacada automaticamente na imagem gerada; ajuste a "
            "situação se alguma empresa for desclassificada ao longo do certame."
        )
        if can_edit():
            with st.expander("Colar classificação copiada do portal", expanded=not rankings):
                st.caption(
                    "Copie a tabela (ou o painel de propostas) do portal e cole abaixo. "
                    "O sistema reconhece tanto uma linha por empresa (sequência, empresa, "
                    "segmento/porte, situação, lance, data/hora — como no Licitações-e do "
                    "Banco do Brasil) quanto o formato em blocos do Compras.gov.br (CNPJ, "
                    "selos, nome, UF, 'Valor ofertado'/'Valor negociado'). A lista final é "
                    "sempre reordenada pelo valor do lance (menor para o maior), com "
                    "desclassificadas/inabilitadas/desistentes ao final. Confira o resultado "
                    "antes de continuar — o desconto é sempre recalculado a partir do valor "
                    f"estimado deste grupo/item ({brl(ranking_scope_estimated_value)})."
                )
                if not ranking_scope_estimated_value:
                    st.warning(
                        f"{'Este grupo/item' if selected_lot else 'Esta licitação'} ainda não tem "
                        "valor estimado preenchido — sem ele, o desconto não pode ser calculado "
                        "automaticamente (cai de reserva para o percentual eventualmente colado, "
                        "se houver)."
                    )
                if not ranking_scope_quantity:
                    st.caption(
                        "💡 Se o edital informa o valor por unidade (não pelo total), preencha "
                        "a quantidade "
                        + ("deste grupo/item (aba Grupos/Itens)" if selected_lot else "desta licitação (aba Resumo e edição)")
                        + " antes de colar — sem ela, o sistema não converte o lance unitário em valor global."
                    )
                pasted_text = st.text_area(
                    "Colar aqui", key=f"paste_ranking_{bid_id}_{selected_lot_id or 0}", height=110,
                    placeholder="1\tA FORCA COMERCIAL E SERVICOS LTDA\tR$ 658.597,28\n2\tAXIONTEK LTDA\tR$ 665.249,78",
                )
                if st.button("Processar texto colado", key=f"parse_paste_{bid_id}_{selected_lot_id or 0}"):
                    parsed_rows = parse_pasted_ranking_auto(
                        pasted_text, estimated_value=ranking_scope_estimated_value,
                        quantity=ranking_scope_quantity, is_confidential=process_is_confidential,
                    )
                    if not parsed_rows:
                        st.warning(
                            "Não consegui reconhecer nenhuma linha nesse texto. Confira se cada "
                            "linha/bloco tem ao menos o nome da empresa e um valor."
                        )
                    else:
                        delete_bid_rankings(bid_id, bid_lot_id=selected_lot_id)
                        for row in parsed_rows:
                            execute(
                                """INSERT INTO bid_rankings(
                                bid_process_id,bid_lot_id,seq,company_name,company_cnpj,final_bid_value,
                                discount_percent,technical_score,situation,is_engemil)
                                VALUES(?,?,?,?,?,?,?,?,?,?)""",
                                (
                                    bid_id, selected_lot_id, row["seq"], row["company_name"], row["company_cnpj"],
                                    row["final_bid_value"], row["discount_percent"], row.get("technical_score"),
                                    row["situation"], 1 if row["is_engemil"] else 0,
                                ),
                            )
                        apply_engemil_ranking_to_process(bid_id, parsed_rows, bid_lot_id=selected_lot_id)
                        log_action(
                            user["id"], "EDITAR", "classificação de licitação (colada)",
                            bid_id, process["process_number"],
                        )
                        st.success(
                            f"{len(parsed_rows)} linha(s) reconhecida(s) e salva(s). Se a ENGEMIL "
                            "estava na lista, "
                            + ("este grupo/item" if selected_lot else "a aba Resumo e edição")
                            + " já foi atualizado com nosso lance, desconto e classificação."
                        )
                        rerun()
        ranking_df = pd.DataFrame([
            {
                "SEQ": r["seq"], "Empresa": r["company_name"],
                "CNPJ": r.get("company_cnpj") or "",
                "Lance final": brl(r["final_bid_value"]) if r["final_bid_value"] is not None else "",
                "Desconto (%)": r["discount_percent"],
                "Nota técnica": r.get("technical_score"),
                "Situação": r.get("situation") or "CLASSIFICADA",
                "ENGEMIL?": bool(r["is_engemil"]),
            }
            for r in rankings
        ]) if rankings else pd.DataFrame(
            columns=["SEQ", "Empresa", "CNPJ", "Lance final", "Desconto (%)", "Nota técnica", "Situação", "ENGEMIL?"]
        )
        if can_edit():
            edited = st.data_editor(
                ranking_df, num_rows="dynamic", width="stretch", hide_index=True,
                key=f"ranking_editor_{bid_id}_{selected_lot_id or 0}",
                column_config={
                    "SEQ": st.column_config.NumberColumn("SEQ", min_value=1, step=1),
                    "CNPJ": st.column_config.TextColumn("CNPJ", help="Somente números ou com máscara."),
                    "Lance final": st.column_config.TextColumn(
                        "Lance final", default="R$ 0,00",
                        help="Informe no padrão brasileiro, por exemplo: R$ 15.400.330,93.",
                    ),
                    "Desconto (%)": st.column_config.NumberColumn("Desconto (%)", format="%.2f%%"),
                    "Nota técnica": st.column_config.NumberColumn(
                        "Nota técnica", format="%.2f",
                        help="Só se aplica a certames julgados por Técnica e Preço — deixe em "
                        "branco nos demais casos.",
                    ),
                    "Situação": st.column_config.SelectboxColumn("Situação", options=RANKING_SITUATIONS),
                    "ENGEMIL?": st.column_config.CheckboxColumn("ENGEMIL?"),
                },
            )
            if st.button("Salvar classificação", key=f"save_ranking_{bid_id}_{selected_lot_id or 0}"):
                delete_bid_rankings(bid_id, bid_lot_id=selected_lot_id)
                save_error = False
                saved_rows = []
                for _, row in edited.fillna("").iterrows():
                    company = str(row.get("Empresa", "")).strip()
                    if not company:
                        continue
                    try:
                        bid_text = str(row.get("Lance final", "")).strip()
                        final_bid_value = parse_brazilian_number(bid_text, default=None) if bid_text else None
                    except ValueError:
                        st.error(
                            f"Lance final inválido para '{company}'. Use o padrão brasileiro, "
                            "por exemplo: R$ 17.710.330,93."
                        )
                        save_error = True
                        break
                    row_is_engemil = bool(row.get("ENGEMIL?"))
                    row_seq = int(row.get("SEQ") or 0)
                    row_discount = (
                        None if process_is_confidential
                        else (float(row.get("Desconto (%)")) if row.get("Desconto (%)") not in ("", None) else None)
                    )
                    row_technical_score = (
                        float(row.get("Nota técnica")) if row.get("Nota técnica") not in ("", None) else None
                    )
                    execute(
                        """INSERT INTO bid_rankings(
                        bid_process_id,bid_lot_id,seq,company_name,company_cnpj,final_bid_value,
                        discount_percent,technical_score,situation,is_engemil)
                        VALUES(?,?,?,?,?,?,?,?,?,?)""",
                        (
                            bid_id,
                            selected_lot_id,
                            row_seq,
                            company,
                            str(row.get("CNPJ", "")).strip() or None,
                            final_bid_value,
                            row_discount,
                            row_technical_score,
                            row.get("Situação") or "CLASSIFICADA",
                            1 if row_is_engemil else 0,
                        ),
                    )
                    saved_rows.append({
                        "is_engemil": row_is_engemil, "final_bid_value": final_bid_value,
                        "discount_percent": row_discount, "seq": row_seq,
                    })
                if not save_error:
                    apply_engemil_ranking_to_process(bid_id, saved_rows, bid_lot_id=selected_lot_id)
                    log_action(user["id"], "EDITAR", "classificação de licitação", bid_id, process["process_number"])
                    st.success("Classificação salva.")
                    rerun()
        else:
            modern_table(ranking_df, max_height=360)

        if rankings:
            active_logo = LOGO_DARK_PATH if LOGO_DARK_PATH.exists() else None
            image_process = dict(process)
            image_process["estimated_value"] = ranking_scope_estimated_value
            if selected_lot:
                image_process["object"] = f"{selected_lot['label']} — {process.get('object') or ''}".strip(" —")
            image_bytes = generate_ranking_image(image_process, rankings, logo_path=active_logo)
            st.image(image_bytes, caption="Pré-visualização da imagem de classificação (identidade ENGEMIL)")
            file_suffix = f"_{safe_filename(selected_lot['label'])}" if selected_lot else ""
            acronym = extract_agency_acronym(process.get("agency") or "") or safe_filename(process.get("agency") or "ORGAO")
            certame_number = (process.get("edital_number") or process.get("process_number") or "SN").replace("/", "-")
            uasg_part = f"_{process['uasg']}" if process.get("uasg") else ""
            download_file_name = f"CLASS_{safe_filename(acronym)}_{safe_filename(certame_number)}{uasg_part}{file_suffix}.png"
            st.download_button(
                "Baixar imagem para enviar aos gestores",
                image_bytes,
                file_name=download_file_name,
                mime="image/png",
                key=f"download_ranking_image_{bid_id}_{selected_lot_id or 0}",
            )
        else:
            st.info("Cadastre a classificação para poder gerar a imagem.")

    with detail_tabs[3]:
        st.caption(
            "Busca automática, sem custo, dos documentos do edital publicados no PNCP "
            "(edital, termo de referência, anexos, minuta) a partir do Número de "
            "controle PNCP cadastrado — sem precisar navegar no portal do PNCP à mão. "
            "Para pedir uma análise de viabilidade sobre esses documentos, baixe-os "
            "aqui e peça diretamente ao Claude no chat, informando a licitação."
        )
        pncp_number = str(process.get("pncp_control_number") or "").strip()
        if not pncp_number:
            st.warning(
                "Esta licitação ainda não tem **Número de controle PNCP** cadastrado. "
                "Preencha-o na aba **Resumo e edição** (mais abaixo, ao editar o "
                "processo) e salve — sem ele não é possível buscar os documentos "
                "automaticamente."
            )
        elif not parse_pncp_control_number(pncp_number):
            st.error(
                f"O Número de controle PNCP cadastrado (\"{pncp_number}\") não está no "
                "formato esperado (00000000000000-1-000000/0000). Corrija-o na aba "
                "Resumo e edição."
            )
        else:
            if st.button("Buscar documentos no PNCP", key=f"pncp_fetch_btn_{bid_id}"):
                with st.spinner("Buscando documentos no PNCP..."):
                    try:
                        zip_bytes, filenames = build_pncp_documents_zip(pncp_number)
                        st.session_state[f"pncp_zip_{bid_id}"] = {
                            "bytes": zip_bytes, "filenames": filenames,
                        }
                    except Exception as error:
                        st.session_state.pop(f"pncp_zip_{bid_id}", None)
                        st.error(f"Não foi possível buscar os documentos: {error}")
            cached_zip = st.session_state.get(f"pncp_zip_{bid_id}")
            if cached_zip:
                st.success(
                    f"{len(cached_zip['filenames'])} documento(s) encontrado(s): " +
                    ", ".join(cached_zip["filenames"])
                )
                st.download_button(
                    "Baixar documentos (.zip)",
                    cached_zip["bytes"],
                    file_name=f"edital_pncp_{safe_filename(pncp_number)}.zip",
                    mime="application/zip",
                    key=f"pncp_zip_download_{bid_id}",
                )


SESMT_EXAM_TYPES = [
    "ADMISSIONAL", "PERIÓDICO", "DEMISSIONAL", "MUDANÇA DE FUNÇÃO",
    "RETORNO AO TRABALHO",
]
SESMT_EXAM_RESULTS = ["APTO", "APTO COM RESTRIÇÃO", "INAPTO"]
SESMT_PROFESSIONAL_STATUSES = ["ATIVO", "AFASTADO", "DESLIGADO"]
SESMT_TRAINING_SUGGESTIONS = [
    "NR-06 - Equipamento de Proteção Individual (EPI)",
    "NR-10 - Segurança em Instalações e Serviços em Eletricidade",
    "NR-11 - Operação de Empilhadeiras/Transporte de Materiais",
    "NR-12 - Segurança no Trabalho em Máquinas e Equipamentos",
    "NR-18 - Condições de Segurança no Trabalho na Indústria da Construção",
    "NR-33 - Espaços Confinados",
    "NR-35 - Trabalho em Altura",
    "Brigada de Incêndio",
    "Outro (digitar abaixo)",
]


def load_sesmt_professionals(where_clause=""):
    sql = f"""SELECT p.*, c.cost_center, c.client, c.contract_number
        FROM sesmt_professionals p
        JOIN contracts c ON c.id = p.contract_id
        {where_clause}
        ORDER BY p.full_name"""
    return [dict(row) for row in query(sql)]


def load_sesmt_exams(professional_id):
    return [
        dict(row) for row in query(
            "SELECT * FROM sesmt_exams WHERE professional_id=? ORDER BY exam_date DESC, id DESC",
            (professional_id,),
        )
    ]


def load_sesmt_trainings(professional_id):
    return [
        dict(row) for row in query(
            "SELECT * FROM sesmt_trainings WHERE professional_id=? ORDER BY issue_date DESC, id DESC",
            (professional_id,),
        )
    ]


def sesmt_validity_caption(valid_until):
    days = days_until(valid_until)
    if valid_until is None or days is None:
        return "Sem validade registrada"
    if days < 0:
        return f"⚠️ Vencido há {abs(days)} dia(s)"
    if days <= 30:
        return f"⏳ Vence em {days} dia(s)"
    return f"Válido — vence em {days} dia(s)"


def page_sesmt():
    st.title("SESMT")
    st.caption(
        "Controle de exames ocupacionais e treinamentos/certificados dos profissionais "
        "acompanhados pelo Serviço Especializado em Engenharia de Segurança e em Medicina "
        "do Trabalho, associados aos contratos da ENGEMIL."
    )
    all_professionals = load_sesmt_professionals()
    professional_ids = [p["id"] for p in all_professionals]
    today_iso = today_brt().isoformat()
    soon_iso = (today_brt() + timedelta(days=30)).isoformat()
    if professional_ids:
        placeholders = ",".join("?" * len(professional_ids))
        expired_exams = query(
            f"""SELECT COUNT(*) n FROM sesmt_exams
            WHERE professional_id IN ({placeholders}) AND valid_until IS NOT NULL AND valid_until<?""",
            (*professional_ids, today_iso),
        )[0]["n"]
        soon_exams = query(
            f"""SELECT COUNT(*) n FROM sesmt_exams
            WHERE professional_id IN ({placeholders}) AND valid_until IS NOT NULL
            AND valid_until>=? AND valid_until<=?""",
            (*professional_ids, today_iso, soon_iso),
        )[0]["n"]
        expired_trainings = query(
            f"""SELECT COUNT(*) n FROM sesmt_trainings
            WHERE professional_id IN ({placeholders}) AND valid_until IS NOT NULL AND valid_until<?""",
            (*professional_ids, today_iso),
        )[0]["n"]
        soon_trainings = query(
            f"""SELECT COUNT(*) n FROM sesmt_trainings
            WHERE professional_id IN ({placeholders}) AND valid_until IS NOT NULL
            AND valid_until>=? AND valid_until<=?""",
            (*professional_ids, today_iso, soon_iso),
        )[0]["n"]
    else:
        expired_exams = soon_exams = expired_trainings = soon_trainings = 0
    active_count = sum(1 for p in all_professionals if p["status"] == "ATIVO")
    responsive_cards([
        ("Profissionais ativos", str(active_count), f"{len(all_professionals)} cadastrado(s) no total", "blue"),
        ("Exames vencidos", str(expired_exams), "ASO com validade expirada", "red" if expired_exams else "green"),
        ("Exames vencendo em 30 dias", str(soon_exams), "Agende com antecedência", "amber" if soon_exams else "green"),
        (
            "Treinamentos/NRs vencidos ou vencendo",
            str(expired_trainings + soon_trainings),
            f"{expired_trainings} vencido(s) · {soon_trainings} nos próximos 30 dias",
            "red" if expired_trainings else ("amber" if soon_trainings else "green"),
        ),
    ])

    st.divider()
    st.subheader("Profissionais acompanhados")
    f1, f2, f3 = st.columns(3)
    status_filter = f1.multiselect("Status", SESMT_PROFESSIONAL_STATUSES, default=[], placeholder="Selecione...")
    contract_filter_options = {
        f"{p['cost_center']} · {p['client']}": p["contract_id"] for p in all_professionals
    }
    contract_filter = f2.multiselect("Contrato", list(dict.fromkeys(contract_filter_options)), default=[], placeholder="Selecione...")
    text_filter = f3.text_input("Pesquisar por nome ou cargo")
    filtered = all_professionals
    if status_filter:
        filtered = [p for p in filtered if p["status"] in status_filter]
    if contract_filter:
        wanted_ids = {contract_filter_options[label] for label in contract_filter}
        filtered = [p for p in filtered if p["contract_id"] in wanted_ids]
    if text_filter:
        needle = text_filter.casefold()
        filtered = [
            p for p in filtered
            if needle in (p["full_name"] or "").casefold() or needle in (p["role_title"] or "").casefold()
        ]
    if filtered:
        rows_for_table = []
        for professional in filtered:
            exams = load_sesmt_exams(professional["id"])
            trainings = load_sesmt_trainings(professional["id"])
            next_exam_due = min(
                (e["valid_until"] for e in exams if e["valid_until"]), default=None
            )
            next_training_due = min(
                (t["valid_until"] for t in trainings if t["valid_until"]), default=None
            )
            rows_for_table.append({
                "Nome": professional["full_name"],
                "Cargo": professional["role_title"] or "—",
                "Contrato": f"{professional['cost_center']} · {professional['client']}",
                "Status": professional["status"],
                "Próximo exame vence": fmt_date(next_exam_due) if next_exam_due else "—",
                "Próximo treinamento vence": fmt_date(next_training_due) if next_training_due else "—",
            })
        modern_table(pd.DataFrame(rows_for_table), max_height=380)
    else:
        st.info("Nenhum profissional encontrado para os filtros atuais.")

    st.divider()
    if can_create():
        with st.expander("Cadastrar novo profissional", expanded=not all_professionals):
            prefill_contract_id = contract_selector("Contrato vinculado")
            roster = query(
                "SELECT id,full_name,role_title FROM contract_employees WHERE contract_id=? ORDER BY full_name",
                (prefill_contract_id,),
            ) if prefill_contract_id else []
            if roster:
                roster_options = {"(preencher manualmente)": None}
                roster_options.update({
                    f"{r['full_name']} · {r['role_title'] or 's/ cargo'}": r["id"] for r in roster
                })
                roster_label = st.selectbox(
                    "Importar dados de um funcionário já cadastrado na equipe deste contrato (opcional)",
                    list(roster_options), key="sesmt_roster_pick",
                )
                if roster_options[roster_label] and st.button("Usar estes dados no formulário abaixo"):
                    chosen_employee = next(r for r in roster if r["id"] == roster_options[roster_label])
                    st.session_state["sesmt_new_full_name"] = chosen_employee["full_name"]
                    st.session_state["sesmt_new_role_title"] = chosen_employee["role_title"] or ""
                    rerun()
            with st.form("new_sesmt_professional", clear_on_submit=True):
                new_contract_id = prefill_contract_id
                n1, n2 = st.columns(2)
                full_name = n1.text_input("Nome completo *", key="sesmt_new_full_name")
                cpf = n2.text_input("CPF")
                n1, n2, n3 = st.columns(3)
                role_title = n1.text_input("Cargo/função", key="sesmt_new_role_title")
                admission_date = n2.date_input("Data de admissão", value=None, format="DD/MM/YYYY")
                status = n3.selectbox("Status", SESMT_PROFESSIONAL_STATUSES)
                notes = st.text_area("Observações")
                if st.form_submit_button("Cadastrar profissional", width="stretch"):
                    if not full_name.strip() or not new_contract_id:
                        st.error("Preencha ao menos o nome completo e o contrato vinculado.")
                    else:
                        new_id = execute(
                            """INSERT INTO sesmt_professionals(
                            contract_id,full_name,cpf,role_title,admission_date,status,notes,created_by)
                            VALUES(?,?,?,?,?,?,?,?)""",
                            (
                                new_contract_id, full_name.strip(), cpf.strip() or None,
                                role_title.strip() or None,
                                admission_date.isoformat() if admission_date else None,
                                status, notes.strip() or None, st.session_state.user["id"],
                            ),
                        )
                        log_action(st.session_state.user["id"], "CADASTRAR", "profissional SESMT", new_id, full_name)
                        st.success("Profissional cadastrado.")
                        rerun()

    if not all_professionals:
        return

    st.subheader("Ficha do profissional")
    options = {
        f"{p['full_name']} · {p['cost_center']}": p["id"] for p in all_professionals
    }
    selected_label = st.selectbox("Abrir profissional", list(options))
    professional_id = options[selected_label]
    professional = next(p for p in all_professionals if p["id"] == professional_id)

    detail_tabs = st.tabs(["Dados e edição", "Exames ocupacionais (ASO)", "Treinamentos e certificados"])

    with detail_tabs[0]:
        d1, d2, d3 = st.columns(3)
        d1.metric("Contrato", f"{professional['cost_center']}")
        d2.metric("Status", professional["status"])
        d3.metric("Admissão", fmt_date(professional["admission_date"]) if professional["admission_date"] else "—")
        if can_edit():
            with st.form(f"edit_sesmt_{professional_id}"):
                e1, e2 = st.columns(2)
                edit_name = e1.text_input("Nome completo", professional["full_name"])
                edit_cpf = e2.text_input("CPF", professional["cpf"] or "")
                e1, e2, e3 = st.columns(3)
                edit_role = e1.text_input("Cargo/função", professional["role_title"] or "")
                edit_admission = e2.date_input(
                    "Data de admissão",
                    value=date.fromisoformat(professional["admission_date"][:10])
                    if professional["admission_date"] else None,
                    format="DD/MM/YYYY",
                )
                edit_status = e3.selectbox(
                    "Status", SESMT_PROFESSIONAL_STATUSES,
                    index=_option_index(SESMT_PROFESSIONAL_STATUSES, professional["status"]),
                )
                edit_notes = st.text_area("Observações", professional["notes"] or "")
                if st.form_submit_button("Salvar alterações"):
                    execute(
                        """UPDATE sesmt_professionals SET full_name=?,cpf=?,role_title=?,
                        admission_date=?,status=?,notes=?,updated_at=CURRENT_TIMESTAMP WHERE id=?""",
                        (
                            edit_name.strip(), edit_cpf.strip() or None, edit_role.strip() or None,
                            edit_admission.isoformat() if edit_admission else None,
                            edit_status, edit_notes.strip() or None, professional_id,
                        ),
                    )
                    log_action(st.session_state.user["id"], "EDITAR", "profissional SESMT", professional_id, edit_name)
                    st.success("Dados atualizados.")
                    rerun()

    with detail_tabs[1]:
        exams = load_sesmt_exams(professional_id)
        if exams:
            for exam in exams:
                with st.container(border=True):
                    c1, c2, c3 = st.columns(3)
                    c1.markdown(f"**{exam['exam_type']}**")
                    c2.write(f"Realizado em: {fmt_date(exam['exam_date']) if exam['exam_date'] else '—'}")
                    c3.write(f"Resultado: {exam['result'] or '—'}")
                    st.caption(sesmt_validity_caption(exam["valid_until"]))
                    exam_docs = query(
                        "SELECT * FROM documents WHERE sesmt_exam_id=? ORDER BY id DESC", (exam["id"],)
                    )
                    sesmt_document_downloads([dict(row) for row in exam_docs], f"exam_doc_{exam['id']}")
        else:
            st.info("Nenhum exame lançado ainda.")
        if can_create():
            with st.expander("Lançar novo exame"):
                with st.form(f"new_exam_{professional_id}", clear_on_submit=True):
                    x1, x2, x3 = st.columns(3)
                    exam_type = x1.selectbox("Tipo de exame", SESMT_EXAM_TYPES)
                    exam_date = x2.date_input("Data do exame", value=today_brt(), format="DD/MM/YYYY")
                    result = x3.selectbox("Resultado", SESMT_EXAM_RESULTS)
                    valid_until = st.date_input("Válido até (ASO)", value=None, format="DD/MM/YYYY")
                    exam_notes = st.text_area("Observações", key=f"exam_notes_{professional_id}")
                    exam_upload = st.file_uploader("Anexar ASO (PDF/imagem)", key=f"exam_upload_{professional_id}")
                    if st.form_submit_button("Salvar exame"):
                        new_exam_id = execute(
                            """INSERT INTO sesmt_exams(
                            professional_id,exam_type,exam_date,result,valid_until,notes,created_by)
                            VALUES(?,?,?,?,?,?,?)""",
                            (
                                professional_id, exam_type,
                                exam_date.isoformat() if exam_date else None,
                                result, valid_until.isoformat() if valid_until else None,
                                exam_notes.strip() or None, st.session_state.user["id"],
                            ),
                        )
                        if exam_upload is not None:
                            save_sesmt_document(
                                professional_id, professional["contract_id"], exam_upload,
                                "ASO", f"ASO {exam_type} - {professional['full_name']}",
                                exam_id=new_exam_id,
                            )
                        log_action(
                            st.session_state.user["id"], "CADASTRAR", "exame SESMT",
                            new_exam_id, professional["full_name"],
                        )
                        st.success("Exame lançado.")
                        rerun()

    with detail_tabs[2]:
        trainings = load_sesmt_trainings(professional_id)
        if trainings:
            for training in trainings:
                with st.container(border=True):
                    c1, c2, c3 = st.columns(3)
                    c1.markdown(f"**{training['training_name']}**")
                    c2.write(f"Emitido em: {fmt_date(training['issue_date']) if training['issue_date'] else '—'}")
                    c3.write(f"Carga horária: {training['workload_hours'] or '—'}")
                    st.caption(sesmt_validity_caption(training["valid_until"]))
                    if training["provider"]:
                        st.caption(f"Instituição/instrutor: {training['provider']}")
                    training_docs = query(
                        "SELECT * FROM documents WHERE sesmt_training_id=? ORDER BY id DESC", (training["id"],)
                    )
                    sesmt_document_downloads([dict(row) for row in training_docs], f"training_doc_{training['id']}")
        else:
            st.info("Nenhum treinamento/certificado lançado ainda.")
        if can_create():
            with st.expander("Lançar novo treinamento/certificado"):
                with st.form(f"new_training_{professional_id}", clear_on_submit=True):
                    suggestion = st.selectbox("Treinamento", SESMT_TRAINING_SUGGESTIONS)
                    custom_name = st.text_input("Nome do treinamento (se selecionou 'Outro' acima)")
                    t1, t2, t3 = st.columns(3)
                    provider = t1.text_input("Instituição/instrutor")
                    workload_hours = t2.number_input("Carga horária (h)", min_value=0.0, step=1.0)
                    issue_date = t3.date_input("Data de emissão", value=today_brt(), format="DD/MM/YYYY")
                    valid_until = st.date_input("Válido até", value=None, format="DD/MM/YYYY")
                    training_notes = st.text_area("Observações", key=f"training_notes_{professional_id}")
                    training_upload = st.file_uploader(
                        "Anexar certificado (PDF/imagem)", key=f"training_upload_{professional_id}"
                    )
                    if st.form_submit_button("Salvar treinamento"):
                        final_name = (
                            custom_name.strip()
                            if suggestion == "Outro (digitar abaixo)" and custom_name.strip()
                            else suggestion
                        )
                        if suggestion == "Outro (digitar abaixo)" and not custom_name.strip():
                            st.error("Digite o nome do treinamento no campo indicado.")
                        else:
                            new_training_id = execute(
                                """INSERT INTO sesmt_trainings(
                                professional_id,training_name,provider,workload_hours,
                                issue_date,valid_until,notes,created_by)
                                VALUES(?,?,?,?,?,?,?,?)""",
                                (
                                    professional_id, final_name, provider.strip() or None,
                                    workload_hours or None,
                                    issue_date.isoformat() if issue_date else None,
                                    valid_until.isoformat() if valid_until else None,
                                    training_notes.strip() or None, st.session_state.user["id"],
                                ),
                            )
                            if training_upload is not None:
                                save_sesmt_document(
                                    professional_id, professional["contract_id"], training_upload,
                                    "TREINAMENTO", f"{final_name} - {professional['full_name']}",
                                    training_id=new_training_id,
                                )
                            log_action(
                                st.session_state.user["id"], "CADASTRAR", "treinamento SESMT",
                                new_training_id, professional["full_name"],
                            )
                            st.success("Treinamento lançado.")
                            rerun()


def page_exports():
    st.title("Exportações")
    st.caption("Gere arquivos Excel atualizados a qualquer momento, sem depender da planilha original.")
    contracts = load_contracts("WHERE c.archived=0 AND c.formalized=1")
    vigent_contracts = [
        contract for contract in contracts
        if days_until(contract["end_date"]) is not None and days_until(contract["end_date"]) >= 0
    ]
    backlog = pd.DataFrame(backlog_rows(contracts, today_brt().year, 6))
    excel_backlog = expand_backlog_with_ata_children(backlog, contracts, today_brt().year)
    summary = pd.DataFrame(
        vigent_contracts
    ).groupby("category", dropna=False).agg(
        Contratos=("id", "count"), Valor_atual=("current_value", "sum")
    ).reset_index() if contracts else pd.DataFrame()
    indices = pd.DataFrame([indices_data()])
    document_history = pd.DataFrame([dict(row) for row in query(
        """SELECT g.document_number numero,t.name modelo,c.cost_center centro_custo,
        c.contract_number contrato,g.recipient destinatario,g.subject assunto,g.status,
        u.name gerado_por,g.created_at gerado_em,g.sent_at encaminhado_em,g.notes observacoes
        FROM generated_company_documents g
        LEFT JOIN company_document_templates t ON t.id=g.template_id
        LEFT JOIN contracts c ON c.id=g.contract_id
        LEFT JOIN users u ON u.id=g.created_by
        ORDER BY g.id DESC"""
    )])
    st.download_button(
        "Exportar Visão Geral",
        workbook_bytes({"Visão Geral": summary}),
        f"visao_geral_{today_brt().isoformat()}.xlsx",
        "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    )
    st.download_button(
        "Exportar Contratos/Backlog",
        workbook_bytes({"Contratos": excel_backlog}),
        f"contratos_backlog_{today_brt().isoformat()}.xlsx",
        "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    )
    backlog_pdf_export(backlog, "exports", contracts=contracts)
    st.download_button(
        "Exportar Índices",
        workbook_bytes({"Índices": indices}),
        f"indices_{today_brt().isoformat()}.xlsx",
        "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    )
    st.download_button(
        "Exportar histórico de documentos",
        workbook_bytes({"Documentos padronizados": document_history}),
        f"historico_documentos_{today_brt().isoformat()}.xlsx",
        "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    )
    st.subheader("Ficha individual")
    cid = contract_selector("Contrato para exportação")
    if cid:
        contract = dict(query("SELECT cost_center FROM contracts WHERE id=?", (cid,))[0])
        st.download_button(
            "Exportar ficha completa",
            workbook_bytes(detail_export_sheets(cid)),
            f"ficha_{contract['cost_center'].replace('.','_')}.xlsx",
            "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        )
        contract_document_exports(cid, "exports")
    st.subheader("Arquivo consolidado")
    all_sheets = {
        "Visão Geral": summary,
        "Contratos": excel_backlog,
        "Índices": indices,
        "Documentos padronizados": document_history,
    }
    st.download_button(
        "Exportar todas as abas",
        workbook_bytes(all_sheets),
        f"gestao_contratual_completa_{today_brt().isoformat()}.xlsx",
        "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    )
    if user["role"] in {"admin", "gestor"}:
        with st.expander("Importação legada da planilha"):
            page_import()


def page_users():
    if st.session_state.user["role"] != "admin":
        log_action(
            st.session_state.user["id"],
            "ACESSO NEGADO",
            "usuários",
            st.session_state.user["id"],
            "Tentativa de abrir ambiente exclusivo do administrador.",
        )
        st.error("Este ambiente é exclusivo do administrador.")
        return

    st.title("Usuários e permissões")
    st.caption(
        "Acesso administrativo protegido. Cada permissão é validada também no "
        "servidor, independentemente da exibição do menu."
    )
    users = [dict(r) for r in query(
        """SELECT id,name,email,role,active,require_2fa,totp_enabled,
        failed_login_attempts,locked_until,last_login_at,must_change_password,created_at
        FROM users ORDER BY active DESC,name"""
    )]
    user_display = pd.DataFrame([{
        "Código": row["id"],
        "Nome": row["name"],
        "E-mail": row["email"],
        "Perfil": row["role"],
        "Ativo": "Sim" if row["active"] else "Não",
        "Exigir 2FA": "Sim" if row["require_2fa"] else "Não",
        "2FA configurado": "Sim" if row["totp_enabled"] else "Não",
        "Troca de senha pendente": "Sim" if row["must_change_password"] else "Não",
        "Bloqueado até": fmt_datetime(row["locked_until"]),
        "Último acesso": fmt_datetime(row["last_login_at"]),
        "Criado em": fmt_datetime(row["created_at"]),
    } for row in users])
    modern_table(user_display)

    st.subheader("Criar usuário")
    with st.form("new_user", clear_on_submit=True):
        name = st.text_input("Nome")
        email = st.text_input("E-mail")
        password = st.text_input(
            "Senha inicial",
            type="password",
            help=(
                "Mínimo de 8 caracteres, com letra maiúscula, minúscula e caractere "
                "especial. Não pode conter nome, e-mail ou termos previsíveis. O "
                "usuário deverá alterá-la no primeiro acesso."
            ),
        )
        role = st.selectbox(
            "Perfil inicial",
            ["viewer", "operador", "sesmt", "engenheiro", "gestor", "admin"],
            format_func=lambda value: {
                "viewer": "Consulta",
                "operador": "Lançamento",
                "sesmt": "SESMT",
                "engenheiro": "Engenheiro",
                "gestor": "Gestor",
                "admin": "Administrador",
            }[value],
        )
        require_2fa = st.checkbox("Exigir autenticação em dois fatores", value=False)
        if st.form_submit_button("Criar usuário"):
            normalized_email = email.strip().lower()
            policy_errors = password_policy_errors(
                password, name=name, email=normalized_email
            )
            if not name.strip():
                st.error("Informe o nome do usuário.")
            elif not re.fullmatch(r"[^\s@]+@[^\s@]+\.[^\s@]+", normalized_email):
                st.error("Informe um endereço de e-mail válido.")
            elif policy_errors:
                st.error("A senha deve conter " + ", ".join(policy_errors) + ".")
            else:
                try:
                    uid = execute(
                        """INSERT INTO users(
                        name,email,password_hash,role,require_2fa,must_change_password)
                        VALUES(?,?,?,?,?,1)""",
                        (
                            name.strip(), normalized_email, hash_password(password),
                            role, int(require_2fa),
                        ),
                    )
                    default_create = role in {
                        "operador", "engenheiro", "gestor"
                    }
                    default_edit = role in {"engenheiro", "gestor"}
                    for module in MODULE_LABELS:
                        execute(
                            """INSERT INTO user_permissions(
                            user_id,module,can_view,can_create,can_edit,can_delete)
                            VALUES(?,?,1,?,?,0)""",
                            (
                                uid, module, int(default_create),
                                int(default_edit),
                            ),
                        )
                    log_action(
                        st.session_state.user["id"],
                        "CRIAR",
                        "usuário",
                        uid,
                        f"{normalized_email} · perfil {role}",
                    )
                    st.success("Usuário criado com troca de senha obrigatória.")
                    rerun()
                except Exception:
                    st.error("O e-mail informado já pode estar cadastrado.")

    st.subheader("Segurança e ciclo de vida da conta")
    target_options = {
        f"{u['name']} · {u['email']}": u["id"] for u in users
    }
    target = target_options[st.selectbox("Usuário administrado", target_options)]
    target_user = next(u for u in users if u["id"] == target)
    role_options = ["viewer", "operador", "sesmt", "engenheiro", "gestor", "admin"]
    with st.form(f"manage_user_{target}"):
        managed_role = st.selectbox(
            "Perfil",
            role_options,
            index=role_options.index(target_user["role"])
            if target_user["role"] in role_options else 0,
        )
        c1, c2 = st.columns(2)
        managed_active = c1.checkbox(
            "Conta ativa", value=bool(target_user["active"])
        )
        desired_2fa = c2.checkbox(
            "Exigir 2FA", value=bool(target_user["require_2fa"])
        )
        unlock_account = st.checkbox(
            "Desbloquear tentativas de acesso",
            value=False,
            disabled=not bool(target_user["locked_until"]),
        )
        save_account = st.form_submit_button("Salvar conta")
    if save_account:
        admin_count = sum(
            1 for candidate in users
            if candidate["active"] and candidate["role"] == "admin"
        )
        removes_last_admin = (
            target_user["role"] == "admin"
            and target_user["active"]
            and admin_count <= 1
            and (managed_role != "admin" or not managed_active)
        )
        if target == user["id"] and not managed_active:
            st.error("O administrador não pode desativar a própria conta.")
        elif removes_last_admin:
            st.error("Mantenha pelo menos um administrador ativo.")
        else:
            execute(
                """UPDATE users SET role=?,active=?,require_2fa=?,
                failed_login_attempts=CASE WHEN ? THEN 0 ELSE failed_login_attempts END,
                locked_until=CASE WHEN ? THEN NULL ELSE locked_until END
                WHERE id=?""",
                (
                    managed_role, int(managed_active), int(desired_2fa),
                    int(unlock_account), int(unlock_account), target,
                ),
            )
            if not managed_active or managed_role != target_user["role"]:
                revoke_user_sessions(target)
            log_action(
                user["id"], "CONFIGURAR CONTA", "usuário", target,
                f"perfil={managed_role}; ativo={managed_active}; 2FA={desired_2fa}",
            )
            st.success("Conta atualizada e sessões incompatíveis encerradas.")
            rerun()

    action_col1, action_col2 = st.columns(2)
    confirm_reset = action_col1.checkbox(
        "Confirmo a redefinição do 2FA",
        key=f"reset_2fa_confirm_{target}",
    )
    if action_col1.button(
        "Redefinir 2FA", disabled=not confirm_reset, key=f"reset_2fa_{target}"
    ):
        execute(
            "UPDATE users SET totp_enabled=0,totp_secret=NULL WHERE id=?",
            (target,),
        )
        revoke_user_sessions(target)
        log_action(user["id"], "RESET 2FA", "usuário", target)
        st.success("2FA redefinido e sessões abertas encerradas.")
        rerun()
    confirm_revoke = action_col2.checkbox(
        "Confirmo o encerramento das sessões",
        key=f"revoke_sessions_confirm_{target}",
    )
    if action_col2.button(
        "Encerrar todas as sessões",
        disabled=not confirm_revoke or target == user["id"],
        key=f"revoke_sessions_{target}",
    ):
        revoke_user_sessions(target)
        log_action(user["id"], "REVOGAR SESSÕES", "usuário", target)
        st.success("Todas as sessões do usuário foram encerradas.")

    st.subheader("Permissões por ambiente")
    permission_user_options = {
        f"{u['name']} · {u['email']}": u["id"] for u in users if u["role"] != "admin"
    }
    if permission_user_options:
        permission_user_label = st.selectbox("Usuário para configurar", permission_user_options)
        permission_user_id = permission_user_options[permission_user_label]
        permission_rows = {
            r["module"]: dict(r) for r in query(
                "SELECT * FROM user_permissions WHERE user_id=?", (permission_user_id,)
            )
        }
        permission_df = pd.DataFrame([{
            "Módulo": module,
            "Ambiente": label,
            "Visualizar": bool(permission_rows.get(module, {}).get("can_view", 1)),
            "Lançar novos itens": bool(permission_rows.get(module, {}).get("can_create", 0)),
            "Modificar existentes": bool(permission_rows.get(module, {}).get("can_edit", 0)),
            "Excluir itens": bool(permission_rows.get(module, {}).get("can_delete", 0)),
        } for module, label in MODULE_LABELS.items()])
        edited_permissions = st.data_editor(
            permission_df, width="stretch", hide_index=True, disabled=["Módulo", "Ambiente"],
            key=f"permissions_{permission_user_id}",
        )
        if st.button("Salvar permissões"):
            for _, permission in edited_permissions.iterrows():
                can_view_value = bool(permission["Visualizar"])
                can_create_value = bool(permission["Lançar novos itens"])
                can_edit_value = bool(permission["Modificar existentes"])
                can_delete_value = bool(permission["Excluir itens"])
                if can_create_value or can_edit_value or can_delete_value:
                    can_view_value = True
                execute(
                    """INSERT INTO user_permissions(
                    user_id,module,can_view,can_create,can_edit,can_delete)
                    VALUES(?,?,?,?,?,?) ON CONFLICT(user_id,module) DO UPDATE SET
                    can_view=excluded.can_view,can_create=excluded.can_create,
                    can_edit=excluded.can_edit,can_delete=excluded.can_delete""",
                    (
                        permission_user_id, permission["Módulo"], int(can_view_value),
                        int(can_create_value), int(can_edit_value), int(can_delete_value),
                    ),
                )
            log_action(user["id"], "EDITAR PERMISSÕES", "usuário", permission_user_id)
            st.success("Permissões atualizadas.")
            rerun()

    st.subheader("Excluir usuário")
    deletable_users = [
        candidate for candidate in users if candidate["id"] != user["id"]
    ]
    if deletable_users:
        delete_options = {
            f"{candidate['name']} · {candidate['email']}": candidate["id"]
            for candidate in deletable_users
        }
        delete_label = st.selectbox("Conta para excluir", delete_options)
        delete_id = delete_options[delete_label]
        delete_user = next(
            candidate for candidate in deletable_users
            if candidate["id"] == delete_id
        )
        typed_email = st.text_input(
            f"Digite {delete_user['email']} para confirmar a exclusão definitiva"
        )
        last_admin = (
            delete_user["role"] == "admin"
            and sum(
                1 for candidate in users
                if candidate["active"] and candidate["role"] == "admin"
            ) <= 1
        )
        if st.button(
            "Excluir usuário definitivamente",
            type="secondary",
            disabled=(typed_email.strip().casefold() != delete_user["email"].casefold())
            or last_admin,
        ):
            log_action(
                user["id"], "EXCLUIR DEFINITIVAMENTE", "usuário",
                delete_id, delete_user["email"],
            )
            execute("DELETE FROM users WHERE id=?", (delete_id,))
            st.success(
                "Usuário excluído. Registros de auditoria e documentos permanecem "
                "preservados sem permitir novo acesso."
            )
            rerun()
        if last_admin:
            st.warning("O último administrador ativo não pode ser excluído.")

    st.subheader("Atividades recentes")
    audit_rows = [dict(row) for row in query(
        """SELECT a.created_at,u.name usuario,a.action,a.entity,a.entity_id,a.details
        FROM audit_log a LEFT JOIN users u ON u.id=a.user_id
        ORDER BY a.id DESC LIMIT 100"""
    )]
    if audit_rows:
        audit_display = pd.DataFrame([{
            "Data e hora": fmt_datetime(row["created_at"]),
            "Usuário": row["usuario"] or "Automação do sistema",
            "Ação": row["action"],
            "Área": row["entity"],
            "Registro": row["entity_id"],
            "Detalhes": row["details"],
        } for row in audit_rows])
        modern_table(audit_display, max_height=360)
    else:
        st.caption("Nenhuma atividade registrada.")


def security_settings():
    current = get_user(user["id"])
    st.subheader("Autenticação em duas etapas")
    if current["totp_enabled"]:
        st.success("O segundo fator está ativado para sua conta.")
    else:
        if "setup_totp_secret" not in st.session_state:
            st.session_state.setup_totp_secret = new_secret()
        secret = st.session_state.setup_totp_secret
        uri = provisioning_uri(secret, user["email"])
        st.write("Escaneie o QR Code no Google Authenticator ou Microsoft Authenticator.")
        try:
            import qrcode
            image = qrcode.make(uri)
            buffer = BytesIO()
            image.save(buffer, format="PNG")
            st.image(buffer.getvalue(), width=220)
        except ImportError:
            st.warning("Instale as dependências do requirements.txt para exibir o QR Code.")
        st.code(secret)
        token = st.text_input("Digite o código gerado pelo aplicativo", max_chars=6, key="enable_2fa_token")
        if st.button("Ativar 2FA"):
            if verify_totp(secret, token):
                execute("UPDATE users SET totp_enabled=1,totp_secret=? WHERE id=?", (secret, user["id"]))
                log_action(user["id"], "ATIVAR 2FA", "usuário", user["id"])
                del st.session_state.setup_totp_secret
                st.success("Segundo fator ativado.")
                rerun()
            st.error(
                "Código inválido. Ative data e hora automáticas no computador e no celular, "
                "aguarde um código novo e tente novamente antes que ele expire."
            )


restore_authenticated_session()
require_login()
user = st.session_state.user
current_user = get_user(user["id"])
if not current_user:
    finish_authenticated_session("LOGOUT POR CONTA INATIVA")
    st.session_state["auth_notice"] = "Sua conta não está ativa. Procure o administrador."
    rerun()
if current_user["must_change_password"]:
    st.title("Defina sua senha pessoal")
    st.info(
        "A senha inicial é temporária. Crie uma nova senha antes de acessar os "
        "dados contratuais."
    )
    with st.form("mandatory_password_change"):
        required_password = st.text_input("Nova senha", type="password")
        required_confirmation = st.text_input("Confirmar nova senha", type="password")
        change_required_password = st.form_submit_button(
            "Salvar nova senha", width="stretch"
        )
    if change_required_password:
        policy_errors = password_policy_errors(
            required_password,
            name=current_user["name"],
            email=current_user["email"],
        )
        if policy_errors:
            st.error("A senha deve conter " + ", ".join(policy_errors) + ".")
        elif required_password != required_confirmation:
            st.error("A confirmação não confere.")
        else:
            execute(
                """UPDATE users SET password_hash=?,password_changed_at=?,
                must_change_password=0 WHERE id=?""",
                (
                    hash_password(required_password),
                    now_brt().isoformat(),
                    current_user["id"],
                ),
            )
            revoke_user_sessions(
                current_user["id"],
                except_token=st.session_state.get("_auth_token"),
            )
            log_action(
                current_user["id"],
                "DEFINIR SENHA PESSOAL",
                "usuário",
                current_user["id"],
            )
            st.session_state.user = dict(get_user(current_user["id"]))
            st.success("Senha pessoal definida com sucesso.")
            rerun()
    professional_footer()
    st.stop()


@st.fragment(run_every=15)
def inactivity_timeout_guard():
    session_token = st.session_state.get("_auth_token")
    if session_token and not validate_user_session(
        session_token,
        browser_user_agent(),
        touch=False,
    ):
        finish_authenticated_session("LOGOUT POR INATIVIDADE")
        st.session_state["auth_notice"] = (
            f"Sua sessão foi encerrada após {SESSION_IDLE_MINUTES} minutos sem atividade."
        )
        rerun()


inactivity_timeout_guard()
if current_user["require_2fa"] and not current_user["totp_enabled"]:
    st.title("Configuração obrigatória de segurança")
    st.info("Antes de acessar o sistema, vincule sua conta a um aplicativo Authenticator.")
    security_settings()
    professional_footer()
    st.stop()
if "alerts_processed" not in st.session_state:
    st.session_state.alerts_processed = process_repactuation_alerts()
if "bid_schedule_checked" not in st.session_state:
    st.session_state.bid_schedule_checked = True
    # Rede de segurança: o gatilho principal roda na nuvem do GitHub
    # (.github/workflows/licitacoes-diarias.yml, 6h50 no horário de
    # Brasília, independente de qualquer computador estar ligado), mas se
    # por algum motivo não rodar, o primeiro acesso ao sistema depois desse
    # horário num dia útil também aciona o envio — a reserva atômica em
    # notification_log (ver send_daily_bid_schedule em alerts.py) garante
    # que isso nunca duplica e-mail, mesmo com múltiplos gatilhos
    # concorrentes.
    if now_brt().time() >= time(6, 50):
        send_daily_bid_schedule()
selected_theme = st.sidebar.radio(
    "Aparência",
    ["Escuro", "Claro"],
    index=0 if st.session_state.ui_theme == "Escuro" else 1,
    horizontal=True,
    key="theme_selector",
)
if selected_theme != st.session_state.ui_theme:
    st.session_state.ui_theme = selected_theme
    execute("UPDATE users SET preferred_theme=? WHERE id=?", (selected_theme, user["id"]))
    apply_theme(selected_theme)
active_logo_path = LOGO_LIGHT_PATH if st.session_state.ui_theme == "Escuro" else LOGO_DARK_PATH
st.sidebar.title("Gestão Contratual")
if active_logo_path.exists():
    st.sidebar.image(str(active_logo_path), width="stretch")
st.sidebar.caption(
    f"{user['name']} · {user['role']} · Versão {APP_VERSION} {APP_STAGE}"
)
with st.sidebar.expander("Alterar minha senha"):
    current_password = st.text_input("Senha atual", type="password", key="pwd_current")
    new_password = st.text_input("Nova senha", type="password", key="pwd_new")
    confirmation = st.text_input("Confirmar nova senha", type="password", key="pwd_confirmation")
    if st.button("Atualizar senha", width="stretch"):
        if not authenticate(user["email"], current_password):
            st.error("A senha atual não confere.")
        elif password_policy_errors(new_password, name=user["name"], email=user["email"]):
            st.error(
                "A nova senha deve conter "
                + ", ".join(
                    password_policy_errors(
                        new_password, name=user["name"], email=user["email"]
                    )
                )
                + "."
            )
        elif new_password != confirmation:
            st.error("A confirmação não confere.")
        else:
            execute(
                """UPDATE users SET password_hash=?,password_changed_at=?,
                must_change_password=0 WHERE id=?""",
                (hash_password(new_password), now_brt().isoformat(), user["id"]),
            )
            revoke_user_sessions(
                user["id"],
                except_token=st.session_state.get("_auth_token"),
            )
            log_action(user["id"], "ALTERAR SENHA", "usuário", user["id"])
            temporary_success(
                "Senha atualizada. As demais sessões abertas desta conta foram encerradas."
            )
with st.sidebar.expander("Segurança e 2FA"):
    security_settings()
page_modules = {
    "Visão geral": "dashboard",
    "Contratos": "contracts",
    "Ficha do contrato": "contract_detail",
    "Novo contrato": "new_contract",
    "Pré-contratos": "new_contract",
    "Licitações": "bids",
    "SESMT": "sesmt",
    "Exportações": "exports",
    "Índices": "indices",
    "Documentos padrões": "company_documents",
}
pages = [
    label for label, module in page_modules.items()
    if has_permission(module, "can_view")
    and (label not in ("Novo contrato", "Pré-contratos") or has_permission(module, "can_create"))
]
if user["role"] == "admin":
    pages.append("Usuários")
if st.session_state.get("navigation_page") not in pages:
    saved_page = current_user["last_page"] or pages[0]
    st.session_state.navigation_page = saved_page if saved_page in pages else pages[0]
page = st.sidebar.radio("Navegação", pages, key="navigation_page")
if st.session_state.get("_rendered_navigation_page") != page:
    scroll_page_to_top()
    st.session_state["_rendered_navigation_page"] = page
if page != (current_user["last_page"] or "Visão geral"):
    execute("UPDATE users SET last_page=? WHERE id=?", (page, user["id"]))
    st.session_state.user["last_page"] = page
if st.sidebar.button("Sair", width="stretch"):
    finish_authenticated_session("LOGOUT")
    rerun()

if active_logo_path.exists():
    st.image(str(active_logo_path), width=250)
st.session_state.current_module = page_modules.get(page, "users")
{
    "Visão geral": page_dashboard,
    "Contratos": page_contracts,
    "Ficha do contrato": page_contract_detail,
    "Novo contrato": page_new_contract,
    "Pré-contratos": page_precontracts,
    "Licitações": page_bids,
    "SESMT": page_sesmt,
    "Exportações": page_exports,
    "Índices": page_indices,
    "Documentos padrões": page_company_documents,
    "Usuários": page_users,
}[page]()
professional_footer()
sync_uploads_to_storage_if_changed()
