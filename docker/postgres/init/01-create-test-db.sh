#!/bin/sh
# Creates the separate database used by the pytest suite.
set -e
psql -v ON_ERROR_STOP=1 --username "$POSTGRES_USER" --dbname "$POSTGRES_DB" <<-EOSQL
  CREATE DATABASE ${POSTGRES_TEST_DB:-support_test};
EOSQL
