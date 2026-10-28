"""El establecimiento de un código público, para las rutas del cliente.

Plan D5 de la feature 003; ADR-0009.

El cliente que llega por el QR no tiene sesión iniciada, y RLS no deja leer
`establishment` sin un establecimiento fijado. Esta función SECURITY DEFINER devuelve
solo el identificador del establecimiento de un código, para fijar el contexto de las
rutas del cliente. `public_establishment`, de la feature 001, sigue devolviendo solo el
nombre. Como el resto de funciones de la API, solo la ejecuta app_api.

Revision ID: 0004_public_establishment_id
Revises: 0003_queue_requests
Create Date: 2026-10-27
"""

from alembic import op

revision = "0004_public_establishment_id"
down_revision = "0003_queue_requests"
branch_labels = None
depends_on = None

SIGNATURE = "public_establishment_id(text)"


def upgrade() -> None:
    op.execute("SET LOCAL ROLE app_migrator")
    op.execute(
        """
        CREATE FUNCTION public_establishment_id(p_public_code text)
        RETURNS TABLE (establishment_id uuid)
        LANGUAGE sql STABLE SECURITY DEFINER SET search_path = pg_catalog, public, pg_temp AS $$
            -- Como public_establishment: el control de longitud evita que el cast a
            -- char(10) trunque y encuentre otro código (feature 001, R013).
            SELECT e.establishment_id FROM establishment e
             WHERE length(p_public_code) = 10 AND e.public_code = p_public_code::char(10)
        $$
        """
    )
    op.execute(f"REVOKE ALL ON FUNCTION {SIGNATURE} FROM PUBLIC")
    op.execute(f"GRANT EXECUTE ON FUNCTION {SIGNATURE} TO app_api")
    op.execute("RESET ROLE")


def downgrade() -> None:
    op.execute("SET LOCAL ROLE app_migrator")
    op.execute(f"DROP FUNCTION {SIGNATURE}")
    op.execute("RESET ROLE")
