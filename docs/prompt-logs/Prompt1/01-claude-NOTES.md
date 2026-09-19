```
backend/
  app/
    main.py            # FastAPI app creation, router registration only
    core/              # config (env-driven), db session/engine, shared deps
    routers/           # HTTP layer
    schemas/           # Pydantic request/response models
    services/          # business logic
    repositories/      # database access (SQLAlchemy queries)
    models/            # SQLAlchemy ORM models
  tests/
frontend/
  app/                 # App Router routes, layouts, pages
  components/
  lib/                 # API client, helpers
```

<Manual Override>Claude suggested this as the structure which is fine, except for repositories which does not seem intuitive to me. So, I remained it to "data-accesses" by hand

