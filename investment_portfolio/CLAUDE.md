# CLAUDE.md - Investment Portfolio Odoo Module

## Project Overview

This is an **Odoo addon module** for comprehensive investment portfolio management. It enables tracking, analyzing, and forecasting investment positions across multiple asset classes including stocks, cryptocurrencies, bonds, and other financial instruments.

**Current Odoo Version**: 18.0 (working branch), with version 16.0 as main branch

## Environment Setup

Before running any Odoo commands, activate the virtual environment:

```bash
activate odoo18 own.conf
```

## Technology Stack

- **Framework**: Odoo 18.0
- **Language**: Python 3.x
- **ORM**: Odoo ORM
- **UI**: Odoo views (XML-based: form, tree, kanban, graph, pivot)
- **Frontend**: Odoo web client with custom JavaScript components
- **Key Libraries**:
  - `pyxirr` - IRR (Internal Rate of Return) calculations
  - Odoo dependencies: `mail`, `timeago_widget`, `api_endpoint`, `version_control`

## File Structure

```
investment_portfolio/
├── __init__.py                 # Module initialization
├── __manifest__.py             # Module metadata, dependencies, data files
├── models/                     # Python business logic
│   ├── __init__.py
│   ├── investment_asset.py               # Tradable assets (stocks, crypto, etc.)
│   ├── investment_asset_price.py         # Historical price data
│   ├── investment_asset_realized.py      # FIFO-based realized gains
│   ├── investment_asset_split.py         # Stock split tracking
│   ├── investment_category.py            # Asset categorization
│   ├── investment_exchange.py            # Trading venues
│   ├── investment_exchange_gap.py        # Non-trading periods
│   ├── investment_milestone.py           # Goal tracking
│   ├── investment_period.py              # Performance analysis periods
│   ├── investment_portfolio.py           # Portfolio container
│   ├── investment_position.py            # Core position model
│   ├── investment_position_move.py       # Transaction grouping
│   ├── investment_position_note.py       # Investment thesis
│   ├── investment_position_tag.py        # Position categorization
│   ├── investment_position_transaction.py # Buy/sell/yield/cost records
│   ├── investment_timeseries.py          # Daily snapshots
│   ├── res_company.py                    # Company extensions
│   ├── res_currency.py                   # Currency extensions
│   └── acquire_lock.py                   # Locking mechanism
├── views/                      # XML view definitions
│   ├── menuitems.xml
│   ├── investment_*.xml        # One view file per model
│   ├── res_company.xml
│   └── res_currency.xml
├── data/                       # System data
│   ├── ir_cron_data.xml        # Scheduled actions
│   ├── endpoints.xml           # API configurations
│   ├── decimal.xml             # Decimal precision
│   ├── export.xml
│   └── users.xml
├── demo/                       # Demo/test data
│   ├── categories.xml
│   ├── assets.xml
│   └── portfolios.xml
├── security/
│   ├── security.xml            # Groups and access rules
│   └── ir.model.access.csv     # Model access rights
├── static/src/                 # Frontend assets
│   ├── dashboard/              # Custom dashboard component
│   └── list/                   # Custom list view controller
└── migrations/                 # Version migration scripts
    └── [version]/
        ├── pre-migrate.py
        └── post-migrate.py
```

## Core Data Models

### Model Relationships

```
investment.portfolio (1) ──< (N) investment.position
investment.position (N) ──> (1) investment.asset
investment.position (1) ──< (N) investment.position.transaction
investment.asset (1) ──< (N) investment.asset.price
investment.position.transaction (N) ──< (N) investment.asset.realized
investment.position (1) ──< (N) investment.timeseries
investment.asset (N) ──> (1) investment.category
investment.asset (N) ──> (1) investment.exchange
```

### Key Models

1. **investment.position** - Central model representing a holding
   - Links asset to portfolio
   - Tracks quantity, cost basis, profit/loss
   - Contains all performance metrics
   - Has transactions, notes, tags

2. **investment.asset** - Tradable instrument definition
   - Ticker symbol, category, currency
   - Price history via `investment.asset.price`
   - API integration for automatic updates
   - Expected appreciation rates

3. **investment.position.transaction** - Individual transactions
   - Types: buy, sell, dividend_yield, holding_cost
   - Automatic type detection based on quantity sign
   - Multi-currency with exchange rates
   - Fee tracking

4. **investment.asset.realized** - FIFO realized gains
   - Links buy transactions with sell transactions
   - Calculates actual profit/loss
   - Handles partial sales

5. **investment.timeseries** - Daily snapshots
   - Historical position values
   - Powers period analysis and charts

6. **investment.period** - Performance analysis
   - Custom date ranges
   - IRR calculations
   - Position filtering via domain

## Odoo Development Conventions

### Model Definition Pattern

```python
from odoo import models, fields, api
from odoo.exceptions import ValidationError

class InvestmentExample(models.Model):
    _name = 'investment.example'
    _description = 'Example Model'
    _inherit = ['mail.thread', 'mail.activity.mixin']  # Common inheritance
    _order = 'sequence, id'

    # Fields
    name = fields.Char(required=True, tracking=True)
    active = fields.Boolean(default=True)

    # Computed fields
    value = fields.Float(compute='_compute_value', store=True)

    @api.depends('dependency_field')
    def _compute_value(self):
        for record in self:
            record.value = record.dependency_field * 2

    # Constraints
    @api.constrains('field_name')
    def _check_field_name(self):
        for record in self:
            if record.field_name < 0:
                raise ValidationError("Field must be positive")
```

### Important Odoo Patterns in This Module

1. **Computed Fields with Store**:
   - Most metrics (profit, value, etc.) are computed and stored
   - Use `@api.depends()` to declare dependencies
   - Recomputation happens automatically on dependency changes

2. **Multi-currency Handling**:
   - Use `currency_id` field and monetary fields
   - Always specify `currency_field='currency_id'` for monetary fields
   - Exchange rate conversion via `res.currency._convert()`

3. **Search/Domain Patterns**:
   - Use domain syntax: `[('field', 'operator', value)]`
   - Dot notation for related fields: `[('position_id.portfolio_id', '=', portfolio.id)]`

4. **SQL Access**:
   - Direct SQL used for performance-critical operations
   - Always use `self.env.cr.execute()` with parameters
   - Prefer ORM unless performance requires SQL

5. **CRON Jobs**:
   - Defined in `data/ir_cron_data.xml`
   - Methods called must be on models
   - Use `@api.model` decorator for cron methods

### View Definitions

Views are XML-based in Odoo:

```xml
<record id="view_investment_position_form" model="ir.ui.view">
    <field name="name">investment.position.form</field>
    <field name="model">investment.position</field>
    <field name="arch" type="xml">
        <form string="Position">
            <header>
                <button name="action_recompute" type="object" string="Recompute"/>
            </header>
            <sheet>
                <group>
                    <field name="name"/>
                    <field name="asset_id"/>
                </group>
                <notebook>
                    <page string="Transactions">
                        <field name="transaction_ids"/>
                    </page>
                </notebook>
            </sheet>
        </form>
    </field>
</record>
```

## Key Business Logic

### Transaction Flow
1. User creates transaction on position
2. Transaction `_compute_type()` determines if buy/sell/yield/cost
3. Transaction triggers position recalculation
4. Position updates quantity, investment, realized gains
5. FIFO matching in `investment.asset.realized` for sells
6. Time series updated via cron

### Price Updates
1. API endpoints configured per asset
2. Scheduled actions or manual triggers
3. Price stored in `investment.asset.price`
4. Position values recomputed automatically
5. Interpolation fills gaps
6. Predictions generated based on expected appreciation

### Performance Calculations
- **Cost Basis**: Weighted average of purchases (split-adjusted)
- **Profit %**: `profit / max_investment`
- **IRR**: Using `pyxirr.xirr()` on cash flows
- **Timeframe Returns**: Compare current value vs historical time series

## Common Tasks

### Adding a New Field to Position
1. Add field to `models/investment_position.py`
2. Add to view in `views/investment_position.xml`
3. If computed, add `@api.depends()` decorator
4. Update security if needed
5. Create migration if data transformation needed

### Creating a New Model
1. Create Python file in `models/`
2. Import in `models/__init__.py`
3. Create view XML in `views/`
4. Add to `__manifest__.py` data section
5. Create security records in `security/ir.model.access.csv`
6. Add menu item if needed

### Adding API Integration
1. Create or extend endpoint in `data/endpoints.xml`
2. Link asset to endpoint via `api_endpoint_id`
3. Implement fetching logic in asset model
4. Test with manual price update

## Migration System

Located in `migrations/[version]/`:
- **pre-migrate.py**: Runs before module upgrade
- **post-migrate.py**: Runs after module upgrade

Common migration tasks:
- Data transformations
- Field renames
- Model structure changes
- Cleanup orphaned records

## Security

Two user groups:
- `group_investment_user`: Regular users (full access)
- `group_investment_admin`: Administrators (configuration access)

Access rules defined in:
- `security/security.xml` - Record rules
- `security/ir.model.access.csv` - Model access rights

## Testing & Debugging

### Running Tests

Run tests using the Odoo CLI with the `--test-enable` flag:

```bash
# Run all tests for this module
odoo --test-enable -i investment_portfolio --stop-after-init -d eniemela_18
```

Key flags:
- `--stop-after-init`: Exit after running tests (don't start the HTTP server)
- `--test-enable`: Enable test execution during module installation/upgrade
- `--test-tags`: Filter which tests to run (use `/module_name` or specific tag)
- `-d <database_name>`: Target database
- `-i investment_portfolio`: Install/upgrade the module

### Manual Testing
- Install module with demo data
- Create test transactions
- Verify calculations manually
- Check cron execution

### Debug Mode
- Enable developer mode in Odoo settings
- View metadata and technical information
- Access Python debugger via `import pdb; pdb.set_trace()`

### Common Debug Points
- Transaction creation/save
- Realized gain computation
- Price updates
- Time series generation
- Period IRR calculation

## Performance Considerations

1. **Computed Fields**: Store important computed fields to avoid recalculation
2. **Batch Operations**: Use recordsets efficiently, avoid loops where possible
3. **SQL Queries**: Direct SQL for heavy aggregations (see `investment.period`)
4. **Price Predictions**: Can generate large datasets, configurable via system parameter
5. **Time Series**: Generated via cron, not real-time

## Important Files to Review

- [models/investment_position.py](models/investment_position.py) - Core position logic
- [models/investment_position_transaction.py](models/investment_position_transaction.py) - Transaction handling
- [models/investment_asset.py](models/investment_asset.py) - Asset and price management
- [models/investment_asset_realized.py](models/investment_asset_realized.py) - FIFO matching logic
- [models/investment_period.py](models/investment_period.py) - IRR and period analysis
- [__manifest__.py](__manifest__.py) - Module dependencies and data loading order

## External Dependencies

Must be installed in Python environment:
```bash
pip install pyxirr  # For IRR calculations
```

## Configuration

### System Parameters
- `investment_portfolio.predict_years`: Forecast horizon (default: 25 years)

### Company Settings
- Extended in `models/res_company.py`
- View in `views/res_company.xml`

## Notes for AI Assistants

1. **Always check dependencies**: Changes to `investment.position` affect many models
2. **Currency handling**: Never assume single currency, always use conversion
3. **FIFO is critical**: Don't break realized gain matching logic
4. **Odoo ORM specifics**:
   - Use `self.env['model.name']` to access other models
   - Recordsets are iterable collections
   - Use `sudo()` carefully for access rights
   - Use `with_context()` for contextual behavior
5. **Migrations**: Major structural changes require migration scripts
6. **Views must match fields**: XML view field names must exactly match Python model fields
7. **Security matters**: Check access rights when adding new models/fields
8. **Cron jobs**: Changes to time-critical computations may need cron adjustments

## Current State (Git Status)

Untracked files suggest recent work on:
- Company settings extension ([models/res_company.py](models/res_company.py))
- Company views ([views/res_company.xml](views/res_company.xml))
- Custom list view component ([static/src/list/](static/src/list/))
- Migration 16.0.2.1.1 ([migrations/16.0.2.1.1/](migrations/16.0.2.1.1/))

Recent commits involve currency rate fetching from asset integration.
