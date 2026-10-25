# Intell-Support

An intelligent knowledge base and support ticket resolution platform. Users raise support tickets;
support agents resolve them through a structured workflow; every ticket is automatically matched
against a knowledge base of PDF/TXT documents using local semantic search (Qdrant + a free local
embedding model), with a PostgreSQL full-text fallback when semantic retrieval is unavailable.

> 🚧 Work in progress. Full setup instructions, architecture overview, API documentation and
> screenshots will be added as the work packages in [docs/PLAN.md](docs/PLAN.md) are completed.

## Stack

FastAPI · PostgreSQL · Qdrant · fastembed (`BAAI/bge-small-en-v1.5`) · React (Vite, JavaScript) ·
Tailwind CSS · pytest · Playwright · Docker Compose

## Quick start (infrastructure only, for now)

```bash
cp .env.example .env        # then edit secrets
docker compose up -d        # starts PostgreSQL and Qdrant
```

## Documentation

- [Implementation plan](docs/PLAN.md)
- [CodeZero development log](docs/CODEZERO_NOTES.md)
