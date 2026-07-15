#!/bin/sh
set -eu

psql --set ON_ERROR_STOP=1 \
    --username "$POSTGRES_USER" \
    --dbname "$POSTGRES_DB" \
    --set reader_password="$DEMO_READER_PASSWORD" <<-'SQL'
        CREATE ROLE recallibrate_reader LOGIN PASSWORD :'reader_password';
        GRANT CONNECT ON DATABASE recallibrate_demo TO recallibrate_reader;
        GRANT USAGE ON SCHEMA public TO recallibrate_reader;
        GRANT SELECT ON ALL TABLES IN SCHEMA public TO recallibrate_reader;
        ALTER DEFAULT PRIVILEGES IN SCHEMA public GRANT SELECT ON TABLES TO recallibrate_reader;
SQL

