from __future__ import annotations

import os
import re
import smtplib
import ssl
from email.message import EmailMessage
from email.utils import getaddresses
from pathlib import Path


SMTP_FIELDS = (
    "SMTP_HOST",
    "SMTP_PORT",
    "SMTP_USE_SSL",
    "SMTP_USER",
    "SMTP_PASSWORD",
    "SMTP_FROM",
    "SMTP_DEFAULT_CC",
)
SMTP_REQUIRED = ("SMTP_HOST", "SMTP_USER", "SMTP_PASSWORD", "SMTP_FROM")
PLACEHOLDER_MARKERS = (
    "SEUDOMINIO",
    "SUBSTITUA",
    "PREENCHA",
    "INFORME_A_",
    "CONTA_GOOGLE",
    "SENHA_DE_APP",
    "USUARIO@",
)


def normalize_recipients(value) -> list[str]:
    if isinstance(value, (list, tuple, set)):
        source = ",".join(
            str(item or "").strip() for item in value if str(item or "").strip()
        )
    else:
        source = str(value or "").strip()
    source = source.replace(";", ",").strip(" ,")
    recipients = []
    for _, address in getaddresses([source]):
        cleaned = address.strip()
        if cleaned and "@" in cleaned and cleaned not in recipients:
            recipients.append(cleaned)
    return recipients


def _config_path() -> Path:
    configured_path = os.getenv("GESTAO_SMTP_CONFIG", "").strip()
    if configured_path:
        return Path(configured_path).expanduser()
    return Path(__file__).resolve().parent / "configuracao_email.bat"


def _read_batch_config(path: Path) -> dict[str, str]:
    """Lê somente as chaves SMTP do BAT, sem executar nem expandir a senha."""
    if not path.is_file():
        return {}
    values: dict[str, str] = {}
    try:
        lines = path.read_text(encoding="utf-8-sig", errors="replace").splitlines()
    except OSError:
        return {}
    quoted_set = re.compile(r'^\s*set\s+"([A-Za-z_][A-Za-z0-9_]*)=(.*)"\s*$', re.I)
    plain_set = re.compile(r"^\s*set\s+([A-Za-z_][A-Za-z0-9_]*)=(.*)$", re.I)
    allowed = set(SMTP_FIELDS)
    for line in lines:
        match = quoted_set.match(line) or plain_set.match(line)
        if not match:
            continue
        key = match.group(1).upper()
        if key in allowed:
            values[key] = match.group(2).strip()
    return values


def _secret(name: str) -> str:
    value = os.getenv(name, "").strip()
    if value:
        return value
    try:
        import streamlit as st
        return str(st.secrets.get(name, "") or "").strip()
    except Exception:
        return ""


def _environment_config() -> dict[str, str]:
    # Lê de variável de ambiente primeiro e, se ausente, dos "Secrets" do
    # Streamlit Cloud — é assim que o app publicado (sem acesso ao .bat
    # local) recebe a configuração de SMTP.
    return {name: _secret(name) for name in SMTP_FIELDS}


def _is_placeholder(value: str) -> bool:
    normalized = str(value or "").strip().upper()
    return not normalized or any(marker in normalized for marker in PLACEHOLDER_MARKERS)


def _invalid_required(config: dict[str, str]) -> list[str]:
    return [name for name in SMTP_REQUIRED if _is_placeholder(config.get(name, ""))]


def _smtp_config() -> dict:
    """Obtém uma configuração SMTP atômica e atualizada.

    Um configuracao_email.bat válido é prioritário sobre variáveis herdadas pelo
    processo. O arquivo é relido em cada chamada, portanto F5, testes manuais e
    o agendador passam a usar a mesma configuração sem reiniciar o Streamlit.
    """
    path = _config_path()
    file_config = _read_batch_config(path)
    env_config = _environment_config()

    if file_config and not _invalid_required(file_config):
        selected = {name: file_config.get(name, "") for name in SMTP_FIELDS}
        source = path.name
    elif not _invalid_required(env_config):
        selected = env_config
        source = "variáveis do ambiente"
    elif file_config:
        selected = {name: file_config.get(name, "") for name in SMTP_FIELDS}
        source = path.name
    else:
        selected = env_config
        source = "variáveis do ambiente"

    missing = _invalid_required(selected)
    try:
        port = int(selected.get("SMTP_PORT") or "587")
        if not 1 <= port <= 65535:
            raise ValueError
    except ValueError:
        port = 587
        if "SMTP_PORT" not in missing:
            missing.append("SMTP_PORT")

    use_ssl = str(selected.get("SMTP_USE_SSL") or "0").strip() == "1"
    warnings: list[str] = []
    host = selected.get("SMTP_HOST", "")
    user = selected.get("SMTP_USER", "")
    sender = selected.get("SMTP_FROM", "") or user
    if "kinghost" in host.lower() and user and sender and user.lower() != sender.lower():
        warnings.append(
            "Na KingHost, mantenha SMTP_USER e SMTP_FROM iguais à caixa postal autenticada."
        )

    return {
        **selected,
        "configured": not missing,
        "missing": missing,
        "host": host,
        "port": port,
        "user": user,
        "sender": sender,
        "default_cc": selected.get("SMTP_DEFAULT_CC", ""),
        "use_ssl": use_ssl,
        "security": "SSL/TLS" if use_ssl else "STARTTLS",
        "source": source,
        "config_file_found": path.is_file(),
        "warnings": warnings,
    }


def smtp_status() -> dict:
    """Retorna somente dados seguros para diagnóstico; nunca retorna a senha."""
    config = _smtp_config()
    return {
        key: config[key]
        for key in (
            "configured",
            "missing",
            "host",
            "port",
            "user",
            "sender",
            "default_cc",
            "use_ssl",
            "security",
            "source",
            "config_file_found",
            "warnings",
        )
    }


def send_email(
    recipient: str, subject: str, body: str, cc=None, html_body: str = None,
    attachments=None,
) -> tuple[bool, str]:
    config = _smtp_config()
    if not config["configured"]:
        return False, "SMTP não configurado. A obrigação continua registrada no painel."

    recipients = normalize_recipients(recipient)
    # normalize_recipients(cc) achata cc primeiro (aceita string única ou
    # lista/tupla/set de endereços) antes de juntar com o CC padrão — sem
    # isso, passar uma lista em cc virava uma lista aninhada e quebrava o
    # parsing dos endereços.
    copies = normalize_recipients([*normalize_recipients(cc), config["default_cc"]])
    copies = [address for address in copies if address not in recipients]
    if not recipients:
        return False, "Nenhum e-mail de destinatário válido foi informado."

    msg = EmailMessage()
    msg["From"] = config["sender"]
    msg["To"] = ", ".join(recipients)
    msg["Subject"] = subject
    msg["Reply-To"] = config["sender"]
    msg["X-Mailer"] = "Gestão Contratual ENGEMIL"
    if copies:
        msg["Cc"] = ", ".join(copies)
    msg.set_content(body)
    if html_body:
        msg.add_alternative(html_body, subtype="html")
    for filename, content in (attachments or []):
        msg.add_attachment(
            content, maintype="application", subtype="octet-stream", filename=filename,
        )

    try:
        context = ssl.create_default_context()
        if config["use_ssl"]:
            server_connection = smtplib.SMTP_SSL(
                config["host"], config["port"], timeout=20, context=context
            )
        else:
            server_connection = smtplib.SMTP(
                config["host"], config["port"], timeout=20
            )
        with server_connection as server:
            if not config["use_ssl"]:
                server.ehlo()
                server.starttls(context=context)
                server.ehlo()
            server.login(config["user"], config["SMTP_PASSWORD"])
            server.send_message(msg, to_addrs=[*recipients, *copies])
        copy_message = f" Cópia enviada para {len(copies)} endereço(s)." if copies else ""
        return True, f"E-mail enviado para {len(recipients)} destinatário(s).{copy_message}"
    except smtplib.SMTPAuthenticationError as exc:
        code = getattr(exc, "smtp_code", "não informado")
        return False, (
            f"Falha na autenticação SMTP (código {code}). Confira o usuário e a nova "
            "senha da caixa postal no arquivo configuracao_email.bat."
        )
    except (smtplib.SMTPConnectError, TimeoutError, OSError) as exc:
        return False, f"Falha de conexão com o servidor SMTP: {exc}"
    except smtplib.SMTPException as exc:
        return False, f"Falha no protocolo SMTP: {exc}"
    except Exception as exc:
        return False, f"Falha no envio: {exc}"


def send_test_email(recipient: str) -> tuple[bool, str]:
    return send_email(
        recipient,
        "Teste dos alertas — Gestão Contratual ENGEMIL",
        (
            "Este é um e-mail de teste da plataforma de Gestão Contratual ENGEMIL.\n\n"
            "O canal SMTP está funcionando e poderá enviar alertas de prazos, "
            "obrigações, repactuações e encerramento de contratos.\n\n"
            "Nenhuma ação é necessária."
        ),
    )
