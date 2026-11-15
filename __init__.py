"""Ghost Lakes: find water that cities bury, using AI and free satellite data (Google Earth Engine).

Modules
  common   paths, Earth Engine setup and the satellite helpers every step uses
  radar    the Sentinel-1 radar rule (confirm water -> land) and radar dating
  terrain  terrain AI (Random Forest): where water *should* be, plus its validation
  archive  archive detector: water seen by Landsat before 2010, built-up today
  infill   infill monitor: water -> land between two periods (any place), and the global screen
  abidjan  the Abidjan case study: every step from detection to figures
  review   image chips and OpenStreetMap checks for manual review
  report   one-page PDFs and the results notebook

Everything is driven from run.py.
"""
