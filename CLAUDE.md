# iCond - Reserva Automática iCondomínio

## Projeto
App Python (FastAPI + SQLite) para agendar reservas automaticamente no iCondomínio. Substitui workflows n8n. Usa `httpx` para controle total de cookies na autenticação multi-hop.

## Tech Stack
- **Python 3.13** / **Poetry**
- **FastAPI** + **Jinja2** (server-side rendering)
- **SQLAlchemy async** + **aiosqlite** (SQLite)
- **httpx** (HTTP client)
- **APScheduler** (cron 23:55 São Paulo)
- **pydantic-settings** (.env)

## Estrutura

```
app/
├── main.py             # FastAPI app, lifespan, scheduler init
├── config.py           # pydantic-settings (.env)
├── database.py         # async engine + session
├── models.py           # Resource, Reservation, AttemptLog
├── schemas.py          # Pydantic DTOs
├── routers/
│   └── reservations.py # Web UI + API routes
├── services/
│   ├── icondominio.py  # Core API client (login → auth → reserve)
│   ├── scheduler.py    # APScheduler cron logic
│   └── notifier.py     # WhatsApp via Evolution API
└── templates/          # Jinja2 HTML
```

## Comandos
- `poetry run uvicorn app.main:app --reload` — dev server
- `poetry install --no-root` — instalar dependências

---

# Especialistas

Ao trabalhar neste projeto, aplique as regras do especialista relevante conforme o contexto da tarefa.

## Especialista Backend

### Regras obrigatórias
- Todas as operações de I/O DEVEM ser async (`await`). Nunca bloquear o event loop.
- Usar `httpx.AsyncClient` com cookie jar manual — nunca `requests`.
- Cada endpoint deve ter tratamento de erro explícito. Nunca engolir exceções silenciosamente.
- Logs estruturados com `logging` em todo service. Formato: `logger = logging.getLogger("icond.<módulo>")`.
- Database sessions via `Depends(get_db)` nos routers. Services recebem `db: AsyncSession` como parâmetro.
- Não usar global state mutável. Estado compartilhado vive no DB.
- Respostas HTTP: `RedirectResponse(status_code=303)` após POST (PRG pattern).
- Background tasks via `asyncio.create_task()`, nunca threads.

### API iCondomínio — Regras críticas
- A autenticação tem redirect chain com até 20 hops. DEVE usar `follow_redirects=False` e loop manual coletando `Set-Cookie` em cada hop.
- Hidden fields do endpoint `/Reservas/Condicao` DEVEM ser parseados dinamicamente via regex. Nunca hardcodar valores — o servidor rejeita com redirect para `ReservaCancelada`.
- Warmup obrigatório: GET `/Reservas/Index` + GET `/Reservas/RecursoData/{id}` antes de chamar Condicao.
- Retry loop: máximo 60 tentativas, 1 segundo entre cada. Logar cada tentativa na tabela `attempt_logs`.
- Janela de reserva: 90 dias antecipados. `trigger_date = target_date - 91 dias`. Cron dispara 23:55, espera até 23:59:30 para iniciar loop.

### Padrões de erro
- Falha no login → status `failed`, notifica WhatsApp, não retenta.
- Falha no Condicao (data indisponível) → retenta no loop de 60.
- Falha no Conclusao → retenta no loop de 60.
- Timeout httpx → retenta com backoff no loop.

## Especialista Python

### Regras de código
- Python 3.11+ features: `type | None` ao invés de `Optional`, `match/case` quando aplicável.
- Type hints em todas as assinaturas de função. Retorno explícito (nunca `-> None` implícito em funções que retornam algo).
- Pydantic v2: usar `model_config = {"from_attributes": True}` ao invés de `class Config`.
- SQLAlchemy 2.0 style: `Mapped[type]`, `mapped_column()`, `select()` ao invés de legacy query.
- Imports organizados: stdlib → terceiros → locais. Sem imports circulares.
- Strings: f-strings para interpolação. Aspas duplas padrão.
- Constantes em UPPER_SNAKE_CASE no topo do módulo.
- Nunca usar `from module import *`.
- Datetime: usar `datetime.now()` para local, `datetime.now(tz=...)` para timezone-aware.
- Paths: usar pathlib quando lidar com filesystem. Para URLs, strings são OK.

### Padrões do projeto
- Config via `app.config.settings` (singleton pydantic-settings).
- DB models herdam de `app.models.Base`.
- Schemas Pydantic em `app.schemas` — sufixo `Create`, `Out`, `Update`.
- Services são classes ou funções async em `app/services/`.
- Routers usam `APIRouter()` e são incluídos no `app.main.app`.

## Especialista Arquitetura

### Princípios
- **Simplicidade primeiro**: este é um app de propósito único. Não over-engineer.
- **Monolito pragmático**: tudo em um processo FastAPI. Sem microserviços, sem message queues, sem Redis.
- **SQLite é suficiente**: volume baixo (dezenas de reservas). Sem necessidade de Postgres.
- **Server-side rendering**: Jinja2 templates. Sem SPA, sem React, sem build frontend.
- **Observabilidade via logs + DB**: attempt_logs é o audit trail. WhatsApp é a notificação.

### Decisões arquiteturais fixas
- Scheduler embutido (APScheduler in-process). Não usar Celery, não usar cron externo.
- Um único `httpx.AsyncClient` por execução de reserva. Criar novo client a cada run (evita cookie leak entre runs).
- Seed data hardcoded em `models.py`. Recursos raramente mudam.
- `.env` para credenciais. Sem vault, sem secrets manager.
- Deploy: uvicorn direto ou via Docker simples. Sem Kubernetes.

### Quando escalar (e quando NÃO)
- NÃO adicionar cache (Redis, memcached) — volume não justifica.
- NÃO adicionar API REST separada da UI — a UI É a interface.
- NÃO separar scheduler em processo diferente — APScheduler async é suficiente.
- SIM adicionar novos recursos ao seed se o condomínio criar novos espaços.
- SIM extrair novo service se surgir integração com outro sistema além do iCondomínio.

### Segurança
- Credenciais APENAS no `.env` (gitignored).
- Sem autenticação na UI web (app roda local ou em rede privada).
- HTTPS delegado ao reverse proxy em produção, não ao app.
