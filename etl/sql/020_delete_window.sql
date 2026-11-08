DELETE FROM core.prices p
USING etl_bounds b
WHERE p.price_id IN (SELECT c.price_id FROM etl_classified c)
   OR (
        (b.start_date IS NULL OR p.loading_date >= b.start_date)
        AND (b.end_date IS NULL OR p.loading_date <= b.end_date)
      );

DELETE FROM dq.quarantine_prices q
USING etl_bounds b
WHERE q.price_id IN (SELECT c.price_id FROM etl_classified c)
   OR (
        (b.start_date IS NULL OR q.loading_date >= b.start_date)
        AND (b.end_date IS NULL OR q.loading_date <= b.end_date)
      );
