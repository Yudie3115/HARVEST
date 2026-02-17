-- PostgreSQL initialization script
-- Runs automatically on first container start (docker-entrypoint-initdb.d)

-- Grant schema privileges to the scraper user.
-- Required for PostgreSQL 15+ which revoked CREATE on the public schema by default.
GRANT ALL ON SCHEMA public TO scraper;
ALTER SCHEMA public OWNER TO scraper;

-- Ensure objects created in the future are accessible to scraper
ALTER DEFAULT PRIVILEGES IN SCHEMA public GRANT ALL ON TABLES TO scraper;
ALTER DEFAULT PRIVILEGES IN SCHEMA public GRANT ALL ON SEQUENCES TO scraper;
ALTER DEFAULT PRIVILEGES IN SCHEMA public GRANT ALL ON TYPES TO scraper;
