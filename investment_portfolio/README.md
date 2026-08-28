# Investment Portfolio

A comprehensive investment portfolio management module for Odoo that enables tracking, analyzing, and forecasting investment positions across multiple asset classes.

## Overview

This module provides a complete solution for managing investment portfolios with support for stocks, cryptocurrencies, bonds, and other financial instruments. It tracks transactions, calculates performance metrics, integrates with external price data sources, and provides detailed analytics for informed decision-making.

## Key Features

### Portfolio Management
- **Multiple Portfolios**: Organize positions across different portfolios
- **Asset Categories**: Categorize investments (stocks, crypto, bonds, real estate, etc.)
- **Position Tracking**: Monitor current holdings with real-time valuations
- **Multi-Currency Support**: Handle investments in different currencies with automatic conversion

### Transaction Management
- **Transaction Types**:
  - Buy/Sell transactions
  - Stock splits
  - Dividend yields
  - Holding costs
  - Fees tracking
- **Automated FIFO Accounting**: Calculate realized gains/losses using First-In-First-Out method
- **Transaction Moves**: Group related transactions together
- **Notes and Tags**: Organize positions with custom tags and investment thesis documentation

### Price Tracking & Integration
- **Historical Price Data**: Store and manage price history for all assets
- **API Integration**: Automatic price updates via configurable API endpoints
- **Exchange Management**: Track exchange hours and only update during trading hours
- **Price Interpolation**: Automatically interpolate missing price data
- **Price Predictions**: Generate future price predictions based on expected appreciation rates
- **All-Time High Tracking**: Monitor ATH prices and current drawdowns

### Performance Analytics

#### Time-Based Returns
Track performance across multiple timeframes:
- Daily (1 day)
- Weekly (1 week)
- Monthly (1 month)
- Quarterly (3 months)
- Semi-annually (6 months)
- Year-to-date (YTD)
- Annual (1, 3, 5, 10 years)

#### Key Metrics
- **Profit/Loss**: Absolute and percentage gains
- **Cost Basis**: Average purchase price calculation
- **Realized vs Unrealized**: Separate tracking of realized and unrealized gains
- **Drawdown Analysis**: Calculate plausible drawdown scenarios
- **IRR Calculation**: Money-weighted rate of return (Internal Rate of Return)

### Time Series Analysis
- **Daily Historical Data**: Automatically generate daily snapshots of portfolio values
- **Future Projections**: Create forecasts based on expected returns
- **Period Analysis**: Compare performance across custom time periods
- **Position-by-Position**: Track individual asset performance over time

### Investment Planning
- **Acquisition Plans**: Model systematic investment strategies (e.g., dollar-cost averaging)
- **Exit Strategies**: Plan systematic exits with interest calculations
- **Cash Flow Modeling**: Project future yields and costs
- **Scenario Analysis**: Test different appreciation and interest rate scenarios

### Milestones & Goals
- Track investment milestones and targets
- Monitor progress toward financial goals

### Reporting & Visualization
- **Dashboard View**: Custom dashboard for portfolio overview
- **Detailed Reports**: Comprehensive position and transaction reports
- **Performance Charts**: Visualize price movements and returns
- **Export Capabilities**: Export data for external analysis

## Data Models

### Core Models

#### investment.portfolio
Top-level container for organizing positions.

#### investment.asset
Represents a tradable asset (stock, crypto, etc.) with:
- Ticker symbol
- Category
- Currency
- Price history
- API integration settings
- Expected appreciation rates
- ATH tracking

#### investment.position
A holding of a specific asset within a portfolio:
- Quantity held
- Current value
- Cost basis
- Profit/loss metrics
- Transaction history
- Investment thesis

#### investment.position.transaction
Individual buy/sell/yield/cost transactions:
- Quantity
- Price
- Fee
- Exchange rate
- Currency conversion
- Automatic type detection

#### investment.asset.price
Historical price data points:
- Timestamp
- Price
- Prediction flag
- Interpolation flag
- Price adjustments for splits

#### investment.asset.realized
FIFO-based realized gain/loss tracking:
- Links buy and sell transactions
- Calculates actual profit/loss per trade
- Includes fee impact

#### investment.timeseries
Daily snapshots of position values:
- Date
- Position value
- Quantity held
- Profit/loss at that point
- Used for historical analysis

#### investment.period
Performance analysis for custom time periods:
- Start/end dates
- Position filtering domain
- IRR calculation
- Transaction summary
- Profit/loss analysis

### Supporting Models

- **investment.category**: Asset classification
- **investment.exchange**: Trading venue with operating hours
- **investment.exchange.gap**: Special non-trading periods
- **investment.position.tag**: Position categorization
- **investment.position.note**: Investment thesis and notes
- **investment.position.move**: Transaction grouping
- **investment.asset.split**: Stock split history
- **investment.milestone**: Goal tracking

## Installation

### Dependencies
This module requires:
- `mail` - Odoo's messaging and activity tracking
- `timeago_widget` - Time formatting widget
- `api_endpoint` - API integration framework
- `version_control` - Version tracking

### Installation Steps
1. Place the module in your Odoo addons directory
2. Update the app list: Settings → Apps → Update Apps List
3. Search for "Investment Portfolio"
4. Click Install

## Configuration

### Initial Setup
1. Create investment categories (Settings → Investment → Categories)
2. Set up portfolios (Investment → Portfolios)
3. Configure API endpoints for automatic price updates (if needed)
4. Set up exchanges with trading hours (if applicable)

### Security Groups
Two security groups are available:
- **Investment User**: Full access to positions, transactions, and analytics
- **Investment Admin**: Additional rights to configure categories, portfolios, and system settings

### Scheduled Actions
The module includes automated cron jobs:
- **Create Investment Time Series**: Runs hourly to generate/update time series data
- **Update Daily Price Links**: Runs daily at midnight to update price reference fields

### API Integration
Configure API endpoints for automatic price updates:
1. Create an API endpoint record
2. Link it to assets
3. Configure the endpoint's integration logic
4. Prices will be fetched automatically

### System Parameters
- `investment_portfolio.predict_years`: Number of years to forecast (default: 25)

## Usage

### Basic Workflow

#### 1. Create Assets
Navigate to Investment → Assets and create records for each tradable asset:
- Enter ticker symbol
- Select category
- Choose currency
- Optionally configure API integration

#### 2. Create Positions
Go to Investment → Positions:
- Select portfolio
- Choose asset
- Enter position name
- Add investment thesis (optional)

#### 3. Record Transactions
Add transactions to positions:
- Enter quantity bought/sold
- Specify price
- Record any fees
- System automatically calculates cash flow

#### 4. Track Performance
View metrics on the position form:
- Current value
- Profit/loss (absolute and percentage)
- Performance across different timeframes
- Realized vs unrealized gains

#### 5. Analyze Periods
Create period records to analyze performance:
- Set date range
- Define position filter
- View IRR and profit metrics
- Compare different time periods

### Advanced Features

#### Investment Planning
Use the planning tab on positions to:
- Model systematic investments (DCA)
- Plan exit strategies
- Project future cash flows
- Test different scenarios

#### Price Predictions
The system can generate price predictions:
- Based on expected yearly appreciation
- Creates daily predictions for configured years
- Useful for long-term planning

#### Realized Gains
FIFO-based calculation automatically:
- Matches sells with oldest buys
- Calculates actual profit/loss
- Tracks cost basis
- Handles partial sales

#### Time Series
Automatic generation of historical data:
- Daily snapshots of portfolio value
- Tracks quantity and profit over time
- Enables historical comparison
- Powers period analysis

### Calculations

#### Cost Basis
Weighted average of purchase prices, adjusted for:
- Stock splits
- Currency conversions
- Fees

#### Profit Percentage
```
profit_percent = profit / max_investment
```
Where `max_investment` is the highest invested amount (handles partial sales).

#### IRR (Internal Rate of Return)
Calculates money-weighted returns from dated cash flows considering:
- Investment timing
- Cash flows (buys, sells, yields, costs)
- Current position value

#### Drawdown Price
```
drawdown_price = (1 - plausible_ath_drawdown) * ath_price
```

## Demo Data

The module includes demo data with:
- Sample categories (Stocks, Crypto, Bonds, etc.)
- Example portfolios
- Sample assets
- Historical price data
- Transaction examples


### Custom Categories
Create categories for any asset type:
- Mark as "liquid" for inclusion in performance periods
- Organize by asset class, risk level, or strategy

## Troubleshooting

### Common Issues

**Prices not updating automatically**
- Check API endpoint configuration
- Verify exchange hours (if configured)
- Check cron job execution
- Review endpoint integration logs

**Missing time series data**
- Run "Create Investment Time Series" cron manually
- Ensure assets have price data
- Check for transactions before first price

**Incorrect profit calculations**
- Verify all transactions have correct exchange rates
- Check currency conversion rates
- Ensure no duplicate transactions
- Recompute position values
