# Princípios de Engenharia

## SOLID

### S — Single Responsibility
Cada módulo/classe/função tem **uma única razão para mudar**.

| Módulo | Responsabilidade |
|---|---|
| `icondominio.py` | Comunicação com API iCondomínio |
| `scheduler.py` | Agendamento e trigger de reservas |
| `notifier.py` | Notificação via WhatsApp |
| `reservations.py` | Entrada/saída HTTP (rotas) |
| `models.py` | Definição de entidades e schema do banco |

**Na prática**: se uma função faz login E reserva E notifica, está violando SRP. Separar em funções/methods distintos.

### O — Open/Closed
Aberto para extensão, fechado para modificação.

- Novo recurso do condomínio → novo seed data, não nova branch no service.
- Novo tipo de notificação → novo service (ex: `email_notifier.py`), não condicional no `notifier.py`.
- Usar composição e parâmetros, não `if/elif` crescente.

### L — Liskov Substitution
Ao usar abstrações (protocols/ABCs), qualquer implementação deve ser **substituível** sem quebrar o chamador.

```python
# Se amanhã trocar WhatsApp por email, o scheduler não muda:
async def execute_reservation(notifier: Notifier, ...):
    await notifier.send(message)  # Funciona com qualquer implementação
```

### I — Interface Segregation
Interfaces mínimas. Services não devem depender de métodos que não usam.

- `notifier.py` expõe apenas `send()` — não `send()`, `format()`, `validate()` etc.
- Se um service precisa de só 1 método de outro, receber esse método (ou protocol mínimo), não o service inteiro.

### D — Dependency Inversion
Módulos de alto nível não dependem de módulos de baixo nível. Ambos dependem de abstrações.

```python
# CERTO — service recebe dependência injetada
async def execute_reservation(db: AsyncSession, client: httpx.AsyncClient, ...):
    ...

# ERRADO — service cria sua própria dependência
async def execute_reservation(...):
    async with httpx.AsyncClient() as client:  # acoplado
        ...
```

Routers injetam via `Depends()`. Testes injetam mocks.

---

## Clean Architecture (pragmática)

### Camadas

```
┌─────────────────────────────────┐
│  Apresentação (routers, templates) │  ← depende de ↓
├─────────────────────────────────┤
│  Aplicação (services)              │  ← depende de ↓
├─────────────────────────────────┤
│  Domínio (models, schemas, exceptions) │  ← não depende de nada externo
├─────────────────────────────────┤
│  Infraestrutura (database, config, HTTP) │
└─────────────────────────────────┘
```

### Regra de dependência
- Camadas internas **NÃO importam** camadas externas.
- `models.py` não importa `services/`.
- `services/` não importam `routers/`.
- `routers/` podem importar `services/` e `schemas`.
- `services/` podem importar `models`, `schemas`, `exceptions`.

### Na prática neste projeto
Não criar abstrações forçadas (interfaces, repositories, use cases) só para "ficar clean". O projeto é simples — as camadas naturais do FastAPI (router → service → model) já respeitam a separação.

---

## DRY — Don't Repeat Yourself

- Extrair código duplicado apenas quando a duplicação ocorrer **3+ vezes**.
- Duplicação **acidental** (código parecido com propósitos diferentes) NÃO é violação de DRY. Não unificar à força.
- Preferir duplicação a uma abstração errada — é mais fácil refatorar código duplicado do que desfazer uma abstração ruim.

```python
# Duplicação acidental — NÃO unificar (propósitos diferentes)
def format_date_for_api(date: datetime) -> str:
    return date.strftime("%d-%m-%Y")

def format_date_for_display(date: datetime) -> str:
    return date.strftime("%d/%m/%Y")
```

---

## KISS — Keep It Simple, Stupid

- Preferir a solução mais simples que funciona.
- Código legível > código "esperto".
- Se precisa de comentário para explicar, **simplifique o código** em vez de adicionar o comentário.
- Evitar abstrações prematuras, generalizações desnecessárias e patterns para impressionar.

```python
# CERTO — simples e direto
if reservation.status == "pending":
    await process(reservation)

# ERRADO — over-engineered
strategy = ReservationStrategyFactory.get_strategy(reservation.status)
await strategy.execute(ReservationContext(reservation))
```

---

## YAGNI — You Ain't Gonna Need It

- Só implementar o que é necessário **AGORA**.
- Não criar abstrações, configurações ou extensões para requisitos hipotéticos.
- Não adicionar parâmetros "por precaução".
- Não criar generalizações para "quando precisar no futuro".

### Checklist antes de adicionar algo
1. Alguém pediu isso? → Se não, não faça.
2. O código funciona sem isso? → Se sim, não faça.
3. Estou preparando para um cenário futuro? → Pare. Faça quando o futuro chegar.
