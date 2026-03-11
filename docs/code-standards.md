# Padrões de Código

## Python

### Regras obrigatórias
- **Async obrigatório**: toda I/O usa `await`. Nunca bloquear o event loop.
- **Type hints** em todas as assinaturas. `type | None` (não `Optional`).
- **SQLAlchemy 2.0**: `Mapped[type]`, `mapped_column()`, `select()`. Sem legacy query.
- **Pydantic v2**: `model_config = {"from_attributes": True}`. Sem `class Config`.
- **f-strings** com aspas duplas. Constantes em `UPPER_SNAKE_CASE`.
- **Imports**: stdlib → terceiros → locais. Sem `import *`, sem circulares.
- **Datetime**: `datetime.now()` local, `datetime.now(tz=...)` timezone-aware.
- **Bibliotecas atualizadas**: sempre usar versões mais recentes estáveis. Ao adicionar dependência, verificar última versão no PyPI. Ao encontrar código usando API deprecated, atualizar para a API atual.

### Early Return (obrigatório)
Sempre validar a negação/erro primeiro e retornar cedo. O "caminho feliz" fica no nível principal, sem indentação desnecessária.

```python
# CERTO — early return com negação primeiro
async def get_reservation(db: AsyncSession, reservation_id: int) -> Reservation:
    """Busca uma reserva pelo ID."""
    reservation = await db.get(Reservation, reservation_id)
    if not reservation:
        raise ReservationNotFoundError(reservation_id)
    return reservation

# ERRADO — lógica aninhada desnecessária
async def get_reservation(db: AsyncSession, reservation_id: int) -> Reservation:
    reservation = await db.get(Reservation, reservation_id)
    if reservation:
        return reservation
    else:
        raise ReservationNotFoundError(reservation_id)
```

### Naming Conventions
- **Variáveis/funções**: `snake_case` — nome explica o "quê", não o "como"
- **Classes**: `PascalCase`
- **Constantes**: `UPPER_SNAKE_CASE` no topo do módulo
- **Privados**: prefixo `_` (ex: `_parse_hidden_fields`)
- **Booleanos**: prefixo `is_`, `has_`, `can_`, `should_` (ex: `is_available`, `has_expired`)
- **Coleções**: plural (ex: `reservations`, `attempt_logs`)

---

## FastAPI

- DB sessions via `Depends(get_db)`. Services recebem `db: AsyncSession` como parâmetro.
- `RedirectResponse(status_code=303)` após POST (PRG pattern).
- Background tasks via `asyncio.create_task()`, nunca threads.
- Sem global state mutável. Estado compartilhado vive no DB.
- Respostas de erro devem retornar status HTTP adequado + mensagem clara.

---

## Tratamento de Erro

### Exceções customizadas
Definir em `app/exceptions.py`. Hierarquia:

```python
class ICondError(Exception):
    """Exceção base do projeto."""

class LoginError(ICondError):
    """Falha na autenticação com o iCondomínio."""

class ReservationError(ICondError):
    """Erro genérico de reserva."""

class ReservationNotFoundError(ReservationError):
    """Reserva não encontrada no banco."""

class ReservationUnavailableError(ReservationError):
    """Data/recurso indisponível para reserva."""
```

### Padrões por tipo de falha
| Falha | Ação | Retenta? |
|---|---|---|
| Login inválido | status `failed`, notifica WhatsApp | Não |
| Condicao (data indisponível) | Retenta no loop | Sim (até 60x) |
| Conclusao falhou | Retenta no loop | Sim (até 60x) |
| Timeout httpx | Retenta com backoff | Sim |
| Exceção inesperada | `logger.exception()`, notifica | Não |

### Regras
- Nunca engolir exceções silenciosamente.
- Logar exceções com `logger.exception()` para preservar traceback.
- Exceções de domínio (negócio) → exceções customizadas.
- Exceções de infraestrutura (HTTP, DB) → capturar e re-empacotar em exceção de domínio quando fizer sentido.

---

## Segurança

### Validação de Input
- **Todo input do usuário** passa por validação Pydantic antes de chegar nos services.
- Schemas Pydantic com `Field(...)` e validators para regras de negócio (ex: data no futuro, recurso válido).
- Nunca confiar em dados vindos de formulários HTML — sempre validar server-side.

### Proteções
- **SQL Injection**: usar SQLAlchemy ORM/Core — nunca concatenar strings em queries.
- **XSS**: Jinja2 faz auto-escape por padrão. Nunca usar `| safe` sem sanitizar antes.
- **CSRF**: formulários POST devem usar tokens ou verificação de origin.
- **Credenciais**: APENAS em `.env` (gitignored). Nunca hardcodar, nunca logar credenciais.
- **Headers HTTP**: não expor stack traces em produção. Usar exception handlers do FastAPI.

### .env
- `.env` no `.gitignore` — nunca comitar credenciais.
- `.env.example` com valores placeholder — manter atualizado com novas variáveis.

---

## Logging

### Configuração
```python
logger = logging.getLogger("icond.<módulo>")
```

### Quando usar cada nível

| Nível | Quando usar | Exemplo |
|---|---|---|
| `DEBUG` | Detalhes internos para troubleshooting | `logger.debug(f"Parsing hidden fields: {html[:100]}")` |
| `INFO` | Eventos normais do fluxo | `logger.info(f"Reserva {id} agendada para {date}")` |
| `WARNING` | Situação inesperada mas recuperável | `logger.warning(f"Tentativa {n}/60 falhou, retentando")` |
| `ERROR` | Falha que impede a operação | `logger.error(f"Login falhou: {status_code}")` |
| `EXCEPTION` | Erro com traceback (dentro de except) | `logger.exception("Erro inesperado na reserva")` |

### Regras
- **Nunca logar credenciais**, tokens ou dados sensíveis.
- **Sempre logar** início e fim de operações importantes (login, reserva, notificação).
- **Contexto**: incluir IDs relevantes (reservation_id, resource_id) em toda mensagem.
- **Formato consistente**: f-strings, sem concatenação com `+`.

---

## Qualidade de Código

### Ruff
Linter e formatter único (substitui black, isort, flake8).

```toml
# pyproject.toml
[tool.ruff]
target-version = "py311"
line-length = 120

[tool.ruff.lint]
select = ["E", "F", "W", "I", "N", "UP", "B", "A", "SIM", "RUF"]

[tool.ruff.format]
quote-style = "double"
```

### Métricas de qualidade
- Funções com no máximo **~20 linhas**. Se maior, extrair sub-função com nome descritivo.
- Máximo **3 níveis de indentação**. Se mais, refatorar com early return ou extrair função.
- Sem código comentado — deletar. Git preserva o histórico.
- Sem magic numbers — extrair para constantes nomeadas.
- **Sem `# TODO` solto** — se precisa ser feito, criar issue. Se não, deletar.

### Dependências
- Sempre verificar última versão estável no PyPI antes de adicionar.
- Ao encontrar API deprecated, atualizar para a API atual imediatamente.
- Manter `poetry.lock` atualizado. Rodar `poetry update` periodicamente.
- Preferir bibliotecas com manutenção ativa (último release < 6 meses).
