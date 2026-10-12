-- Runs once, as the owner role, when the data volume is first initialised.
--
-- The API must NOT connect as the owner: superusers and table owners bypass
-- Row-Level Security. This creates the restricted runtime role instead.

\getenv app_user PMS_APP_USER
\getenv app_password PMS_APP_PASSWORD

CREATE ROLE :"app_user" LOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE NOBYPASSRLS PASSWORD :'app_password';

GRANT USAGE ON SCHEMA public TO :"app_user";

-- Tables and sequences created later by migrations (run as the owner) are
-- automatically usable by the runtime role.
ALTER DEFAULT PRIVILEGES IN SCHEMA public
    GRANT SELECT, INSERT, UPDATE, DELETE ON TABLES TO :"app_user";
ALTER DEFAULT PRIVILEGES IN SCHEMA public
    GRANT USAGE, SELECT ON SEQUENCES TO :"app_user";
