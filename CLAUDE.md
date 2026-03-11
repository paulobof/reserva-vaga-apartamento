# iCond - Reserva Automática iCondomínio

## Projeto
App Python (FastAPI + SQLite) para agendar reservas automaticamente no portal iCondomínio. Substitui workflows n8n. Usa `httpx` com cookie jar manual para controle total da autenticação multi-hop (até 20 redirects).

## Documentação Detalhada
> Ao trabalhar em código, consultar os guias relevantes:
- **[Padrões de Código](docs/code-standards.md)** — Python, FastAPI, segurança, logging, qualidade
- **[Estratégia de Testes](docs/testing-strategy.md)** — pirâmide, unitários, integração, E2E
- **[Princípios de Engenharia](docs/principles.md)** — SOLID, Clean Architecture, DRY/KISS/YAGNI
- **[Convenções Git](docs/git-conventions.md)** — commits, branches, code review, hooks

## Tech Stack
- **Python ^3.11** / **Poetry** (sem virtualenv no Docker)
- **FastAPI** + **Jinja2** (server-side rendering, sem SPA)
- **SQLAlchemy 2.0 async** + **aiosqlite** (SQLite em `data/icond.db`)
- **httpx** (HTTP client async, nunca `requests`)
- **APScheduler 3.x** (cron 23:55 America/Sao_Paulo, in-process)
- **pydantic-settings** (config via `.env`)
- **pytest** + **pytest-asyncio** + **respx** (testes)
- **ruff** (linter + formatter)
- **pre-commit** + **commitizen** (hooks: lint, format, commit-msg, testes)

## Estrutura

```
app/
├── main.py              # FastAPI app, lifespan, scheduler init
├── config.py            # pydantic-settings (.env)
├── database.py          # async engine + session factory
├── models.py            # Resource, Reservation, AttemptLog + seed data
├── schemas.py           # Pydantic DTOs (sufixos: Create, Out, Update)
├── exceptions.py        # Exceções customizadas de domínio
├── logging_config.py    # Logging estruturado (JSON/text), correlation ID
├── middleware.py         # Request logging, timing, correlation ID
├── routers/
│   └── reservations.py  # Web UI + API routes (CRUD reservas)
├── services/
│   ├── icondominio.py   # Core: login → auth → warmup → reserve
│   ├── scheduler.py     # APScheduler cron job logic
│   └── notifier.py      # WhatsApp via Evolution API
└── templates/
    ├── base.html         # Layout base
    ├── index.html        # Lista de reservas
    └── detail.html       # Detalhe/edição de reserva
tests/
├── conftest.py          # Fixtures globais: async client, db, mocks
├── unit/                # Services isolados, sem I/O
├── integration/         # Router → service → DB
└── e2e/                 # Fluxo completo mockado
docs/
├── code-standards.md    # Padrões de código
├── testing-strategy.md  # Estratégia de testes
├── principles.md        # Princípios de engenharia
└── git-conventions.md   # Convenções Git
data/
└── icond.db             # SQLite database (gitignored)
Dockerfile               # Python 3.13-slim, poetry, uvicorn
README.md                # Documentação pública do projeto
```

## Comandos

```bash
# Dev
poetry install --no-root
poetry run uvicorn app.main:app --reload

# Testes
poetry run pytest                        # todos
poetry run pytest tests/unit             # unitários
poetry run pytest tests/integration      # integração
poetry run pytest tests/e2e              # end-to-end
poetry run pytest --cov=app --cov-report=term-missing  # cobertura

# Lint & Format
poetry run ruff check .                  # lint
poetry run ruff check . --fix            # lint com auto-fix
poetry run ruff format .                 # format

# Pre-commit (roda automaticamente no git commit)
poetry run pre-commit install            # instalar hooks (1x após clone)
poetry run pre-commit run --all-files    # rodar manualmente em todos os arquivos

# Docker
docker build -t icond .
docker run -p 8000:8000 --env-file .env icond
```

## Variáveis de Ambiente (.env)

| Variável | Descrição | Default |
|---|---|---|
| `ICOND_LOGIN` | Login do portal iCondomínio | (obrigatório) |
| `ICOND_SENHA` | Senha do portal | (obrigatório) |
| `EVOLUTION_API_KEY` | API key da Evolution API (WhatsApp) | `""` |
| `WHATSAPP_NUMBER` | Número destino das notificações (formato: 5511...) | `5511996293140` |
| `LOG_LEVEL` | Nível de log: DEBUG, INFO, WARNING, ERROR | `INFO` |
| `LOG_FORMAT` | Formato: `text` (dev) ou `json` (produção) | `text` |

## Deploy
- **Dokploy** em `panel.paulobof.com.br`, domínio `reserva.paulobof.com.br`
- **GitHub**: `paulobof/reserva-vaga-apartamento`
- HTTPS via reverse proxy (Dokploy/Traefik), não pelo app

---

# Fluxo de Reserva (Core Business)

## Sequência de chamadas API

1. **Login** → POST `servicoacesso.webware.com.br/Aplicativo/Login/Usuario` (APP=34)
2. **Redireciona** → POST `servicoacesso.webware.com.br/Aplicativo/Redireciona` (NIU + Token no header)
3. **Autentica** → GET `icondominio.com.br/Ativacao/Autentica/{token}` (follow redirects manual, coleta cookies a cada hop)
4. **Warmup** → GET `/Reservas/Index` + GET `/Reservas/RecursoData/{recurso_id}`
5. **Condicao** → GET `/Reservas/Condicao?data=...&recurso=...&periodo=...&unidade=`
6. **Conclusao** → POST `/Reservas/Conclusao?Length=8` (hidden fields do Condicao como form data)

## Regras de timing
- Janela de reserva: **90 dias** antecipados, abre à meia-noite
- `trigger_date = target_date - 91 dias`
- Cron dispara às **23:55**, espera até **23:59:30** para iniciar retry loop
- Retry: máximo **60 tentativas**, 1 segundo entre cada
- Cada tentativa é logada na tabela `attempt_logs`

## Armadilhas conhecidas
- Hidden fields de `/Reservas/Condicao` DEVEM ser parseados dinamicamente (regex). Hardcodar → redirect para `ReservaCancelada`
- Autenticação tem redirect chain de até 20 hops. DEVE usar `follow_redirects=False` com loop manual coletando `Set-Cookie`
- Criar **novo** `httpx.AsyncClient` a cada run (evita cookie leak entre execuções)

---

# Pre-commit & Qualidade

## Hooks configurados (`.pre-commit-config.yaml`)
- **pre-commit-hooks**: trailing whitespace, end-of-file, check-yaml/toml, large files, merge conflicts, debug statements
- **ruff**: lint (`ruff check --fix`) + format (`ruff format`) — substitui black, isort, flake8
- **commitizen**: valida mensagens de commit no formato **Conventional Commits** (`feat:`, `fix:`, `refactor:`, `docs:`, `test:`, `chore:`, etc.)
- **pytest**: roda todos os testes antes de permitir o commit

## Regras obrigatórias
- **SEMPRE rodar `poetry run pre-commit run --all-files` antes de commitar** para garantir que o código passa em todos os checks.
- Após clonar o repo: `poetry install --no-root && poetry run pre-commit install && poetry run pre-commit install --hook-type commit-msg`
- Mensagens de commit DEVEM seguir Conventional Commits: `tipo(escopo): descrição`. Exemplos:
  - `feat: add reservation retry with backoff`
  - `fix(scheduler): correct timezone calculation`
  - `refactor(services): extract auth flow to separate method`
- **NÃO usar `--no-verify`** para pular hooks. Se o hook falhar, corrigir o problema.
- Ruff config em `pyproject.toml` (`[tool.ruff]`): line-length=100, regras de lint selecionadas (E, W, F, I, N, UP, B, SIM, ASYNC, S, T20, RUF).

---

# Arquitetura — Decisões Fixas

## O que este projeto É
- Monolito pragmático: tudo em um processo FastAPI
- SQLite suficiente: volume baixo (dezenas de reservas)
- Server-side rendering: Jinja2, sem JavaScript framework
- Scheduler embutido: APScheduler in-process
- Seed data hardcoded em `models.py` (recursos raramente mudam)

## O que NÃO fazer
- NÃO adicionar cache (Redis, memcached) — volume não justifica
- NÃO separar API REST da UI — a UI É a interface
- NÃO separar scheduler em processo diferente
- NÃO usar Celery, message queues, ou cron externo
- NÃO usar Kubernetes, microserviços, ou secrets manager
- NÃO over-engineer: este é um app de propósito único

## Quando expandir
- Novo recurso no condomínio → adicionar ao seed em `models.py`
- Nova integração externa → extrair novo service em `app/services/`

## Health Check
- Endpoint `GET /health` retornando `{"status": "ok", "version": "x.y.z"}` para monitoramento do Dokploy/reverse proxy.
