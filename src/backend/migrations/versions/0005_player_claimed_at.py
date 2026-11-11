"""Hora de la última toma de control del reproductor.

Plan D11 y Modelo de datos de la feature 004.

- music_session.player_claimed_at: cuándo se puso en marcha el reproductor activo, en
  cada toma de control (R004 y R010 de 002). TrackGap solo mide el hueco entre dos
  canciones si el reproductor no cambió desde que terminó la anterior. La columna hereda
  la política RLS y los permisos de la tabla.

Revision ID: 0005_player_claimed_at
Revises: 0004_public_establishment_id
Create Date: 2026-11-11
"""

from alembic import op

revision = "0005_player_claimed_at"
down_revision = "0004_public_establishment_id"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("SET LOCAL ROLE app_migrator")
    op.execute("ALTER TABLE music_session ADD COLUMN player_claimed_at timestamptz")
    op.execute("RESET ROLE")


def downgrade() -> None:
    op.execute("SET LOCAL ROLE app_migrator")
    op.execute("ALTER TABLE music_session DROP COLUMN player_claimed_at")
    op.execute("RESET ROLE")
