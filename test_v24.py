import os
import tempfile
from pathlib import Path
from unittest.mock import patch


def bat_text(host, user, password, sender, default_cc=""):
    return (
        "@echo off\n"
        f'set "SMTP_HOST={host}"\n'
        'set "SMTP_PORT=587"\n'
        'set "SMTP_USE_SSL=0"\n'
        f'set "SMTP_USER={user}"\n'
        f'set "SMTP_PASSWORD={password}"\n'
        f'set "SMTP_FROM={sender}"\n'
        f'set "SMTP_DEFAULT_CC={default_cc}"\n'
    )


class FakeSMTP:
    instances = []

    def __init__(self, host, port, timeout=20):
        self.host = host
        self.port = port
        self.timeout = timeout
        self.ehlo_count = 0
        self.started_tls = False
        self.login_args = None
        self.message = None
        self.to_addrs = None
        self.__class__.instances.append(self)

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, traceback):
        return False

    def ehlo(self):
        self.ehlo_count += 1

    def starttls(self, context=None):
        self.started_tls = context is not None

    def login(self, user, password):
        self.login_args = (user, password)

    def send_message(self, message, to_addrs=None):
        self.message = message
        self.to_addrs = to_addrs


def run():
    with tempfile.TemporaryDirectory() as directory:
        config_path = Path(directory) / "configuracao_email.bat"
        os.environ["GESTAO_SMTP_CONFIG"] = str(config_path)
        os.environ["SMTP_HOST"] = "smtp.seudominio.com"
        os.environ["SMTP_PORT"] = "587"
        os.environ["SMTP_USER"] = "gestao.contratos@seudominio.com"
        os.environ["SMTP_PASSWORD"] = "senha-antiga"
        os.environ["SMTP_FROM"] = "gestao.contratos@seudominio.com"

        config_path.write_text(
            bat_text(
                "smtp.kinghost.net",
                "licitacao@engemil.com.br",
                "Senha-Ficticia!V24",
                "licitacao@engemil.com.br",
                "gestao@engemil.com.br",
            ),
            encoding="utf-8",
        )

        import notifications

        status = notifications.smtp_status()
        assert status["configured"] is True
        assert status["host"] == "smtp.kinghost.net"
        assert status["sender"] == "licitacao@engemil.com.br"
        assert status["security"] == "STARTTLS"
        assert status["source"] == "configuracao_email.bat"
        assert "SMTP_PASSWORD" not in status
        assert "Senha-Ficticia" not in repr(status)

        # A alteração do arquivo deve ser percebida sem reiniciar/importar o módulo.
        config_path.write_text(
            bat_text(
                "smtp.kinghost.net",
                "teste@engemil.com.br",
                "Outra-Senha!V24",
                "teste@engemil.com.br",
            ),
            encoding="utf-8",
        )
        assert notifications.smtp_status()["sender"] == "teste@engemil.com.br"

        FakeSMTP.instances.clear()
        with patch.object(notifications.smtplib, "SMTP", FakeSMTP):
            ok, message = notifications.send_email(
                "destino@engemil.com.br",
                "Teste V24",
                "Mensagem de teste",
                cc="copia@engemil.com.br",
            )
        assert ok, message
        sent = FakeSMTP.instances[-1]
        assert (sent.host, sent.port) == ("smtp.kinghost.net", 587)
        assert sent.started_tls and sent.ehlo_count == 2
        assert sent.login_args == ("teste@engemil.com.br", "Outra-Senha!V24")
        assert sent.message["From"] == "teste@engemil.com.br"
        assert sent.message["Reply-To"] == "teste@engemil.com.br"
        assert sent.to_addrs == ["destino@engemil.com.br", "copia@engemil.com.br"]

        config_path.write_text(
            bat_text(
                "smtp.seudominio.com",
                "usuario@seudominio.com",
                "PREENCHA_A_SENHA",
                "usuario@seudominio.com",
            ),
            encoding="utf-8",
        )
        for name in ("SMTP_HOST", "SMTP_USER", "SMTP_PASSWORD", "SMTP_FROM"):
            os.environ.pop(name, None)
        assert notifications.smtp_status()["configured"] is False

        app_source = Path("app.py").read_text(encoding="utf-8")
        alerts_source = Path("alerts.py").read_text(encoding="utf-8")
        assert 'APP_VERSION = "' in app_source
        assert "email_status['security']" in app_source
        assert "--smtp-status" in alerts_source

    print("Testes da versão 24 concluídos com sucesso.")


if __name__ == "__main__":
    run()
