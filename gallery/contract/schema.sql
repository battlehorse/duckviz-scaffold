-- The gallery's made-up contract: the Ask window's sample answer reads it. No database is ever made from it.
CREATE TABLE v_daily (
    day DATE PRIMARY KEY,  -- one row per day
    shop VARCHAR NOT NULL,  -- which shop
    spend DECIMAL(10, 2) NOT NULL  -- what was spent that day, in pounds
);
