# Plataforma de confirmação de consultas

Aplicação Full Stack para importar a agenda de uma clínica, disparar confirmações, acompanhar o
processamento assíncrono e registrar a resposta do paciente. O envio é simulado de forma
determinística: nenhum WhatsApp, SMS, e-mail ou serviço pago é utilizado.

O projeto prioriza migrations versionadas, worker independente, idempotência no banco,
concorrência segura, retries limitados, recuperação de falhas de publicação, logs estruturados,
healthchecks e CI.

## Execução rápida

Para executar desde o clone:

```bash
git clone https://github.com/NasserCaixeta/Desafio-Algarys.git
cd Desafio-Algarys
cp .env.example .env
docker compose up --build
```

O serviço `migrate` espera o PostgreSQL ficar saudável, aplica `alembic upgrade head` e libera os
demais serviços. Não há etapa manual escondida.

Depois que os healthchecks estabilizarem:

- frontend: <http://localhost:3000>;
- Swagger: <http://localhost:8000/docs>;
- OpenAPI: <http://localhost:8000/openapi.json>;
- readiness: <http://localhost:8000/health/ready>;
- status: <http://localhost:8000/status>.

Para parar preservando os dados, execute `docker compose down`. Para remover também os volumes
locais, use conscientemente `docker compose down --volumes`.

## Demonstração do fluxo

1. A clínica envia um CSV pelo frontend ou por `POST /api/v1/imports/appointments`.
2. Linhas válidas são importadas; linhas inválidas voltam no relatório sem abortar o arquivo.
3. Se a agenda estiver vazia, o frontend abre uma data importada; datas com consultas aparecem como
   atalhos.
4. O operador filtra a agenda e seleciona consultas específicas ou todas as elegíveis do dia.
5. A API persiste uma única mensagem `pending` por agendamento e publica uma tarefa no Redis.
6. O worker Celery reivindica a mensagem atomicamente e registra a tentativa.
7. O simulador conclui como `sent` ou `failed`; falhas elegíveis retornam com backoff.
8. Depois do envio, o operador simula a resposta `confirmed` ou `declined`.

O fluxo completo pode ser executado contra os containers com:

```bash
./scripts/smoke.sh
```

O script é repetível e também verifica importação, disparo e resposta idempotentes.

## Arquitetura

```mermaid
flowchart LR
    B[Browser] -->|HTTP :3000| F[Frontend React<br/>Nginx não root]
    F -->|/api| A[FastAPI :8000]
    A --> P[(PostgreSQL)]
    A --> R[(Redis broker)]
    R --> W[Celery worker<br/>2 processos]
    W --> P
    S[Celery Beat<br/>scheduler] --> R
    S --> P
    M[Alembic migrate<br/>one-shot] --> P
```

| Serviço | Responsabilidade |
| --- | --- |
| `frontend` | SPA React estática e proxy `/api` por Nginx |
| `api` | HTTP, validação dos contratos e orquestração dos casos de uso |
| `worker` | Consumo, reivindicação atômica, envio simulado e tentativas |
| `scheduler` | Reconciliação, retry automático e recuperação de leases |
| `migrate` | Job one-shot que aplica as migrations antes da aplicação |
| `postgres` | Fonte de verdade, constraints, locks e histórico |
| `redis` | Broker Celery, sem exposição pública em produção |
| `nginx` | TLS e reverse proxy no Compose de produção |

API, worker, scheduler, PostgreSQL, Redis e frontend executam em processos separados. O worker não
é uma thread nem uma background task da API.

### Organização do backend

```text
backend/src/clinic_confirmations/
├── api/             # rotas, dependências, middleware e tradução de erros
├── schemas/         # contratos Pydantic de entrada e saída
├── services/        # casos de uso e regras da aplicação
├── domain/          # enums, erros e funções puras de domínio
├── repositories/    # consultas, locks e operações SQL atômicas
├── db/models/       # modelos SQLAlchemy e constraints
├── queue/           # Celery, publicação, tarefas e reconciliação
├── sender/          # contrato e simulador determinístico
└── core/            # configuração e logging
```

As rotas validam e traduzem HTTP; os services coordenam os casos de uso; e as garantias contra
corridas ficam nos repositórios e, principalmente, no PostgreSQL. A separação mantém as regras
testáveis sem adicionar camadas artificiais.

## Stack e configuração

- Backend: Python 3.12+, FastAPI, Pydantic 2, SQLAlchemy 2, Alembic e Psycopg 3.
- Assíncrono: Celery com Redis e Celery Beat.
- Banco: PostgreSQL 17.
- Frontend: React 19, TypeScript, Vite e TanStack Query.
- Qualidade: Pytest, Ruff, mypy estrito, Vitest, Testing Library, ESLint e TypeScript.
- Operação: Docker Compose, imagens multi-stage, Nginx, GitHub Actions e GHCR.

Para a execução recomendada, são necessários Docker Engine ou Docker Desktop, Compose v2 e as
portas locais `3000`, `8000`, `5433` e `6380` livres. Para desenvolvimento fora dos containers,
use Python `>=3.12,<3.15` e Node.js 22.

Toda configuração vem de variáveis de ambiente. O arquivo [`.env.example`](.env.example) é a fonte
completa e documentada; arquivos `.env*`, exceto o exemplo, são ignorados pelo Git. Os principais
grupos são:

- aplicação: `APP_ENV`, `APP_VERSION`, `APP_TIMEZONE`, `CORS_ORIGINS` e limites de upload/timeout;
- persistência: `DATABASE_URL`, `POSTGRES_*`, `REDIS_URL` e equivalentes de teste;
- fila: `CELERY_QUEUE`, visibilidade, reconciliação, lease, limite e backoff;
- simulador: `SIMULATED_FAILURE_SUFFIXES`, `SIMULATED_FAILURE_ATTEMPTS` e latência;
- frontend: `VITE_API_URL`, timeout e intervalo de polling.

Em produção, `POSTGRES_PASSWORD` é obrigatória e o Compose recusa a configuração sem ela. Como a
URL é montada pelo Compose, caracteres reservados exigem percent-encoding; uma senha hexadecimal
longa evita essa ambiguidade.

## CSV

O arquivo deve ser UTF-8, aceita BOM, usa vírgulas e possui exatamente este cabeçalho:

```csv
data_hora,paciente,telefone,procedimento
```

Regras:

- `data_hora`: aceita `YYYY-MM-DD HH:MM` ou `DD/MM/YYYY HH:MM`;
- a data é interpretada em `APP_TIMEZONE` e armazenada em UTC;
- `paciente` e `procedimento`: obrigatórios, com espaços internos normalizados;
- `telefone`: brasileiro, com ou sem `+55`, normalizado para E.164;
- linhas em branco são ignoradas;
- linhas inválidas voltam com número, dados originais e motivo sem abortar as válidas.

O exemplo está em [`examples/appointments.csv`](examples/appointments.csv). Para importar pela API:

```bash
curl -F 'file=@examples/appointments.csv;type=text/csv' \
  http://localhost:8000/api/v1/imports/appointments
```

### Reimportação e duplicidade

O fingerprint é o SHA-256 de data/hora UTC, paciente, telefone e procedimento normalizados, e a
coluna possui constraint única. Uma reimportação não cria cópia silenciosa: a linha aparece em
`duplicate_lines` e incrementa `summary.duplicates`. Duas linhas iguais no mesmo arquivo seguem a
mesma regra. A resposta também inclui as datas válidas encontradas no arquivo.

## API

As rotas de negócio estão sob `/api/v1`. Swagger e OpenAPI são gerados pelo FastAPI.

| Método | Rota | Uso |
| --- | --- | --- |
| `POST` | `/api/v1/imports/appointments` | upload multipart e relatório por linha |
| `GET` | `/api/v1/appointments` | filtros por data/status e paginação |
| `GET` | `/api/v1/appointments/calendar` | datas com consultas e quantidades |
| `GET` | `/api/v1/appointments/{id}` | detalhe do agendamento e mensagem |
| `POST` | `/api/v1/confirmations/dispatch` | disparo por data e IDs opcionais |
| `POST` | `/api/v1/appointments/{id}/response` | resposta `confirmed` ou `declined` |
| `GET` | `/api/v1/messages` | filtro por status e paginação |
| `GET` | `/api/v1/messages/{id}` | mensagem e histórico de tentativas |
| `POST` | `/api/v1/messages/{id}/retry` | retry manual da mesma mensagem |
| `GET` | `/health/live` | liveness e versão |
| `GET` | `/health/ready` | PostgreSQL e Redis, `200` ou `503` |
| `GET` | `/status` | versão, ambiente, dependências e contagens |

Erros usam um envelope estável com `code`, `message`, `details` e `request_id`. A API responde com
`400/413/422` para entradas inválidas, `404` para recurso ausente, `409` para transições
incompatíveis e `503` quando as dependências do readiness estão indisponíveis.

## Fila, idempotência e concorrência

### Disparo e publicação

1. A API seleciona as consultas `pending` do dia na timezone da clínica.
2. `INSERT ... ON CONFLICT DO NOTHING` cria uma `ConfirmationMessage` `pending`.
3. `UNIQUE (appointment_id)` é a garantia final contra mensagens duplicadas.
4. A transação é commitada e a tarefa é publicada no Redis.
5. Sucesso marca `enqueued_at`; falha persiste erro, contador e próxima publicação.
6. O scheduler busca publicações vencidas com `FOR UPDATE SKIP LOCKED` e tenta novamente.

Essa reconciliação recupera automaticamente o caso “banco persistiu, Redis falhou” sem criar uma
segunda entidade de outbox para um único tipo de evento.

### Dois ou mais workers

O Compose inicia um worker com dois processos prefork. Também é possível escalar containers:

```bash
docker compose up -d --scale worker=2
```

Cada entrega faz um `UPDATE` condicional de `pending` para `processing`, incrementa
`attempt_count` e recebe um `processing_token`. Só uma transação obtém a linha; entregas duplicadas
viram no-op. A finalização exige o mesmo token, impedindo um worker antigo de concluir depois que
seu lease expirou e foi recuperado.

Garantias fornecidas:

- uma única `ConfirmationMessage` por agendamento;
- uma única tentativa válida entre consumidores concorrentes;
- tolerância à entrega “at least once” do Celery;
- resposta repetida do paciente idempotente;
- respostas opostas simultâneas com um vencedor e um conflito, sem overwrite silencioso;
- dispatches e reconciliadores concorrentes protegidos e testados em PostgreSQL real.

### Retry

Uma falha registra `MessageAttempt`, preserva `last_error` e calcula:

```text
delay = min(base * 2^(attempt_number - 1), maximum)
```

O scheduler devolve falhas vencidas a `pending` e republica a mesma mensagem; o endpoint manual
antecipa esse agendamento. O retry não cria outra `ConfirmationMessage`, respeita
`MAX_MESSAGE_ATTEMPTS` e registra leases abandonados como `abandoned`.

### Resposta do paciente

Somente consultas cuja mensagem está `sent` aceitam resposta. `pending → confirmed` e
`pending → declined` são válidas. Repetir a mesma resposta retorna sucesso; tentar a oposta retorna
`409 response_conflict`.

## Frontend

A interface responsiva oferece filtro de data/status, atalhos para datas com agenda, tabela no
desktop e cartões no mobile, upload com relatório por linha, seleção de consultas, disparo seletivo
ou do dia, polling, confirmação/recusa e retry de falhas. Tentativas aparecem somente quando são
úteis: durante processamento, retry ou falha.

TanStack Query controla cache, invalidação e polling. O cliente aplica timeout e traduz o envelope
de erro da API para feedback operacional, incluindo loading, vazio e indisponibilidade.

## Migrations

As migrations ficam em `backend/migrations/versions`. A inicial cria enums, tabelas, FKs, checks,
índices e constraints de importação e idempotência.

```bash
# aplicar até a versão atual
docker compose run --rm migrate alembic upgrade head

# consultar a versão
docker compose run --rm migrate alembic current

# reverter e reaplicar a última migration
docker compose run --rm migrate alembic downgrade -1
docker compose run --rm migrate alembic upgrade head
```

Para criar uma migration durante o desenvolvimento:

```bash
DATABASE_URL='postgresql+psycopg://clinic:clinic_local_password@localhost:5433/clinic_confirmations' \
  .venv/bin/alembic -c backend/alembic.ini revision --autogenerate -m 'descricao curta'
```

Revise o arquivo gerado antes de executar. Em produção, não faça downgrade sem backup e sem
confirmar a compatibilidade com a versão anterior da aplicação.

## Testes e qualidade

### Backend

```bash
docker compose up -d postgres redis
python3 -m venv .venv
.venv/bin/pip install -e './backend[dev]'
.venv/bin/ruff check backend
.venv/bin/mypy --config-file backend/pyproject.toml backend/src
.venv/bin/pytest -q backend/tests \
  --cov=clinic_confirmations --cov-report=term-missing --cov-fail-under=90
```

A suíte usa PostgreSQL e Redis reais, não SQLite, para exercitar constraints, locks e concorrência.
Cobre importação parcial, filtros, publicação, idempotência, processamento, retry, lease, entrega
duplicada, respostas e healthchecks.

### Frontend

```bash
cd frontend
npm ci
npm run lint
npm run typecheck
npm run test -- --run --coverage
npm run build
```

Vitest, Testing Library e MSW testam o comportamento pela camada HTTP sem substituir os hooks da
aplicação por mocks de implementação.

### Smoke test

```bash
./scripts/smoke.sh
```

O smoke reconstrói os serviços, importa o exemplo, lista, dispara, aguarda o worker, verifica envio
simples e `failed → sent`, registra resposta e confere o filtro `confirmed`.

## CI, CD e publicação de imagens

`.github/workflows/ci.yml` roda em pushes e pull requests:

1. backend: Ruff, mypy, ciclo de migrations, testes e cobertura mínima de 90%;
2. frontend: ESLint, typecheck, testes com cobertura e build;
3. containers: valida os Compose, constrói as imagens e executa o smoke completo;
4. em falha, publica os logs dos containers e limpa os volumes do runner.

O resultado aparece na aba **Actions** e no check **CI** do commit ou PR. O job de containers só
começa depois que backend e frontend passam.

`.github/workflows/publish.yml` publica as imagens da API, worker e frontend no GHCR em tags `v*`
ou por disparo manual. O procedimento de publicação e atualização está no
[guia operacional](deploy/README.md#ghcr).

Depois de um `push` na `main`, `.github/workflows/deploy.yml` aguarda o workflow **CI** terminar.
Somente um CI verde, originado por `push` no próprio repositório, pode publicar imagens imutáveis
`sha-<commit>` e iniciar o deploy de `production`. Pull requests nunca recebem as credenciais da
VPS e não disparam o CD.

O deploy é pull-based: um timer root-owned na VPS consulta a `main` por HTTPS e só aceita o commit
quando as três imagens `sha-<commit>` existem no GHCR. O processo é serializado por `flock`, cria
backup local antes da migration, atualiza os containers e verifica todos os healthchecks. O job de
CD registra a release imutável no Environment `production`; a confirmação operacional fica no
journal do watcher, porque os runners hospedados do GitHub não alcançam esta VPS. Se uma etapa
falhar, o servidor restaura checkout e imagens anteriores. Downgrade de schema e restauração do
banco nunca são automáticos, pois poderiam descartar dados. Configuração e rollback estão no
[guia de CD](deploy/README.md#cd-automatico-da-main).

## Healthchecks e logs

PostgreSQL usa `pg_isready`; Redis, `redis-cli ping`; API, `/health/ready`; worker, `celery inspect
ping`; scheduler verifica o processo; e frontend usa `/nginx-health`. Dependências no Compose são
condicionadas à saúde ou à conclusão da migration.

API e eventos próprios do worker usam JSON por linha. A API aceita ou gera `X-Request-ID`, devolve
o header e o propaga como `correlation_id` da mensagem. Eventos incluem serviço, timestamp,
request/correlation ID, mensagem, agendamento, tentativa, status e erro quando aplicáveis. DSNs,
senhas, conteúdo do CSV e telefone completo não são logados.

Logs nativos de Uvicorn e Celery permanecem textuais ao redor dos eventos estruturados da aplicação.

## Decisões arquiteturais

| Decisão | Justificativa |
| --- | --- |
| Monólito modular + worker | Escopo coeso e separação real onde a assincronicidade exige |
| PostgreSQL como fonte de verdade | Constraints e locks superam checks apenas em memória |
| Reconciliação persistida | Recupera o dual-write banco/Redis com complexidade proporcional |
| Celery Beat separado | Retry e reconciliação sem loop ou thread na API |
| Falha por sufixo e N tentativas | Simulação reproduzível, sem testes aleatórios |
| UTC no banco e timezone na borda | Evita filtros diários e comparações ambíguas |
| Resposta somente após `sent` | Evita resposta sem uma confirmação simulada enviada |
| Frontend same-origin | Simplifica CORS, TLS e configuração da API em produção |

### Alternativas consideradas

- **Outbox transacional dedicado:** mais geral, mas adicionaria entidade e fluxo para um único tipo
  de evento. A reconciliação na própria mensagem atende ao desafio.
- **BackgroundTasks ou thread:** não são workers independentes e podem perder trabalho no reinício.
- **SQLite nos testes:** não reproduz locks, enums e concorrência do PostgreSQL.
- **Retry apenas no Celery:** esconderia tentativas e erros que pertencem ao domínio auditável.
- **WebSocket:** polling adaptativo atende ao volume com menor complexidade operacional.

Deliberadamente não foram implementados integração paga, autenticação sem requisito, Kubernetes,
microsserviços artificiais, aleatoriedade, observabilidade pesada ou funcionalidades clínicas fora
do desafio.

## Limitações e riscos de produção

- PostgreSQL e Redis são instâncias únicas, sem HA ou failover.
- A entrega é “at least once”, não exactly-once físico. Uma integração real deve usar `message_id`
  como chave de idempotência no provedor externo.
- Uma perda total do Redis depois de `enqueued_at` pode deixar trabalho pendente; um outbox dedicado
  ou lease de publicação seria a evolução natural.
- Não há DLQ, métricas, alertas, rate limiting ou autenticação.
- O telefone é validado como brasileiro; internacionalização exigiria regra por país.
- O CD mantém cinco backups locais anteriores às migrations; cópia externa, teste de restauração e
  renovação TLS ainda dependem de agendamento e monitoramento da VPS.
- Imagem e schema incompatíveis podem impedir rollback; produção exige migrations expand/contract.

DNS não propagado, portas 80/443 bloqueadas, falta de disco, relógio incorreto e segredos mal
codificados podem interromper deploy, certificados, banco, fila ou leases.

Com mais tempo, as prioridades seriam autenticação/RBAC, outbox ou lease de publicação mais forte,
DLQ e alertas, métricas, backup automatizado com teste de restauração, E2E de navegador na CI e
deploy blue/green com migrations expand/contract.

## Deploy em VPS

O projeto inclui `compose.prod.yaml`, Nginx com TLS e um stack para Portainer. O caminho mínimo é:

1. preparar uma VPS Ubuntu/Debian com Docker e domínio apontado;
2. clonar o repositório e criar `.env.production` a partir de `.env.example`;
3. definir `APP_ENV`, `DOMAIN`, `GHCR_OWNER`, `IMAGE_TAG`, `POSTGRES_PASSWORD` e `CORS_ORIGINS`;
4. autenticar no GHCR e iniciar os serviços internos;
5. emitir o primeiro certificado Let's Encrypt;
6. iniciar o Nginx e validar healthchecks por HTTPS.

```bash
sudo install -d -m 0750 -o "$USER" -g "$USER" /opt/clinic-confirmations
git clone <URL_DO_REPOSITORIO> /opt/clinic-confirmations
cd /opt/clinic-confirmations
cp .env.example .env.production

echo '<GHCR_READ_TOKEN>' | docker login ghcr.io -u '<GHCR_USER>' --password-stdin
docker compose --env-file .env.production -f compose.yaml -f compose.prod.yaml pull
docker compose --env-file .env.production -f compose.yaml -f compose.prod.yaml \
  up -d postgres redis migrate api worker scheduler frontend
```

Com domínio e e-mail reais, emita o certificado antes de iniciar o proxy TLS:

```bash
docker volume create clinic-confirmations_letsencrypt
docker run --rm -p 80:80 \
  -v clinic-confirmations_letsencrypt:/etc/letsencrypt \
  certbot/certbot:v5.7.0 certonly --standalone \
  -d clinica.example.com -m admin@example.com --agree-tos --no-eff-email
docker compose --env-file .env.production -f compose.yaml -f compose.prod.yaml up -d nginx

curl -fsS https://clinica.example.com/health/ready
curl -fsS https://clinica.example.com/status
```

PostgreSQL e Redis permanecem apenas na rede Docker interna. Senhas e tokens ficam fora do Git.
Renovação TLS, firewall, atualizações, rollback, backup/restauração, GHCR e Portainer estão detalhados
no [guia operacional de deploy](deploy/README.md).

## Uso de IA

A IA foi utilizada como ferramenta de apoio durante o desenvolvimento. Houve geração assistida na
estrutura inicial de módulos, schemas, serviços e repositórios, na migration Alembic, em casos de
teste, nos arquivos de Docker e CI e em rascunhos da documentação. Ela também apoiou a comparação
de alternativas, investigação de falhas reais do CI e revisão de riscos de concorrência e operação.

Esses materiais serviram como ponto de partida e foram modificados conforme as decisões tomadas.
Foram revisados manualmente os fluxos de importação, transições de estado, concorrência, migrations,
configuração dos containers, cenários de teste e instruções operacionais. O resultado também foi
submetido a lint, typecheck, testes unitários e de integração com PostgreSQL e Redis reais, build,
migrations, Docker Compose, smoke test e validação com múltiplos workers.

### Sugestões descartadas ou reformuladas

- **Outbox transacional dedicado:** descartado por adicionar uma entidade e um fluxo para um único
  evento. A solução mantém a reconciliação na própria `ConfirmationMessage`.
- **BackgroundTasks ou thread na API:** descartados porque não atenderiam ao worker independente e
  poderiam perder trabalho no reinício da API.
- **Retry somente pelo Celery:** descartado para manter tentativas, erros e limite auditáveis no
  PostgreSQL.
- **SQLite nos testes críticos:** descartado porque não reproduz enums, locks, constraints e
  concorrência do PostgreSQL.
- **WebSocket:** descartado porque polling adaptativo atende ao fluxo com menor custo operacional.
- **Exibir tentativas em todo envio:** reformulado porque “enviado na primeira tentativa” não ajuda
  o operador; tentativas aparecem durante processamento, retry ou falha.
- **Disparar somente o dia inteiro:** complementado com seleção individual, mantendo também o fluxo
  em lote pedido pelo desafio.

As decisões finais foram tomadas pelo desenvolvedor: normalização de telefones brasileiros,
formatos do CSV, reimportação por fingerprint, falha determinística, reconciliação persistida,
transições de resposta e ajustes de usabilidade do frontend.
