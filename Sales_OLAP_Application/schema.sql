-- Sales OLAP Star Schema
CREATE TABLE dim_time (
    date TEXT PRIMARY KEY,
    year INTEGER,
    quarter TEXT,
    month INTEGER,
    month_name TEXT
);

CREATE TABLE dim_product (
    product_id TEXT PRIMARY KEY,
    product TEXT,
    category TEXT,
    unit_price REAL
);

CREATE TABLE dim_customer (
    customer_id TEXT PRIMARY KEY,
    customer TEXT,
    customer_type TEXT
);

CREATE TABLE dim_location (
    location_id TEXT PRIMARY KEY,
    state TEXT,
    city TEXT
);

CREATE TABLE fact_sales (
    sale_id INTEGER PRIMARY KEY AUTOINCREMENT,
    date TEXT,
    product_id TEXT,
    customer_id TEXT,
    location_id TEXT,
    quantity INTEGER,
    sales REAL,
    profit REAL
);
