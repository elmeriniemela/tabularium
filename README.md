# Tabularium

The Tabularium was the official records office of ancient Rome and housed the offices of many city officials. This project is for managing my personal records and documents related to investing/finance workflows and other hobbies.

## Module Map

### Finance and investment

- `investment_portfolio`: Full portfolio/position/transaction engine with price history, FIFO realized PnL, dashboard, cron jobs, and external market data endpoints.
- `bitcoin_browser`: Bitcoin block/transaction ingestion and browsing models.
- `bitcoin_treasury`: Wallet/key/address/transaction management on top of `bitcoin_browser`.
- `bitcoin_investment`: Bridge module syncing treasury wallets to investment positions (`auto_install`).
- `cashflow_management`: Cashflow parsing, import, planning, categories, and account-level tracking.
- `account_financials`: Fiscal year financial exports/reports, including ODT template rendering.
- `trade_ideas`: Imports market aggregate datasets and runs strategy analysis jobs.

### Integrations and operations

- `api_endpoint`: Programmable integration framework (HTTP/XML-RPC/JSON-RPC/SFTP), message logging, queueing, cron execution, and inbound route `/api-v1/<location>`.
- `cloud_manager`: Cloud servers/instances/modules/backups/DNS management plus integration endpoints.
- `cloud_manager_website`: Simple website layer for cloud manager flows.
- `toggl_sync`: Toggl time entry sync + export to Odoo tasks/timesheets via XML-RPC.
- `xml_export`: Adds XML as a standard export format in Odoo list/form export flow.
- `document_directory`: Document folder model backed by `ir.attachment`.
- `multi_uninstall`: Wizard for uninstalling multiple modules.
- `version_control`: Field-level text/html change tracking with diff view based on `mail_tracking_value`.

### UX and productivity

- `note`: Notes/todo app (customized module).
- `flight_log`: Flight logbook models (plane, airport, purpose, entries).
- `flight_log_portal`: Portal view and signature/acceptance flow for flight logs.
- `chart_widget`: Adds `chart` view type (lightweight-charts) for backend records.
- `diff_widget`: Backend diff rendering widget.
- `timeago_widget`: Relative time widget for backend views.
- `save_button_mods`: Backend save/cancel button style overrides.
- `muk_web_theme_mods`: Backend style patches for MuK theme.

