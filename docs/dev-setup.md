# Development Setup

## Local bench

The app is developed and tested inside a standard Frappe bench.

### 1. Install bench and Frappe

```bash
# Ubuntu/Debian dependencies (run on the host or in a VM/WSL container)
sudo apt update
sudo apt install python3.11-dev python3.11-venv python3.12-dev python3.12-venv build-essential mariadb-client libmariadb-dev redis-server nodejs yarn wkhtmltopdf

# Create bench
bench init --frappe-branch version-16 --python python3.14 frappe-bench
# or for v15
bench init --frappe-branch version-15 --python python3.11 frappe-bench
```

### 2. Add the app

```bash
cd frappe-bench
bench get-app reversible_import /path/to/reversible_import
```

### 3. Create a site

```bash
bench new-site test_site --mariadb-root-password root --admin-password admin
bench --site test_site install-app reversible_import
```

### 4. Run tests

```bash
bench --site test_site run-tests --app reversible_import
```

Or with pytest directly inside the bench env:

```bash
bench --site test_site python -m pytest reversible_import/reversible_import/tests
```

## CI

CI uses the same `bench init` workflow. See `.github/workflows/ci.yml`. The matrix covers Frappe `version-15` on Python 3.11 and `version-16` on Python 3.12. The `develop` branch is not tested in CI because its current Python requirement is not available on standard GitHub Actions runners.
