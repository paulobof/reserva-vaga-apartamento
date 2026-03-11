# Convenções Git

## Commits

### Formato: Conventional Commits
```
<tipo>(<escopo>): <descrição curta>

<corpo opcional>
```

### Tipos permitidos
| Tipo | Quando usar |
|---|---|
| `feat` | Nova funcionalidade |
| `fix` | Correção de bug |
| `refactor` | Refatoração (sem mudar comportamento) |
| `test` | Adição ou alteração de testes |
| `docs` | Documentação |
| `style` | Formatação (sem mudar lógica) |
| `chore` | Tarefas de manutenção (deps, config, CI) |
| `perf` | Melhoria de performance |

### Escopos comuns
`api`, `scheduler`, `notifier`, `db`, `ui`, `auth`, `config`, `docker`

### Exemplos
```
feat(api): adicionar endpoint de health check
fix(auth): corrigir redirect chain perdendo cookies no hop 15
refactor(scheduler): extrair cálculo de trigger_date para função pura
test(api): adicionar testes de integração para CRUD de reservas
docs: atualizar README com instruções de teste
chore(deps): atualizar httpx para 0.28.1
```

### Regras
- Descrição em **português**, imperativo, minúscula, sem ponto final.
- Máximo **72 caracteres** na primeira linha.
- Corpo opcional para explicar o **porquê**, não o "o quê" (o diff mostra o quê).
- **Um commit por mudança lógica**. Não misturar feature + refactor + fix no mesmo commit.
- **NUNCA** adicionar `Co-Authored-By` nos commits.

---

## Branches

### Formato
```
<tipo>/<descrição-curta>
```

### Exemplos
```
feat/health-check
fix/cookie-leak-redirect
refactor/extract-date-utils
test/integration-reservations
```

### Regras
- Branch `main` é a branch de produção — sempre deployável.
- Criar branch para qualquer mudança que não seja trivial (typo, bump de versão).
- Manter branches de curta duração — mergear rápido, deletar após merge.

---

## Code Review Checklist

Antes de mergear, verificar:

### Funcionalidade
- [ ] Atende ao requisito? Testar manualmente o cenário feliz.
- [ ] Cenários de erro tratados? (input inválido, timeout, API fora do ar)
- [ ] Sem regressão? Testes existentes continuam passando.

### Código
- [ ] Segue os [padrões de código](code-standards.md)?
- [ ] Early return aplicado? Sem nesting desnecessário.
- [ ] Funções <= 20 linhas? Nomes descritivos?
- [ ] Type hints em todas as assinaturas?
- [ ] Docstrings nas funções públicas (Google Style)?
- [ ] Sem magic numbers, sem código comentado?

### Testes
- [ ] Testes unitários para lógica nova?
- [ ] Testes de integração para endpoints novos/alterados?
- [ ] Cobertura >= 80%?
- [ ] Testes passam localmente? (`poetry run pytest`)

### Segurança
- [ ] Input validado via Pydantic?
- [ ] Sem credenciais hardcoded ou logadas?
- [ ] Queries via SQLAlchemy ORM (sem SQL raw concatenado)?
- [ ] Templates sem `| safe` em dados do usuário?

### Documentação
- [ ] README.md atualizado se houve mudança de interface, comandos ou config?
- [ ] CLAUDE.md atualizado se houve mudança arquitetural?
- [ ] `.env.example` atualizado se adicionou variável de ambiente?

### Qualidade
- [ ] `ruff check .` sem erros?
- [ ] `ruff format .` aplicado?
- [ ] Sem warnings novos nos logs?

---

## Pre-commit Hooks

### Setup com Ruff
```yaml
# .pre-commit-config.yaml
repos:
  - repo: https://github.com/astral-sh/ruff-pre-commit
    rev: v0.9.0  # usar versão mais recente
    hooks:
      - id: ruff
        args: [--fix]
      - id: ruff-format
```

### Instalação
```bash
pip install pre-commit
pre-commit install
```

### O que roda automaticamente
1. **ruff check --fix** — lint com auto-fix no `git commit`
2. **ruff format** — formatação automática no `git commit`

Se o hook falhar, o commit é bloqueado. Corrigir o problema e tentar novamente.

---

## Workflow Completo

```
1. Criar branch       → git checkout -b feat/nova-feature
2. Desenvolver        → código + testes + docstrings
3. Lint/Format        → poetry run ruff check . && poetry run ruff format .
4. Testar             → poetry run pytest
5. Commit             → git commit (hooks rodam automaticamente)
6. Push               → git push -u origin feat/nova-feature
7. Code Review        → seguir checklist acima
8. Merge              → merge na main, deletar branch
9. Atualizar docs     → README.md, CLAUDE.md se necessário
```
