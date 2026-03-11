# Estratégia de Testes

## Pirâmide de Testes

```
        /  E2E  \          ← poucos, fluxo completo
       /----------\
      / Integração \       ← médio, camadas conectadas
     /--------------\
    /   Unitários    \     ← muitos, rápidos, isolados
   /------------------\
```

---

## Testes Unitários (`tests/unit/`)

### O que testam
- Services e funções **isoladamente**, sem I/O real.
- Lógica de negócio pura: parsing, cálculos, validações, transformações.

### Como
- Toda dependência externa (DB, HTTP, filesystem) é **mockada** com `unittest.mock` ou `pytest-mock`.
- Um teste por comportamento: cenário feliz + cada cenário de erro.
- Devem ser **rápidos** (< 1s por teste) e **determinísticos** (sem dependência de tempo, rede, etc.).

### Exemplos de testes necessários
```
test_parse_hidden_fields_extrai_campos_corretos
test_parse_hidden_fields_html_vazio_levanta_erro
test_calcular_trigger_date_90_dias_antes
test_calcular_trigger_date_ano_bissexto
test_formatar_data_formato_icondominio
test_notifier_monta_mensagem_sucesso
test_notifier_monta_mensagem_falha
```

---

## Testes de Integração (`tests/integration/`)

### O que testam
- **Interação entre camadas**: router → service → DB.
- Endpoints HTTP da aplicação (status codes, redirects, corpo da resposta).
- Queries e mutations no banco de dados.

### Como
- Banco SQLite **in-memory** (`:memory:`) com fixtures de setup/teardown.
- `httpx.AsyncClient` com `ASGITransport` — testa endpoints sem levantar servidor.
- Cada teste cria seu próprio estado e limpa ao final.

### Setup padrão
```python
# tests/conftest.py
import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from app.main import app
from app.database import Base, get_db

@pytest.fixture
async def db_session():
    """Cria banco in-memory para o teste."""
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    async with AsyncSession(engine) as session:
        yield session
    await engine.dispose()

@pytest.fixture
async def client(db_session):
    """HTTP client que usa o banco de teste."""
    async def override_get_db():
        yield db_session

    app.dependency_overrides[get_db] = override_get_db
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as c:
        yield c
    app.dependency_overrides.clear()
```

### Exemplos de testes necessários
```
test_criar_reserva_retorna_303_e_persiste_no_db
test_listar_reservas_retorna_200_com_html
test_deletar_reserva_remove_do_db
test_criar_reserva_data_passada_retorna_422
test_health_check_retorna_ok
```

---

## Testes E2E (`tests/e2e/`)

### O que testam
- **Fluxo completo** de uma reserva: criação → agendamento → execução → notificação.
- Side effects: registros no DB, logs de tentativas, notificações enviadas.

### Como
- Chamadas HTTP externas (iCondomínio, Evolution API) mockadas com **`respx`**.
- Banco SQLite in-memory com seed data (recursos).
- Valida estado final: reservation.status, attempt_logs count, notificação chamada.

### Exemplo de fluxo E2E
```python
async def test_fluxo_reserva_completo_sucesso(client, db_session, respx_mock):
    """Simula o ciclo completo: login → warmup → condicao → conclusao."""
    # Arrange: mockar todas as chamadas externas
    respx_mock.post("https://servicoacesso.webware.com.br/Aplicativo/Login/Usuario").respond(
        json={"NIU": "123", "Token": "abc"}
    )
    respx_mock.post("https://servicoacesso.webware.com.br/Aplicativo/Redireciona").respond(
        json={"Token": "redirect-token"}
    )
    # ... demais mocks

    # Act: executar o fluxo de reserva
    result = await execute_reservation(db_session, reservation_id=1)

    # Assert
    assert result.status == "confirmed"
    logs = await get_attempt_logs(db_session, reservation_id=1)
    assert len(logs) >= 1
    assert logs[-1].success is True
```

---

## Regras Gerais

### Nomenclatura
```
test_<funcionalidade>_<cenário>_<resultado_esperado>
```
Exemplos:
- `test_login_credenciais_invalidas_retorna_failed`
- `test_reserva_data_disponivel_confirma_sucesso`
- `test_notificacao_whatsapp_api_offline_loga_erro`

### Fixtures
- **Compartilhadas** em `conftest.py` de cada nível (root, unit, integration, e2e).
- Uma fixture por recurso: `db_session`, `client`, `respx_mock`, `sample_reservation`.
- Fixtures devem ser **autônomas** — cada teste cria e limpa seu estado.

### Cobertura
- Mínimo **80%** de cobertura de código.
- Focar em **lógica de negócio**, não em boilerplate (imports, configs).
- Rodar com `pytest --cov=app --cov-report=term-missing` para identificar linhas não cobertas.

### Disciplina
- **Novo feature → novos testes.** Não mergear código sem testes.
- **Bug fix → teste que reproduz o bug primeiro**, depois o fix.
- Testes são código de produção: mesmos padrões de qualidade (type hints, docstrings, nomes claros).
- Sem `sleep()` em testes. Usar mocks de tempo se necessário (`freezegun` ou `time_machine`).
- Sem dependência entre testes — ordem de execução não importa.
