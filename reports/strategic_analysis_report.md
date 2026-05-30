# Strategic E-Commerce Analytics Report

- Snapshot Date: `2026-05-30`
- Charts Generated: `5`
- Rejected Unverified Rows: `0`
- Raw Rows: `894`
- Latest Snapshot Rows: `894`
- Active Verified Offers: `894`
- Product Metrics: `50`

## Output Inventory

### Marketplace Lowest-Price Win Rate

- Plotter: `MarketplaceAggressivenessPlotter`
- File: `01_marketplace_lowest_price_win_rate.png`
- Path: `reports/charts/01_marketplace_lowest_price_win_rate.png`
- Summary: Measures how often each marketplace matches the lowest visible price within each product category.

### Price Spread vs. Market Depth

- Plotter: `PriceDispersionPlotter`
- File: `02_price_spread_market_depth.png`
- Path: `reports/charts/02_price_spread_market_depth.png`
- Summary: Shows whether broader offer depth compresses or amplifies price spread across products.

### Category Price Distribution & Outlier Risk

- Plotter: `GhostListingPlotter`
- File: `03_category_price_outlier_risk.png`
- Path: `reports/charts/03_category_price_outlier_risk.png`
- Summary: Highlights category-level price distributions and isolates upper-tail price outlier candidates.

### Seller Depth Risk Profile

- Plotter: `AssortmentVulnerabilityPlotter`
- File: `04_seller_depth_risk_profile.png`
- Path: `reports/charts/04_seller_depth_risk_profile.png`
- Summary: Groups products into consistent seller-depth tiers to reveal assortment fragility and concentration risk.

### Portfolio Mix by Category and Price Tier

- Plotter: `PortfolioSegmentationPlotter`
- File: `05_portfolio_price_tier_mix.png`
- Path: `reports/charts/05_portfolio_price_tier_mix.png`
- Summary: Shows the product portfolio split by category and price tier using minimum visible price per product.
