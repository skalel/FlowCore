# FlowCore — Multi-Environment Financial Management Platform

![Python](https://img.shields.io/badge/python-3.12+-blue.svg)
![FastAPI](https://img.shields.io/badge/FastAPI-0.100+-009688.svg)
![PostgreSQL](https://img.shields.io/badge/PostgreSQL-15-316192.svg)
![Docker](https://img.shields.io/badge/Docker-Ready-2496ED.svg)
![License](https://img.shields.io/badge/license-MIT-green.svg)

Sistema de gestão financeira multiambiente focado em controle de receitas, despesas, dívidas e colaboração entre usuários com diferentes níveis de permissão.

O projeto foi desenhado com arquitetura moderna, suporte a múltiplos contextos (solo, família, negócios), controle granular de permissões (RBAC + ABAC), auditoria, motor de IA e extensibilidade para módulos futuros, preparado para operar como um SaaS completo.

---

## Features

### Multi-Ambientes (Multi-tenant)
* Ambientes do tipo Solo, Família, Amigos e Negócios.
* Isolamento completo de dados por ambiente (via Headers).
* Convite de usuários com roles e permissões específicas.
* Ambientes com prazo de validade (Business).

### Controle Financeiro
* Cadastro de receitas e despesas com suporte a soft delete e histórico auditável.
* Controle por competência e vencimento (Data de Impacto).
* Gestão completa de cartões de crédito (faturas, múltiplos titulares, cálculo automático de dias de fechamento/vencimento).

### Permissões e Segurança
* RBAC com overrides híbridos (ALLOW / DENY).
* Controle granular por ambiente (Ownership e roles configuráveis).
* Identificadores universais seguros (UUIDv7).

### Fechamento Fiscal
* Fechamento mensal por ambiente.
* Bloqueio criptográfico de alterações em meses encerrados.
* Histórico imutável após fechamento (Conciliação).

### Motor de Inteligência & SaaS
* AI Insights: Motor heurístico avançado com fallback para LLMs gratuitos, gerando análises trimestrais de gastos, detecção de gastos fantasmas e planos de ação.
* Módulo SaaS: Suporte nativo a Plan Tiers (Free, Pro), sistema de captação de feedbacks (Bug, Sugestões, Elogios) e painel Superadmin global.

---

## Arquitetura e Stack

* Backend: FastAPI
* ORM: SQLAlchemy 2.x
* Database: PostgreSQL
* Migrations: Alembic
* Auth: JWT
* Package Manager: uv
* Deploy: Docker & Docker Compose otimizados para baixo consumo de RAM (Bare Metal).

Arquitetura baseada em princípios de:
* Clean Architecture / Hexagonal
* Domain-driven design (DDD-lite)
* Multi-tenant isolation
* Graceful Degradation (Serviços externos e IA)

---

## Setup do Projeto (Desenvolvimento)

### Requisitos
* Python 3.12+
* PostgreSQL local ou em container
* uv (Package Manager)

Instalar o uv:
```bash
curl -Ls [https://astral.sh/uv/install.sh](https://astral.sh/uv/install.sh) | sh
```
### Passo a Passo
1. Instalar dependências:

```bash
uv sync
```

2. Configurar variáveis de ambiente: \
Copie o .env.example para .env e preencha suas credenciais do banco de dados e JWT Secret.

3. Rodar as migrações do banco:

```bash
alembic upgrade head
```

4. Rodar aplicação:

```bash
uv run fastapi dev
```

Acesse a documentação interativa em: http://127.0.0.1:8000/docs

## Deploy (Produção com Docker)

O projeto está otimizado para rodar em instâncias com recursos limitados (ex: 1 OCPU, 1GB RAM).
1. Clone o repositório no seu servidor.
2. Crie o seu arquivo .env de produção.
3. Suba os containers (A API e o PostgreSQL):

```bash
docker-compose up -d --build
```
As migrações do banco de dados serão aplicadas automaticamente via entrypoint.sh ao iniciar o container da API.

## Convenções Importantes
- Multi-tenant por ambiente: Todas as rotas que manipulam dados de um ambiente exigem o envio do header: X-Environment-Id: .
- Visão mensal (Impacto): A aplicação usa o conceito de "impacto" para agrupamento mensal: impact_date = COALESCE(due_on, occurred_on). Isso faz compras no cartão realizadas em janeiro, mas pagas em fevereiro, aparecerem corretamente no mês de fevereiro.
- Políticas de Delete:
  - Padrão: Até 24h, o sistema permite hard delete automático.
  - Após 24h: Aplica-se soft delete (preservando o histórico).
  - SuperAdmin: Pode forçar hard delete passando a query ?hard=true.
  - Mês fiscal fechado: Bloqueia integralmente alterações e deleções.

## Testes
Execute a suíte de testes com:

```bash
pytest
```

Cobertura inclui: unit tests (domínio), integração com API, validação de permissões RBAC/ABAC e isolamento por ambiente.

## Estrutura de Diretórios
```
app/
 ├── api/           # Rotas FastAPI, dependências e controllers
 ├── config/        # Configurações do Pydantic para validação de Ambiente
 └── database/
      └── versions/ # Migrations do Alembic
 ├── domain/        # Entidades e regras de negócio puras (DDD)
 ├── infra/         # Banco de dados (Modelos ORM), integrações e serviços externos
 ├── services/      # Lógica de orquestração e IA
 └── shared/        # Utilidades, schemas base e segurança
tests/              # Testes unitários e de integração
```

## Roadmap
[x] Dashboards com métricas e Skeletons

[x] Motor de análise financeira com IA e Heurística (Fallback)

[x] Módulo SaaS (Superadmin e Feedbacks de Usuários)

[x] Suporte completo a Cartões de Crédito (Titulares e Faturas)

[x] Dívidas, Parcelas e Recorrência Automática

[x] Importação Inteligente de planilhas

[ ] Importação de OFX

[ ] Integração com Telegram Bot

[ ] Módulos específicos (Mercado, Farmácia, Educação)
