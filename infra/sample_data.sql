-- ============================================================
-- Snowflake Agentic AI — Sample Data
-- ============================================================

USE DATABASE AGENTIC_DB;
USE SCHEMA RAW;
USE WAREHOUSE AGENTIC_WH;

-- ============================================================
-- CUSTOMERS (30 clients réalistes)
-- ============================================================
INSERT INTO RAW.CUSTOMERS (CUSTOMER_ID, FIRST_NAME, LAST_NAME, EMAIL, PHONE, CITY, COUNTRY, SEGMENT) VALUES
(1,  'Sophie',    'Martin',    'sophie.martin@email.fr',     '+33612345678', 'Paris',         'France',  'Premium'),
(2,  'Lucas',     'Dubois',    'lucas.dubois@email.fr',      '+33623456789', 'Lyon',           'France',  'Standard'),
(3,  'Emma',      'Bernard',   'emma.bernard@email.fr',      '+33634567890', 'Marseille',     'France',  'Basic'),
(4,  'Hugo',      'Petit',     'hugo.petit@email.fr',        '+33645678901', 'Toulouse',      'France',  'Standard'),
(5,  'Léa',       'Moreau',    'lea.moreau@email.fr',        '+33656789012', 'Nice',           'France',  'Premium'),
(6,  'Nathan',    'Simon',     'nathan.simon@email.fr',      '+33667890123', 'Nantes',         'France',  'Basic'),
(7,  'Jade',      'Laurent',   'jade.laurent@email.fr',      '+33678901234', 'Strasbourg',    'France',  'Premium'),
(8,  'Tom',       'Lefebvre',  'tom.lefebvre@email.fr',      '+33689012345', 'Bordeaux',      'France',  'Standard'),
(9,  'Camille',   'Michel',    'camille.michel@email.fr',    '+33690123456', 'Lille',          'France',  'Standard'),
(10, 'Théo',      'Garcia',    'theo.garcia@email.fr',       '+33601234567', 'Rennes',         'France',  'Basic'),
(11, 'Manon',     'David',     'manon.david@email.fr',       '+33712345678', 'Paris',          'France',  'Premium'),
(12, 'Maxime',    'Bertrand',  'maxime.bertrand@email.fr',   '+33723456789', 'Lyon',           'France',  'Standard'),
(13, 'Inès',      'Roux',      'ines.roux@email.fr',         '+33734567890', 'Grenoble',      'France',  'Premium'),
(14, 'Raphaël',   'Vincent',   'raphael.vincent@email.fr',   '+33745678901', 'Montpellier',   'France',  'Basic'),
(15, 'Chloé',     'Fournier',  'chloe.fournier@email.fr',    '+33756789012', 'Bordeaux',      'France',  'Standard'),
(16, 'Antoine',   'Morel',     'antoine.morel@email.fr',     '+33767890123', 'Paris',          'France',  'Premium'),
(17, 'Zoé',       'Girard',    'zoe.girard@email.fr',        '+33778901234', 'Nantes',         'France',  'Standard'),
(18, 'Baptiste',  'André',     'baptiste.andre@email.fr',    '+33789012345', 'Nice',           'France',  'Basic'),
(19, 'Alice',     'Leroy',     'alice.leroy@email.fr',       '+33790123456', 'Toulouse',      'France',  'Premium'),
(20, 'Clément',   'Durand',    'clement.durand@email.fr',    '+33701234567', 'Strasbourg',    'France',  'Standard'),
(21, 'Pauline',   'Bonnet',    'pauline.bonnet@email.fr',    '+32478123456', 'Bruxelles',     'Belgique','Premium'),
(22, 'Kevin',     'Dupont',    'kevin.dupont@email.fr',      '+41791234567', 'Genève',         'Suisse',  'Standard'),
(23, 'Marie',     'Lemaire',   'marie.lemaire@email.fr',     '+33612987654', 'Paris',          'France',  'Premium'),
(24, 'Alexis',    'Renard',    'alexis.renard@email.fr',     '+33623876543', 'Lyon',           'France',  'Basic'),
(25, 'Clara',     'Blanc',     'clara.blanc@email.fr',       '+33634765432', 'Marseille',     'France',  'Standard'),
(26, 'Florian',   'Chevalier', 'florian.chevalier@email.fr', '+33645654321', 'Bordeaux',      'France',  'Premium'),
(27, 'Sarah',     'Gauthier',  'sarah.gauthier@email.fr',    '+33656543210', 'Lille',          'France',  'Standard'),
(28, 'Pierre',    'Marchand',  'pierre.marchand@email.fr',   '+33667432109', 'Rennes',         'France',  'Basic'),
(29, 'Lucie',     'Faure',     'lucie.faure@email.fr',       '+33678321098', 'Grenoble',      'France',  'Premium'),
(30, 'Mathieu',   'Robin',     'mathieu.robin@email.fr',     '+33689210987', 'Montpellier',   'France',  'Standard');

-- ============================================================
-- PRODUCTS (25 produits réalistes)
-- ============================================================
INSERT INTO RAW.PRODUCTS (PRODUCT_ID, PRODUCT_NAME, CATEGORY, SUB_CATEGORY, UNIT_PRICE, COST_PRICE, STOCK_QTY, SUPPLIER) VALUES
(1,  'MacBook Pro 14"',          'Informatique',    'Ordinateurs',    2499.00, 1800.00,  45,  'Apple France'),
(2,  'iPhone 15 Pro',            'Téléphonie',      'Smartphones',    1299.00,  890.00,  120, 'Apple France'),
(3,  'Samsung Galaxy S24',       'Téléphonie',      'Smartphones',     999.00,  680.00,  85,  'Samsung'),
(4,  'Dell XPS 15',              'Informatique',    'Ordinateurs',    1899.00, 1350.00,  30,  'Dell'),
(5,  'Sony WH-1000XM5',          'Audio',           'Casques',         399.00,  220.00,  200, 'Sony'),
(6,  'iPad Air M2',              'Informatique',    'Tablettes',       899.00,  620.00,  75,  'Apple France'),
(7,  'LG OLED 55"',              'TV & Vidéo',      'Téléviseurs',    1299.00,  890.00,  25,  'LG'),
(8,  'Nintendo Switch OLED',     'Gaming',          'Consoles',        349.00,  220.00,  150, 'Nintendo'),
(9,  'PS5 Digital Edition',      'Gaming',          'Consoles',        449.00,  340.00,  40,  'Sony'),
(10, 'Dyson V15 Detect',         'Électroménager',  'Aspirateurs',     699.00,  420.00,  60,  'Dyson'),
(11, 'AirPods Pro 2',            'Audio',           'Écouteurs',       299.00,  180.00,  300, 'Apple France'),
(12, 'Canon EOS R50',            'Photo',           'Appareils photo', 879.00,  580.00,  35,  'Canon'),
(13, 'Microsoft Surface Pro 9',  'Informatique',    'Tablettes',      1299.00,  880.00,  28,  'Microsoft'),
(14, 'Logitech MX Master 3S',    'Informatique',    'Périphériques',   109.00,   58.00,  500, 'Logitech'),
(15, 'Samsung 4K Monitor 27"',   'Informatique',    'Moniteurs',       449.00,  290.00,  80,  'Samsung'),
(16, 'Bose SoundLink Max',       'Audio',           'Enceintes',       399.00,  240.00,  120, 'Bose'),
(17, 'GoPro Hero 12',            'Photo',           'Caméras',         449.00,  280.00,  90,  'GoPro'),
(18, 'Garmin Fenix 7',           'Sport & Santé',   'Montres',         799.00,  500.00,  55,  'Garmin'),
(19, 'Kindle Paperwhite',        'Liseuses',        'Liseuses',        159.00,   85.00,  250, 'Amazon'),
(20, 'Corsair K95 RGB',          'Gaming',          'Claviers',        199.00,  110.00,  180, 'Corsair'),
(21, 'Jabra Evolve2 75',         'Audio',           'Casques Pro',     449.00,  270.00,  70,  'Jabra'),
(22, 'HP LaserJet Pro',          'Informatique',    'Imprimantes',     399.00,  230.00,  45,  'HP'),
(23, 'Xiaomi 13T Pro',           'Téléphonie',      'Smartphones',     749.00,  480.00,  110, 'Xiaomi'),
(24, 'ASUS ROG Zephyrus G14',    'Informatique',    'Ordinateurs',    1699.00, 1200.00,  20,  'ASUS'),
(25, 'Philips Hue Starter Kit',  'Maison connectée','Éclairage',       199.00,  100.00,  300, 'Philips');

-- ============================================================
-- SALES (60 ventes sur les 6 derniers mois)
-- ============================================================
INSERT INTO RAW.SALES (CUSTOMER_ID, PRODUCT_ID, QUANTITY, UNIT_PRICE, DISCOUNT_PCT, TOTAL_AMOUNT, SALE_DATE, CHANNEL, STATUS) VALUES
-- Novembre 2024
(1,  2,  1, 1299.00, 0.00,  1299.00, '2024-11-02', 'online', 'completed'),
(5,  5,  1,  399.00, 5.00,   379.05, '2024-11-04', 'store',  'completed'),
(11, 1,  1, 2499.00, 10.00, 2249.10, '2024-11-06', 'online', 'completed'),
(3,  8,  2,  349.00, 0.00,   698.00, '2024-11-08', 'store',  'completed'),
(16, 7,  1, 1299.00, 5.00,  1234.05, '2024-11-10', 'online', 'completed'),
(22, 11, 2,  299.00, 0.00,   598.00, '2024-11-12', 'online', 'completed'),
(7,  3,  1,  999.00, 0.00,   999.00, '2024-11-15', 'phone',  'completed'),
(13, 18, 1,  799.00, 5.00,   759.05, '2024-11-18', 'online', 'completed'),
(2,  14, 3,  109.00, 0.00,   327.00, '2024-11-20', 'store',  'completed'),
(25, 25, 2,  199.00, 0.00,   398.00, '2024-11-22', 'online', 'completed'),

-- Décembre 2024 (fêtes de fin d'année)
(1,  11, 1,  299.00, 0.00,   299.00, '2024-12-01', 'online', 'completed'),
(5,  1,  1, 2499.00, 15.00, 2124.15, '2024-12-03', 'online', 'completed'),
(19, 9,  1,  449.00, 0.00,   449.00, '2024-12-05', 'store',  'completed'),
(26, 2,  2, 1299.00, 10.00, 2338.20, '2024-12-08', 'online', 'completed'),
(11, 7,  1, 1299.00, 0.00,  1299.00, '2024-12-10', 'store',  'completed'),
(8,  8,  1,  349.00, 5.00,   331.55, '2024-12-12', 'online', 'completed'),
(29, 17, 1,  449.00, 0.00,   449.00, '2024-12-14', 'online', 'completed'),
(16, 1,  1, 2499.00, 0.00,  2499.00, '2024-12-15', 'store',  'completed'),
(23, 5,  1,  399.00, 5.00,   379.05, '2024-12-18', 'online', 'completed'),
(4,  20, 1,  199.00, 0.00,   199.00, '2024-12-20', 'store',  'completed'),
(7,  24, 1, 1699.00, 10.00, 1529.10, '2024-12-22', 'online', 'completed'),
(13, 6,  1,  899.00, 5.00,   854.05, '2024-12-24', 'store',  'completed'),
(21, 2,  1, 1299.00, 0.00,  1299.00, '2024-12-26', 'online', 'completed'),
(30, 3,  1,  999.00, 15.00,  849.15, '2024-12-28', 'online', 'completed'),

-- Janvier 2025 (soldes)
(2,  15, 1,  449.00, 20.00,  359.20, '2025-01-05', 'online', 'completed'),
(6,  19, 2,  159.00, 0.00,   318.00, '2025-01-07', 'store',  'completed'),
(14, 3,  1,  999.00, 15.00,  849.15, '2025-01-10', 'online', 'completed'),
(17, 10, 1,  699.00, 10.00,  629.10, '2025-01-12', 'online', 'completed'),
(24, 11, 3,  299.00, 5.00,   851.55, '2025-01-15', 'store',  'completed'),
(9,  8,  1,  349.00, 20.00,  279.20, '2025-01-18', 'online', 'completed'),
(12, 16, 1,  399.00, 0.00,   399.00, '2025-01-22', 'online', 'completed'),
(3,  2,  1, 1299.00, 0.00,  1299.00, '2025-01-25', 'phone',  'completed'),
(18, 21, 1,  449.00, 10.00,  404.10, '2025-01-28', 'online', 'completed'),

-- Février 2025
(1,  18, 1,  799.00, 0.00,   799.00, '2025-02-03', 'online', 'completed'),
(27, 4,  1, 1899.00, 5.00,  1804.05, '2025-02-06', 'store',  'completed'),
(5,  12, 1,  879.00, 0.00,   879.00, '2025-02-10', 'online', 'completed'),
(20, 25, 3,  199.00, 0.00,   597.00, '2025-02-12', 'store',  'completed'),
(29, 9,  1,  449.00, 5.00,   426.55, '2025-02-14', 'online', 'completed'),
(10, 14, 2,  109.00, 0.00,   218.00, '2025-02-18', 'store',  'completed'),
(16, 11, 1,  299.00, 0.00,   299.00, '2025-02-22', 'online', 'completed'),
(22, 6,  1,  899.00, 10.00,  809.10, '2025-02-25', 'online', 'completed'),

-- Mars 2025
(7,  1,  1, 2499.00, 0.00,  2499.00, '2025-03-03', 'online', 'completed'),
(19, 5,  2,  399.00, 5.00,   758.10, '2025-03-07', 'store',  'completed'),
(26, 15, 2,  449.00, 0.00,   898.00, '2025-03-10', 'online', 'completed'),
(13, 3,  1,  999.00, 0.00,   999.00, '2025-03-12', 'phone',  'completed'),
(28, 8,  1,  349.00, 5.00,   331.55, '2025-03-15', 'store',  'completed'),
(2,  17, 1,  449.00, 0.00,   449.00, '2025-03-18', 'online', 'completed'),
(11, 24, 1, 1699.00, 0.00,  1699.00, '2025-03-22', 'online', 'completed'),
(4,  2,  1, 1299.00, 5.00,  1234.05, '2025-03-25', 'store',  'completed'),
(15, 22, 1,  399.00, 0.00,   399.00, '2025-03-28', 'online', 'completed'),

-- Avril 2025
(23, 1,  1, 2499.00, 10.00, 2249.10, '2025-04-02', 'online', 'completed'),
(8,  7,  1, 1299.00, 5.00,  1234.05, '2025-04-05', 'store',  'completed'),
(30, 11, 2,  299.00, 0.00,   598.00, '2025-04-08', 'online', 'completed'),
(17, 18, 1,  799.00, 0.00,   799.00, '2025-04-12', 'online', 'completed'),
(6,  9,  1,  449.00, 0.00,   449.00, '2025-04-15', 'store',  'completed'),
(25, 16, 1,  399.00, 5.00,   379.05, '2025-04-18', 'online', 'completed'),
(1,  4,  1, 1899.00, 0.00,  1899.00, '2025-04-22', 'online', 'completed'),
(14, 20, 2,  199.00, 10.00,  358.20, '2025-04-25', 'store',  'completed'),
(21, 3,  1,  999.00, 5.00,   949.05, '2025-04-28', 'online', 'completed'),

-- Remboursement (pour tester STATUS)
(3,  8,  1,  349.00, 0.00,  -349.00, '2025-04-30', 'store',  'refunded');

-- ============================================================
-- Vérification rapide
-- ============================================================
SELECT 'CUSTOMERS' AS TABLE_NAME, COUNT(*) AS NB_ROWS FROM RAW.CUSTOMERS
UNION ALL
SELECT 'PRODUCTS',  COUNT(*) FROM RAW.PRODUCTS
UNION ALL
SELECT 'SALES',     COUNT(*) FROM RAW.SALES;
