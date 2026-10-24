-- The contract this database offers: one row.
CREATE TABLE v_contract (
    contract VARCHAR NOT NULL,  -- the contract's name
    version VARCHAR NOT NULL    -- its version, major.minor
);

-- One row per item.
-- Items never repeat.
CREATE TABLE v_items (
    item VARCHAR NOT NULL,      -- the item's name
    kind VARCHAR NOT NULL,      -- fruit or veg
    price DOUBLE,               -- in pounds;
                                -- NULL when unknown
    PRIMARY KEY (item)
);
