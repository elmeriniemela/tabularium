# CLAUDE.md - Investment Portfolio Odoo Module

## Project Overview

This is an **Odoo addon module** for comprehensive investment portfolio management. It enables tracking, analyzing, and forecasting investment positions across multiple asset classes including stocks, cryptocurrencies, bonds, and other financial instruments.

**Current Odoo Version**: 18.0 (working branch), with version 16.0 as main branch

## Environment Setup

Before running any Odoo commands, activate the virtual environment:

```bash
source activate odoo18 own.conf
```

### Running Tests

Run tests using the Odoo CLI with the `--test-enable` flag:

```bash
# Run all tests for this module
odoo --test-enable -i investment_portfolio --stop-after-init -d eniemela_18
```

### Upgrade the module

```bash
odoo --upgrade investment_portfolio --stop-after-init -d eniemela_18
```

