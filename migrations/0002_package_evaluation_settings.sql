-- Customer-configurable technical/commercial evaluation weights.
-- Apply once to existing production databases before deploying this release.
CREATE TABLE IF NOT EXISTS package_evaluation_settings (
    id INTEGER PRIMARY KEY,
    package_id INTEGER NOT NULL UNIQUE,
    technical_weight FLOAT NOT NULL DEFAULT 70.0,
    commercial_weight FLOAT NOT NULL DEFAULT 30.0,
    created_at DATETIME NOT NULL,
    updated_at DATETIME NOT NULL,
    FOREIGN KEY(package_id) REFERENCES procurement_packages(id)
);

INSERT INTO package_evaluation_settings (
    package_id, technical_weight, commercial_weight, created_at, updated_at
)
SELECT id, 70.0, 30.0, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP
FROM procurement_packages
WHERE id NOT IN (SELECT package_id FROM package_evaluation_settings);
