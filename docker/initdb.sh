(
  set -euo pipefail
  psql -v ON_ERROR_STOP=1 --username "$POSTGRES_USER" --dbname "$POSTGRES_DB" -f /assignment/schema.sql
  psql -v ON_ERROR_STOP=1 --username "$POSTGRES_USER" --dbname "$POSTGRES_DB" -v n_prices="${N_PRICES:-300000}" -f /assignment/synthetic.sql
)
