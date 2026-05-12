BEGIN;

ALTER TABLE ingredient_class
  ADD COLUMN is_commodity BOOLEAN NOT NULL DEFAULT FALSE;

-- Mark commodities
UPDATE ingredient_class SET is_commodity = TRUE WHERE name IN (
  -- Carbonated mixers
  'Soda Water', 'Tonic Water', 'Ginger Beer', 'Ginger Ale',
  'Cola', 'Pink Grapefruit Soda',
  -- Fresh juices (squeezed at the moment)
  'Fresh Lemon Juice', 'Fresh Lime Juice', 'Fresh Orange Juice',
  'Fresh Pineapple Juice', 'Fresh Grapefruit Juice',
  'Cranberry Juice', 'Tomato Juice', 'Sugar Cane Juice',
  -- Sugars
  'Sugar', 'Sugar Cube', 'Fine Sugar', 'Cane Sugar',
  'Demerara Sugar', 'Vanilla Sugar',
  -- Simple syrups (preparable in 2 minutes)
  'Simple Syrup', 'Honey Syrup', 'Honey Mix', 'Raw Honey',
  -- Dairy & eggs
  'Egg White', 'Egg Yolk', 'Cream', 'Coconut Cream',
  -- Pantry staples
  'Salt', 'Cloves', 'Vanilla Extract', 'Water', 'Worcestershire Sauce',
  -- Coffee
  'Hot Coffee', 'Espresso'
);

-- Validation: counts how many commodities were flagged
DO $$
DECLARE
  marked_count INT;
BEGIN
  SELECT COUNT(*) INTO marked_count FROM ingredient_class WHERE is_commodity = TRUE;
  RAISE NOTICE 'Marked % classes as commodity', marked_count;
  IF marked_count < 30 THEN
    RAISE EXCEPTION 'Expected at least 30 commodities marked, got %', marked_count;
  END IF;
END$$;

COMMIT;
