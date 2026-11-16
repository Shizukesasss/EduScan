"""Review and restrict PostgreSQL privileges on EduScan-owned relations."""

from sqlalchemy import text
from sqlalchemy.engine import make_url
from sqlalchemy.exc import ArgumentError

from .database import Base
from . import models, models_grading  # noqa: F401 - register application tables.


DATA_API_ROLES = ("anon", "authenticated", "service_role", "authenticator")
TABLE_DML = "SELECT, INSERT, UPDATE, DELETE"


def application_tables() -> list[str]:
    return sorted(set(Base.metadata.tables) | {"schema_migrations"})


def _relations(connection):
    return connection.execute(text("""
        WITH app_tables AS (
            SELECT c.oid, c.relname, c.relkind, c.relowner, c.relacl
            FROM pg_class c JOIN pg_namespace n ON n.oid = c.relnamespace
            WHERE n.nspname = 'public' AND c.relkind IN ('r', 'p') AND c.relname = ANY(:names)
        )
        SELECT * FROM app_tables
        UNION
        SELECT c.oid, c.relname, c.relkind, c.relowner, c.relacl
        FROM pg_class c JOIN pg_namespace n ON n.oid = c.relnamespace
        JOIN pg_depend d ON d.classid = 'pg_class'::regclass AND d.objid = c.oid
                        AND d.refclassid = 'pg_class'::regclass AND d.deptype IN ('a', 'i')
        JOIN app_tables t ON t.oid = d.refobjid
        WHERE n.nspname = 'public' AND c.relkind = 'S'
    """), {"names": application_tables()}).all()


def _api_roles(connection):
    return list(connection.scalars(text("SELECT rolname FROM pg_roles WHERE rolname = ANY(:roles)"),
                                   {"roles": list(DATA_API_ROLES)}))


def maintenance_url(runtime, supplied):
    try:
        owner = make_url(supplied)
    except ArgumentError:
        raise RuntimeError("Supply a valid PostgreSQL maintenance URL.") from None
    if owner.get_backend_name() != "postgresql" or not owner.username or not owner.database or not runtime.username:
        raise RuntimeError("Supply a valid PostgreSQL maintenance URL.")
    if (runtime.host, runtime.port or 5432, runtime.database) != (owner.host, owner.port or 5432, owner.database):
        raise RuntimeError("Maintenance must use the same PostgreSQL host, port and database as DATABASE_URL.")
    if (runtime.host or "").endswith(".pooler.supabase.com"):
        project = (runtime.username or "").partition(".")[2]
        if not project or project != owner.username.partition(".")[2]:
            raise RuntimeError("Maintenance must target the same Supabase project as DATABASE_URL.")
    if postgres_role(runtime) == postgres_role(owner):
        raise RuntimeError("The runtime and maintenance roles must be separate EduScan logins.")
    return owner


def postgres_role(url):
    return url.username.split(".", 1)[0] if (url.host or "").endswith(".pooler.supabase.com") else url.username


def audit_postgres_access(connection, runtime_role=None):
    relations, api_roles = _relations(connection), _api_roles(connection)
    runtime_role = runtime_role or connection.scalar(text("SELECT current_user"))
    available = {row.relname for row in relations if row.relkind != "S"}
    relation_ids = [row.oid for row in relations]
    api_grants = connection.execute(text("""
        SELECT r.rolname, c.relname
        FROM pg_roles r CROSS JOIN pg_class c
        WHERE r.rolname = ANY(:roles) AND c.oid = ANY(:relations) AND
            CASE WHEN c.relkind = 'S' THEN has_sequence_privilege(r.oid, c.oid, 'USAGE,SELECT,UPDATE')
            ELSE has_table_privilege(r.oid, c.oid, :table_privileges)
                OR has_any_column_privilege(r.oid, c.oid, 'SELECT,INSERT,UPDATE,REFERENCES')
            END
        ORDER BY r.rolname, c.relname
    """), {"roles": api_roles, "relations": relation_ids, "table_privileges": _table_privileges(connection)}).all()
    public_grants = connection.execute(text("""
        SELECT c.relname FROM pg_class c WHERE c.oid = ANY(:relations)
          AND (EXISTS (SELECT 1 FROM aclexplode(c.relacl) a WHERE a.grantee = 0)
            OR EXISTS (SELECT 1 FROM pg_attribute col CROSS JOIN LATERAL aclexplode(col.attacl) a
                       WHERE col.attrelid = c.oid AND a.grantee = 0))
    """), {"relations": relation_ids}).scalars().all()
    issues = []
    role = connection.execute(text("""
        SELECT oid, rolsuper OR rolcreatedb OR rolcreaterole OR rolreplication OR rolbypassrls AS elevated,
               rolcanlogin
        FROM pg_roles WHERE rolname = :role
    """), {"role": runtime_role}).one_or_none()
    if not role:
        issues.append("Runtime role does not exist")
    else:
        if role.elevated or not role.rolcanlogin:
            issues.append("Runtime role must be a login without elevated role attributes")
        if connection.scalar(text("""
            SELECT has_database_privilege(:role, current_database(), 'CREATE')
                OR EXISTS (SELECT 1 FROM pg_namespace n
                    WHERE n.nspname !~ '^pg_' AND n.nspname <> 'information_schema'
                      AND has_schema_privilege(:role, n.oid, 'CREATE'))
        """), {"role": role.oid}):
            issues.append("Runtime can create permanent database objects")
        if not connection.scalar(text("SELECT has_schema_privilege(:role, 'public', 'USAGE')"), {"role": role.oid}):
            issues.append("Runtime lacks USAGE on the application schema")
        if connection.scalar(text("""
            SELECT EXISTS (SELECT 1 FROM pg_class WHERE oid = ANY(:relations)
                           AND pg_has_role(:role, relowner, 'MEMBER'))
                OR EXISTS (SELECT 1 FROM pg_auth_members WHERE member = :role)
        """), {"role": role.oid, "relations": relation_ids}):
            issues.append("Runtime owns application objects or has role memberships")
        extras = connection.scalar(text("""
            SELECT EXISTS (SELECT 1 FROM pg_class WHERE oid = ANY(:relations) AND
                CASE WHEN relkind = 'S' THEN has_sequence_privilege(:role, oid, 'UPDATE')
                WHEN relname = 'schema_migrations' THEN has_table_privilege(:role, oid, :ledger_privileges)
                    OR has_any_column_privilege(:role, oid, 'INSERT,UPDATE,REFERENCES')
                ELSE has_table_privilege(:role, oid, :extra_privileges) END)
        """), {"role": role.oid, "relations": relation_ids,
               "ledger_privileges": _table_privileges(connection).removeprefix("SELECT,"),
               "extra_privileges": _table_privileges(connection).split("DELETE,", 1)[1]})
        if extras:
            issues.append("Runtime has privileges beyond application DML and migration-ledger reads")
        missing_grants = connection.scalar(text("""
            SELECT EXISTS (SELECT 1 FROM pg_class WHERE oid = ANY(:relations) AND NOT
                CASE WHEN relkind = 'S' THEN has_sequence_privilege(:role, oid, 'USAGE')
                                         AND has_sequence_privilege(:role, oid, 'SELECT')
                WHEN relname = 'schema_migrations' THEN has_table_privilege(:role, oid, 'SELECT')
                ELSE has_table_privilege(:role, oid, 'SELECT') AND has_table_privilege(:role, oid, 'INSERT')
                   AND has_table_privilege(:role, oid, 'UPDATE') AND has_table_privilege(:role, oid, 'DELETE') END)
        """), {"role": role.oid, "relations": relation_ids})
        if missing_grants:
            issues.append("Runtime is missing application or migration-ledger privileges")
    return {"data_api_grants": [tuple(row) for row in api_grants], "public_grants": public_grants,
            "runtime_issues": issues, "application_tables": len(available),
            "missing_tables": sorted(set(application_tables()) - available)}


def _table_privileges(connection):
    privileges = "SELECT,INSERT,UPDATE,DELETE,TRUNCATE,REFERENCES,TRIGGER"
    return privileges + ",MAINTAIN" if connection.dialect.server_version_info >= (17,) else privileges


def _change_relation_grants(connection, revoked, runtime=None):
    quote = connection.dialect.identifier_preparer.quote_identifier
    for relation in _relations(connection):
        qualified = f"public.{quote(relation.relname)}"
        kind = "SEQUENCE" if relation.relkind == "S" else "TABLE"
        connection.execute(text(f"REVOKE ALL PRIVILEGES ON {kind} {qualified} FROM {revoked}"))
        if kind == "TABLE":
            columns = connection.scalars(text("""
                SELECT attname FROM pg_attribute WHERE attrelid = :oid AND attnum > 0 AND NOT attisdropped
                ORDER BY attnum
            """), {"oid": relation.oid}).all()
            if columns:
                names = ", ".join(quote(column) for column in columns)
                connection.execute(text(f"REVOKE ALL PRIVILEGES ({names}) ON TABLE {qualified} FROM {revoked}"))
        if runtime:
            privileges = ("USAGE, SELECT" if kind == "SEQUENCE" else
                          "SELECT" if relation.relname == "schema_migrations" else TABLE_DML)
            connection.execute(text(f"GRANT {privileges} ON {kind} {qualified} TO {runtime}"))


def revoke_data_api_access(connection):
    connection.execute(text("SET LOCAL lock_timeout = '3s'"))
    quote = connection.dialect.identifier_preparer.quote_identifier
    revoked = ", ".join(["PUBLIC", *(quote(role) for role in _api_roles(connection))])
    _change_relation_grants(connection, revoked)
    audit = audit_postgres_access(connection)
    if audit["data_api_grants"] or audit["public_grants"]:
        raise RuntimeError("Effective Data API grants remain. Review inherited grants with the database owner.")
    return audit


def configure_postgres_access(connection, runtime_role: str):
    if runtime_role == connection.scalar(text("SELECT current_user")) or runtime_role in DATA_API_ROLES:
        raise RuntimeError("The runtime and maintenance roles must be separate EduScan logins.")
    quote = connection.dialect.identifier_preparer.quote_identifier
    runtime = quote(runtime_role)
    revoked = ", ".join(["PUBLIC", runtime, *(quote(role) for role in _api_roles(connection))])
    connection.execute(text(f"GRANT USAGE ON SCHEMA public TO {runtime}"))
    _change_relation_grants(connection, revoked, runtime)
    audit = audit_postgres_access(connection, runtime_role)
    if audit["runtime_issues"] or audit["data_api_grants"] or audit["public_grants"]:
        raise RuntimeError("Effective PostgreSQL grants do not match the EduScan policy. Review the audit and role membership.")
    return audit
