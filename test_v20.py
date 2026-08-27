import os
import tempfile
from pathlib import Path


temporary = tempfile.TemporaryDirectory()
os.environ["GESTAO_DB_PATH"] = str(Path(temporary.name) / "test_v20.db")
os.environ["GESTAO_UPLOAD_DIR"] = str(Path(temporary.name) / "uploads")

from db import (  # noqa: E402
    create_user_session,
    execute,
    get_user,
    init_db,
    query,
    revoke_user_session,
    revoke_user_sessions,
    validate_user_session,
)


def run():
    init_db()
    admin = query("SELECT * FROM users WHERE email='admin@engemil.local'")[0]
    assert admin["last_page"] == "Visão geral"

    token = create_user_session(admin["id"], "Navegador de teste")
    assert len(token) >= 48
    stored = query(
        "SELECT token_hash,user_agent_hash,revoked_at FROM user_sessions WHERE user_id=?",
        (admin["id"],),
    )[0]
    assert stored["token_hash"] != token
    assert len(stored["token_hash"]) == 64
    assert validate_user_session(token, "Navegador de teste")
    assert not validate_user_session(token, "Outro navegador")

    expired_token = create_user_session(admin["id"], "Navegador de teste")
    execute(
        "UPDATE user_sessions SET expires_at='2020-01-01T00:00:00+00:00' WHERE token_hash<>?",
        (stored["token_hash"],),
    )
    assert not validate_user_session(expired_token, "Navegador de teste")

    current_token = create_user_session(admin["id"], "Navegador de teste")
    other_token = create_user_session(admin["id"], "Navegador de teste")
    revoke_user_sessions(admin["id"], except_token=current_token)
    assert validate_user_session(current_token, "Navegador de teste", touch=False)
    assert not validate_user_session(other_token, "Navegador de teste", touch=False)
    revoke_user_session(current_token)
    assert not validate_user_session(current_token, "Navegador de teste", touch=False)

    execute(
        "UPDATE users SET last_page='Ficha do contrato' WHERE id=?",
        (admin["id"],),
    )
    assert get_user(admin["id"])["last_page"] == "Ficha do contrato"

    app_source = Path("app.py").read_text(encoding="utf-8")
    requirements = Path("requirements.txt").read_text(encoding="utf-8")
    starter = Path("iniciar_sistema.bat").read_text(encoding="utf-8")
    assert 'APP_VERSION = "' in app_source
    assert "restore_authenticated_session()" in app_source
    assert "@st.fragment(run_every=15)" in app_source
    assert "SESSION_IDLE_MINUTES" in app_source
    assert "temporary-success-hide 8s" in app_source
    assert 'st.success(\\n            "Conferência cadastral concluída' not in app_source
    assert "extra-streamlit-components" in requirements
    assert "extra_streamlit_components" in starter
    assert Path(
        "vendor/extra_streamlit_components-0.1.81-py3-none-any.whl"
    ).is_file()
    print("Testes da versão 20 concluídos com sucesso.")


if __name__ == "__main__":
    run()
