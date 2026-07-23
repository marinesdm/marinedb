# Spatial data curation

This section documents the `marinedb` modules dedicated to cleaning 
the spatial dimension of species occurrence data.

These tools can remove land-based records and detect common geospatial issues, 
including:

- missing coordinates;
- invalid coordinates;
- zero-valued coordinates;
- identical latitude and longitude values;
- low coordinate precision.
 
## Tools

- [`islatloninvalid`](islatloninvalid.md): detect missing latitude or longitude
  values and coordinates outside their valid geographic ranges.
- [`islatlonzero`](islatlonzero.md): detect records with zero-valued
  coordinates.
- [`doeslateqlon`](doeslateqlon.md): detect records whose latitude and
  longitude values are identical.
- [`belowminlatlonprecision`](belowminlatlonprecision.md): detect records with
  insufficient coordinate precision.
- [`marineloc`](marineloc/index.md): run the complete land–sea filtering
  workflow to remove land-based records.
