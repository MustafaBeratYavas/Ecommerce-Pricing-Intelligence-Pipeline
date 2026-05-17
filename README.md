<div align="center">
  <h1>E-COMMERCE PRICING INTELLIGENCE PIPELINE</h1>
  <p>
    <strong>Project Focus:</strong> End-to-end marketplace pricing intelligence, local data warehousing, and strategic analytics.
  </p>

  <p>
    <a href="https://www.python.org/">
      <img src="https://img.shields.io/badge/Python-3.11%2B-3776AB?logo=python&amp;logoColor=white" alt="Python" />
    </a>
    <a href="https://pandas.pydata.org/">
      <img src="https://img.shields.io/badge/Pandas-3.0.2-150458?logo=pandas&amp;logoColor=white" alt="Pandas" />
    </a>
    <a href="https://seleniumbase.io/">
      <img src="https://img.shields.io/badge/SeleniumBase-4.46%2B-00A98F?logo=selenium&amp;logoColor=white" alt="SeleniumBase" />
    </a>
    <a href="./LICENSE">
      <img src="https://img.shields.io/badge/License-MIT-green.svg" alt="License" />
    </a>
  </p>
</div>

This repository implements an end-to-end data engineering and analytics pipeline for building a structured marketplace pricing intelligence layer from publicly available e-commerce listing data. The system processes targeted product codes, resolves candidate product pages through a multi-step search strategy, extracts product, seller, marketplace, and price signals, and persists validated daily snapshots into a local SQLite warehouse.

The downstream analytics layer transforms the normalized offer table into product-level metrics such as seller depth, offer count, minimum price, maximum price, average price, price spread, and price tier. It then generates a compact portfolio of strategic charts that summarize marketplace price competition, product-level price dispersion, category outlier risk, seller-depth fragility, and portfolio price-tier composition.

The current seed universe in `product_codes.txt` contains 50 unique Razer product codes: 25 mouse targets using the `RZ01` family and 25 headset targets using the `RZ04` family. Keyboard targets are intentionally not part of the active seed list.

<details>
<summary><b>Click to expand project structure details</b></summary>

```text
.
├── .github
│   └── workflows
│       └── ci.yml                        # Lint, test, and coverage workflow
├── config
│   ├── analysis.yaml                     # Analytics thresholds, chart style, category aliases, and plot behavior
│   ├── browser.yaml                      # Browser runtime and target URL settings
│   ├── marketplaces.yaml                 # Marketplace IDs, canonical aliases, and display aliases
│   ├── scraping.yaml                     # Retry policy, scraping delays, fallback behavior, and seller collection tuning
│   ├── selectors.yaml                    # DOM selector contracts for search, product, card, Google, and overlays
│   └── settings.yaml                     # Paths, database, and observability defaults
├── database
│   ├── .gitkeep                          # Keeps the database directory available in fresh clones
│   └── scraper.db                        # Versioned SQLite warehouse snapshot used by the analytics report
├── logs
│   └── .gitkeep                          # Keeps the runtime log directory available in fresh clones
├── reports
│   ├── charts                            # Generated strategic chart artifacts
│   └── strategic_analysis_report.md      # Markdown inventory of generated analytics outputs
├── src
│   ├── analysis                          # Pandas/Matplotlib analytics and reporting layer
│   │   ├── core                          # Read-only DB loading, dataset preparation, plotting engine, report writer
│   │   └── plotters                      # Five strategic chart generators
│   ├── core                              # Configuration, exceptions, logger, and shared definitions
│   ├── engine                            # Browser lifecycle and batch queue orchestration
│   ├── models                            # Product DTOs and database row conversion logic
│   ├── services                          # Search, detail scraping, seller extraction, marketplace resolution, DB access
│   ├── tasks                             # Operational helpers for browser profile creation and target seeding
│   └── utils                             # Text, price, and timing helper functions
├── tests
│   ├── fixtures                          # Local HTML fixtures for selector and product identity contract tests
│   ├── integration                       # Browser-facing tests that may need external runtime support
│   ├── unit                              # Unit coverage for scraper, queue, DB, analytics, DTO, and task helpers
│   └── conftest.py                       # Shared pytest fixtures for mocks, config stubs, and DTO instances
├── .vscode
│   ├── extensions.json                   # Recommended VS Code extensions for Python, Pylance, Ruff, and EditorConfig
│   └── settings.json                     # Workspace interpreter, Pylance paths, and pytest defaults
├── .editorconfig                         # Editor defaults for indentation, charset, whitespace, and line endings
├── .gitattributes                        # Cross-platform line-ending rules for launch scripts
├── .gitignore                            # Git exclusions for runtime artifacts and generated caches
├── .pre-commit-config.yaml               # Local quality hooks for lint, format, and config syntax checks
├── LICENSE                               # MIT license terms
├── Makefile                              # Repeatable developer and CI command shortcuts
├── pyproject.toml                        # Project metadata, build config, and dependency source of truth
├── pyrightconfig.json                    # Pylance/Pyright import resolution and type analysis settings
├── README.md                             # Project documentation
├── product_codes.txt                     # Seed list of target product codes
├── start.bat                             # Windows launcher for environment setup and scraper execution
└── start.sh                              # Linux/macOS launcher for environment setup and scraper execution
```

</details>

<details>
<summary><b>Click to expand technology stack details</b></summary>

| Component | Technology | Purpose |
|:---|:---|:---|
| **Data Extraction** | SeleniumBase & Selenium | Browser automation, DOM traversal, search execution, and dynamic page interaction |
| **Core Architecture** | Python 3.11+ | Pipeline orchestration, service boundaries, DTO modeling, and queue processing |
| **Data Processing** | Pandas & NumPy | Snapshot filtering, product-level metric aggregation, price-tier assignment, and analytical transforms |
| **Visualizations** | Matplotlib & Seaborn | Deterministic strategic chart generation |
| **Persistence** | SQLite3 | Local relational warehouse for `products` snapshots and `target_products` queue state |
| **Configuration** | PyYAML | Declarative selectors, browser configuration, search behavior, retry policy, and marketplace aliases |
| **Testing & Coverage** | Pytest, pytest-cov & coverage.py | Unit regression tests, branch coverage measurement, XML coverage output, and an 80% coverage gate |
| **Developer Experience** | VS Code workspace settings, Pylance/Pyright & EditorConfig | Stable interpreter discovery, source-path analysis, editor defaults, and recommended extensions |
| **Code Quality** | Ruff & pre-commit | Python linting/formatting, TOML/YAML/JSON syntax validation, and EditorConfig syntax validation before commits |
| **Automation & CI** | GNU Make, GitHub Actions & Codecov | Repeatable local/CI command targets, Python version matrix validation, and coverage report upload |

</details>

## Table of Contents
- [Quantitative Data Analysis & Market Intelligence Report](#quantitative-data-analysis--market-intelligence-report)
- [Executive Conclusion & Business Impact](#executive-conclusion--business-impact)
- [Dependencies](#dependencies)
- [Quickstart](#quickstart)
- [Configuration](#configuration)
- [Limitations & Disclaimers](#limitations--disclaimers)
- [License](#license)

## Quantitative Data Analysis & Market Intelligence Report

The analytics suite produces five focused charts from the latest verified dataset stored in `database/scraper.db`. The report prioritizes decision-oriented visuals over chart quantity, focusing on marketplace competitiveness, price dispersion, outlier risk, seller-depth resilience, and portfolio composition. Rows whose resolved page does not expose the requested product code are excluded from analytical outputs.

<table width="100%">
  <tr align="center">
    <td>
      <img src="./reports/charts/01_marketplace_lowest_price_win_rate.png?v=20260509-2109" width="100%" alt="Marketplace Lowest-Price Win Rate">
    </td>
  </tr>
</table>

> **Analyst Insight:** This heatmap reports category-level lowest-price win credit for the top marketplaces by verified offer volume. Tied lowest prices split win credit evenly, and percentages use all verified products in the category as the denominator. A 0.0 value does not automatically indicate a data or algorithm error; it can mean the marketplace had no verified offer in that category or had offers that never became the lowest visible price. With the current seed list, conclusions should be interpreted across Mouse and Headset targets only.

<table width="100%">
  <tr align="center">
    <td>
      <img src="./reports/charts/02_price_spread_market_depth.png?v=20260509-2109" width="100%" alt="Price Spread vs. Market Depth">
    </td>
  </tr>
</table>

> **Analyst Insight:** Each point represents one verified product snapshot. The x-axis shows offer depth, the y-axis shows percentage spread between maximum and minimum visible prices, and bubble size reflects average price. The latest snapshot shows a high-spread market, with median product spread around 100% and the maximum spread above 450%. Products in the upper-right area deserve priority review because broad offer availability has not compressed prices, suggesting fragmented pricing, premium reseller behavior, stock scarcity, or residual variant ambiguity.

<table width="100%">
  <tr align="center">
    <td>
      <img src="./reports/charts/03_category_price_outlier_risk.png?v=20260509-2109" width="100%" alt="Category Price Distribution and Outlier Risk">
    </td>
  </tr>
</table>

> **Analyst Insight:** Category-level boxplots summarize verified visible price distributions while red points mark upper-tail outliers using Tukey's IQR rule. These outliers are not automatically wrong, but they are important candidates for manual review. With the current target universe, category comparisons should focus on Mouse and Headset price distributions. Likely explanations for upper-tail points include low-stock pricing, premium resellers, bundle or layout variants, and stale listings.

<table width="100%">
  <tr align="center">
    <td>
      <img src="./reports/charts/04_seller_depth_risk_profile.png?v=20260509-2109" width="100%" alt="Seller Depth Risk Profile">
    </td>
  </tr>
</table>

> **Analyst Insight:** Seller depth is calculated as the number of unique active marketplaces per product, not the number of individual merchants. The latest profile skews toward medium-to-high marketplace coverage: 31 of 50 products have 10+ active marketplaces, while only 3 products sit in the 1-3 marketplace band. Low-depth products remain the clearest availability and data-quality risk; high-depth products are better candidates for competitive pricing analysis because the observed price floor is supported by broader market coverage.

<table width="100%">
  <tr align="center">
    <td>
      <img src="./reports/charts/05_portfolio_price_tier_mix.png?v=20260509-2109" width="100%" alt="Portfolio Mix by Category and Price Tier">
    </td>
  </tr>
</table>

> **Analyst Insight:** The portfolio chart segments verified products by category and minimum visible price tier. With the default configured thresholds, Entry-Level products are below 3000 TRY, Mid-Range products are between 3000 and 8000 TRY, and Premium products are above 8000 TRY. The active seed list is intentionally balanced between Mouse and Headset targets, so regenerated analytics should be interpreted as a two-category portfolio unless additional product families are added later.

## Executive Conclusion & Business Impact

- **Marketplace Price Leadership:** Identifies which marketplaces most frequently match the lowest visible price by category, while making zero-win cells and small-category denominators explicit.
- **Pricing Volatility Detection:** Surfaces products with unusually wide price spreads or upper-tail outliers, supporting targeted review of unstable listings, premium reseller behavior, low-stock pricing, and residual variant risk.
- **Seller-Depth Risk Assessment:** Measures marketplace availability per product to distinguish resilient multi-marketplace items from thinly supplied products with higher availability and data-quality exposure.
- **Portfolio Price-Tier Composition:** Segments the product universe into entry-level, mid-range, and premium tiers so marketplace conclusions can be interpreted against the dataset's actual category and pricing structure.
- **Data Quality Governance:** Enforces minimum persistence standards by excluding empty price or marketplace records, normalizing marketplace names, preventing sub-seller leakage, deduplicating indistinguishable offer rows, rejecting unverified fallback matches by default, and preserving row-level source/run metadata.

## Dependencies

To ensure reproducibility and isolate dependencies, it is recommended to use a virtual environment.

### Step 1 - Create Virtual Environment:

```bash
python -m venv .venv
```

### Step 2 - Activate Virtual Environment:

```bash
# Linux/macOS
source .venv/bin/activate

# Windows
.venv\Scripts\activate
```

### Step 3 - Upgrade pip:

```bash
python -m pip install --upgrade pip
```

### Step 4 - Install Project Dependencies:

Install only the runtime dependencies when you only need to run the pipeline:

```bash
python -m pip install .
```

Install the development extras when you also need tests, linting, coverage, and
pre-commit tooling:

```bash
python -m pip install ".[dev]"
```

*Runtime dependencies: `seleniumbase`, `selenium`, `PyYAML`, `pandas`, `numpy`, `matplotlib`, `seaborn`.*

*Development dependencies: `pytest`, `pytest-cov`, `pre-commit`, `ruff`.*

## Quickstart

### 1. Web Extraction

Initialize the browser profile, seed target products from `product_codes.txt`, and process the queued codes. Validated offer snapshots are persisted into `database/scraper.db`.

The active `product_codes.txt` file is expected to contain exactly 50 unique targets: 25 `RZ01-*` mouse codes and 25 `RZ04-*` headset codes. `RZ03` keyboard targets are no longer part of the default run.

```bash
# Full Linux/macOS setup and scraper run
chmod +x start.sh
./start.sh
```

```bash
# Full Windows setup and scraper run
start.bat
```

```bash
# Manual run after dependency installation
python -m src.tasks.create_profile
python -m src.tasks.seed_targets --file product_codes.txt
python -m src.main
```

### 2. Strategic Analytics Engine

Run the analytics engine after product snapshots are available. It rebuilds the strategic chart portfolio and refreshes `reports/strategic_analysis_report.md` from the latest validated dataset.

```bash
python -m src.analysis.main
```

## Configuration

Runtime behavior is loaded from the YAML files in `config/`. `settings.yaml` keeps common path, database, and observability defaults, while domain-specific files keep browser, scraping, selector, marketplace, and analytics settings outside Python code. The loader deep-merges these files, so application code still reads a single logical configuration tree through `Config.get(...)`.

| Section | Key Parameters | Description |
|:---|:---|:---|
| `urls` | `base`, `search` | Primary marketplace URL and fallback search engine URL |
| `paths` | `database`, `logs_dir`, `reports_dir`, `charts_dir`, `strategic_report_filename` | Local database, log, chart, and markdown report output locations |
| `database` | `connect_timeout_seconds`, `busy_timeout_ms`, `analysis_busy_timeout_ms`, `snapshot_replacement_min_ratio` | SQLite connection behavior and same-day snapshot replacement guardrails |
| `observability` | `selector_usage.*`, `normalization_usage.*` | Runtime telemetry written after scraper/analysis runs so selector matches and category/marketplace alias usage can be reviewed |
| `browser` | `headless`, `page_load_timeout`, `implicit_wait`, `captcha_auto_click`, `reconnect_time`, `user_agent`, `user_data_dir`, `profile_name` | Browser runtime mode, timeout behavior, session persistence, profile reuse, CAPTCHA posture, and recovery timing |
| `scraping` | `default_brand`, `retries`, `search_engine_fallback`, `persist_unverified_fallback`, `google_query_format`, `input_verification_*`, `seller_collection.*`, `marketplace_id_map`, `marketplace_name_aliases` | Retry policy, fallback strategy, query formatting, input validation, seller extraction tuning, marketplace ID mapping, and canonical marketplace normalization |
| `analysis` | `category_aliases`, `price_tiers`, `marketplace_top_n`, `outlier_detection`, `seller_depth_tiers`, `marketplace_display_aliases` | Analytics thresholds, category normalization, seller-depth bands, outlier behavior, top-marketplace scope, and report-only display aliases |
| `charts` | `style.figure_size`, `style.plot_rect`, `style.colors`, `style.category_colors`, `style.tier_colors` | Visual design tokens for deterministic 1920x1080 chart generation and category/tier coloring |
| `delays` | `typing`, `pre_enter`, `post_search`, `page_switch`, `google_switch`, `internal_navigation`, `scroll`, `scroll_motion` | Randomized wait intervals used to make browser automation more stable across dynamic page states |
| `selectors` | `search_input`, `search_result_*`, `search_no_result`, `product.*`, `card.*`, `google.*` | DOM selector groups used for search pages, product pages, seller cards, expandable seller lists, and fallback search results |

After a scraper run, selector telemetry is written to `logs/selector_usage_latest.json`. Each configured selector entry receives a status such as `matched`, `looked_up_never_matched`, `looked_up_not_measured`, or `configured_unused`, making it easier to remove stale selectors or investigate layout drift after the run finishes.

Category and marketplace normalization telemetry is written to `logs/normalization_usage_latest.json`. Each configured alias entry is marked as `used` or `configured_unused`, with raw values and call sites included so stale alias rules can be removed based on observed runtime evidence rather than guesses.

## Limitations & Disclaimers

> **Important:** This section is critical for understanding the operational, analytical, and compliance boundaries of the reported marketplace metrics.

### Responsible Automation and Access Boundaries

- **Educational and portfolio scope:** This project is designed for academic research, data engineering practice, and portfolio demonstration. It should be used responsibly and in accordance with applicable website policies, Terms of Service, and local regulations.
- **No access-control bypassing:** CAPTCHA auto-clicking is disabled by default and should not be treated as a mechanism for bypassing anti-bot controls, authentication barriers, rate limits, or other access restrictions.
- **Browser session sensitivity:** The persistent browser profile under `.browser_profile` can contain cookies, preferences, or session state. Treat it as local-only runtime data and do not commit, publish, or share it.
- **Execution reliability:** Automated browser workflows may encounter CAPTCHAs, temporary blocks, rate limits, expired sessions, layout experiments, or network instability. Randomized delays and profile reuse can improve stability, but they do not guarantee uninterrupted scraping.

### Data Scope and Snapshot Interpretation

- **Point-in-time observations:** Prices, sellers, marketplace availability, and product-page signals are captured as historical snapshots. They should not be interpreted as live market truth after the run has completed.
- **Current seed coverage:** The active seed list contains Razer mouse and headset targets only. Reported category-level conclusions should not be generalized to keyboards, other brands, or the broader consumer electronics market without expanding the target universe.
- **Versioned sample artifacts:** `database/scraper.db`, `reports/strategic_analysis_report.md`, and `reports/charts/*.png` are versioned sample artifacts for reproducible portfolio review. Regenerate them deliberately and review data-quality metrics before using them as current market evidence.
- **Incomplete market visibility:** The pipeline stores only visible offers with valid marketplace and positive price values. Listings can still be missed because of dynamic rendering, regional availability, failed retries, page instability, hidden seller data, or missing visible price signals.

### Product Matching and Extraction Limitations

- **SKU validation dependency:** Fallback search can occasionally resolve a close variant instead of the exact requested product when the target SKU is not visible on the page. These cases are rejected by default and logged as unverified matches.
- **Selector and layout dependency:** The scraper depends on the current page structure and configured DOM selectors. Website layout changes, lazy-loading behavior, class-name changes, or selector drift may require updates in `config/selectors.yaml` or the extraction logic.
- **Seller identity normalization:** Seller depth is measured as unique active marketplaces per product, not every individual merchant behind a marketplace listing. This keeps analytics stable, but it can hide sub-seller-level variation.
- **Price signal quality:** Upper-tail prices, wide spreads, and outliers are analytical review candidates, not automatic evidence of incorrect scraping. They may reflect low stock, premium resellers, bundles, stale listings, variant ambiguity, or real market fragmentation.

### Intended Use

- **Decision-support use case:** The project is intended to support pricing intelligence exploration, data-quality review, and marketplace analytics workflows, not automated commercial decision-making without human validation.
- **Manual review requirement:** High-impact conclusions should be reviewed against fresh runs, source pages, and telemetry outputs such as selector and normalization usage reports.
- **Configuration responsibility:** Users who change target categories, marketplaces, selectors, or persistence rules should rerun the test suite and inspect the generated reports before relying on the resulting metrics.

## License

This project is licensed under the **MIT License** - see the [LICENSE](./LICENSE) file for full terms.

Copyright (c) 2026 **Mustafa Berat Yavaş**
