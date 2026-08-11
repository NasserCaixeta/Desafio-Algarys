# Plataforma de confirmação de consultas

Aplicação Full Stack para importar a agenda de uma clínica, disparar confirmações em lote,
acompanhar o processamento assíncrono e registrar a resposta do paciente. O envio é simulado de
forma determinística: nenhum WhatsApp, SMS, e-mail ou serviço pago é utilizado.

O projeto prioriza as propriedades relevantes para operação: migrations versionadas, worker real,
idempotência no banco, processamento concorrente seguro, retries limitados, recuperação de falha de
publicação, logs estruturados, healthchecks, CI e um caminho de deploy em VPS.

## Demonstração do fluxo

1. A clínica envia um CSV pelo frontend ou por `POST /api/v1/imports/appointments`.
2. Linhas válidas são importadas; linhas inválidas voltam no relatório sem abortar o arquivo.
3. Se a agenda exibida estiver vazia, o frontend abre automaticamente a data importada mais
   próxima de hoje; datas com consultas também ficam disponíveis como atalhos.
4. A agenda é filtrada por data e status.
5. O operador dispara as confirmações para os agendamentos selecionados ou para todos daquela data.
6. A API persiste uma única mensagem `pending` por agendamento e publica uma tarefa no Redis.
7. Um worker Celery separado reivindica a mensagem atomicamente e registra a tentativa.
8. O simulador conclui como `sent` ou `failed`; falhas elegíveis voltam com backoff.
9. Depois de `sent`, o operador simula a resposta `confirmed` ou `declined`.

O fluxo completo pode ser executado contra os containers com:

```bash
./scripts/smoke.sh
```

O script é repetível: na segunda execução ele também comprova a idempotência da importação, do
disparo e da resposta.

## Arquitetura

```mermaid
flowchart LR
    B[Browser] -->|HTTP :3000| F[Frontend React<br/>Nginx não root]
    F -->|/api| A[FastAPI :8000<br/>container API]
    A --> P[(PostgreSQL)]
    A --> R[(Redis broker)]
    R --> W[Celery worker<br/>2 processos]
    W --> P
    S[Celery Beat<br/>scheduler] --> R
    R --> W
    W -->|reconcilia, agenda retries<br/>e recupera leases| P
    M[Alembic migrate<br/>one-shot] --> P
```

### Serviços

| Serviço | Responsabilidade | Processo/container |
| --- | --- | --- |
| `frontend` | React estático, SPA fallback e proxy `/api` | Nginx, UID 101 |
| `api` | HTTP, validação de contratos e orquestração dos casos de uso | Uvicorn/FastAPI, UID 10001 |
| `worker` | Consumo, reivindicação atômica, envio simulado e tentativas | Celery worker, UID 10001 |
| `scheduler` | Reconciliação, retry automático e recuperação de lease | Celery Beat, UID 10001 |
| `migrate` | Aplica `alembic upgrade head` antes da aplicação | Job one-shot |
| `postgres` | Fonte de verdade, constraints, locks e histórico | PostgreSQL 17 |
| `redis` | Broker Celery, sem exposição pública em produção | Redis 8 com AOF |
| `nginx` | TLS e reverse proxy de borda no Compose de produção | Nginx 1.28 |

### Organização do backend

```text
backend/src/clinic_confirmations/
├── api/             # rotas, dependências, middleware e tradução de erros
├── schemas/         # contratos Pydantic de entrada e saída
├── services/        # casos de uso e orquestração das regras
├── domain/          # enums, erros e funções puras de domínio
├── repositories/    # consultas, locks e operações SQL atômicas
├── db/models/       # modelos SQLAlchemy e constraints
├── queue/           # Celery, publicação, tarefas e reconciliação
├── sender/          # contrato e simulador determinístico
└── core/            # configuração e logging
```

As rotas validam e traduzem HTTP. Os services coordenam o caso de uso. As garantias contra corrida
ficam nos repositórios e, principalmente, no PostgreSQL. Essa divisão mantém as regras testáveis sem
transformar o desafio em um conjunto de abstrações artificiais.

## Stack

- Backend: Python 3.12+, FastAPI, Pydantic 2, SQLAlchemy 2, Alembic e Psycopg 3.
- Assíncrono: Celery com Redis como broker e Celery Beat como scheduler.
- Banco: PostgreSQL 17.
- Frontend: React 19, TypeScript, Vite e TanStack Query.
- Testes: Pytest, PostgreSQL/Redis reais, Vitest, Testing Library e MSW.
- Qualidade: Ruff, mypy estrito, ESLint e TypeScript.
- Operação: Docker Compose, imagens multi-stage, Nginx, GitHub Actions e GHCR.

## Requisitos locais

Para a execução recomendada basta:

- Docker Engine ou Docker Desktop;
- Docker Compose v2 com suporte a `service_completed_successfully`;
- portas locais `3000`, `8000`, `5433` e `6380` livres.

Para desenvolvimento fora dos containers:

- Python `>=3.12,<3.15`;
- Node.js 22 e npm;
- PostgreSQL e Redis podem continuar nos containers.

## Do clone ao primeiro uso

```bash
git clone https://github.com/NasserCaixeta/Desafio-Algarys.git
cd Desafio-Algarys
cp .env.example .env
docker compose up --build
```

Não existe etapa manual escondida de migration. O serviço `migrate` espera o PostgreSQL ficar
saudável, aplica a migration atual e somente então libera API, worker e scheduler.

Depois que os healthchecks estabilizarem:

- frontend: <http://localhost:3000>;
- Swagger: <http://localhost:8000/docs>;
- OpenAPI JSON: <http://localhost:8000/openapi.json>;
- readiness: <http://localhost:8000/health/ready>;
- status: <http://localhost:8000/status>.

Para parar preservando os dados:

```bash
docker compose down
```

Para remover também os volumes locais, use conscientemente:

```bash
docker compose down --volumes
```

## Configuração

Toda configuração da aplicação vem de variáveis de ambiente. `.env.example` contém o conjunto
completo e valores exclusivamente locais; arquivos `.env*`, exceto o exemplo, são ignorados pelo
Git.

| Variável | Função | Padrão local |
| --- | --- | --- |
| `APP_NAME`, `APP_VERSION`, `APP_ENV` | Identidade e ambiente exposto em `/status` | `Clinic Confirmations`, `1.0.0`, `development` |
| `APP_TIMEZONE` | Interpretação de datas locais e filtro diário | `America/Sao_Paulo` |
| `LOG_LEVEL`, `LOG_JSON` | Nível e formato dos eventos da API/worker | `INFO`, `true` |
| `API_HOST`, `API_PORT` | Bind do Uvicorn | `0.0.0.0`, `8000` |
| `CORS_ORIGINS` | Origins permitidas, separadas por vírgula | localhost |
| `MAX_UPLOAD_BYTES` | Limite lido antes de rejeitar upload | `5242880` |
| `DEPENDENCY_TIMEOUT_SECONDS` | Timeout dos checks de PostgreSQL/Redis | `2` |
| `POSTGRES_DB`, `POSTGRES_USER`, `POSTGRES_PASSWORD` | Inicialização do PostgreSQL | somente desenvolvimento |
| `DATABASE_URL` | DSN SQLAlchemy/Psycopg | PostgreSQL do Compose |
| `TEST_DATABASE_URL` | Banco de integração executado no host | porta `5433` |
| `REDIS_URL`, `TEST_REDIS_URL` | Broker da aplicação e Redis de integração | Compose/porta `6380` |
| `CELERY_QUEUE` | Nome da fila | `confirmations` |
| `CELERY_VISIBILITY_TIMEOUT_SECONDS` | Visibilidade de entrega não confirmada | `3600` |
| `RECONCILIATION_INTERVAL_SECONDS` | Frequência do scheduler | `5` |
| `RECONCILIATION_BATCH_SIZE` | Limite por ciclo | `100` |
| `MAX_MESSAGE_ATTEMPTS` | Limite total por mensagem | `3` |
| `RETRY_BACKOFF_BASE_SECONDS`, `RETRY_BACKOFF_MAX_SECONDS` | Backoff exponencial limitado | `5`, `300` |
| `PROCESSING_LEASE_SECONDS` | Tempo para considerar `processing` abandonado | `120` |
| `SIMULATED_FAILURE_SUFFIXES` | Sufixos de telefone que falham | `0000` |
| `SIMULATED_FAILURE_ATTEMPTS` | Quantas primeiras tentativas falham | `1` |
| `SIMULATED_LATENCY_MS` | Latência artificial do envio | `250` |
| `VITE_API_URL` | API absoluta; vazio usa o proxy da mesma origem | vazio |
| `VITE_API_TIMEOUT_MS`, `VITE_POLL_INTERVAL_MS` | Timeout e polling do frontend | `10000`, `2000` |

Em produção, `POSTGRES_PASSWORD` é obrigatória e o Compose recusa a configuração quando ela não é
informada. Use uma senha hexadecimal longa; como a URL é construída pelo Compose, caracteres
reservados de URL exigiriam percent-encoding.

## CSV

O arquivo deve ser UTF-8 (BOM é aceito), separado por vírgulas e possuir exatamente este cabeçalho:

```csv
data_hora,paciente,telefone,procedimento
```

Regras:

- `data_hora`: aceita `YYYY-MM-DD HH:MM` ou `DD/MM/YYYY HH:MM`;
- a data é interpretada em `APP_TIMEZONE` e armazenada em UTC;
- `paciente` e `procedimento`: obrigatórios, espaços internos normalizados;
- `telefone`: número brasileiro válido, com ou sem código `+55`, normalizado para E.164;
- linhas em branco são ignoradas;
- uma linha inválida é reportada com número, dados originais e motivo, sem abortar as válidas.

O exemplo versionado está em [`examples/appointments.csv`](examples/appointments.csv).

Importação por linha de comando:

```bash
curl -F 'file=@examples/appointments.csv;type=text/csv' \
  http://localhost:8000/api/v1/imports/appointments
```

### Reimportação e duplicidade

O fingerprint é SHA-256 de data/hora UTC, paciente, telefone e procedimento normalizados. A coluna
possui constraint única. Uma reimportação não cria cópia silenciosa: a linha aparece em
`duplicate_lines` e incrementa `summary.duplicates`. Duas linhas iguais no mesmo arquivo seguem a
mesma regra. A resposta também inclui `appointment_dates`, com as datas válidas, únicas e ordenadas
encontradas no arquivo.

## API

Todas as rotas de negócio estão sob `/api/v1`. Swagger e OpenAPI são gerados pelo FastAPI.

| Método | Rota | Uso | Resposta principal |
| --- | --- | --- | --- |
| `POST` | `/api/v1/imports/appointments` | multipart CSV | resumo, datas, linhas importadas, duplicadas e erros |
| `GET` | `/api/v1/appointments` | filtros `date`, `status`, `page`, `page_size` | agenda ordenada e paginada |
| `GET` | `/api/v1/appointments/calendar` | sem parâmetros | datas com consultas e suas quantidades |
| `GET` | `/api/v1/appointments/{id}` | detalhe para a UI | agendamento e mensagem |
| `POST` | `/api/v1/confirmations/dispatch` | `date` e `appointment_ids` opcional | elegíveis, criadas, existentes, ignoradas e enfileiradas |
| `POST` | `/api/v1/appointments/{id}/response` | `confirmed` ou `declined` | estado final da consulta |
| `GET` | `/api/v1/messages` | filtro `status` e paginação | estados de processamento |
| `GET` | `/api/v1/messages/{id}` | detalhe | mensagem e todas as tentativas |
| `POST` | `/api/v1/messages/{id}/retry` | retry manual | mesma mensagem reagendada |
| `GET` | `/health/live` | processo da API vivo | versão |
| `GET` | `/health/ready` | PostgreSQL e Redis alcançáveis | `200` ou `503` |
| `GET` | `/status` | visão operacional não sensível | versão, ambiente, dependências e contagens |

Erros seguem um envelope estável:

```json
{
  "error": {
    "code": "response_conflict",
    "message": "...",
    "details": {},
    "request_id": "..."
  }
}
```

São usados `400/413/422` para entrada inválida, `404` para recurso ausente, `409` para transição ou
retry incompatível e `503` para readiness indisponível.

## Fila, idempotência e concorrência

### Disparo e publicação

1. A API seleciona consultas `pending` do dia na timezone da clínica.
2. Um `INSERT ... ON CONFLICT DO NOTHING` cria `ConfirmationMessage` com status `pending`.
3. A constraint `UNIQUE (appointment_id)` é a garantia final contra duplicidade.
4. A transação é commitada e a tarefa é publicada no Redis.
5. Em sucesso, `enqueued_at` é marcado. Em falha, erro, contador e próxima tentativa de publicação
   ficam persistidos.
6. O scheduler procura mensagens vencidas com `FOR UPDATE SKIP LOCKED` e tenta publicar novamente.

Essa é a estratégia de reconciliação escolhida para o desafio. Ela resolve automaticamente o caso
“banco persistiu, Redis falhou” sem criar uma segunda entidade de outbox.

### Dois ou mais workers

O Compose inicia um worker com dois processos prefork. Também é possível escalar containers:

```bash
docker compose up -d --scale worker=2
```

Cada entrega executa um `UPDATE` condicional de `pending` para `processing`, incrementa
`attempt_count` e recebe um `processing_token` único. Apenas uma transação obtém a linha retornada;
entregas duplicadas se tornam no-op. A finalização exige o mesmo token, então um worker antigo não
pode concluir depois que seu lease expirou e foi recuperado.

Garantias fornecidas:

- no máximo uma `ConfirmationMessage` por agendamento;
- no máximo uma tentativa válida por entrega concorrente;
- tarefas Celery são tolerantes a entrega “at least once”;
- a mesma resposta do paciente é idempotente;
- respostas opostas simultâneas produzem um vencedor e um conflito, nunca overwrite silencioso;
- dois dispatches e dois reconciliadores concorrentes foram testados em PostgreSQL real.

### Retries

Uma falha registra `MessageAttempt` como `failed`, preserva `last_error` e calcula:

```text
delay = min(base * 2^(attempt_number - 1), maximum)
```

O scheduler move falhas vencidas de volta para `pending`; a reconciliação publica a mesma mensagem.
O endpoint manual antecipa esse agendamento. Nenhum retry cria outra `ConfirmationMessage` e o
limite `MAX_MESSAGE_ATTEMPTS` é aplicado no banco/caso de uso. Leases abandonados registram a
tentativa como `abandoned`.

### Resposta do paciente

Somente consultas cuja mensagem está `sent` aceitam resposta. `pending → confirmed` e
`pending → declined` são válidas. Repetir a mesma resposta retorna sucesso; tentar a oposta retorna
`409 response_conflict`.

## Frontend

A interface é responsiva e cobre:

- seletor de data e filtro por status;
- atalhos das datas com agenda, contagem de consultas e navegação automática após importação;
- tabela no desktop e cartões no mobile;
- upload/drag-and-drop, progresso, resumo e erros por linha;
- seleção individual ou dos elegíveis da página e disparo seletivo ou do dia inteiro;
- polling enquanto houver trabalho assíncrono;
- confirmação/recusa somente depois de envio;
- falha temporária ou definitiva, erro, retry automático, ação manual e indicação de limite;
- loading, vazio, erro da API e feedback das ações.

TanStack Query mantém cache, invalidação e polling. O cliente possui timeout e traduz o envelope de
erro da API para mensagens operacionais.

## Migrations

As migrations ficam em `backend/migrations/versions`. A inicial cria enums, tabelas, FKs com
`ON DELETE CASCADE`, checks, índices e as constraints únicas de importação/idempotência.

Aplicar até a versão atual:

```bash
docker compose run --rm migrate alembic upgrade head
```

Ver a versão atual:

```bash
docker compose run --rm migrate alembic current
```

Reverter a última migration:

```bash
docker compose run --rm migrate alembic downgrade -1
```

Reaplicar:

```bash
docker compose run --rm migrate alembic upgrade head
```

Criar uma migration durante o desenvolvimento, com o ambiente Python instalado:

```bash
DATABASE_URL='postgresql+psycopg://clinic:clinic_local_password@localhost:5433/clinic_confirmations' \
  .venv/bin/alembic -c backend/alembic.ini revision --autogenerate -m 'descricao curta'
```

Revise sempre o arquivo gerado antes de executar. Nunca faça downgrade de produção sem backup e
sem confirmar compatibilidade com a versão anterior da aplicação.

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

A suíte usa PostgreSQL real, não SQLite, para testar constraints, `FOR UPDATE`, `SKIP LOCKED` e
corridas. Ela cobre CSV válido/parcial/inválido, filtros, idempotência, publicação, Redis real,
processamento, retries, lease, duplicidade de entrega, respostas e healthchecks.

### Frontend

```bash
cd frontend
npm ci
npm run lint
npm run typecheck
npm run test -- --run --coverage
npm run build
```

Os testes usam Vitest, Testing Library e MSW em nível HTTP. Não substituem os hooks da aplicação por
mocks de implementação.

### Smoke

```bash
./scripts/smoke.sh
```

O smoke sobe/reconstrói os serviços, importa o exemplo, lista, dispara, aguarda Celery, verifica uma
tentativa simples e outra `failed → sent`, registra resposta e confere o filtro `confirmed`.

## CI e GHCR

`.github/workflows/ci.yml` roda em todo push e pull request:

1. backend: cache pip, Ruff, mypy, upgrade/downgrade/re-upgrade, 131 testes e cobertura mínima 90%;
2. frontend: cache npm, ESLint, typecheck, 22 testes com cobertura e build;
3. containers: valida os dois Compose, constrói imagens e executa o smoke completo;
4. em falha do smoke, publica os logs dos containers e sempre remove os volumes do runner.

O resultado verde aparece na aba **Actions** e no check **CI** do commit/PR. O job de containers só
começa depois de backend e frontend passarem.

`.github/workflows/publish.yml` publica imagens `linux/amd64` e `linux/arm64` em tags `v*` ou por
disparo manual:

```bash
git tag v1.0.0
git push origin v1.0.0
```

Imagens geradas:

- `ghcr.io/<owner>/clinic-confirmations-api:<tag>`;
- `ghcr.io/<owner>/clinic-confirmations-worker:<tag>`;
- `ghcr.io/<owner>/clinic-confirmations-frontend:<tag>`.

O workflow usa `GITHUB_TOKEN` com apenas `contents:read` e `packages:write`.

## Healthchecks e logs

PostgreSQL usa `pg_isready`; Redis usa `redis-cli ping`; API usa `/health/ready`; worker usa
`celery inspect ping`; scheduler verifica o processo PID 1; frontend usa `/nginx-health`. As
dependências no Compose são condicionadas à saúde ou à conclusão da migration.

API e eventos próprios do worker são JSON por linha, por exemplo:

```json
{"service":"worker","message_id":"...","appointment_id":"...","correlation_id":"...","attempt_number":2,"event":"message_processing_completed","level":"info","timestamp":"..."}
```

A API aceita ou gera `X-Request-ID`, devolve o header e o persiste como `correlation_id` da mensagem.
Eventos incluem, quando aplicável, serviço, nível, timestamp, request/correlation ID, mensagem,
tentativa, status e erro. Logs nativos de Uvicorn/Celery continuam textuais ao redor dos eventos da
aplicação. Não são logados DSNs, senhas, conteúdo do CSV ou telefone completo.

## Decisões arquiteturais

| Decisão | Justificativa |
| --- | --- |
| Monólito modular + worker | Escopo coeso, deploy simples e separação real onde a assincronicidade exige |
| PostgreSQL como fonte de verdade | Constraints e locks fornecem garantias que checks em memória não fornecem |
| Reconciliação persistida | Recupera dual-write banco/Redis com complexidade proporcional ao desafio |
| Celery Beat separado | Retry/reconciliação automáticos sem loop ou thread dentro da API |
| Falha por sufixo + N tentativas | Cenários reproduzíveis e testes estáveis, sem aleatoriedade |
| UTC no banco e timezone na borda | Evita filtros diários e comparações ambíguas |
| Resposta somente após `sent` | Impede estado de negócio sem uma confirmação efetivamente simulada |
| Frontend same-origin via Nginx | Evita URL de API embutida e simplifica CORS/TLS em produção |

### Alternativas consideradas

- **Outbox transacional dedicado:** oferece um log de eventos mais geral; foi preterido pela opção
  aprovada de campos de reconciliação na própria mensagem, suficiente para este único tipo de evento.
- **FastAPI BackgroundTasks/thread:** mais simples, mas não é worker independente e perde trabalho ao
  reiniciar a API.
- **SQLite nos testes:** rápido, porém não reproduz locks, enums e concorrência do PostgreSQL.
- **Retry nativo opaco do Celery:** não deixaria cada tentativa e erro como fonte auditável no domínio.
- **WebSocket:** polling adaptativo é menor e suficiente para o volume demonstrado.

### Deliberadamente não implementado

- integração real com WhatsApp/SMS/e-mail ou serviço pago;
- autenticação/RBAC, porque não há requisito de usuários e ela bloquearia a demonstração;
- Kubernetes ou microsserviços artificiais;
- aleatoriedade na simulação;
- Prometheus, tracing distribuído e stack pesada de observabilidade;
- funcionalidades clínicas fora do desafio.

## Limitações e riscos de produção

- PostgreSQL e Redis são instâncias únicas; não há HA, replica ou failover.
- Redis usa AOF, mas não é uma fila com garantia exatamente uma vez. Se uma tarefa já marcada como
  enfileirada for perdida por perda total do Redis, a mensagem pode permanecer `pending`; um outbox
  dedicado ou lease de publicação seria a evolução natural.
- A estratégia fornece entrega “at least once”, não exactly-once físico. O banco impede duas
  tentativas válidas simultâneas, mas uma queda depois de o provedor externo aceitar o envio e antes
  da finalização no PostgreSQL pode causar reenvio após o lease. Uma integração real deve passar
  `message_id` como chave de idempotência ao provedor e reconciliar pelo identificador externo.
- Não há DLQ, painel de métricas, alertas ou rate limiting.
- Não há autenticação; em produção a rede/UI deve ser restrita até RBAC ser implementado.
- O telefone é validado como brasileiro; internacionalização exigiria regra explícita por país.
- O simulador não representa limites, templates ou callbacks de um provedor real.
- Backup e renovação TLS dependem de agendamento/monitoramento do operador da VPS.
- Alterar a migration em produção sem uma estratégia expand/contract pode impedir rollback da imagem.

O que pode quebrar em produção: DNS ainda não propagado impede certificado; portas 80/443 bloqueadas
impedem ACME; senha com caractere reservado sem encoding quebra o DSN; falta de disco interrompe
PostgreSQL/AOF/logs; relógio incorreto afeta leases; Redis apagado depois do marcador `enqueued_at`
pode deixar trabalho pendente; imagem e schema incompatíveis podem impedir rollback.

Com mais tempo, as prioridades seriam: autenticação/RBAC, outbox/lease de publicação mais forte,
DLQ e alertas, métricas de fila/tentativas, backup automatizado com teste de restauração, testes E2E
de navegador na CI e deploy blue/green com migrations expand/contract.

## Deploy em VPS

Pré-requisitos: Ubuntu/Debian atualizado, Docker + Compose v2, domínio apontando para a VPS,
credencial de leitura do GHCR se as imagens forem privadas e portas 22/80/443 liberadas. PostgreSQL,
Redis, API e frontend não publicam portas no override de produção.

### 1. Preparar host e configuração

```bash
sudo install -d -m 0750 -o "$USER" -g "$USER" /opt/clinic-confirmations
git clone <URL_DO_REPOSITORIO> /opt/clinic-confirmations
cd /opt/clinic-confirmations
cp .env.example .env.production
```

Edite `.env.production` e defina, no mínimo:

```dotenv
APP_ENV=production
DOMAIN=clinica.example.com
GHCR_OWNER=seu-usuario-ou-org
IMAGE_TAG=1.0.0
POSTGRES_PASSWORD=<SAIDA_DE_openssl_rand_hex_32>
CORS_ORIGINS=https://clinica.example.com
VITE_API_URL=
```

Gere a senha com `openssl rand -hex 32`. Não versione `.env.production`.

### 2. Autenticar e iniciar o núcleo

```bash
echo '<GHCR_READ_TOKEN>' | docker login ghcr.io -u '<GHCR_USER>' --password-stdin
docker compose --env-file .env.production -f compose.yaml -f compose.prod.yaml pull
docker compose --env-file .env.production -f compose.yaml -f compose.prod.yaml \
  up -d postgres redis migrate api worker scheduler frontend
```

### 3. Emitir o primeiro certificado

Antes de iniciar o Nginx TLS, a porta 80 deve estar livre:

```bash
docker volume create clinic-confirmations_letsencrypt
docker run --rm -p 80:80 \
  -v clinic-confirmations_letsencrypt:/etc/letsencrypt \
  certbot/certbot:v5.7.0 certonly --standalone \
  -d clinica.example.com -m admin@example.com --agree-tos --no-eff-email
docker compose --env-file .env.production -f compose.yaml -f compose.prod.yaml up -d nginx
```

Troque domínio/e-mail pelos reais. O Nginx de produção redireciona HTTP para HTTPS, serve o desafio
ACME por webroot, aplica HSTS e encaminha `/api`, Swagger/health e frontend aos serviços internos.

### 4. Renovação HTTPS

Teste a renovação:

```bash
docker compose --env-file .env.production -f compose.yaml -f compose.prod.yaml \
  --profile tls run --rm certbot renew --dry-run --webroot --webroot-path=/var/www/certbot
```

Agende diariamente no cron da VPS e recarregue somente após sucesso:

```cron
17 3 * * * cd /opt/clinic-confirmations && docker compose --env-file .env.production -f compose.yaml -f compose.prod.yaml --profile tls run --rm certbot && docker compose --env-file .env.production -f compose.yaml -f compose.prod.yaml exec -T nginx nginx -s reload
```

### 5. Firewall

```bash
sudo ufw default deny incoming
sudo ufw default allow outgoing
sudo ufw allow OpenSSH
sudo ufw allow 80/tcp
sudo ufw allow 443/tcp
sudo ufw enable
```

Nunca libere 5432/6379. No Compose de produção esses serviços existem apenas na rede Docker interna.

### 6. Atualização e rollback

```bash
cd /opt/clinic-confirmations
git pull --ff-only
docker compose --env-file .env.production -f compose.yaml -f compose.prod.yaml pull
docker compose --env-file .env.production -f compose.yaml -f compose.prod.yaml up -d
docker compose --env-file .env.production -f compose.yaml -f compose.prod.yaml ps
```

Para rollback da aplicação, restaure `IMAGE_TAG` para a tag anterior, execute `pull` e `up -d`.
Downgrade de schema é uma decisão separada: faça backup, confirme compatibilidade e então use o
comando Alembic explícito. Não associe automaticamente rollback de imagem a downgrade destrutivo.

### 7. Backup e restauração

Backup custom format (ajuste usuário/banco se alterados):

```bash
docker compose --env-file .env.production -f compose.yaml -f compose.prod.yaml \
  exec -T postgres pg_dump -U clinic -d clinic_confirmations -Fc > clinic.dump
```

Restauração substitui dados existentes; pare escritores e confirme o arquivo antes:

```bash
docker compose --env-file .env.production -f compose.yaml -f compose.prod.yaml \
  stop api worker scheduler
docker compose --env-file .env.production -f compose.yaml -f compose.prod.yaml \
  exec -T postgres pg_restore -U clinic -d clinic_confirmations --clean --if-exists < clinic.dump
docker compose --env-file .env.production -f compose.yaml -f compose.prod.yaml \
  up -d migrate api worker scheduler
```

Copie backups para armazenamento externo e teste restauração periodicamente.

### 8. Logs e verificação

```bash
docker compose --env-file .env.production -f compose.yaml -f compose.prod.yaml ps
docker compose --env-file .env.production -f compose.yaml -f compose.prod.yaml logs -f api worker
curl -fsS https://clinica.example.com/health/ready
curl -fsS https://clinica.example.com/status
```

Configure rotação do Docker daemon e alertas externos para healthcheck, disco, backup e expiração TLS.

### Portainer

1. Em **Registries**, cadastre `ghcr.io` com usuário e token `read:packages`.
2. Use um endpoint **Docker Standalone**, não Swarm, pois o stack depende das condições de saúde do
   Compose.
3. Em **Stacks → Add stack → Repository**, informe o Git do projeto e use o caminho
   `deploy/portainer/stack.yaml`. O modo Git é necessário para levar também o template Nginx relativo.
4. Cadastre no formulário de ambiente pelo menos `DOMAIN`, `GHCR_OWNER`, `IMAGE_TAG` e uma
   `POSTGRES_PASSWORD` hexadecimal forte. Não salve esses valores no repositório.
5. Emita o primeiro certificado no host como descrito acima e então faça o deploy/redeploy do stack.
6. Para atualizar, altere `IMAGE_TAG`, habilite **Re-pull image** e use **Update the stack**.
7. Verifique `migrate` concluído, healthchecks verdes e os logs antes de remover a tag anterior.

Portainer não substitui backup, controle de migration nem rollback documentado.

## Uso de IA

Este projeto foi desenvolvido com apoio de IA e isso faz parte do processo registrado.

### Onde a IA foi usada

- condução do brainstorming e comparação de alternativas;
- geração assistida de código, migrations, testes, Docker, CI e documentação;
- depuração a partir de falhas reais e revisão sistemática do diff;
- execução/organização das evidências de testes, builds, containers e smoke.
