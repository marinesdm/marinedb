# Advanced utilities

The following lower-level utilities provide more granular control than the corresponding
high-level spatial modules.

## isna

Related high-level module: [`islatloninvalid`](islatloninvalid.md)

Use [`isna`](../generic/isna.md) to handle missing values independently in the latitude
and longitude columns.

## isboundedby

Related high-level module: [`islatloninvalid`](islatloninvalid.md)

Use [`isboundedby`](../generic/isboundedby.md) to apply boundary checks independently to 
the latitude and longitude columns.

## iszero

Related high-level module: [`islatlonzero`](islatlonzero.md)

Use [`iszero`](iszero.md) to identify zero-valued entries independently in the latitude and
longitude columns.

??? abstract "API reference"
 
    <h2><code>marinedb.tools.spatial.iszero.apply</code></h2>

    ::: marinedb.tools.spatial.iszero.apply
        options:
          show_root_heading: false
          show_root_toc_entry: false

## belowminfloatprecision

Related high-level module:
[`belowminlatlonprecision`](belowminlatlonprecision.md)

Use [`belowminfloatprecision`](belowminfloatprecision.md) to assess decimal-place precision independently in
the latitude and longitude columns.

??? abstract "API reference"
 
    <h2><code>marinedb.tools.spatial.iszero.apply</code></h2>

    ::: marinedb.tools.spatial.belowminfloatprecision.apply
        options:
          show_root_heading: false
          show_root_toc_entry: false
