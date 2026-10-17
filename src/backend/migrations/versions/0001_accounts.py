"""Cuentas y establecimientos: roles, tablas, RLS y trigger de public_code.

Plan D1, D4, D5 y Modelo de datos; ADR-0009. Incluye las funciones
SECURITY DEFINER de D4 (T005).

Roles (de clúster, se crean si no existen y no se borran al bajar, porque los
comparten todas las bases del clúster):
- app_migrator: dueño de las tablas y de las funciones SECURITY DEFINER. Como
  dueño, no está sujeto a RLS.
- app_api: sin BYPASSRLS; DML sobre las tablas de negocio, siempre con
  app.establishment_id fijado por transacción.
- app_worker: sin acceso directo a tablas; solo ejecuta outbox_claim,
  outbox_mark y login_attempt_purge (T025).

Los tres son NOLOGIN: cada entorno crea su usuario de conexión y le concede
el rol que toque. Por la misma razón, bajar no revoca los permisos de esquema
ni la pertenencia a app_migrator que concede la subida.

Revision ID: 0001_accounts
Revises:
Create Date: 2026-10-16
"""

from alembic import op

revision = "0001_accounts"
down_revision = None
branch_labels = None
depends_on = None

# Tablas con establishment_id y política RLS (S8). login_attempt es la
# excepción documentada en el plan (D5).
TENANT_TABLES = (
    "establishment",
    "owner_account",
    "data_authorization",
    "owner_session",
    "email_token",
    "email_outbox",
)

# Sin establecimiento fijado, la consulta falla en lugar de devolver 0 filas: olvidar
# el SET LOCAL es un error que se tiene que ver (plan, Modelo de datos).
CURRENT_ESTABLISHMENT = "current_setting('app.establishment_id')::uuid"

# D4: lo que ocurre antes de conocer el establecimiento. Cada función es una
# puerta en el aislamiento: devuelve solo las columnas que su caso necesita y la
# ejecuta únicamente app_api.
DEFINER_FUNCTIONS = {
    "auth_account_by_email(text)": """
        CREATE FUNCTION auth_account_by_email(p_email text)
        RETURNS TABLE (
            account_id uuid,
            establishment_id uuid,
            password_hash text,
            email_verified boolean
        )
        LANGUAGE sql STABLE SECURITY DEFINER SET search_path = pg_catalog, public, pg_temp AS $$
            SELECT a.id, a.establishment_id, a.password_hash, a.email_verified_at IS NOT NULL
              FROM owner_account a
             WHERE a.email_normalized = lower(btrim(p_email))
        $$
    """,
    "auth_session(bytea)": """
        CREATE FUNCTION auth_session(p_token_hash bytea)
        RETURNS TABLE (
            session_id uuid,
            account_id uuid,
            establishment_id uuid,
            last_seen_at timestamptz,
            revoked_at timestamptz
        )
        LANGUAGE sql STABLE SECURITY DEFINER SET search_path = pg_catalog, public, pg_temp AS $$
            SELECT s.id, s.account_id, s.establishment_id, s.last_seen_at, s.revoked_at
              FROM owner_session s
             WHERE s.token_hash = p_token_hash
        $$
    """,
    "auth_email_token(bytea,email_token_purpose)": """
        CREATE FUNCTION auth_email_token(p_token_hash bytea, p_purpose email_token_purpose)
        RETURNS TABLE (
            token_id uuid,
            account_id uuid,
            establishment_id uuid,
            expires_at timestamptz,
            used_at timestamptz,
            superseded_at timestamptz,
            email_verified boolean
        )
        LANGUAGE sql STABLE SECURITY DEFINER SET search_path = pg_catalog, public, pg_temp AS $$
            SELECT t.id, t.account_id, t.establishment_id, t.expires_at,
                   t.used_at, t.superseded_at, a.email_verified_at IS NOT NULL
              FROM email_token t
              JOIN owner_account a ON a.id = t.account_id
             WHERE t.token_hash = p_token_hash AND t.purpose = p_purpose
        $$
    """,
    "public_establishment(text)": """
        CREATE FUNCTION public_establishment(p_public_code text)
        RETURNS TABLE (name text)
        LANGUAGE sql STABLE SECURITY DEFINER SET search_path = pg_catalog, public, pg_temp AS $$
            -- Comparar como char(10) usa el índice único, pero el cast trunca: sin el
            -- control de longitud, 'AAAAAAAAAAxyz' encontraría 'AAAAAAAAAA' (R013).
            SELECT e.name FROM establishment e
             WHERE length(p_public_code) = 10 AND e.public_code = p_public_code::char(10)
        $$
    """,
}

# D4, D7: el trabajador de correo recorre todos los establecimientos, así que no
# toca las tablas: solo ejecuta estas funciones, y únicamente app_worker.
WORKER_FUNCTIONS = {
    # Reclama hasta p_batch mensajes vencidos. FOR UPDATE SKIP LOCKED evita que dos
    # trabajadores tomen el mismo; mover next_attempt_at actúa de arrendamiento, de
    # modo que un mensaje reclamado por un trabajador que muere vuelve a salir.
    "outbox_claim(integer,interval)": """
        CREATE FUNCTION outbox_claim(p_batch integer, p_lease interval DEFAULT '5 minutes')
        RETURNS TABLE (
            id uuid,
            to_address text,
            template email_template,
            payload jsonb,
            attempts integer
        )
        LANGUAGE sql VOLATILE SECURITY DEFINER SET search_path = pg_catalog, public, pg_temp AS $$
            UPDATE email_outbox o
               SET attempts = o.attempts + 1,
                   next_attempt_at = now() + p_lease
             WHERE o.id IN (
                   SELECT c.id FROM email_outbox c
                    WHERE c.status = 'pending' AND c.next_attempt_at <= now()
                    ORDER BY c.next_attempt_at
                    LIMIT greatest(coalesce(p_batch, 0), 0)
                    FOR UPDATE SKIP LOCKED)
            RETURNING o.id, o.to_address, o.template, o.payload, o.attempts
        $$
    """,
    # Resultado de un envío: 'sent', 'failed' (definitivo) o 'pending' con la hora
    # del siguiente intento. Solo cambia mensajes aún pendientes: uno ya enviado o
    # fallado no se reabre. La entrega es «al menos una vez»: si un arrendamiento
    # vence durante un envío lento, otro trabajador puede repetirlo.
    "outbox_mark(uuid,email_status,timestamptz)": """
        CREATE FUNCTION outbox_mark(
            p_id uuid, p_status email_status, p_retry_at timestamptz DEFAULT NULL
        )
        RETURNS void
        LANGUAGE plpgsql VOLATILE SECURITY DEFINER SET search_path = pg_catalog, public, pg_temp
        AS $$
        BEGIN
            IF p_status = 'pending' AND p_retry_at IS NULL THEN
                RAISE EXCEPTION 'un reintento necesita p_retry_at';
            END IF;
            UPDATE email_outbox
               SET status = p_status,
                   sent_at = CASE WHEN p_status = 'sent' THEN now() END,
                   next_attempt_at = COALESCE(p_retry_at, next_attempt_at)
             WHERE email_outbox.id = p_id AND email_outbox.status = 'pending';
            IF NOT FOUND THEN
                RAISE EXCEPTION 'mensaje % no existe o ya no está pendiente', p_id;
            END IF;
        END $$
    """,
    # D5: los intentos de inicio de sesión de más de un día ya no cuentan.
    "login_attempt_purge(interval)": """
        CREATE FUNCTION login_attempt_purge(p_older_than interval DEFAULT '1 day')
        RETURNS bigint
        LANGUAGE sql VOLATILE SECURITY DEFINER SET search_path = pg_catalog, public, pg_temp AS $$
            WITH purged AS (
                DELETE FROM login_attempt WHERE attempted_at < now() - p_older_than
                RETURNING 1
            )
            SELECT count(*) FROM purged
        $$
    """,
}


def upgrade() -> None:
    for role in ("app_migrator", "app_api", "app_worker"):
        op.execute(
            f"""
            DO $$ BEGIN
                IF NOT EXISTS (SELECT FROM pg_roles WHERE rolname = '{role}') THEN
                    CREATE ROLE {role} NOLOGIN;
                END IF;
            END $$
            """
        )
        # Si el rol ya existía, se corrige: ninguno puede saltarse RLS (ADR-0009).
        op.execute(f"ALTER ROLE {role} NOBYPASSRLS")
    op.execute("GRANT app_migrator TO current_user")
    op.execute("GRANT USAGE ON SCHEMA public TO app_api, app_worker")
    op.execute("GRANT CREATE ON SCHEMA public TO app_migrator")
    op.execute("SET LOCAL ROLE app_migrator")

    op.execute("CREATE TYPE email_token_purpose AS ENUM ('verify', 'reset')")
    op.execute(
        "CREATE TYPE email_template AS ENUM "
        "('verify_email', 'password_reset', 'registration_attempt')"
    )
    op.execute("CREATE TYPE email_status AS ENUM ('pending', 'sent', 'failed')")

    op.execute(
        """
        CREATE TABLE establishment (
            id uuid PRIMARY KEY,
            establishment_id uuid NOT NULL UNIQUE CHECK (establishment_id = id),
            public_code char(10) NOT NULL UNIQUE,
            name text NOT NULL CHECK (btrim(name) <> ''),
            address text,
            phone text,
            created_at timestamptz NOT NULL DEFAULT now(),
            updated_at timestamptz NOT NULL DEFAULT now()
        )
        """
    )
    op.execute(
        """
        CREATE TABLE owner_account (
            id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
            establishment_id uuid NOT NULL UNIQUE
                REFERENCES establishment (establishment_id) ON DELETE CASCADE,
            email text NOT NULL,
            email_normalized text NOT NULL UNIQUE,
            password_hash text NOT NULL,
            email_verified_at timestamptz,
            created_at timestamptz NOT NULL DEFAULT now()
        )
        """
    )
    op.execute(
        """
        CREATE TABLE data_authorization (
            id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
            establishment_id uuid NOT NULL
                REFERENCES establishment (establishment_id) ON DELETE CASCADE,
            account_id uuid NOT NULL REFERENCES owner_account (id) ON DELETE CASCADE,
            policy_version text NOT NULL,
            granted_at timestamptz NOT NULL
        )
        """
    )
    op.execute(
        """
        CREATE TABLE owner_session (
            id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
            establishment_id uuid NOT NULL
                REFERENCES establishment (establishment_id) ON DELETE CASCADE,
            account_id uuid NOT NULL REFERENCES owner_account (id) ON DELETE CASCADE,
            token_hash bytea NOT NULL UNIQUE,
            created_at timestamptz NOT NULL DEFAULT now(),
            last_seen_at timestamptz NOT NULL DEFAULT now(),
            revoked_at timestamptz
        )
        """
    )
    op.execute("CREATE INDEX owner_session_account_idx ON owner_session (account_id)")
    op.execute(
        """
        CREATE TABLE email_token (
            id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
            establishment_id uuid NOT NULL
                REFERENCES establishment (establishment_id) ON DELETE CASCADE,
            account_id uuid NOT NULL REFERENCES owner_account (id) ON DELETE CASCADE,
            purpose email_token_purpose NOT NULL,
            token_hash bytea NOT NULL UNIQUE,
            expires_at timestamptz,
            used_at timestamptz,
            superseded_at timestamptz,
            created_at timestamptz NOT NULL DEFAULT now()
        )
        """
    )
    op.execute("CREATE INDEX email_token_account_idx ON email_token (account_id, purpose)")
    op.execute(
        """
        CREATE TABLE email_outbox (
            id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
            establishment_id uuid NOT NULL
                REFERENCES establishment (establishment_id) ON DELETE CASCADE,
            to_address text NOT NULL,
            to_address_normalized text NOT NULL,
            template email_template NOT NULL,
            payload jsonb NOT NULL DEFAULT '{}'::jsonb,
            created_at timestamptz NOT NULL DEFAULT now(),
            status email_status NOT NULL DEFAULT 'pending',
            attempts integer NOT NULL DEFAULT 0,
            next_attempt_at timestamptz NOT NULL DEFAULT now(),
            sent_at timestamptz
        )
        """
    )
    op.execute(
        "CREATE INDEX email_outbox_pending_idx ON email_outbox (next_attempt_at) "
        "WHERE status = 'pending'"
    )
    # Límite de R027: correos de una plantilla a un destinatario en la última hora.
    op.execute(
        "CREATE INDEX email_outbox_quota_idx ON email_outbox "
        "(establishment_id, to_address_normalized, template, created_at)"
    )
    op.execute(
        """
        CREATE TABLE login_attempt (
            id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
            email_normalized text NOT NULL,
            attempted_at timestamptz NOT NULL DEFAULT now(),
            succeeded boolean NOT NULL
        )
        """
    )
    op.execute(
        "CREATE INDEX login_attempt_email_idx ON login_attempt (email_normalized, attempted_at)"
    )

    # D1: el código público no cambia en la vida del establecimiento (R009, R014).
    op.execute(
        """
        CREATE FUNCTION establishment_public_code_immutable() RETURNS trigger
        LANGUAGE plpgsql AS $$
        BEGIN
            RAISE EXCEPTION 'public_code es inmutable' USING ERRCODE = 'check_violation';
        END $$
        """
    )
    op.execute(
        """
        CREATE TRIGGER establishment_public_code_immutable
        BEFORE UPDATE OF public_code ON establishment
        FOR EACH ROW WHEN (OLD.public_code IS DISTINCT FROM NEW.public_code)
        EXECUTE FUNCTION establishment_public_code_immutable()
        """
    )

    for table in TENANT_TABLES:
        op.execute(f"ALTER TABLE {table} ENABLE ROW LEVEL SECURITY")
        op.execute(
            f"CREATE POLICY tenant_isolation ON {table} "
            f"USING (establishment_id = {CURRENT_ESTABLISHMENT}) "
            f"WITH CHECK (establishment_id = {CURRENT_ESTABLISHMENT})"
        )
        op.execute(f"GRANT SELECT, INSERT, UPDATE, DELETE ON {table} TO app_api")
    op.execute("GRANT SELECT, INSERT ON login_attempt TO app_api")

    for signature, ddl in DEFINER_FUNCTIONS.items():
        op.execute(ddl)
        op.execute(f"REVOKE ALL ON FUNCTION {signature} FROM PUBLIC")
        op.execute(f"GRANT EXECUTE ON FUNCTION {signature} TO app_api")
    for signature, ddl in WORKER_FUNCTIONS.items():
        op.execute(ddl)
        op.execute(f"REVOKE ALL ON FUNCTION {signature} FROM PUBLIC")
        op.execute(f"GRANT EXECUTE ON FUNCTION {signature} TO app_worker")

    # alembic_version pertenece al usuario de conexión, no a app_migrator.
    op.execute("RESET ROLE")


def downgrade() -> None:
    op.execute("SET LOCAL ROLE app_migrator")
    for signature in (*WORKER_FUNCTIONS, *DEFINER_FUNCTIONS):
        op.execute(f"DROP FUNCTION {signature}")
    for table in ("login_attempt", *reversed(TENANT_TABLES)):
        op.execute(f"DROP TABLE {table}")
    op.execute("DROP FUNCTION establishment_public_code_immutable()")
    op.execute("DROP TYPE email_status")
    op.execute("DROP TYPE email_template")
    op.execute("DROP TYPE email_token_purpose")
    op.execute("RESET ROLE")
