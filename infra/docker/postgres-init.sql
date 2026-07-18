-- Local development only: create the same kind of non-superuser role that the
-- production application expects. A superuser bypasses PostgreSQL RLS even
-- when FORCE ROW LEVEL SECURITY is enabled.
CREATE ROLE cash
    LOGIN
    PASSWORD 'cash'
    NOSUPERUSER
    NOCREATEDB
    NOCREATEROLE
    NOINHERIT
    NOBYPASSRLS;

GRANT CONNECT ON DATABASE cash TO cash;
GRANT USAGE, CREATE ON SCHEMA public TO cash;
