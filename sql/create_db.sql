-- =============================================================================
-- Run this FIRST as the postgres superuser to create the database
-- psql -U postgres -f create_db.sql
-- =============================================================================

-- Create database
CREATE DATABASE energy_db;

-- Connect to it
\c energy_db

-- Enable TimescaleDB
CREATE EXTENSION IF NOT EXISTS timescaledb CASCADE;

-- Optional: create a dedicated app user
-- CREATE USER energy_user WITH PASSWORD 'energy_pass';
-- GRANT ALL PRIVILEGES ON DATABASE energy_db TO energy_user;
-- GRANT ALL ON SCHEMA public TO energy_user;

\echo 'Database energy_db is ready.'
