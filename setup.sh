#!/usr/bin/env bash
# ================================================
# Architect-JS Setup Script for Linux/macOS
# ================================================

set -e

BOLD='\033[1m'
GREEN='\033[0;32m'
YELLOW='\033[0;33m'
RED='\033[0;31m'
NC='\033[0m' # No Color

log_ok()   { echo -e " ${GREEN}[OK]${NC}   $1"; }
log_warn() { echo -e " ${YELLOW}[WARN]${NC}  $1"; }
log_err()  { echo -e " ${RED}[ERROR]${NC} $1"; }
log_skip() { echo -e " [SKIP]  $1"; }
log_step() { echo -e "\n ${BOLD}$1${NC}"; }

echo ""
echo " [Architect-JS] Production Setup"
echo " ====================================="

# ---- Check Prerequisites ----
log_step "Checking prerequisites..."

if ! command -v node &>/dev/null; then
    log_err "Node.js is not installed. Install v18+ from https://nodejs.org"
    exit 1
fi
NODE_VER=$(node --version)
log_ok "Node.js $NODE_VER found"

if ! command -v python3 &>/dev/null && ! command -v python &>/dev/null; then
    log_err "Python 3.10+ is required. Install from https://python.org"
    exit 1
fi
PYTHON_CMD=$(command -v python3 || command -v python)
PY_VER=$($PYTHON_CMD --version)
log_ok "$PY_VER found"

# ---- Python venv ----
log_step "Step 1: Python virtual environment..."
if [ ! -d ".venv" ]; then
    $PYTHON_CMD -m venv .venv
    log_ok "Virtual environment created at .venv"
else
    log_skip "Virtual environment already exists"
fi

source .venv/bin/activate

# ---- Python deps ----
log_step "Step 2: Installing Python dependencies..."
pip install --upgrade pip --quiet
pip install -r requirements.txt --quiet
log_ok "Python dependencies installed"

# ---- Node analyzer deps ----
log_step "Step 3: Installing Node.js dependencies (src/analyzer)..."
(cd src/analyzer && npm install --silent)
log_ok "src/analyzer dependencies installed"

# ---- Node pipeline deps ----
log_step "Step 4: Installing Node.js dependencies (packages/ast-pipeline)..."
(cd packages/ast-pipeline && npm install --silent)
log_ok "packages/ast-pipeline dependencies installed"

# ---- Build TypeScript ----
log_step "Step 5: Building TypeScript package..."
(cd packages/ast-pipeline && npm run build) && log_ok "TypeScript package built" || log_warn "TypeScript build had warnings"

# ---- Directory structure ----
log_step "Step 6: Creating required directories..."
mkdir -p data/test_ast data/test_files data/rag_db
mkdir -p datasets/v1_synthetic datasets/v2_mined datasets/v3_hybrid
mkdir -p logs/failures models
log_ok "Directory structure verified"

# ---- Environment config ----
log_step "Step 7: Setting up environment configuration..."
if [ ! -f ".env" ]; then
    cp .env.example .env
    log_ok ".env created from template — please review and edit"
else
    log_skip ".env already exists"
fi

# ---- Done ----
echo ""
echo " ================================================"
echo "  Setup Complete!"
echo " ================================================"
echo ""
echo "  To start the CLI:"
echo "    source .venv/bin/activate"
echo "    python core_engine/main.py"
echo ""
echo "  Quick commands:"
echo "    python core_engine/main.py --help"
echo "    python core_engine/main.py index --path data/"
echo "    python core_engine/main.py query 'useEffect cleanup'"
echo "    node src/analyzer/ast_compressor.js path/to/Component.tsx"
echo ""
