CREATE database products_db
use products_db

-- 1) Categories (lookup table)
IF OBJECT_ID('dbo.categories', 'U') IS NULL
CREATE TABLE dbo.categories (
    category_id  INT IDENTITY(1,1) PRIMARY KEY,
    name         NVARCHAR(100) NOT NULL UNIQUE
);
GO
 
-- 2) Products (one row per book = current state)
IF OBJECT_ID('dbo.products', 'U') IS NULL
CREATE TABLE dbo.products (
    product_id       INT IDENTITY(1,1) PRIMARY KEY,
    url              NVARCHAR(400) NOT NULL UNIQUE,      -- natural key from the scraper
    title            NVARCHAR(500) NOT NULL,
    category_id      INT NULL REFERENCES dbo.categories(category_id),
    first_seen_date  DATE NOT NULL,
    last_seen_date   DATE NOT NULL,
    is_active        BIT NOT NULL DEFAULT 1              -- 0 = removed product
);
GO
 
-- 3) Price history (one row per product per run/snapshot)
IF OBJECT_ID('dbo.price_history', 'U') IS NULL
CREATE TABLE dbo.price_history (
    product_id     INT NOT NULL REFERENCES dbo.products(product_id),
    snapshot_date  DATE NOT NULL,
    price          DECIMAL(8,2) NOT NULL CHECK (price >= 0),
    rating         TINYINT NULL CHECK (rating BETWEEN 1 AND 5),
    in_stock       BIT NULL,
    category_id    INT NULL REFERENCES dbo.categories(category_id),  -- per snapshot, to detect category changes
    scraped_at     DATETIMEOFFSET NULL,
    CONSTRAINT PK_price_history PRIMARY KEY (product_id, snapshot_date)   -- one row per product per snapshot
);
GO
 
-- Indexes for frequently queried fields
IF NOT EXISTS (SELECT 1 FROM sys.indexes WHERE name = 'idx_history_snapshot_date' AND object_id = OBJECT_ID('dbo.price_history'))
    CREATE INDEX idx_history_snapshot_date ON dbo.price_history (snapshot_date);
GO
IF NOT EXISTS (SELECT 1 FROM sys.indexes WHERE name = 'idx_products_category' AND object_id = OBJECT_ID('dbo.products'))
    CREATE INDEX idx_products_category ON dbo.products (category_id);
GO
IF NOT EXISTS (SELECT 1 FROM sys.indexes WHERE name = 'idx_products_active' AND object_id = OBJECT_ID('dbo.products'))
    CREATE INDEX idx_products_active ON dbo.products (is_active);
GO
 