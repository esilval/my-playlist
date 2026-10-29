"""Quién pidió cada canción de la cola.

Plan D4 y Modelo de datos de la feature 003; ADR-0007, ADR-0009.

- queue_item.requested_by: el identificador anónimo del dispositivo que la pidió.
  Es NULL para las canciones que no pidió un cliente (la herramienta de desarrollo y,
  más adelante, el propietario). Es lo único que se guarda del cliente (S9).
- El cupo se cuenta con las pendientes de cada dispositivo: un índice parcial lo hace
  barato. La columna hereda la política RLS y los permisos de la tabla.

Revision ID: 0003_queue_requests
Revises: 0002_music_sessions
Create Date: 2026-10-27
"""

from alembic import op

revision = "0003_queue_requests"
down_revision = "0002_music_sessions"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("SET LOCAL ROLE app_migrator")
    op.execute("ALTER TABLE queue_item ADD COLUMN requested_by uuid")
    # R006: las pendientes de un dispositivo en la sesión, para su cupo.
    op.execute(
        "CREATE INDEX queue_item_pending_by_device_idx "
        "ON queue_item (session_id, requested_by) WHERE state = 'pending'"
    )
    op.execute("RESET ROLE")


def downgrade() -> None:
    op.execute("SET LOCAL ROLE app_migrator")
    op.execute("DROP INDEX queue_item_pending_by_device_idx")
    op.execute("ALTER TABLE queue_item DROP COLUMN requested_by")
    op.execute("RESET ROLE")
