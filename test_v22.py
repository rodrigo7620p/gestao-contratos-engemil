import os
import re
import tempfile
from datetime import date
from io import BytesIO
from pathlib import Path

from pypdf import PdfReader


def run():
    with tempfile.TemporaryDirectory() as directory:
        os.environ["GESTAO_DB_PATH"] = str(Path(directory) / "v22.db")
        os.environ["GESTAO_UPLOAD_DIR"] = str(Path(directory) / "uploads")

        from db import (
            authenticate,
            execute,
            get_user,
            hash_password,
            init_db,
            query,
        )
        from reports import generate_backlog_pdf

        init_db()
        user_columns = {
            row["name"] for row in query("PRAGMA table_info(users)")
        }
        permission_columns = {
            row["name"] for row in query("PRAGMA table_info(user_permissions)")
        }
        assert {
            "failed_login_attempts", "locked_until", "last_login_at",
            "must_change_password",
        }.issubset(user_columns)
        assert "can_create" in permission_columns

        operator_id = execute(
            """INSERT INTO users(
            name,email,password_hash,role,must_change_password)
            VALUES(?,?,?,'operador',1)""",
            (
                "Operador de Teste",
                "operador@example.com",
                hash_password("SenhaForte#2026"),
            ),
        )
        execute(
            """INSERT INTO user_permissions(
            user_id,module,can_view,can_create,can_edit,can_delete)
            VALUES(?,'contracts',1,1,0,0)""",
            (operator_id,),
        )
        permission = dict(query(
            "SELECT * FROM user_permissions WHERE user_id=? AND module='contracts'",
            (operator_id,),
        )[0])
        assert permission["can_create"] == 1
        assert permission["can_edit"] == 0
        assert permission["can_delete"] == 0

        for _ in range(5):
            assert authenticate("operador@example.com", "senha-invalida") is None
        locked = dict(query("SELECT * FROM users WHERE id=?", (operator_id,))[0])
        assert locked["locked_until"]
        assert authenticate("operador@example.com", "SenhaForte#2026") is None
        execute(
            "UPDATE users SET locked_until=NULL,failed_login_attempts=0 WHERE id=?",
            (operator_id,),
        )
        assert get_user(operator_id)
        assert authenticate("operador@example.com", "SenhaForte#2026")

        rows = []
        for item in range(1, 66):
            rows.append({
                "Item": item,
                "Centro de custo": f"01.02.{item:04d}",
                "Contratante": f"CONTRATANTE DE TESTE {item:02d}",
                "Contrato": f"{item:02d}/2026",
                "Início": "01/01/2026",
                "Fim": "31/12/2027",
                "Valor atual": 1_000_000 + item,
                "Instrumento vigente": "Contrato",
                "Remanescente total": 500_000 + item,
            })
        pdf = generate_backlog_pdf(
            rows,
            reference_date=date(2026, 7, 31),
            signatory={
                "name": "MATHEUS ANTONIO MILITAO DE MENEZES",
                "title": "Engenheiro Civil - Sócio Diretor",
                "registration": "CREA 13.814/D-DF",
                "cpf": "000.400.681-02",
            },
            sort_label="Centro de custo",
        )
        reader = PdfReader(BytesIO(pdf))
        assert len(reader.pages) == 1
        page = reader.pages[0]
        assert float(page.mediabox.height) > float(page.mediabox.width)
        text = page.extract_text()
        assert "BACKLOG ENGEMIL" in text
        assert "Engenharia, Empreendimentos" in text
        assert "MATHEUS ANTONIO MILITAO DE MENEZES" in text

        app_source = Path("app.py").read_text(encoding="utf-8")
        version_match = re.search(r'APP_VERSION\s*=\s*"(\d+)"', app_source)
        assert version_match and int(version_match.group(1)) >= 22
        assert "st.context.cookies.get(AUTH_COOKIE_NAME)" in app_source
        assert "scroll_page_to_top" in app_source
        assert "Sessão protegida · saída automática" not in app_source
        assert 'st.session_state.user["role"] != "admin"' in app_source
        assert "Excluir usuário definitivamente" in app_source
        assert "can_create" in app_source

    print("Testes da versão 22 concluídos com sucesso.")


if __name__ == "__main__":
    run()
