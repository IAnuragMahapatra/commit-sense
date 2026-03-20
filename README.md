# CommitSense

A Git commit quality analyzer. Every push triggers an analysis — code changes and commit message are checked against static rules and an LLM. Results go to a self-hosted dashboard. CommitSense never modifies commits, never writes back to GitHub. Optionally, developers can install a local pre-push hook that rewrites commit messages before the push goes out.

## Architecture Overview

- **CI Analysis**: Triggered via GitHub Actions on every push. Runs git diff, parses AST using tree-sitter (Python, JS, TS, TSX), applies deterministic rules, validates alignment with an LLM (OpenAI or Anthropic), and POSTs the report to the Dashboard.
- **Pre-push Hook**: Optional local hook that runs deterministic checks and uses an LLM to rewrite bad commit messages *before* the push leaves the machine. Prompts to amend the commit.
- **Dashboard**: FastAPI + SQLAlchemy + PostgreSQL backend. React + Vite + shadcn frontend. Receives reports and displays repo histories, commit trends, and rule patterns.
- **Rule Engine**: Evaluates commit diff size, message length, generic subjects, module mentions, missing breaking markers, and changed public function signatures.

## Setup

1. Copy `.env.example` to `.env` and fill in your keys:
   ```bash
   cp .env.example .env
   ```
2. Copy `commitsense.example.yml` to `commitsense.yml`:
   ```bash
   cp commitsense.example.yml commitsense.yml
   ```
3. Install the Python dependencies for the core analyzer:
   ```bash
   pip install -r requirements.txt
   ```
4. Start the dashboard services (PostgreSQL + API):
   ```bash
   docker compose up -d
   ```
5. Start the frontend:
   ```bash
   cd frontend/commitsense-dashboard
   npm install
   npm run dev
   ```

## Usage

### CI Workflow
CommitSense runs automatically on GitHub Actions if `.github/workflows/commitsense.yml` is present. Configure your GitHub repository variables `COMMITSENSE_BASE_URL`, `COMMITSENSE_MODEL`, `COMMITSENSE_PROVIDER_TYPE`, `DASHBOARD_URL`, and secrets `COMMITSENSE_API_KEY`, `DASHBOARD_TOKEN`.

### Pre-push Hook (Optional)
To install the pre-push hook locally and get automated message rewrite suggestions:

**Unix/macOS:**
```bash
./install.sh
```

**Windows:**
```powershell
.\install.ps1
```

Once installed, running `git push` will intercept bad commit messages and prompt you to accept a rewrite before pushing.

### CLI Testing
To test the analysis pipeline locally without the dashboard:
```bash
python -m ci.analyze
```
