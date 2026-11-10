"""Alembic migration: optional geographic fields for map-registered assets.

Revision ID: infra_geo_v1
Revises: alert_results_v1

Adds four NULLABLE columns to the frozen Phase 1 assets table so a public
map infrastructure point (OpenStreetMap) can be registered as a
SilentSignal asset with its real coordinates:

- latitude / longitude: WGS84 point from the map feature (NULL for all
  seeded/demo assets, which keep grid-derived schematic coordinates).
- infra_type: human label from the OSM tags (e.g. 'Street light').
- infra_source: 'osm:<node-id>' provenance, UNIQUE so the same public
  point cannot be registered twice (NULLs never collide).

No existing column is altered, no data is touched, all new columns are
nullable: fully backward compatible. Downgrade drops them again.
"""

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = "infra_geo_v1"
down_revision = "alert_results_v1"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column("assets", sa.Column("latitude", sa.Float(), nullable=True))
    op.add_column("assets", sa.Column("longitude", sa.Float(), nullable=True))
    op.add_column("assets", sa.Column("infra_type", sa.String(), nullable=True))
    op.add_column("assets", sa.Column("infra_source", sa.String(), nullable=True))
    op.create_unique_constraint("uq_assets_infra_source", "assets", ["infra_source"])


def downgrade():
    op.drop_constraint("uq_assets_infra_source", "assets", type_="unique")
    op.drop_column("assets", "infra_source")
    op.drop_column("assets", "infra_type")
    op.drop_column("assets", "longitude")
    op.drop_column("assets", "latitude")
