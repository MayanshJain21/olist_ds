-- ==============================================================================
-- Script: 01_create_schemas.sql
-- Description: Idempotently creates 'staging' and 'dw' schemas in Azure SQL Database.
-- ==============================================================================

IF NOT EXISTS (SELECT 1 FROM sys.schemas WHERE name = 'staging')
BEGIN
    EXEC('CREATE SCHEMA staging');
    PRINT 'Schema [staging] created successfully.';
END
ELSE
BEGIN
    PRINT 'Schema [staging] already exists.';
END;
GO

IF NOT EXISTS (SELECT 1 FROM sys.schemas WHERE name = 'dw')
BEGIN
    EXEC('CREATE SCHEMA dw');
    PRINT 'Schema [dw] created successfully.';
END
ELSE
BEGIN
    PRINT 'Schema [dw] already exists.';
END;
GO
