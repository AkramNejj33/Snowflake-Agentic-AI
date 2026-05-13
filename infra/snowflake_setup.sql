-- ============================================================
-- Snowflake Agentic AI — Infrastructure Setup
-- Exécuter en tant qu'ACCOUNTADMIN
-- ============================================================

USE ROLE ACCOUNTADMIN;

-- ============================================================
-- 1. Warehouse
-- ============================================================
CREATE WAREHOUSE IF NOT EXISTS AGENTIC_WH
    WAREHOUSE_SIZE = 'X-SMALL'
    AUTO_SUSPEND = 60
    AUTO_RESUME = TRUE
    INITIALLY_SUSPENDED = TRUE
    COMMENT = 'Warehouse pour le système agentic AI';

-- ============================================================
-- 2. Database & Schemas
-- ============================================================
CREATE DATABASE IF NOT EXISTS AGENTIC_DB
    COMMENT = 'Base de données principale pour le système agentic AI';

USE DATABASE AGENTIC_DB;

CREATE SCHEMA IF NOT EXISTS AGENTIC_DB.RAW
    COMMENT = 'Données brutes ingérées';

CREATE SCHEMA IF NOT EXISTS AGENTIC_DB.ANALYTICS
    COMMENT = 'Données transformées et agrégées';

-- ============================================================
-- 3. Rôle et permissions minimales
-- ============================================================
CREATE ROLE IF NOT EXISTS AGENTIC_ROLE
    COMMENT = 'Rôle pour les agents IA — permissions minimales';

-- Permissions sur le warehouse
GRANT USAGE ON WAREHOUSE AGENTIC_WH TO ROLE AGENTIC_ROLE;

-- Permissions sur la database
GRANT USAGE ON DATABASE AGENTIC_DB TO ROLE AGENTIC_ROLE;

-- Permissions sur les schemas
GRANT USAGE ON SCHEMA AGENTIC_DB.RAW       TO ROLE AGENTIC_ROLE;
GRANT USAGE ON SCHEMA AGENTIC_DB.ANALYTICS TO ROLE AGENTIC_ROLE;

-- Permissions sur les tables (présentes et futures)
GRANT SELECT, INSERT, UPDATE, DELETE ON ALL TABLES IN SCHEMA AGENTIC_DB.RAW       TO ROLE AGENTIC_ROLE;
GRANT SELECT, INSERT, UPDATE, DELETE ON ALL TABLES IN SCHEMA AGENTIC_DB.ANALYTICS TO ROLE AGENTIC_ROLE;
GRANT SELECT, INSERT, UPDATE, DELETE ON FUTURE TABLES IN SCHEMA AGENTIC_DB.RAW       TO ROLE AGENTIC_ROLE;
GRANT SELECT, INSERT, UPDATE, DELETE ON FUTURE TABLES IN SCHEMA AGENTIC_DB.ANALYTICS TO ROLE AGENTIC_ROLE;

-- Permissions CREATE TABLE pour l'ingestion agent
GRANT CREATE TABLE ON SCHEMA AGENTIC_DB.RAW       TO ROLE AGENTIC_ROLE;
GRANT CREATE TABLE ON SCHEMA AGENTIC_DB.ANALYTICS TO ROLE AGENTIC_ROLE;

-- Assigner le rôle à l'utilisateur courant (adapter si besoin)
-- GRANT ROLE AGENTIC_ROLE TO USER <votre_utilisateur>;

-- ============================================================
-- 4. Tables RAW
-- ============================================================
USE SCHEMA AGENTIC_DB.RAW;

CREATE OR REPLACE TABLE RAW.CUSTOMERS (
    CUSTOMER_ID     NUMBER(10,0)    NOT NULL PRIMARY KEY,
    FIRST_NAME      VARCHAR(100)    NOT NULL,
    LAST_NAME       VARCHAR(100)    NOT NULL,
    EMAIL           VARCHAR(255)    NOT NULL UNIQUE,
    PHONE           VARCHAR(20),
    CITY            VARCHAR(100),
    COUNTRY         VARCHAR(100)    DEFAULT 'France',
    SEGMENT         VARCHAR(50)     COMMENT 'Premium | Standard | Basic',
    CREATED_AT      TIMESTAMP_NTZ   DEFAULT CURRENT_TIMESTAMP(),
    UPDATED_AT      TIMESTAMP_NTZ   DEFAULT CURRENT_TIMESTAMP()
);

CREATE OR REPLACE TABLE RAW.PRODUCTS (
    PRODUCT_ID      NUMBER(10,0)    NOT NULL PRIMARY KEY,
    PRODUCT_NAME    VARCHAR(255)    NOT NULL,
    CATEGORY        VARCHAR(100)    NOT NULL,
    SUB_CATEGORY    VARCHAR(100),
    UNIT_PRICE      NUMBER(10,2)    NOT NULL,
    COST_PRICE      NUMBER(10,2)    NOT NULL,
    STOCK_QTY       NUMBER(10,0)    DEFAULT 0,
    SUPPLIER        VARCHAR(255),
    IS_ACTIVE       BOOLEAN         DEFAULT TRUE,
    CREATED_AT      TIMESTAMP_NTZ   DEFAULT CURRENT_TIMESTAMP()
);

CREATE OR REPLACE TABLE RAW.SALES (
    SALE_ID         NUMBER(10,0)    NOT NULL PRIMARY KEY AUTOINCREMENT,
    CUSTOMER_ID     NUMBER(10,0)    NOT NULL REFERENCES RAW.CUSTOMERS(CUSTOMER_ID),
    PRODUCT_ID      NUMBER(10,0)    NOT NULL REFERENCES RAW.PRODUCTS(PRODUCT_ID),
    QUANTITY        NUMBER(10,0)    NOT NULL,
    UNIT_PRICE      NUMBER(10,2)    NOT NULL,
    DISCOUNT_PCT    NUMBER(5,2)     DEFAULT 0,
    TOTAL_AMOUNT    NUMBER(12,2)    NOT NULL,
    SALE_DATE       DATE            NOT NULL,
    CHANNEL         VARCHAR(50)     COMMENT 'online | store | phone',
    STATUS          VARCHAR(50)     DEFAULT 'completed' COMMENT 'completed | refunded | pending',
    CREATED_AT      TIMESTAMP_NTZ   DEFAULT CURRENT_TIMESTAMP()
);

-- ============================================================
-- 5. Vues ANALYTICS
-- ============================================================
USE SCHEMA AGENTIC_DB.ANALYTICS;

CREATE OR REPLACE VIEW ANALYTICS.SALES_SUMMARY AS
SELECT
    s.SALE_DATE,
    p.CATEGORY,
    p.SUB_CATEGORY,
    COUNT(DISTINCT s.SALE_ID)       AS NB_TRANSACTIONS,
    COUNT(DISTINCT s.CUSTOMER_ID)   AS NB_CUSTOMERS,
    SUM(s.QUANTITY)                 AS TOTAL_QTY,
    SUM(s.TOTAL_AMOUNT)             AS TOTAL_REVENUE,
    AVG(s.TOTAL_AMOUNT)             AS AVG_ORDER_VALUE
FROM RAW.SALES s
JOIN RAW.PRODUCTS p ON s.PRODUCT_ID = p.PRODUCT_ID
WHERE s.STATUS = 'completed'
GROUP BY 1, 2, 3;

CREATE OR REPLACE VIEW ANALYTICS.CUSTOMER_LTV AS
SELECT
    c.CUSTOMER_ID,
    c.FIRST_NAME || ' ' || c.LAST_NAME  AS FULL_NAME,
    c.SEGMENT,
    c.CITY,
    c.COUNTRY,
    COUNT(DISTINCT s.SALE_ID)           AS NB_ORDERS,
    SUM(s.TOTAL_AMOUNT)                 AS LIFETIME_VALUE,
    AVG(s.TOTAL_AMOUNT)                 AS AVG_ORDER_VALUE,
    MIN(s.SALE_DATE)                    AS FIRST_ORDER_DATE,
    MAX(s.SALE_DATE)                    AS LAST_ORDER_DATE,
    DATEDIFF('day', MAX(s.SALE_DATE), CURRENT_DATE()) AS DAYS_SINCE_LAST_ORDER
FROM RAW.CUSTOMERS c
LEFT JOIN RAW.SALES s ON c.CUSTOMER_ID = s.CUSTOMER_ID AND s.STATUS = 'completed'
GROUP BY 1, 2, 3, 4, 5;

-- ============================================================
-- Vérification
-- ============================================================
SHOW TABLES IN SCHEMA AGENTIC_DB.RAW;
SHOW VIEWS  IN SCHEMA AGENTIC_DB.ANALYTICS;
