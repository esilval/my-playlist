"""Sesión de música y cola: tablas, índices y RLS.

Plan D2 y Modelo de datos de la feature 002; ADR-0004, ADR-0009.

- music_session: una sola abierta por establecimiento (índice único parcial).
- queue_item: cada canción de la cola, con su estado. Solo una en `playing` por
  sesión. La clave foránea compuesta (session_id, establishment_id) impide que
  una canción apunte a la sesión de otro establecimiento.

Revision ID: 0002_music_sessions
Revises: 0001_accounts
Create Date: 2026-10-21
"""

from alembic import op

revision = "0002_music_sessions"
down_revision = "0001_accounts"
branch_labels = None
depends_on = None

TENANT_TABLES = ("music_session", "queue_item")

# Mismo criterio que 0001: sin establecimiento fijado, la consulta falla.
CURRENT_ESTABLISHMENT = "current_setting('app.establishment_id')::uuid"


def upgrade() -> None:
    op.execute("SET LOCAL ROLE app_migrator")

    op.execute(
        "CREATE TYPE queue_item_state AS ENUM "
        "('pending', 'playing', 'played', 'skipped', 'discarded')"
    )

    op.execute(
        """
        CREATE TABLE music_session (
            id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
            establishment_id uuid NOT NULL
                REFERENCES establishment (establishment_id) ON DELETE CASCADE,
            opened_at timestamptz NOT NULL DEFAULT now(),
            closed_at timestamptz,
            player_epoch integer NOT NULL DEFAULT 0,
            player_seen_at timestamptz,
            version bigint NOT NULL DEFAULT 0,
            UNIQUE (id, establishment_id)
        )
        """
    )
    # R003: un establecimiento no puede tener dos sesiones de música abiertas.
    op.execute(
        "CREATE UNIQUE INDEX music_session_one_open_idx "
        "ON music_session (establishment_id) WHERE closed_at IS NULL"
    )

    op.execute(
        """
        CREATE TABLE queue_item (
            id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
            establishment_id uuid NOT NULL
                REFERENCES establishment (establishment_id) ON DELETE CASCADE,
            session_id uuid NOT NULL,
            position bigint NOT NULL,
            track_ref text NOT NULL,
            title text NOT NULL,
            state queue_item_state NOT NULL DEFAULT 'pending',
            failure_reason text,
            created_at timestamptz NOT NULL DEFAULT now(),
            started_at timestamptz,
            finished_at timestamptz,
            FOREIGN KEY (session_id, establishment_id)
                REFERENCES music_session (id, establishment_id) ON DELETE CASCADE
        )
        """
    )
    op.execute(
        "CREATE INDEX queue_item_session_state_idx ON queue_item (session_id, state, position)"
    )
    # R006: como mucho una canción sonando por sesión.
    op.execute(
        "CREATE UNIQUE INDEX queue_item_one_playing_idx "
        "ON queue_item (session_id) WHERE state = 'playing'"
    )

    for table in TENANT_TABLES:
        op.execute(f"ALTER TABLE {table} ENABLE ROW LEVEL SECURITY")
        op.execute(
            f"CREATE POLICY tenant_isolation ON {table} "
            f"USING (establishment_id = {CURRENT_ESTABLISHMENT}) "
            f"WITH CHECK (establishment_id = {CURRENT_ESTABLISHMENT})"
        )
        op.execute(f"GRANT SELECT, INSERT, UPDATE, DELETE ON {table} TO app_api")

    # alembic_version pertenece al usuario de conexión, no a app_migrator.
    op.execute("RESET ROLE")


def downgrade() -> None:
    op.execute("SET LOCAL ROLE app_migrator")
    for table in reversed(TENANT_TABLES):
        op.execute(f"DROP TABLE {table}")
    op.execute("DROP TYPE queue_item_state")
    op.execute("RESET ROLE")
