from pathlib import Path

from etl.sql_script import split_sql

ROOT = Path(__file__).resolve().parents[1]


def test_semicolon_inside_string_stays_in_statement():
    assert split_sql("SELECT 'a;b'; SELECT 1;") == ["SELECT 'a;b'", "SELECT 1"]


def test_dollar_quoted_function_body_is_not_split():
    script = """
        CREATE OR REPLACE FUNCTION demo()
        RETURNS int
        LANGUAGE sql
        AS $$
            SELECT CASE WHEN 1 = 1 THEN 1 ELSE 0 END;
        $$;
        SELECT 1;
    """
    parts = split_sql(script)
    assert len(parts) == 2
    assert "END;" in parts[0]
    assert parts[1] == "SELECT 1"


def test_dwh_functions_stay_intact():
    parts = split_sql((ROOT / "sql" / "dwh" / "010_functions.sql").read_text(encoding="utf-8"))
    assert len(parts) == 4
    assert all(part.count("CREATE OR REPLACE FUNCTION") == 1 for part in parts)


def test_dwh_tables_stay_intact():
    parts = split_sql((ROOT / "sql" / "dwh" / "020_tables.sql").read_text(encoding="utf-8"))
    assert len(parts) == 9
    assert all(part.startswith("CREATE ") for part in parts)


def test_etl_steps_have_no_client_placeholders():
    for path in sorted((ROOT / "etl" / "sql").glob("*.sql")):
        for statement in split_sql(path.read_text(encoding="utf-8")):
            assert "%(" not in statement
            assert statement.strip()
