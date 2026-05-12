BEGIN;

-- Mark select wines as commodity (semantically: "assumed always available
-- in the home bar").  These are not consumables like soda water or fresh
-- juice, but they're given for granted in Francesco's home setup.
-- The is_commodity flag is reused to avoid schema bloat; see backend
-- README § "Assumed-Available Ingredients" for the dual-meaning docs.
UPDATE ingredient_class
SET is_commodity = TRUE
WHERE name IN ('Champagne', 'Prosecco', 'Red Wine', 'Dry White Wine');

-- Validation
DO $$
DECLARE
  marked_count INT;
BEGIN
  SELECT COUNT(*) INTO marked_count
  FROM ingredient_class
  WHERE name IN ('Champagne', 'Prosecco', 'Red Wine', 'Dry White Wine')
    AND is_commodity = TRUE;
  IF marked_count <> 4 THEN
    RAISE EXCEPTION 'Expected 4 wines marked as commodity, got %', marked_count;
  END IF;
  RAISE NOTICE 'Marked Champagne, Prosecco, Red Wine, Dry White Wine as assumed-available';
END$$;

COMMIT;
