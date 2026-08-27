import os
import tempfile
from datetime import date, timedelta
from pathlib import Path

from streamlit.testing.v1 import AppTest


def run():
    with tempfile.TemporaryDirectory() as directory:
        os.environ["GESTAO_DB_PATH"] = str(Path(directory) / "ui.db")
        os.environ["GESTAO_UPLOAD_DIR"] = str(Path(directory) / "uploads")
        app_source = Path("app.py").read_text(encoding="utf-8")
        assert "Gerar Backlog oficial em PDF" in app_source
        assert "application/pdf" in app_source

        from db import execute, init_db, query

        init_db()
        execute(
            "UPDATE users SET must_change_password=0 "
            "WHERE email='admin@engemil.local'"
        )
        ata_id = execute(
            """INSERT INTO contracts(
            cost_center,client,contract_number,category,start_date,end_date,
            original_value,current_value,status)
            VALUES(?,?,?,'ATA',?,?,?,?, 'ATIVO')""",
            (
                "TESTE.ATA", "Órgão de Teste", "ATA 01/2026",
                date.today().isoformat(),
                (date.today() + timedelta(days=365)).isoformat(),
                100000, 100000,
            ),
        )
        execute(
            """INSERT INTO ata_contracts(
            ata_id,contract_number,client,start_date,end_date,original_value,current_value)
            VALUES(?,?,?,?,?,?,?)""",
            (
                ata_id, "CT 01/2026", "Órgão de Teste", date.today().isoformat(),
                (date.today() + timedelta(days=180)).isoformat(), 50000, 50000,
            ),
        )
        execute(
            """INSERT INTO contract_bdis(
            contract_id,name,reference_name,tax_regime,calculation_method,
            indirect_costs,profit,pis,cofins,iss,cprb)
            VALUES(?,?,?,?,?,?,?,?,?,?,?)""",
            (
                ata_id, "BDI 1", "Mão de obra", "DESONERADO", "SOMA_DIRETA",
                3.20, 4.00, 0.65, 3.00, 5.00, 4.50,
            ),
        )
        position_id = execute(
            """INSERT INTO contract_positions(contract_id,title,quantity,base_salary)
            VALUES(?,?,?,?)""",
            (ata_id, "Cargo inserido incorretamente", 1, 2500),
        )

        app = AppTest.from_file("app.py", default_timeout=30)
        app.run()
        assert not app.exception, app.exception
        assert any("Rodrigo de Sousa da Silva" in item.value for item in app.markdown)
        assert any("stFileUploaderDropzone" in item.value for item in app.markdown)
        assert any("bar-label.long" in item.value for item in app.markdown)
        app.text_input[0].set_value("admin@engemil.local")
        app.text_input[1].set_value("Alterar@123")
        next(button for button in app.button if button.label == "Entrar").click()
        app.run()
        assert not app.exception, app.exception
        assert any("modern-table-shell" in item.value for item in app.markdown)
        assert any('data-testid="stDownloadButton"' in item.value for item in app.markdown)
        navigation = next(radio for radio in app.sidebar.radio if radio.label == "Navegação")
        navigation.set_value("Ficha do contrato")
        app.run()
        assert not app.exception, app.exception
        assert any(tab.label == "Contratos decorrentes da ATA" for tab in app.tabs)
        assert any(tab.label == "BDI" for tab in app.tabs)
        assert any(tab.label == "CNO" for tab in app.tabs)
        assert any(
            text_input.label == "Título profissional"
            for text_input in app.text_input
        )
        assert any(
            selectbox.label == "Regime de faturamento do contrato"
            for selectbox in app.selectbox
        )
        assert any(
            selectbox.label == "Contrato decorrente da ATA *"
            for selectbox in app.selectbox
        )
        assert any(
            button.label == "Salvar novo BDI" for button in app.button
        )
        assert any(button.label == "Excluir BDI" for button in app.button)
        assert any(
            selectbox.label == "Abrir ficha do contrato"
            for selectbox in app.selectbox
        )
        assert any(
            text_input.label == "Nome do instrumento quando o tipo for “Outro”"
            for text_input in app.text_input
        )
        assert any(
            text_input.label == "E-mails em cópia ou grupo"
            for text_input in app.text_input
        )
        assert any(
            button.label == "Preparar ficha completa em Word"
            for button in app.button
        )
        assert not any("PDF" in button.label.upper() for button in app.button)
        assert any("Rodrigo de Sousa da Silva" in item.value for item in app.markdown)
        confirm_position = next(
            checkbox for checkbox in app.checkbox
            if checkbox.label == "Confirmo a remoção deste cargo"
        )
        confirm_position.set_value(True)
        app.run()
        assert not app.exception, app.exception
        next(button for button in app.button if button.label == "Remover cargo").click()
        app.run()
        assert not app.exception, app.exception
        assert not query(
            "SELECT id FROM contract_positions WHERE id=?", (position_id,)
        )
        # Reinicia a árvore de teste após a exclusão dinâmica remover o seletor do cargo.
        app = AppTest.from_file("app.py", default_timeout=30)
        app.run()
        app.text_input[0].set_value("admin@engemil.local")
        app.text_input[1].set_value("Alterar@123")
        next(button for button in app.button if button.label == "Entrar").click()
        app.run()
        navigation = next(
            radio for radio in app.sidebar.radio if radio.label == "Navegação"
        )
        navigation.set_value("Ficha do contrato")
        app.run()
        assert not app.exception, app.exception
        assert any("modern-table-shell" in item.value for item in app.markdown)
        appearance = next(radio for radio in app.sidebar.radio if radio.label == "Aparência")
        appearance.set_value("Claro")
        app.run()
        assert not app.exception, app.exception
        assert app.session_state["navigation_page"] == "Ficha do contrato"
        assert any(tab.label == "Contratos decorrentes da ATA" for tab in app.tabs)
        assert any(
            selectbox.label == "Abrir ficha do contrato"
            for selectbox in app.selectbox
        )
        assert next(
            radio for radio in app.sidebar.radio if radio.label == "Navegação"
        ).value == "Ficha do contrato"
        assert next(
            radio for radio in app.sidebar.radio if radio.label == "Aparência"
        ).value == "Claro"
        pages = [
            "Visão geral",
            "Contratos",
            "Ficha do contrato",
            "Novo contrato",
            "Exportações",
            "Índices",
            "Documentos padrões",
            "Usuários",
        ]
        for theme in ("Claro", "Escuro"):
            appearance = next(
                radio for radio in app.sidebar.radio if radio.label == "Aparência"
            )
            current_page = app.session_state["navigation_page"]
            appearance.set_value(theme)
            app.run()
            assert not app.exception, app.exception
            assert app.session_state["navigation_page"] == current_page
            for page in pages:
                navigation = next(
                    radio for radio in app.sidebar.radio if radio.label == "Navegação"
                )
                navigation.set_value(page)
                app.run()
                assert not app.exception, (theme, page, app.exception)
                assert app.session_state["navigation_page"] == page
                assert any(
                    'data-testid="stDownloadButton"' in item.value
                    for item in app.markdown
                )
                if page == "Contratos":
                    assert any(
                        button.label == "Gerar Backlog oficial em PDF — modelo Análise Crítica"
                        for button in app.button
                    )
                    assert any(
                        selectbox.label == "Ordenar o Backlog por"
                        for selectbox in app.selectbox
                    )
                    assert any(
                        selectbox.label == "Responsável pela assinatura"
                        for selectbox in app.selectbox
                    )
                elif page != "Exportações":
                    assert not any(
                        "PDF" in button.label.upper() for button in app.button
                    ), (theme, page)
                if page == "Índices":
                    equity_input = next(
                        text_input for text_input in app.text_input
                        if text_input.label == "Patrimônio líquido"
                    )
                    assert equity_input.value == "R$ 139.259.969,94"
                if page == "Documentos padrões":
                    assert any(
                        button.label == "Gerar documento em Word"
                        for button in app.button
                    )
        print(
            "Todos os menus, navegação da ATA, permanência na página e os "
            "temas claro e escuro foram validados."
        )


if __name__ == "__main__":
    run()
