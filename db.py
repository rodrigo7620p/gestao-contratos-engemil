from __future__ import annotations

import atexit
import hashlib
import hmac
import io
import os
import secrets
import sqlite3
import threading
import zipfile
from contextlib import contextmanager
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

from contract_utils import contract_duration_months

try:
    import libsql_client
except ImportError:
    libsql_client = None

BASE_DIR = Path(__file__).resolve().parent
DB_PATH = Path(os.getenv("GESTAO_DB_PATH", BASE_DIR / "gestao_contratos.db"))
UPLOAD_DIR = Path(os.getenv("GESTAO_UPLOAD_DIR", BASE_DIR / "uploads"))
try:
    SESSION_IDLE_MINUTES = max(
        5, int(os.getenv("GESTAO_SESSION_IDLE_MINUTES", "30"))
    )
except ValueError:
    SESSION_IDLE_MINUTES = 30


def _secret(name: str) -> str | None:
    value = os.getenv(name)
    if value:
        return value
    try:
        import streamlit as st
        return st.secrets.get(name)
    except Exception:
        return None


def _turso_config() -> tuple[str, str | None] | None:
    """Lê a configuração do banco hospedado (Turso/libSQL), se houver.

    Sem essa configuração o app volta a usar o arquivo SQLite local — é o
    que acontece em desenvolvimento. Em produção (Streamlit Cloud), o disco
    é apagado a cada reinício, então lá essas variáveis são obrigatórias
    para os dados sobreviverem.
    """
    url = _secret("TURSO_DATABASE_URL")
    if not url:
        return None
    # O protocolo por WebSocket (libsql://, wss://) tem se mostrado instável
    # atrás de alguns proxies/regiões da Turso (handshake rejeitado com 400).
    # HTTP é stateless por statement, mais simples e igualmente suportado.
    if url.startswith("libsql://"):
        url = "https://" + url[len("libsql://"):]
    elif url.startswith("wss://"):
        url = "https://" + url[len("wss://"):]
    elif url.startswith("ws://"):
        url = "http://" + url[len("ws://"):]
    return (url, _secret("TURSO_AUTH_TOKEN"))


class _LibsqlRow:
    """Imita `sqlite3.Row`: acesso por índice (row[0]) e por nome (row["col"])."""

    __slots__ = ("_columns", "_values")

    def __init__(self, columns, values):
        self._columns = columns
        self._values = values

    def __getitem__(self, key):
        if isinstance(key, str):
            return self._values[self._columns.index(key)]
        return self._values[key]

    def keys(self):
        return list(self._columns)

    def __iter__(self):
        return iter(self._values)

    def __len__(self):
        return len(self._values)

    def __repr__(self):
        return f"<Row {dict(zip(self._columns, self._values))!r}>"


class _LibsqlResult:
    """Imita o objeto retornado por `sqlite3.Connection.execute()`."""

    def __init__(self, result_set):
        columns = tuple(result_set.columns)
        self._rows = [_LibsqlRow(columns, tuple(row)) for row in result_set.rows]
        self.lastrowid = result_set.last_insert_rowid
        self.rowcount = result_set.rows_affected

    def fetchall(self):
        return self._rows

    def fetchone(self):
        return self._rows[0] if self._rows else None

    def __iter__(self):
        return iter(self._rows)


class _LibsqlConnection:
    """Imita a interface de `sqlite3.Connection` usada em todo este módulo,
    mas fala com um banco Turso/libSQL remoto (HTTP) por baixo dos panos."""

    def __init__(self, client):
        self._client = client

    def execute(self, sql: str, params=()):
        args = tuple(params) if params else None
        return _LibsqlResult(self._client.execute(sql, args))

    def executemany(self, sql: str, seq_of_params):
        result = None
        for params in seq_of_params:
            result = self.execute(sql, params)
        return result

    def executescript(self, script: str) -> None:
        statements = [s.strip() for s in script.split(";") if s.strip()]
        if statements:
            self._client.batch(statements)

    def commit(self) -> None:
        pass  # sobre HTTP cada execute() já é aplicado imediatamente

    def close(self) -> None:
        pass  # conexão compartilhada; ver _get_libsql_client()


_libsql_client = None
_libsql_lock = threading.Lock()


def _get_libsql_client(url: str, token: str | None):
    """Cliente único e compartilhado por todo o processo do Streamlit.

    Abrir um cliente novo a cada chamada seria caro (cada um sobe sua
    própria thread), por isso mantemos um só, reaproveitado, protegido por
    um lock (ver connect()) para uso seguro entre sessões/threads.
    """
    global _libsql_client
    if _libsql_client is None:
        if libsql_client is None:
            raise RuntimeError(
                "TURSO_DATABASE_URL configurado, mas o pacote 'libsql-client' "
                "não está instalado. Rode: pip install libsql-client"
            )
        _libsql_client = libsql_client.create_client_sync(url, auth_token=token or None)
        _libsql_client.execute("PRAGMA foreign_keys = ON")
        atexit.register(_libsql_client.close)
    return _libsql_client


@contextmanager
def connect():
    config = _turso_config()
    if config:
        url, token = config
        client = _get_libsql_client(url, token)
        with _libsql_lock:
            yield _LibsqlConnection(client)
        return
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    try:
        yield conn
        conn.commit()
    finally:
        conn.close()


def hash_password(password: str, salt: bytes | None = None) -> str:
    salt = salt or os.urandom(16)
    digest = hashlib.pbkdf2_hmac("sha256", password.encode(), salt, 260_000)
    return f"{salt.hex()}:{digest.hex()}"


def verify_password(password: str, encoded: str) -> bool:
    try:
        salt_hex, digest_hex = encoded.split(":", 1)
        candidate = hash_password(password, bytes.fromhex(salt_hex)).split(":", 1)[1]
        return hmac.compare_digest(candidate, digest_hex)
    except (ValueError, TypeError):
        return False


SCHEMA = """
CREATE TABLE IF NOT EXISTS users (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL,
    email TEXT NOT NULL UNIQUE COLLATE NOCASE,
    password_hash TEXT NOT NULL,
    role TEXT NOT NULL DEFAULT 'viewer',
    active INTEGER NOT NULL DEFAULT 1,
    totp_secret TEXT,
    totp_enabled INTEGER NOT NULL DEFAULT 0,
    require_2fa INTEGER NOT NULL DEFAULT 0,
    preferred_theme TEXT NOT NULL DEFAULT 'Escuro',
    last_page TEXT NOT NULL DEFAULT 'Visão geral',
    failed_login_attempts INTEGER NOT NULL DEFAULT 0,
    locked_until TEXT,
    last_login_at TEXT,
    password_changed_at TEXT,
    must_change_password INTEGER NOT NULL DEFAULT 0,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);
CREATE TABLE IF NOT EXISTS contracts (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    cost_center TEXT UNIQUE,
    client TEXT NOT NULL,
    contract_number TEXT,
    bid_number TEXT,
    process_number TEXT,
    uasg TEXT,
    category TEXT,
    procurement_method TEXT,
    object TEXT,
    signature_date TEXT,
    start_date TEXT,
    end_date TEXT,
    original_start_date TEXT,
    original_end_date TEXT,
    original_value REAL DEFAULT 0,
    current_value REAL DEFAULT 0,
    status TEXT DEFAULT 'ATIVO',
    manager_name TEXT,
    manager_email TEXT,
    engineer_name TEXT,
    engineer_email TEXT,
    union_name TEXT,
    collective_agreement TEXT,
    base_date TEXT,
    employee_count INTEGER DEFAULT 0,
    repactuation_date TEXT,
    adjustment_index TEXT,
    guarantee_end_date TEXT,
    observations TEXT,
    source_sheet TEXT,
    tax_regime TEXT NOT NULL DEFAULT 'NÃO DEFINIDO',
    cno_required INTEGER,
    archived INTEGER NOT NULL DEFAULT 0,
    archived_at TEXT,
    archived_by INTEGER REFERENCES users(id) ON DELETE SET NULL,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);
CREATE TABLE IF NOT EXISTS amendments (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    contract_id INTEGER NOT NULL REFERENCES contracts(id) ON DELETE CASCADE,
    ordinal TEXT,
    kind TEXT,
    description TEXT,
    value REAL,
    start_date TEXT,
    end_date TEXT,
    duration_months INTEGER,
    guarantee_status TEXT,
    art_status TEXT,
    notes TEXT,
    justification_text TEXT,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);
CREATE TABLE IF NOT EXISTS contract_budget_dates (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    contract_id INTEGER NOT NULL REFERENCES contracts(id) ON DELETE CASCADE,
    reference_date TEXT NOT NULL,
    description TEXT,
    notes TEXT,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);
CREATE TABLE IF NOT EXISTS ata_contracts (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    ata_id INTEGER NOT NULL REFERENCES contracts(id) ON DELETE CASCADE,
    contract_number TEXT NOT NULL,
    process_number TEXT,
    client TEXT,
    object TEXT,
    signature_date TEXT,
    start_date TEXT,
    end_date TEXT,
    original_value REAL NOT NULL DEFAULT 0,
    current_value REAL NOT NULL DEFAULT 0,
    status TEXT NOT NULL DEFAULT 'ATIVO',
    responsible_name TEXT,
    responsible_email TEXT,
    notes TEXT,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);
CREATE TABLE IF NOT EXISTS ata_contract_amendments (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    ata_contract_id INTEGER NOT NULL REFERENCES ata_contracts(id) ON DELETE CASCADE,
    ordinal TEXT,
    kind TEXT,
    description TEXT,
    value REAL,
    start_date TEXT,
    end_date TEXT,
    duration_months INTEGER,
    guarantee_status TEXT,
    art_status TEXT,
    notes TEXT,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);
CREATE TABLE IF NOT EXISTS contract_guarantees (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    contract_id INTEGER NOT NULL REFERENCES contracts(id) ON DELETE CASCADE,
    amendment_id INTEGER REFERENCES amendments(id) ON DELETE SET NULL,
    ata_contract_id INTEGER REFERENCES ata_contracts(id) ON DELETE SET NULL,
    ata_amendment_id INTEGER REFERENCES ata_contract_amendments(id) ON DELETE SET NULL,
    guarantee_type TEXT NOT NULL,
    custom_type TEXT,
    instrument_scope TEXT NOT NULL DEFAULT 'CONTRATO INICIAL',
    modality TEXT,
    legal_basis TEXT,
    calculation_method TEXT NOT NULL DEFAULT 'PERCENTUAL_BASE',
    calculation_base REAL NOT NULL DEFAULT 0,
    percentage REAL NOT NULL DEFAULT 0,
    estimated_budget REAL NOT NULL DEFAULT 0,
    proposal_value REAL NOT NULL DEFAULT 0,
    required_amount REAL NOT NULL DEFAULT 0,
    guaranteed_amount REAL NOT NULL DEFAULT 0,
    provider_name TEXT,
    broker_name TEXT,
    policy_number TEXT,
    susep_registration TEXT,
    insured_name TEXT,
    co_insured_name TEXT,
    object_description TEXT,
    issue_date TEXT,
    start_date TEXT,
    end_date TEXT,
    premium_value REAL NOT NULL DEFAULT 0,
    payment_due_date TEXT,
    request_status TEXT NOT NULL DEFAULT 'A SOLICITAR',
    request_date TEXT,
    request_due_date TEXT,
    received_date TEXT,
    approval_date TEXT,
    responsible_name TEXT,
    responsible_email TEXT,
    copy_emails TEXT,
    notification_enabled INTEGER NOT NULL DEFAULT 1,
    notes TEXT,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);
CREATE TABLE IF NOT EXISTS guarantee_coverages (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    guarantee_id INTEGER NOT NULL REFERENCES contract_guarantees(id) ON DELETE CASCADE,
    coverage_name TEXT NOT NULL,
    insured_limit REAL NOT NULL DEFAULT 0,
    start_date TEXT,
    end_date TEXT,
    deductible TEXT,
    notes TEXT,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);
CREATE TABLE IF NOT EXISTS guarantee_endorsements (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    guarantee_id INTEGER NOT NULL REFERENCES contract_guarantees(id) ON DELETE CASCADE,
    amendment_id INTEGER REFERENCES amendments(id) ON DELETE SET NULL,
    endorsement_number TEXT,
    movement_type TEXT NOT NULL DEFAULT 'ENDOSSO',
    description TEXT,
    issue_date TEXT,
    previous_end_date TEXT,
    new_end_date TEXT,
    previous_amount REAL NOT NULL DEFAULT 0,
    new_amount REAL NOT NULL DEFAULT 0,
    premium_adjustment REAL NOT NULL DEFAULT 0,
    request_status TEXT NOT NULL DEFAULT 'A SOLICITAR',
    request_date TEXT,
    received_date TEXT,
    notes TEXT,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);
CREATE TABLE IF NOT EXISTS bid_processes (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    process_number TEXT NOT NULL,
    edital_number TEXT,
    uasg TEXT,
    platform TEXT NOT NULL DEFAULT 'OUTRO',
    agency TEXT NOT NULL,
    agency_cnpj TEXT,
    uf TEXT,
    municipality TEXT,
    object TEXT,
    modality TEXT,
    scope TEXT,
    quantity REAL,
    estimated_unit_value REAL,
    estimated_value REAL NOT NULL DEFAULT 0,
    our_bid_value REAL,
    our_discount_percent REAL,
    our_ranking INTEGER,
    dispute_date TEXT,
    dispute_time TEXT,
    is_confidential INTEGER NOT NULL DEFAULT 0,
    dispute_mode TEXT,
    proposal_deadline TEXT,
    status TEXT NOT NULL DEFAULT 'EM ANDAMENTO',
    pncp_control_number TEXT,
    contract_id INTEGER REFERENCES contracts(id) ON DELETE SET NULL,
    responsible_name TEXT,
    responsible_email TEXT,
    notes TEXT,
    archived INTEGER NOT NULL DEFAULT 0,
    created_by INTEGER REFERENCES users(id) ON DELETE SET NULL,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);
CREATE TABLE IF NOT EXISTS bid_rankings (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    bid_process_id INTEGER NOT NULL REFERENCES bid_processes(id) ON DELETE CASCADE,
    bid_lot_id INTEGER REFERENCES bid_lots(id) ON DELETE CASCADE,
    seq INTEGER NOT NULL DEFAULT 0,
    company_name TEXT NOT NULL,
    company_cnpj TEXT,
    final_bid_value REAL,
    discount_percent REAL,
    technical_score REAL,
    situation TEXT NOT NULL DEFAULT 'CLASSIFICADA',
    is_engemil INTEGER NOT NULL DEFAULT 0,
    notes TEXT,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);
CREATE TABLE IF NOT EXISTS bid_lots (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    bid_process_id INTEGER NOT NULL REFERENCES bid_processes(id) ON DELETE CASCADE,
    label TEXT NOT NULL,
    lot_type TEXT NOT NULL DEFAULT 'ITEM',
    item_count INTEGER,
    quantity REAL,
    estimated_unit_value REAL,
    estimated_value REAL NOT NULL DEFAULT 0,
    our_bid_value REAL,
    our_discount_percent REAL,
    our_ranking INTEGER,
    notes TEXT,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);
CREATE TABLE IF NOT EXISTS bid_lot_items (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    bid_lot_id INTEGER NOT NULL REFERENCES bid_lots(id) ON DELETE CASCADE,
    item_name TEXT NOT NULL,
    quantity REAL NOT NULL DEFAULT 0,
    estimated_unit_value REAL NOT NULL DEFAULT 0,
    offered_unit_value REAL,
    notes TEXT,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);
CREATE INDEX IF NOT EXISTS idx_bid_lot_process ON bid_lots(bid_process_id);
CREATE INDEX IF NOT EXISTS idx_bid_lot_items_lot ON bid_lot_items(bid_lot_id);
CREATE INDEX IF NOT EXISTS idx_bid_ranking_process ON bid_rankings(bid_process_id);
CREATE INDEX IF NOT EXISTS idx_bid_process_status ON bid_processes(status);
CREATE INDEX IF NOT EXISTS idx_bid_process_archived ON bid_processes(archived);
CREATE TABLE IF NOT EXISTS sesmt_professionals (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    contract_id INTEGER NOT NULL REFERENCES contracts(id) ON DELETE CASCADE,
    full_name TEXT NOT NULL,
    cpf TEXT,
    role_title TEXT,
    admission_date TEXT,
    status TEXT NOT NULL DEFAULT 'ATIVO',
    notes TEXT,
    created_by INTEGER REFERENCES users(id) ON DELETE SET NULL,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);
CREATE TABLE IF NOT EXISTS sesmt_exams (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    professional_id INTEGER NOT NULL REFERENCES sesmt_professionals(id) ON DELETE CASCADE,
    exam_type TEXT NOT NULL DEFAULT 'PERIÓDICO',
    exam_date TEXT,
    result TEXT,
    valid_until TEXT,
    notes TEXT,
    created_by INTEGER REFERENCES users(id) ON DELETE SET NULL,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);
CREATE TABLE IF NOT EXISTS sesmt_trainings (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    professional_id INTEGER NOT NULL REFERENCES sesmt_professionals(id) ON DELETE CASCADE,
    training_name TEXT NOT NULL,
    provider TEXT,
    workload_hours REAL,
    issue_date TEXT,
    valid_until TEXT,
    notes TEXT,
    created_by INTEGER REFERENCES users(id) ON DELETE SET NULL,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);
CREATE INDEX IF NOT EXISTS idx_sesmt_professionals_contract ON sesmt_professionals(contract_id);
CREATE TABLE IF NOT EXISTS contract_employees (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    contract_id INTEGER NOT NULL REFERENCES contracts(id) ON DELETE CASCADE,
    full_name TEXT NOT NULL,
    cpf TEXT,
    role_title TEXT,
    admission_date TEXT,
    base_salary REAL,
    status TEXT NOT NULL DEFAULT 'ATIVO',
    source TEXT NOT NULL DEFAULT 'MANUAL',
    notes TEXT,
    created_by INTEGER REFERENCES users(id) ON DELETE SET NULL,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);
CREATE INDEX IF NOT EXISTS idx_contract_employees_contract ON contract_employees(contract_id);
CREATE INDEX IF NOT EXISTS idx_sesmt_exams_professional ON sesmt_exams(professional_id);
CREATE INDEX IF NOT EXISTS idx_sesmt_trainings_professional ON sesmt_trainings(professional_id);
CREATE TABLE IF NOT EXISTS obligations (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    contract_id INTEGER NOT NULL REFERENCES contracts(id) ON DELETE CASCADE,
    title TEXT NOT NULL,
    category TEXT,
    due_date TEXT,
    recurrence TEXT,
    responsible_name TEXT,
    responsible_email TEXT,
    copy_emails TEXT,
    priority TEXT DEFAULT 'MÉDIA',
    status TEXT DEFAULT 'PENDENTE',
    advance_days INTEGER DEFAULT 30,
    notification_enabled INTEGER NOT NULL DEFAULT 1,
    reminder_frequency_days INTEGER NOT NULL DEFAULT 7,
    last_reminder_at TEXT,
    reminder_count INTEGER NOT NULL DEFAULT 0,
    notes TEXT,
    notified_at TEXT,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);
CREATE TABLE IF NOT EXISTS documents (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    contract_id INTEGER NOT NULL REFERENCES contracts(id) ON DELETE CASCADE,
    amendment_id INTEGER REFERENCES amendments(id) ON DELETE SET NULL,
    ata_contract_id INTEGER REFERENCES ata_contracts(id) ON DELETE SET NULL,
    ata_amendment_id INTEGER REFERENCES ata_contract_amendments(id) ON DELETE SET NULL,
    union_id INTEGER REFERENCES contract_unions(id) ON DELETE SET NULL,
    art_id INTEGER REFERENCES arts(id) ON DELETE SET NULL,
    cno_id INTEGER REFERENCES contract_cnos(id) ON DELETE SET NULL,
    guarantee_id INTEGER REFERENCES contract_guarantees(id) ON DELETE SET NULL,
    guarantee_endorsement_id INTEGER REFERENCES guarantee_endorsements(id) ON DELETE SET NULL,
    category TEXT NOT NULL,
    title TEXT NOT NULL,
    filename TEXT NOT NULL,
    stored_path TEXT NOT NULL,
    uploaded_by INTEGER REFERENCES users(id) ON DELETE SET NULL,
    uploaded_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);
CREATE TABLE IF NOT EXISTS contract_unions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    contract_id INTEGER NOT NULL REFERENCES contracts(id) ON DELETE CASCADE,
    amendment_id INTEGER REFERENCES amendments(id) ON DELETE SET NULL,
    union_name TEXT NOT NULL,
    collective_agreement TEXT,
    category_name TEXT,
    base_month INTEGER,
    base_date TEXT,
    next_repactuation TEXT,
    notes TEXT,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);
CREATE TABLE IF NOT EXISTS contract_positions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    contract_id INTEGER NOT NULL REFERENCES contracts(id) ON DELETE CASCADE,
    title TEXT NOT NULL,
    quantity INTEGER NOT NULL DEFAULT 1,
    base_salary REAL NOT NULL DEFAULT 0,
    monthly_benefits REAL NOT NULL DEFAULT 0,
    additional_type TEXT,
    additional_percent REAL NOT NULL DEFAULT 0,
    additional_value REAL NOT NULL DEFAULT 0,
    hazard_percent REAL NOT NULL DEFAULT 0,
    unhealthy_percent REAL NOT NULL DEFAULT 0,
    unhealthy_base_year INTEGER,
    union_id INTEGER REFERENCES contract_unions(id) ON DELETE SET NULL,
    notes TEXT,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);
CREATE TABLE IF NOT EXISTS position_benefits (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    position_id INTEGER NOT NULL REFERENCES contract_positions(id) ON DELETE CASCADE,
    benefit_type TEXT NOT NULL,
    description TEXT,
    monthly_value REAL NOT NULL DEFAULT 0,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);
CREATE TABLE IF NOT EXISTS contract_bdis (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    contract_id INTEGER NOT NULL REFERENCES contracts(id) ON DELETE CASCADE,
    name TEXT NOT NULL,
    reference_name TEXT NOT NULL,
    tax_regime TEXT NOT NULL DEFAULT 'CONTRATO',
    calculation_method TEXT NOT NULL DEFAULT 'FORMULA_COMPOSTA',
    rounding_method TEXT NOT NULL DEFAULT 'TRUNCAR_4',
    indirect_costs REAL NOT NULL DEFAULT 0,
    central_administration REAL NOT NULL DEFAULT 0,
    insurance REAL NOT NULL DEFAULT 0,
    risks REAL NOT NULL DEFAULT 0,
    guarantees REAL NOT NULL DEFAULT 0,
    other_indirect_costs REAL NOT NULL DEFAULT 0,
    financial_expenses REAL NOT NULL DEFAULT 0,
    profit REAL NOT NULL DEFAULT 0,
    pis REAL NOT NULL DEFAULT 0,
    cofins REAL NOT NULL DEFAULT 0,
    iss REAL NOT NULL DEFAULT 0,
    cprb REAL NOT NULL DEFAULT 0,
    other_taxes REAL NOT NULL DEFAULT 0,
    notes TEXT,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);
CREATE TABLE IF NOT EXISTS arts (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    contract_id INTEGER NOT NULL REFERENCES contracts(id) ON DELETE CASCADE,
    amendment_id INTEGER REFERENCES amendments(id) ON DELETE SET NULL,
    ata_contract_id INTEGER REFERENCES ata_contracts(id) ON DELETE SET NULL,
    ata_amendment_id INTEGER REFERENCES ata_contract_amendments(id) ON DELETE SET NULL,
    instrument_scope TEXT NOT NULL DEFAULT 'NÃO DEFINIDO',
    professional_name TEXT NOT NULL,
    professional_title TEXT,
    professional_registration TEXT,
    art_number TEXT NOT NULL,
    issue_date TEXT,
    end_date TEXT,
    status TEXT DEFAULT 'ATIVA',
    description TEXT,
    notes TEXT,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);
CREATE TABLE IF NOT EXISTS contract_cnos (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    contract_id INTEGER NOT NULL REFERENCES contracts(id) ON DELETE CASCADE,
    ata_contract_id INTEGER REFERENCES ata_contracts(id) ON DELETE SET NULL,
    registration_number TEXT NOT NULL,
    registration_date TEXT,
    responsibility_start_date TEXT,
    work_area TEXT,
    notes TEXT,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);
CREATE TABLE IF NOT EXISTS labor_parameters (
    year INTEGER PRIMARY KEY,
    minimum_wage REAL NOT NULL DEFAULT 0,
    notes TEXT,
    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);
CREATE TABLE IF NOT EXISTS notification_log (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    event_type TEXT NOT NULL,
    reference_id INTEGER NOT NULL,
    event_date TEXT NOT NULL,
    recipient TEXT,
    sent_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(event_type,reference_id,event_date,recipient)
);
CREATE TABLE IF NOT EXISTS financial_parameters (
    id INTEGER PRIMARY KEY CHECK (id=1),
    reference_year INTEGER NOT NULL,
    equity_value REAL NOT NULL DEFAULT 0,
    gross_revenue REAL NOT NULL DEFAULT 0,
    notes TEXT,
    justification_text TEXT,
    signatory_name TEXT,
    signatory_registration TEXT,
    signatory_cpf TEXT,
    signatory_title TEXT,
    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);
CREATE TABLE IF NOT EXISTS company_document_templates (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL UNIQUE,
    document_type TEXT NOT NULL DEFAULT 'DIVERSO',
    description TEXT,
    original_filename TEXT NOT NULL,
    original_path TEXT NOT NULL,
    generation_filename TEXT NOT NULL,
    generation_path TEXT NOT NULL,
    active INTEGER NOT NULL DEFAULT 1,
    created_by INTEGER REFERENCES users(id) ON DELETE SET NULL,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);
CREATE TABLE IF NOT EXISTS company_signatories (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL UNIQUE,
    registration TEXT,
    cpf TEXT,
    title TEXT,
    active INTEGER NOT NULL DEFAULT 1,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);
CREATE TABLE IF NOT EXISTS document_sequences (
    document_type TEXT NOT NULL,
    year INTEGER NOT NULL,
    last_number INTEGER NOT NULL DEFAULT 0,
    PRIMARY KEY(document_type,year)
);
CREATE TABLE IF NOT EXISTS generated_company_documents (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    template_id INTEGER REFERENCES company_document_templates(id) ON DELETE SET NULL,
    contract_id INTEGER REFERENCES contracts(id) ON DELETE SET NULL,
    document_number TEXT NOT NULL UNIQUE,
    recipient TEXT,
    subject TEXT,
    status TEXT NOT NULL DEFAULT 'GERADO',
    docx_filename TEXT NOT NULL,
    docx_path TEXT NOT NULL,
    pdf_filename TEXT,
    pdf_path TEXT,
    fields_json TEXT,
    created_by INTEGER REFERENCES users(id) ON DELETE SET NULL,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    sent_at TEXT,
    notes TEXT
);
CREATE TABLE IF NOT EXISTS user_permissions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    module TEXT NOT NULL,
    can_view INTEGER NOT NULL DEFAULT 1,
    can_create INTEGER NOT NULL DEFAULT 0,
    can_edit INTEGER NOT NULL DEFAULT 0,
    can_delete INTEGER NOT NULL DEFAULT 0,
    UNIQUE(user_id,module)
);
CREATE TABLE IF NOT EXISTS user_sessions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    token_hash TEXT NOT NULL UNIQUE,
    user_agent_hash TEXT,
    created_at TEXT NOT NULL,
    last_activity_at TEXT NOT NULL,
    expires_at TEXT NOT NULL,
    revoked_at TEXT
);
CREATE TABLE IF NOT EXISTS audit_log (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER REFERENCES users(id) ON DELETE SET NULL,
    action TEXT NOT NULL,
    entity TEXT NOT NULL,
    entity_id INTEGER,
    details TEXT,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);
CREATE TABLE IF NOT EXISTS blob_store (
    key TEXT PRIMARY KEY,
    data BLOB NOT NULL,
    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);
CREATE INDEX IF NOT EXISTS idx_contract_end ON contracts(end_date);
CREATE INDEX IF NOT EXISTS idx_obligation_due ON obligations(due_date);
CREATE INDEX IF NOT EXISTS idx_amendment_contract ON amendments(contract_id);
CREATE INDEX IF NOT EXISTS idx_ata_parent ON ata_contracts(ata_id);
CREATE INDEX IF NOT EXISTS idx_ata_amendment ON ata_contract_amendments(ata_contract_id);
CREATE INDEX IF NOT EXISTS idx_guarantee_contract ON contract_guarantees(contract_id);
CREATE INDEX IF NOT EXISTS idx_guarantee_amendment ON contract_guarantees(amendment_id);
CREATE INDEX IF NOT EXISTS idx_guarantee_ata_contract ON contract_guarantees(ata_contract_id);
CREATE INDEX IF NOT EXISTS idx_guarantee_ata_amendment ON contract_guarantees(ata_amendment_id);
CREATE INDEX IF NOT EXISTS idx_guarantee_end ON contract_guarantees(end_date);
CREATE INDEX IF NOT EXISTS idx_guarantee_coverage ON guarantee_coverages(guarantee_id);
CREATE INDEX IF NOT EXISTS idx_guarantee_endorsement ON guarantee_endorsements(guarantee_id);
CREATE INDEX IF NOT EXISTS idx_union_contract ON contract_unions(contract_id);
CREATE INDEX IF NOT EXISTS idx_position_contract ON contract_positions(contract_id);
CREATE INDEX IF NOT EXISTS idx_benefit_position ON position_benefits(position_id);
CREATE INDEX IF NOT EXISTS idx_bdi_contract ON contract_bdis(contract_id);
CREATE INDEX IF NOT EXISTS idx_art_contract ON arts(contract_id);
CREATE INDEX IF NOT EXISTS idx_budget_date_contract ON contract_budget_dates(contract_id);
CREATE INDEX IF NOT EXISTS idx_cno_contract ON contract_cnos(contract_id);
CREATE INDEX IF NOT EXISTS idx_permission_user ON user_permissions(user_id);
CREATE INDEX IF NOT EXISTS idx_user_session_user ON user_sessions(user_id);
CREATE INDEX IF NOT EXISTS idx_user_session_expiry ON user_sessions(expires_at);
CREATE INDEX IF NOT EXISTS idx_generated_company_contract ON generated_company_documents(contract_id);
CREATE INDEX IF NOT EXISTS idx_generated_company_status ON generated_company_documents(status);
"""


_schema_initialized = False


def init_db() -> None:
    global _schema_initialized
    if _schema_initialized:
        # init_db() é chamada a cada rerun do Streamlit (todo clique reexecuta
        # o script), mas o schema é idempotente e só precisa rodar uma vez por
        # processo. Sem essa guarda, contra um banco remoto (Turso) as ~70
        # verificações abaixo — cada uma uma requisição HTTP separada —
        # acrescentariam vários segundos a CADA interação do usuário.
        return
    _schema_initialized = True
    UPLOAD_DIR.mkdir(parents=True, exist_ok=True)
    (UPLOAD_DIR / "company_documents").mkdir(parents=True, exist_ok=True)
    (UPLOAD_DIR / "company_templates").mkdir(parents=True, exist_ok=True)
    with connect() as conn:
        conn.executescript(SCHEMA)
        user_columns = {row["name"] for row in conn.execute("PRAGMA table_info(users)")}
        contract_columns = {row["name"] for row in conn.execute("PRAGMA table_info(contracts)")}
        if "totp_secret" not in user_columns:
            conn.execute("ALTER TABLE users ADD COLUMN totp_secret TEXT")
        if "totp_enabled" not in user_columns:
            conn.execute("ALTER TABLE users ADD COLUMN totp_enabled INTEGER NOT NULL DEFAULT 0")
        if "require_2fa" not in user_columns:
            conn.execute("ALTER TABLE users ADD COLUMN require_2fa INTEGER NOT NULL DEFAULT 0")
        if "preferred_theme" not in user_columns:
            conn.execute("ALTER TABLE users ADD COLUMN preferred_theme TEXT NOT NULL DEFAULT 'Escuro'")
        if "last_page" not in user_columns:
            conn.execute("ALTER TABLE users ADD COLUMN last_page TEXT NOT NULL DEFAULT 'Visão geral'")
        user_security_additions = {
            "failed_login_attempts": "INTEGER NOT NULL DEFAULT 0",
            "locked_until": "TEXT",
            "last_login_at": "TEXT",
            "password_changed_at": "TEXT",
            "must_change_password": "INTEGER NOT NULL DEFAULT 0",
        }
        for name, definition in user_security_additions.items():
            if name not in user_columns:
                conn.execute(f"ALTER TABLE users ADD COLUMN {name} {definition}")
        permission_columns = {
            row["name"]
            for row in conn.execute("PRAGMA table_info(user_permissions)")
        }
        if "can_create" not in permission_columns:
            conn.execute(
                "ALTER TABLE user_permissions "
                "ADD COLUMN can_create INTEGER NOT NULL DEFAULT 0"
            )
            conn.execute(
                """UPDATE user_permissions SET can_create=can_edit
                WHERE can_edit=1"""
            )
        if "archived" not in contract_columns:
            conn.execute("ALTER TABLE contracts ADD COLUMN archived INTEGER NOT NULL DEFAULT 0")
        if "archived_at" not in contract_columns:
            conn.execute("ALTER TABLE contracts ADD COLUMN archived_at TEXT")
        if "archived_by" not in contract_columns:
            conn.execute("ALTER TABLE contracts ADD COLUMN archived_by INTEGER")
        if "tax_regime" not in contract_columns:
            conn.execute(
                "ALTER TABLE contracts ADD COLUMN tax_regime TEXT NOT NULL DEFAULT 'NÃO DEFINIDO'"
            )
        if "original_start_date" not in contract_columns:
            conn.execute("ALTER TABLE contracts ADD COLUMN original_start_date TEXT")
        if "original_end_date" not in contract_columns:
            conn.execute("ALTER TABLE contracts ADD COLUMN original_end_date TEXT")
        if "cno_required" not in contract_columns:
            conn.execute("ALTER TABLE contracts ADD COLUMN cno_required INTEGER")
        if "process_number" not in contract_columns:
            conn.execute("ALTER TABLE contracts ADD COLUMN process_number TEXT")
        bid_process_columns = {row["name"] for row in conn.execute("PRAGMA table_info(bid_processes)")}
        if bid_process_columns and "agency_cnpj" not in bid_process_columns:
            conn.execute("ALTER TABLE bid_processes ADD COLUMN agency_cnpj TEXT")
        if bid_process_columns and "uasg" not in bid_process_columns:
            conn.execute("ALTER TABLE bid_processes ADD COLUMN uasg TEXT")
        if bid_process_columns and "scope" not in bid_process_columns:
            conn.execute("ALTER TABLE bid_processes ADD COLUMN scope TEXT")
        if bid_process_columns and "quantity" not in bid_process_columns:
            conn.execute("ALTER TABLE bid_processes ADD COLUMN quantity REAL")
        if bid_process_columns and "estimated_unit_value" not in bid_process_columns:
            conn.execute("ALTER TABLE bid_processes ADD COLUMN estimated_unit_value REAL")
        if bid_process_columns and "dispute_time" not in bid_process_columns:
            conn.execute("ALTER TABLE bid_processes ADD COLUMN dispute_time TEXT")
        if bid_process_columns and "is_confidential" not in bid_process_columns:
            conn.execute("ALTER TABLE bid_processes ADD COLUMN is_confidential INTEGER NOT NULL DEFAULT 0")
        if bid_process_columns and "dispute_mode" not in bid_process_columns:
            conn.execute("ALTER TABLE bid_processes ADD COLUMN dispute_mode TEXT")
        bid_lot_columns = {row["name"] for row in conn.execute("PRAGMA table_info(bid_lots)")}
        if bid_lot_columns and "lot_type" not in bid_lot_columns:
            conn.execute("ALTER TABLE bid_lots ADD COLUMN lot_type TEXT NOT NULL DEFAULT 'ITEM'")
        bid_ranking_columns = {row["name"] for row in conn.execute("PRAGMA table_info(bid_rankings)")}
        if bid_ranking_columns and "company_cnpj" not in bid_ranking_columns:
            conn.execute("ALTER TABLE bid_rankings ADD COLUMN company_cnpj TEXT")
        if bid_ranking_columns and "situation" not in bid_ranking_columns:
            conn.execute(
                "ALTER TABLE bid_rankings ADD COLUMN situation TEXT NOT NULL DEFAULT 'CLASSIFICADA'"
            )
        if bid_ranking_columns and "bid_lot_id" not in bid_ranking_columns:
            conn.execute("ALTER TABLE bid_rankings ADD COLUMN bid_lot_id INTEGER")
        if bid_ranking_columns and "technical_score" not in bid_ranking_columns:
            conn.execute("ALTER TABLE bid_rankings ADD COLUMN technical_score REAL")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_bid_ranking_lot ON bid_rankings(bid_lot_id)")
        document_columns = {row["name"] for row in conn.execute("PRAGMA table_info(documents)")}
        if "union_id" not in document_columns:
            conn.execute("ALTER TABLE documents ADD COLUMN union_id INTEGER")
        if "art_id" not in document_columns:
            conn.execute("ALTER TABLE documents ADD COLUMN art_id INTEGER")
        if "cno_id" not in document_columns:
            conn.execute("ALTER TABLE documents ADD COLUMN cno_id INTEGER")
        if "ata_contract_id" not in document_columns:
            conn.execute("ALTER TABLE documents ADD COLUMN ata_contract_id INTEGER")
        if "ata_amendment_id" not in document_columns:
            conn.execute("ALTER TABLE documents ADD COLUMN ata_amendment_id INTEGER")
        if "guarantee_id" not in document_columns:
            conn.execute("ALTER TABLE documents ADD COLUMN guarantee_id INTEGER")
        if "guarantee_endorsement_id" not in document_columns:
            conn.execute(
                "ALTER TABLE documents ADD COLUMN guarantee_endorsement_id INTEGER"
            )
        if "sesmt_professional_id" not in document_columns:
            conn.execute("ALTER TABLE documents ADD COLUMN sesmt_professional_id INTEGER")
        if "sesmt_exam_id" not in document_columns:
            conn.execute("ALTER TABLE documents ADD COLUMN sesmt_exam_id INTEGER")
        if "sesmt_training_id" not in document_columns:
            conn.execute("ALTER TABLE documents ADD COLUMN sesmt_training_id INTEGER")
        guarantee_columns = {
            row["name"]
            for row in conn.execute("PRAGMA table_info(contract_guarantees)")
        }
        if "ata_amendment_id" not in guarantee_columns:
            conn.execute(
                "ALTER TABLE contract_guarantees ADD COLUMN ata_amendment_id INTEGER"
            )
        art_columns = {row["name"] for row in conn.execute("PRAGMA table_info(arts)")}
        if "professional_title" not in art_columns:
            conn.execute("ALTER TABLE arts ADD COLUMN professional_title TEXT")
        if "amendment_id" not in art_columns:
            conn.execute(
                "ALTER TABLE arts ADD COLUMN amendment_id INTEGER "
                "REFERENCES amendments(id) ON DELETE SET NULL"
            )
        if "instrument_scope" not in art_columns:
            conn.execute(
                "ALTER TABLE arts ADD COLUMN instrument_scope TEXT "
                "NOT NULL DEFAULT 'NÃO DEFINIDO'"
            )
        if "ata_contract_id" not in art_columns:
            conn.execute(
                "ALTER TABLE arts ADD COLUMN ata_contract_id INTEGER "
                "REFERENCES ata_contracts(id) ON DELETE SET NULL"
            )
        if "ata_amendment_id" not in art_columns:
            conn.execute(
                "ALTER TABLE arts ADD COLUMN ata_amendment_id INTEGER "
                "REFERENCES ata_contract_amendments(id) ON DELETE SET NULL"
            )
        conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_art_amendment ON arts(amendment_id)"
        )
        conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_art_ata_contract ON arts(ata_contract_id)"
        )
        conn.execute(
            """UPDATE arts SET instrument_scope='ADITIVO'
            WHERE amendment_id IS NOT NULL
            AND COALESCE(instrument_scope,'NÃO DEFINIDO')<>'ADITIVO'"""
        )
        cno_columns = {
            row["name"] for row in conn.execute("PRAGMA table_info(contract_cnos)")
        }
        if "ata_contract_id" not in cno_columns:
            conn.execute("ALTER TABLE contract_cnos ADD COLUMN ata_contract_id INTEGER")
        conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_cno_ata_contract "
            "ON contract_cnos(ata_contract_id)"
        )
        conn.execute(
            """UPDATE contracts SET cno_required=1
            WHERE cno_required IS NULL
            AND EXISTS (
                SELECT 1 FROM contract_cnos n WHERE n.contract_id=contracts.id
            )"""
        )
        obligation_columns = {row["name"] for row in conn.execute("PRAGMA table_info(obligations)")}
        obligation_additions = {
            "copy_emails": "TEXT",
            "notification_enabled": "INTEGER NOT NULL DEFAULT 1",
            "reminder_frequency_days": "INTEGER NOT NULL DEFAULT 7",
            "last_reminder_at": "TEXT",
            "reminder_count": "INTEGER NOT NULL DEFAULT 0",
        }
        for name, definition in obligation_additions.items():
            if name not in obligation_columns:
                conn.execute(f"ALTER TABLE obligations ADD COLUMN {name} {definition}")
        initial_instruments = conn.execute(
            """SELECT id,contract_id,start_date,end_date
            FROM amendments
            WHERE UPPER(TRIM(COALESCE(ordinal,'')))
                IN ('INICIAL','CONTRATO INICIAL')
            AND UPPER(TRIM(COALESCE(kind,'')))
                IN ('CONTRATO','CONTRATO INICIAL')
            ORDER BY id"""
        ).fetchall()
        if initial_instruments:
            for row in initial_instruments:
                conn.execute(
                    """UPDATE contracts SET
                    original_start_date=COALESCE(
                        NULLIF(original_start_date,''),NULLIF(?,''),start_date
                    ),
                    original_end_date=COALESCE(
                        NULLIF(original_end_date,''),NULLIF(?,''),end_date
                    )
                    WHERE id=?""",
                    (row["start_date"], row["end_date"], row["contract_id"]),
                )
            initial_ids = [int(row["id"]) for row in initial_instruments]
            placeholders = ",".join("?" for _ in initial_ids)
            conn.execute(
                f"UPDATE documents SET amendment_id=NULL "
                f"WHERE amendment_id IN ({placeholders})",
                initial_ids,
            )
            conn.execute(
                f"UPDATE contract_unions SET amendment_id=NULL "
                f"WHERE amendment_id IN ({placeholders})",
                initial_ids,
            )
            conn.execute(
                f"DELETE FROM amendments WHERE id IN ({placeholders})",
                initial_ids,
            )
            conn.execute(
                """INSERT INTO audit_log(
                user_id,action,entity,entity_id,details)
                VALUES(NULL,'MIGRAR CONTRATO INICIAL','aditivos',NULL,?)""",
                (
                    f"{len(initial_ids)} registro(s) de contrato inicial foram "
                    "retirados da lista de aditivos. As datas originais foram "
                    "preservadas na ficha do contrato.",
                ),
            )
        conn.execute(
            """UPDATE contracts SET
            original_start_date=COALESCE(NULLIF(original_start_date,''),start_date),
            original_end_date=COALESCE(NULLIF(original_end_date,''),end_date)
            WHERE original_start_date IS NULL OR original_start_date=''
               OR original_end_date IS NULL OR original_end_date=''"""
        )
        for table_name in ("amendments", "ata_contract_amendments"):
            pending_durations = conn.execute(
                f"""SELECT id,start_date,end_date FROM {table_name}
                WHERE start_date IS NOT NULL AND start_date<>''
                AND end_date IS NOT NULL AND end_date<>''
                AND duration_months IS NULL"""
            ).fetchall()
            for row in pending_durations:
                duration = contract_duration_months(row["start_date"], row["end_date"])
                if duration is not None:
                    conn.execute(
                        f"UPDATE {table_name} SET duration_months=? WHERE id=?",
                        (duration, row["id"]),
                    )
        corrected_contracts = conn.execute(
            """UPDATE contracts
            SET current_value=original_value, updated_at=CURRENT_TIMESTAMP
            WHERE COALESCE(current_value,0)<=0
            AND COALESCE(original_value,0)>0
            AND NOT EXISTS (
                SELECT 1 FROM amendments a WHERE a.contract_id=contracts.id
            )"""
        )
        corrected_ata_contracts = conn.execute(
            """UPDATE ata_contracts
            SET current_value=original_value, updated_at=CURRENT_TIMESTAMP
            WHERE COALESCE(current_value,0)<=0
            AND COALESCE(original_value,0)>0
            AND NOT EXISTS (
                SELECT 1 FROM ata_contract_amendments a
                WHERE a.ata_contract_id=ata_contracts.id
            )"""
        )
        if corrected_contracts.rowcount:
            conn.execute(
                """INSERT INTO audit_log(
                user_id,action,entity,entity_id,details)
                VALUES(NULL,'CORRIGIR VALOR ATUAL','contratos sem aditivo',NULL,?)""",
                (
                    f"{corrected_contracts.rowcount} contrato(s) atualizado(s): "
                    "valor atual definido a partir do valor original.",
                ),
            )
        if corrected_ata_contracts.rowcount:
            conn.execute(
                """INSERT INTO audit_log(
                user_id,action,entity,entity_id,details)
                VALUES(NULL,'CORRIGIR VALOR ATUAL','contratos de ATA sem aditivo',NULL,?)""",
                (
                    f"{corrected_ata_contracts.rowcount} contrato(s) atualizado(s): "
                    "valor atual definido a partir do valor original.",
                ),
            )
        position_columns = {row["name"] for row in conn.execute("PRAGMA table_info(contract_positions)")}
        if "hazard_percent" not in position_columns:
            conn.execute("ALTER TABLE contract_positions ADD COLUMN hazard_percent REAL NOT NULL DEFAULT 0")
        if "unhealthy_percent" not in position_columns:
            conn.execute("ALTER TABLE contract_positions ADD COLUMN unhealthy_percent REAL NOT NULL DEFAULT 0")
        if "unhealthy_base_year" not in position_columns:
            conn.execute("ALTER TABLE contract_positions ADD COLUMN unhealthy_base_year INTEGER")
        union_columns = {row["name"] for row in conn.execute("PRAGMA table_info(contract_unions)")}
        if "amendment_id" not in union_columns:
            conn.execute("ALTER TABLE contract_unions ADD COLUMN amendment_id INTEGER")
        financial_columns = {row["name"] for row in conn.execute("PRAGMA table_info(financial_parameters)")}
        for name in (
            "justification_text", "signatory_name", "signatory_registration",
            "signatory_cpf", "signatory_title",
        ):
            if name not in financial_columns:
                conn.execute(f"ALTER TABLE financial_parameters ADD COLUMN {name} TEXT")
        admin = conn.execute("SELECT id FROM users WHERE email = ?", ("admin@engemil.local",)).fetchone()
        if not admin:
            conn.execute(
                """INSERT INTO users(
                name,email,password_hash,role,must_change_password)
                VALUES(?,?,?,?,1)""",
                ("Administrador", "admin@engemil.local", hash_password("Alterar@123"), "admin"),
            )
        conn.execute(
            """INSERT OR IGNORE INTO financial_parameters
            (id,reference_year,equity_value,gross_revenue,notes) VALUES(1,2025,139259969.94,420350912.61,'Valores importados da planilha de referência.')"""
        )
        conn.execute(
            """UPDATE financial_parameters SET
            signatory_name=COALESCE(signatory_name,'MATHEUS ANTÔNIO MILITÃO DE MENEZES'),
            signatory_registration=COALESCE(signatory_registration,'CREA 13.814/D-DF'),
            signatory_cpf=COALESCE(signatory_cpf,'000.400.681-02'),
            signatory_title=COALESCE(signatory_title,'Engenheiro Civil - Sócio Diretor')
            WHERE id=1"""
        )
        templates = (
            (
                "Ofício ENGEMIL",
                "OFICIO",
                "Ofício padronizado com numeração automática, destinatário, assunto e assinatura.",
                "MODELO_OFICIO_ENGEMIL-2026.dotm",
                "templates/company_documents/MODELO_OFICIO_ENGEMIL-2026.dotm",
                "MODELO_OFICIO_ENGEMIL-2026.docx",
                "templates/company_documents/MODELO_OFICIO_ENGEMIL-2026.docx",
            ),
            (
                "Carta de Preposto ENGEMIL",
                "CARTA_PREPOSTO",
                "Carta padronizada para indicação de preposto ou responsável técnico.",
                "MODELO_PREPOSTO_ENGEMIL-2026.dotm",
                "templates/company_documents/MODELO_PREPOSTO_ENGEMIL-2026.dotm",
                "MODELO_PREPOSTO_ENGEMIL-2026.docx",
                "templates/company_documents/MODELO_PREPOSTO_ENGEMIL-2026.docx",
            ),
            (
                "Procuração ENGEMIL",
                "PROCURACAO",
                "Procuração padronizada com outorgado, poderes, validade e assinatura.",
                "MODELO_PROCURACAO_ENGEMIL-2026.dotm",
                "templates/company_documents/MODELO_PROCURACAO_ENGEMIL-2026.dotm",
                "MODELO_PROCURACAO_ENGEMIL-2026.docx",
                "templates/company_documents/MODELO_PROCURACAO_ENGEMIL-2026.docx",
            ),
        )
        conn.executemany(
            """INSERT OR IGNORE INTO company_document_templates(
            name,document_type,description,original_filename,original_path,
            generation_filename,generation_path) VALUES(?,?,?,?,?,?,?)""",
            templates,
        )
        conn.executemany(
            """INSERT OR IGNORE INTO company_signatories(name,registration,cpf,title)
            VALUES(?,?,?,?)""",
            (
                (
                    "MATHEUS ANTONIO MILITAO DE MENEZES",
                    "CREA 13.814/D-DF",
                    "000.400.681-02",
                    "Engenheiro Civil - Sócio Diretor",
                ),
                (
                    "REGITON LUIZ MILITÃO DE MENEZES",
                    "",
                    "907.015.771-34",
                    "Diretor Administrativo",
                ),
            ),
        )
        modules = (
            "dashboard", "contracts", "contract_detail", "new_contract",
            "exports", "indices", "company_documents", "bids", "sesmt",
        )
        for user in conn.execute("SELECT id,role FROM users WHERE role<>'admin'").fetchall():
            default_create = 1 if user["role"] in ("gestor", "engenheiro", "operador") else 0
            default_edit = 1 if user["role"] in ("gestor", "engenheiro") else 0
            for module in modules:
                if module == "sesmt" and user["role"] == "sesmt":
                    module_create, module_edit = 1, 1
                else:
                    module_create, module_edit = default_create, default_edit
                conn.execute(
                    """INSERT OR IGNORE INTO user_permissions(
                    user_id,module,can_view,can_create,can_edit,can_delete)
                    VALUES(?,?,1,?,?,0)""",
                    (user["id"], module, module_create, module_edit),
                )
        conn.execute(
            "INSERT OR IGNORE INTO labor_parameters(year,minimum_wage,notes) VALUES(?,?,?)",
            (datetime.now().year, 0, "Informe o salário mínimo oficial antes de calcular a insalubridade."),
        )


UPLOADS_BLOB_KEY = "uploads_archive_v1"
_uploads_restored = False
_last_uploads_fingerprint = None


def save_blob(key: str, data: bytes) -> None:
    with connect() as conn:
        conn.execute("DELETE FROM blob_store WHERE key=?", (key,))
        conn.execute(
            "INSERT INTO blob_store(key,data,updated_at) VALUES(?,?,CURRENT_TIMESTAMP)",
            (key, data),
        )


def load_blob(key: str) -> bytes | None:
    with connect() as conn:
        row = conn.execute("SELECT data FROM blob_store WHERE key=?", (key,)).fetchone()
        return bytes(row["data"]) if row and row["data"] is not None else None


def _uploads_fingerprint() -> tuple[int, int, float]:
    count = 0
    total_size = 0
    latest_mtime = 0.0
    if UPLOAD_DIR.exists():
        for path in UPLOAD_DIR.rglob("*"):
            if path.is_file():
                stat = path.stat()
                count += 1
                total_size += stat.st_size
                latest_mtime = max(latest_mtime, stat.st_mtime)
    return (count, total_size, latest_mtime)


def sync_uploads_from_storage() -> None:
    """Restaura uploads/ a partir do banco quando o contêiner sobe do zero.

    Só faz algo quando há um banco hospedado configurado (_turso_config) —
    em desenvolvimento local os arquivos já estão em disco e isso não roda.
    """
    global _uploads_restored, _last_uploads_fingerprint
    if _uploads_restored or not _turso_config():
        return
    _uploads_restored = True
    data = load_blob(UPLOADS_BLOB_KEY)
    if data:
        UPLOAD_DIR.mkdir(parents=True, exist_ok=True)
        with zipfile.ZipFile(io.BytesIO(data)) as zf:
            zf.extractall(UPLOAD_DIR)
    _last_uploads_fingerprint = _uploads_fingerprint()


def sync_uploads_to_storage_if_changed() -> None:
    """Salva uploads/ no banco quando algo mudou desde a última verificação."""
    global _last_uploads_fingerprint
    if not _turso_config():
        return
    fingerprint = _uploads_fingerprint()
    if fingerprint == _last_uploads_fingerprint:
        return
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as zf:
        for path in UPLOAD_DIR.rglob("*"):
            if path.is_file():
                zf.write(path, path.relative_to(UPLOAD_DIR))
    save_blob(UPLOADS_BLOB_KEY, buffer.getvalue())
    _last_uploads_fingerprint = fingerprint


def query(sql: str, params: tuple = ()):
    with connect() as conn:
        return conn.execute(sql, params).fetchall()


def execute(sql: str, params: tuple = ()) -> int:
    with connect() as conn:
        cur = conn.execute(sql, params)
        return cur.lastrowid


def next_document_sequence(document_type: str, year: int) -> int:
    with connect() as conn:
        conn.execute(
            """INSERT OR IGNORE INTO document_sequences(document_type,year,last_number)
            VALUES(?,?,0)""",
            (document_type, year),
        )
        conn.execute(
            """UPDATE document_sequences SET last_number=last_number+1
            WHERE document_type=? AND year=?""",
            (document_type, year),
        )
        return int(conn.execute(
            """SELECT last_number FROM document_sequences
            WHERE document_type=? AND year=?""",
            (document_type, year),
        ).fetchone()["last_number"])


def _effective_contract_end(conn, contract_id: int) -> str | None:
    row = conn.execute(
        """SELECT COALESCE(
            (SELECT end_date FROM amendments
             WHERE contract_id=? AND end_date IS NOT NULL AND end_date<>''
             AND NOT (
                UPPER(TRIM(COALESCE(ordinal,'')))
                    IN ('INICIAL','CONTRATO INICIAL')
                AND UPPER(TRIM(COALESCE(kind,'')))
                    IN ('CONTRATO','CONTRATO INICIAL')
             )
             ORDER BY id DESC LIMIT 1),
            (SELECT end_date FROM contracts WHERE id=?)
        ) effective_end""",
        (contract_id, contract_id),
    ).fetchone()
    return row["effective_end"] if row else None


def refresh_contract_lifecycle(contract_id: int, grace_days: int = 30) -> str:
    """Reativa uma vigência prorrogada ou arquiva um contrato vencido após a tolerância."""
    with connect() as conn:
        effective_end = _effective_contract_end(conn, contract_id)
        if not effective_end:
            return "SEM_PRAZO"
        try:
            end_date = date.fromisoformat(str(effective_end)[:10])
        except ValueError:
            return "PRAZO_INVALIDO"
        if end_date >= date.today():
            conn.execute(
                """UPDATE contracts SET archived=0,archived_at=NULL,archived_by=NULL,
                status=CASE WHEN status='ENCERRADO' THEN 'ATIVO' ELSE status END,
                updated_at=CURRENT_TIMESTAMP WHERE id=?""",
                (contract_id,),
            )
            return "ATIVO"
        if end_date <= date.today() - timedelta(days=grace_days):
            conn.execute(
                """UPDATE contracts SET archived=1,archived_at=COALESCE(archived_at,CURRENT_TIMESTAMP),
                archived_by=NULL,status='ENCERRADO',updated_at=CURRENT_TIMESTAMP WHERE id=?""",
                (contract_id,),
            )
            return "ARQUIVADO"
        return "AGUARDANDO_ADITIVO"


_last_archive_scan_date = None


def archive_expired_contracts(grace_days: int = 30) -> list[int]:
    """Arquiva somente vigências sem prorrogação há pelo menos `grace_days`.

    Chamada a cada rerun do Streamlit, mas o critério é por data (dia), então
    rodar mais de uma vez no mesmo dia não muda o resultado — só reexecuta
    uma consulta por contrato ativo à toa. Contra um banco remoto isso soma
    segundos a cada clique conforme a base de contratos cresce, por isso
    limitamos a varredura a uma vez por dia por processo.
    """
    global _last_archive_scan_date
    today = date.today()
    if _last_archive_scan_date == today:
        return []
    _last_archive_scan_date = today
    archived_ids = []
    with connect() as conn:
        rows = conn.execute("SELECT id FROM contracts WHERE archived=0").fetchall()
        cutoff = date.today() - timedelta(days=grace_days)
        for row in rows:
            effective_end = _effective_contract_end(conn, row["id"])
            if not effective_end:
                continue
            try:
                end_date = date.fromisoformat(str(effective_end)[:10])
            except ValueError:
                continue
            if end_date <= cutoff:
                conn.execute(
                    """UPDATE contracts SET archived=1,archived_at=CURRENT_TIMESTAMP,
                    archived_by=NULL,status='ENCERRADO',updated_at=CURRENT_TIMESTAMP WHERE id=?""",
                    (row["id"],),
                )
                conn.execute(
                    """INSERT INTO audit_log(user_id,action,entity,entity_id,details)
                    VALUES(NULL,'ARQUIVAR AUTOMATICAMENTE','contrato',?,
                    'Vigência encerrada há 30 dias sem novo aditivo')""",
                    (row["id"],),
                )
                archived_ids.append(row["id"])
    return archived_ids


def log_action(user_id: int | None, action: str, entity: str, entity_id: int | None, details: str = ""):
    execute(
        "INSERT INTO audit_log(user_id,action,entity,entity_id,details) VALUES(?,?,?,?,?)",
        (user_id, action, entity, entity_id, details),
    )


def authenticate(email: str, password: str):
    """Autentica com bloqueio temporário após tentativas consecutivas."""
    normalized_email = str(email or "").strip()
    rows = query(
        "SELECT * FROM users WHERE email=? AND active=1",
        (normalized_email,),
    )
    if not rows:
        # Mantém custo criptográfico próximo ao de um usuário real e evita
        # facilitar enumeração de contas por diferença de tempo.
        verify_password(str(password or ""), hash_password("credencial-inexistente"))
        return None
    account = rows[0]
    now = _utc_now()
    locked_until = _stored_datetime(account["locked_until"])
    if locked_until and now < locked_until:
        return None
    if not verify_password(str(password or ""), account["password_hash"]):
        attempts = int(account["failed_login_attempts"] or 0) + 1
        new_lock = (
            (now + timedelta(minutes=15)).isoformat()
            if attempts >= 5 else None
        )
        execute(
            """UPDATE users SET failed_login_attempts=?,locked_until=?
            WHERE id=?""",
            (0 if new_lock else attempts, new_lock, account["id"]),
        )
        log_action(
            None,
            "LOGIN RECUSADO",
            "segurança",
            account["id"],
            "Conta temporariamente bloqueada por 15 minutos."
            if new_lock else f"Tentativa inválida {attempts} de 5.",
        )
        return None
    execute(
        """UPDATE users SET failed_login_attempts=0,locked_until=NULL,
        last_login_at=? WHERE id=?""",
        (now.isoformat(), account["id"]),
    )
    return get_user(account["id"])


def get_user(user_id: int):
    rows = query("SELECT * FROM users WHERE id=? AND active=1", (user_id,))
    return rows[0] if rows else None


def _utc_now() -> datetime:
    return datetime.now(timezone.utc).replace(microsecond=0)


def _session_token_hash(token: str) -> str:
    return hashlib.sha256(str(token or "").encode("utf-8")).hexdigest()


def _user_agent_hash(user_agent: str | None) -> str | None:
    normalized = str(user_agent or "").strip()
    return hashlib.sha256(normalized.encode("utf-8")).hexdigest() if normalized else None


def _stored_datetime(value) -> datetime | None:
    if not value:
        return None
    try:
        parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except ValueError:
        return None
    return parsed.replace(tzinfo=parsed.tzinfo or timezone.utc).astimezone(timezone.utc)


def create_user_session(
    user_id: int,
    user_agent: str | None = None,
    idle_minutes: int = SESSION_IDLE_MINUTES,
) -> str:
    """Cria uma sessão revogável; somente o hash do token fica no banco."""
    token = secrets.token_urlsafe(48)
    now = _utc_now()
    expires_at = now + timedelta(minutes=max(5, int(idle_minutes)))
    execute(
        """INSERT INTO user_sessions(
        user_id,token_hash,user_agent_hash,created_at,last_activity_at,expires_at)
        VALUES(?,?,?,?,?,?)""",
        (
            user_id,
            _session_token_hash(token),
            _user_agent_hash(user_agent),
            now.isoformat(),
            now.isoformat(),
            expires_at.isoformat(),
        ),
    )
    return token


def validate_user_session(
    token: str,
    user_agent: str | None = None,
    *,
    touch: bool = True,
    idle_minutes: int = SESSION_IDLE_MINUTES,
):
    """Valida a sessão persistente e renova a expiração quando há atividade."""
    if not token:
        return None
    rows = query(
        """SELECT s.id session_id,s.user_id,s.user_agent_hash,s.expires_at,u.*
        FROM user_sessions s
        JOIN users u ON u.id=s.user_id
        WHERE s.token_hash=? AND s.revoked_at IS NULL AND u.active=1""",
        (_session_token_hash(token),),
    )
    if not rows:
        return None
    session = rows[0]
    now = _utc_now()
    expires_at = _stored_datetime(session["expires_at"])
    expected_agent = session["user_agent_hash"]
    received_agent = _user_agent_hash(user_agent)
    if (
        expires_at is None
        or now >= expires_at
        or (expected_agent and received_agent and expected_agent != received_agent)
    ):
        execute(
            "UPDATE user_sessions SET revoked_at=? WHERE id=? AND revoked_at IS NULL",
            (now.isoformat(), session["session_id"]),
        )
        return None
    if touch:
        renewed_until = now + timedelta(minutes=max(5, int(idle_minutes)))
        execute(
            """UPDATE user_sessions
            SET last_activity_at=?,expires_at=? WHERE id=? AND revoked_at IS NULL""",
            (now.isoformat(), renewed_until.isoformat(), session["session_id"]),
        )
    return get_user(session["user_id"])


def revoke_user_session(token: str) -> None:
    if not token:
        return
    execute(
        """UPDATE user_sessions SET revoked_at=?
        WHERE token_hash=? AND revoked_at IS NULL""",
        (_utc_now().isoformat(), _session_token_hash(token)),
    )


def revoke_user_sessions(user_id: int, except_token: str | None = None) -> None:
    parameters: list[object] = [_utc_now().isoformat(), user_id]
    condition = ""
    if except_token:
        condition = " AND token_hash<>?"
        parameters.append(_session_token_hash(except_token))
    execute(
        f"""UPDATE user_sessions SET revoked_at=?
        WHERE user_id=? AND revoked_at IS NULL{condition}""",
        tuple(parameters),
    )


def iso(value) -> str | None:
    if value in (None, ""):
        return None
    if isinstance(value, datetime):
        return value.date().isoformat()
    if hasattr(value, "isoformat"):
        return value.isoformat()
    text = str(value).strip()
    for fmt in ("%d/%m/%Y", "%Y-%m-%d", "%Y-%m-%d %H:%M:%S"):
        try:
            return datetime.strptime(text, fmt).date().isoformat()
        except ValueError:
            pass
    return text
