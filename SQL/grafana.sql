SELECT
  $__timeGroup(timestamp, $__interval) AS "time",
  avg(value) AS "Vibrasyon (mm/s)"
FROM public.metrics_raw
WHERE
  $__timeFilter(timestamp) AND
  equipment_id = 'centrifugal_pump' AND
  tag = 'vibration'
GROUP BY 1
ORDER BY 1 ASC;