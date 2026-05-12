import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, event, text
from sqlalchemy.orm import sessionmaker

from app.config import settings
from app.db import get_db
from app.main import app

TEST_SCHEMA = "test_cocktail"

_DDL = """
CREATE TABLE ingredient_class (
    id           SERIAL PRIMARY KEY,
    parent_id    INT REFERENCES ingredient_class(id),
    name         TEXT NOT NULL UNIQUE,
    is_garnish   BOOLEAN NOT NULL DEFAULT FALSE,
    is_commodity BOOLEAN NOT NULL DEFAULT FALSE,
    notes        TEXT
);
CREATE TABLE bottle (
    id              SERIAL PRIMARY KEY,
    class_id        INT NOT NULL REFERENCES ingredient_class(id),
    brand           TEXT NOT NULL,
    label           TEXT,
    abv             NUMERIC(4,1),
    on_hand         BOOLEAN NOT NULL DEFAULT TRUE,
    flavor_profile  JSONB NOT NULL,
    notes           TEXT,
    added_at        TIMESTAMPTZ DEFAULT NOW()
);
CREATE TABLE recipe (
    id            SERIAL PRIMARY KEY,
    name          TEXT NOT NULL UNIQUE,
    iba_category  TEXT NOT NULL CHECK (iba_category IN
                   ('unforgettable','contemporary','new_era')),
    method        TEXT NOT NULL,
    glass         TEXT,
    garnish       TEXT,
    source_url    TEXT
);
CREATE TABLE recipe_ingredient (
    id                    SERIAL PRIMARY KEY,
    recipe_id             INT NOT NULL REFERENCES recipe(id) ON DELETE CASCADE,
    class_id              INT NOT NULL REFERENCES ingredient_class(id),
    amount                NUMERIC(7,2),
    unit                  TEXT,
    is_optional           BOOLEAN NOT NULL DEFAULT FALSE,
    is_garnish            BOOLEAN NOT NULL DEFAULT FALSE,
    alternative_group_id  INT,
    raw_name              TEXT,
    notes                 TEXT
);
"""

_SEED = """
-- 5 classes: 1 parent + 2 leaf children + 1 garnish parent + 1 garnish child
INSERT INTO ingredient_class (name, is_garnish)
    VALUES ('TestSpirit', FALSE);
INSERT INTO ingredient_class (name, parent_id, is_garnish)
    VALUES ('TestGin',
            (SELECT id FROM ingredient_class WHERE name = 'TestSpirit'),
            FALSE);
INSERT INTO ingredient_class (name, parent_id, is_garnish)
    VALUES ('TestVodka',
            (SELECT id FROM ingredient_class WHERE name = 'TestSpirit'),
            FALSE);
INSERT INTO ingredient_class (name, is_garnish)
    VALUES ('TestGarnish', TRUE);
INSERT INTO ingredient_class (name, parent_id, is_garnish)
    VALUES ('TestLemonWheel',
            (SELECT id FROM ingredient_class WHERE name = 'TestGarnish'),
            TRUE);
-- extra leaf for "optional" ingredient
INSERT INTO ingredient_class (name, parent_id, is_garnish)
    VALUES ('TestBitters',
            (SELECT id FROM ingredient_class WHERE name = 'TestSpirit'),
            FALSE);

-- 2 recipes
INSERT INTO recipe (name, iba_category, method, glass, garnish, source_url)
    VALUES ('Test Negroni', 'unforgettable', 'Stir and strain',
            'old fashioned', 'Orange peel', 'https://example.com/negroni');
INSERT INTO recipe (name, iba_category, method, glass, garnish, source_url)
    VALUES ('Test Mule', 'contemporary', 'Build in glass',
            'highball', 'Lime wedge', 'https://example.com/mule');

-- Test Negroni: 2 mandatory + 1 optional + 1 garnish
INSERT INTO recipe_ingredient (recipe_id, class_id, amount, unit,
                               is_optional, is_garnish, raw_name)
    VALUES ((SELECT id FROM recipe WHERE name = 'Test Negroni'),
            (SELECT id FROM ingredient_class WHERE name = 'TestGin'),
            30, 'ml', FALSE, FALSE, 'Gin');
INSERT INTO recipe_ingredient (recipe_id, class_id, amount, unit,
                               is_optional, is_garnish, raw_name)
    VALUES ((SELECT id FROM recipe WHERE name = 'Test Negroni'),
            (SELECT id FROM ingredient_class WHERE name = 'TestVodka'),
            30, 'ml', FALSE, FALSE, 'Vodka');
INSERT INTO recipe_ingredient (recipe_id, class_id, amount, unit,
                               is_optional, is_garnish, raw_name)
    VALUES ((SELECT id FROM recipe WHERE name = 'Test Negroni'),
            (SELECT id FROM ingredient_class WHERE name = 'TestBitters'),
            2, 'dash', TRUE, FALSE, 'Bitters');
INSERT INTO recipe_ingredient (recipe_id, class_id, amount, unit,
                               is_optional, is_garnish, raw_name)
    VALUES ((SELECT id FROM recipe WHERE name = 'Test Negroni'),
            (SELECT id FROM ingredient_class WHERE name = 'TestLemonWheel'),
            1, NULL, FALSE, TRUE, 'Lemon wheel');

-- Test Mule: 2 alternatives (alt_group=1)
INSERT INTO recipe_ingredient (recipe_id, class_id, amount, unit,
                               is_optional, is_garnish, alternative_group_id,
                               raw_name)
    VALUES ((SELECT id FROM recipe WHERE name = 'Test Mule'),
            (SELECT id FROM ingredient_class WHERE name = 'TestGin'),
            45, 'ml', FALSE, FALSE, 1, 'Gin');
INSERT INTO recipe_ingredient (recipe_id, class_id, amount, unit,
                               is_optional, is_garnish, alternative_group_id,
                               raw_name)
    VALUES ((SELECT id FROM recipe WHERE name = 'Test Mule'),
            (SELECT id FROM ingredient_class WHERE name = 'TestVodka'),
            45, 'ml', FALSE, FALSE, 1, 'Vodka');

-- Commodity classes (always-available pantry items)
INSERT INTO ingredient_class (name, is_garnish, is_commodity)
    VALUES ('TestMixer', FALSE, FALSE);
INSERT INTO ingredient_class (name, parent_id, is_garnish, is_commodity)
    VALUES ('TestSodaWater',
            (SELECT id FROM ingredient_class WHERE name = 'TestMixer'),
            FALSE, TRUE);
INSERT INTO ingredient_class (name, parent_id, is_garnish, is_commodity)
    VALUES ('TestOrangeJuice',
            (SELECT id FROM ingredient_class WHERE name = 'TestMixer'),
            FALSE, TRUE);

-- Recipe that needs spirit + commodity (e.g., a "Test Spritz")
INSERT INTO recipe (name, iba_category, method, glass, garnish, source_url)
    VALUES ('Test Spritz', 'contemporary', 'Build over ice',
            'highball', NULL, 'https://example.com/spritz');

-- Test Spritz: 1 mandatory spirit + 1 commodity
INSERT INTO recipe_ingredient (recipe_id, class_id, amount, unit,
                               is_optional, is_garnish, raw_name)
    VALUES ((SELECT id FROM recipe WHERE name = 'Test Spritz'),
            (SELECT id FROM ingredient_class WHERE name = 'TestGin'),
            45, 'ml', FALSE, FALSE, 'Gin');
INSERT INTO recipe_ingredient (recipe_id, class_id, amount, unit,
                               is_optional, is_garnish, raw_name)
    VALUES ((SELECT id FROM recipe WHERE name = 'Test Spritz'),
            (SELECT id FROM ingredient_class WHERE name = 'TestSodaWater'),
            120, 'ml', FALSE, FALSE, 'Soda Water');

-- Recipe with only commodities (e.g., "Test Juice Mix")
INSERT INTO recipe (name, iba_category, method, glass, garnish, source_url)
    VALUES ('Test Juice Mix', 'new_era', 'Shake and strain',
            'highball', NULL, 'https://example.com/juicemix');
INSERT INTO recipe_ingredient (recipe_id, class_id, amount, unit,
                               is_optional, is_garnish, raw_name)
    VALUES ((SELECT id FROM recipe WHERE name = 'Test Juice Mix'),
            (SELECT id FROM ingredient_class WHERE name = 'TestSodaWater'),
            90, 'ml', FALSE, FALSE, 'Soda Water');
INSERT INTO recipe_ingredient (recipe_id, class_id, amount, unit,
                               is_optional, is_garnish, raw_name)
    VALUES ((SELECT id FROM recipe WHERE name = 'Test Juice Mix'),
            (SELECT id FROM ingredient_class WHERE name = 'TestOrangeJuice'),
            60, 'ml', FALSE, FALSE, 'Orange Juice');
"""


@pytest.fixture(scope="session", autouse=True)
def _setup_test_schema():
    """Create a temporary schema with test data; drop it after the session."""
    setup_engine = create_engine(settings.database_url)
    with setup_engine.begin() as conn:
        conn.execute(text(f"DROP SCHEMA IF EXISTS {TEST_SCHEMA} CASCADE"))
        conn.execute(text(f"CREATE SCHEMA {TEST_SCHEMA}"))
        conn.execute(text(f"SET search_path TO {TEST_SCHEMA}"))
        for stmt in _DDL.split(";"):
            stmt = stmt.strip()
            if stmt:
                conn.execute(text(stmt))
        for stmt in _SEED.split(";"):
            stmt = stmt.strip()
            if stmt:
                conn.execute(text(stmt))
    setup_engine.dispose()

    yield

    teardown_engine = create_engine(settings.database_url)
    with teardown_engine.begin() as conn:
        conn.execute(text(f"DROP SCHEMA IF EXISTS {TEST_SCHEMA} CASCADE"))
    teardown_engine.dispose()


@pytest.fixture(scope="session")
def _test_engine(_setup_test_schema):
    """Engine whose connections always use the test schema."""
    eng = create_engine(settings.database_url, pool_pre_ping=True)

    @event.listens_for(eng, "connect")
    def _set_search_path(dbapi_conn, _connection_record):
        with dbapi_conn.cursor() as cur:
            cur.execute(f"SET search_path TO {TEST_SCHEMA}")

    @event.listens_for(eng, "checkout")
    def _reset_search_path(dbapi_conn, _connection_record, _connection_proxy):
        with dbapi_conn.cursor() as cur:
            cur.execute(f"SET search_path TO {TEST_SCHEMA}")

    yield eng
    eng.dispose()


@pytest.fixture(scope="session")
def client(_test_engine):
    """TestClient that uses the test schema for all DB operations."""
    TestSession = sessionmaker(bind=_test_engine)

    def _override_get_db():
        db = TestSession()
        try:
            yield db
        finally:
            db.close()

    app.dependency_overrides[get_db] = _override_get_db

    with TestClient(app) as c:
        yield c

    app.dependency_overrides.clear()
