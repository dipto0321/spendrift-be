# Example Project README

This is a complete, working example of a FastAPI application using the `fastapi-scaffold-with-auth` template.

## Quick Start

### 1. Install Dependencies

```bash
pip install -e ".[postgres]"
```

### 2. Setup Environment

Copy `.env.example` to `.env`:

```bash
cp ../.env.example .env
```

Edit `.env` with your settings:

```env
SECRET_KEY=your-secret-key-here-must-be-32-chars-minimum
DATABASE_URL=sqlite:///./app.db
DEBUG=False
```

### 3. Initialize Database

```bash
alembic upgrade head
```

### 4. Run the Application

```bash
fastapi dev app/main.py
```

Server will start at `http://localhost:8000`

## API Endpoints

Visit `http://localhost:8000/docs` for interactive API documentation.

### Authentication

```bash
# Register
curl -X POST "http://localhost:8000/api/v1/auth/register" \
  -H "Content-Type: application/json" \
  -d '{"email":"user@example.com","password":"securepass123"}'

# Login
curl -X POST "http://localhost:8000/api/v1/auth/login" \
  -H "Content-Type: application/json" \
  -d '{"email":"user@example.com","password":"securepass123"}'
```

### Get Current User

```bash
curl -H "Authorization: Bearer YOUR_ACCESS_TOKEN" \
  "http://localhost:8000/api/v1/users/me"
```

## Development

```bash
# Run tests
pytest

# Format code
make format

# Check types
mypy app modules

# Create migration
alembic revision --autogenerate -m "Your migration message"
```

## Project Structure

```
example_project/
├── app/
│   ├── main.py           # FastAPI app instance
│   ├── api/
│   │   └── v1/          # API routes
│   └── core/            # Config, DB, security
├── modules/
│   ├── auth/            # Authentication
│   └── users/           # User management
├── alembic/             # Database migrations
├── pyproject.toml
└── Makefile
```

## Logs

The application logs in JSON format to stdout by default. To change:

```env
LOG_FORMAT=text  # Switch to plain text
LOG_LEVEL=DEBUG  # Set log level
```

## Next Steps

1. **Add new endpoints** in `modules/*/router.py`
2. **Add models** in `modules/*/model.py`
3. **Create migrations** with `alembic revision --autogenerate`
4. **Write tests** in `../tests/`
5. **Deploy** to your cloud platform

See [CONTRIBUTING](../CONTRIBUTING.md) for more info.
