# Security policy

JobScout Pro is a beta project. Please do not post credentials, CVs, personal data, or vulnerability details in public issues.

## Report a vulnerability
Use GitHub's **Security → Report a vulnerability** / private vulnerability reporting option for this repository if it is enabled. If that option is unavailable, contact the repository owner privately rather than opening a public issue. Do not include real CVs or live API tokens in the report.

## Secret handling
- Never commit busqueda.yaml, config.yaml, .env, .streamlit/secrets.toml, SQLite databases, PDFs or exported user data.
- Supply tokens and API keys through environment variables or the hosting platform's secret manager.
- If a token may have entered Git history, revoke/rotate it first; deleting the current file alone does not invalidate a leaked credential.
- The security workflow scans the full Git history for known secret patterns and audits declared Python dependencies. A clean scan is not a guarantee that all forms of secrets or all historic exposures have been detected.
