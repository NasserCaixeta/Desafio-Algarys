# Guia operacional de deploy

Este documento complementa o passo a passo resumido da README com os procedimentos de operação em
uma VPS. A configuração utiliza `compose.yaml` e `compose.prod.yaml`, imagens publicadas no GHCR e
Nginx como proxy TLS. PostgreSQL, Redis, API e frontend não publicam portas no override de produção.

## Pré-requisitos

- Ubuntu ou Debian atualizado;
- Docker Engine e Docker Compose v2;
- domínio apontando para a VPS;
- credencial de leitura do GHCR, caso as imagens sejam privadas;
- portas 22, 80 e 443 liberadas.

## 1. Preparar host e configuração

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

## 2. Autenticar e iniciar os serviços internos

```bash
echo '<GHCR_READ_TOKEN>' | docker login ghcr.io -u '<GHCR_USER>' --password-stdin
docker compose --env-file .env.production -f compose.yaml -f compose.prod.yaml pull
docker compose --env-file .env.production -f compose.yaml -f compose.prod.yaml \
  up -d postgres redis migrate api worker scheduler frontend
```

## 3. Emitir o primeiro certificado

Antes de iniciar o Nginx TLS, a porta 80 deve estar livre:

```bash
docker volume create clinic-confirmations_letsencrypt
docker run --rm -p 80:80 \
  -v clinic-confirmations_letsencrypt:/etc/letsencrypt \
  certbot/certbot:v5.7.0 certonly --standalone \
  -d clinica.example.com -m admin@example.com --agree-tos --no-eff-email
docker compose --env-file .env.production -f compose.yaml -f compose.prod.yaml up -d nginx
```

Troque domínio e e-mail pelos valores reais. O Nginx redireciona HTTP para HTTPS, serve o desafio
ACME por webroot, aplica HSTS e encaminha API, documentação, healthchecks e frontend aos serviços
internos.

## 4. Renovar o certificado

Teste a renovação antes de agendá-la:

```bash
docker compose --env-file .env.production -f compose.yaml -f compose.prod.yaml \
  --profile tls run --rm certbot renew --dry-run --webroot --webroot-path=/var/www/certbot
```

Exemplo de agendamento diário no cron da VPS:

```cron
17 3 * * * cd /opt/clinic-confirmations && docker compose --env-file .env.production -f compose.yaml -f compose.prod.yaml --profile tls run --rm certbot && docker compose --env-file .env.production -f compose.yaml -f compose.prod.yaml exec -T nginx nginx -s reload
```

## 5. Configurar o firewall

```bash
sudo ufw default deny incoming
sudo ufw default allow outgoing
sudo ufw allow OpenSSH
sudo ufw allow 80/tcp
sudo ufw allow 443/tcp
sudo ufw enable
```

Não libere 5432 ou 6379. No Compose de produção, PostgreSQL e Redis existem apenas na rede Docker
interna.

## 6. Atualizar e reverter a aplicação

```bash
cd /opt/clinic-confirmations
git pull --ff-only
docker compose --env-file .env.production -f compose.yaml -f compose.prod.yaml pull
docker compose --env-file .env.production -f compose.yaml -f compose.prod.yaml up -d
docker compose --env-file .env.production -f compose.yaml -f compose.prod.yaml ps
```

Para rollback, restaure `IMAGE_TAG` para a tag anterior e execute novamente `pull` e `up -d`.
Downgrade de schema é uma decisão separada: faça backup, confirme a compatibilidade com a versão
anterior da aplicação e só então execute o comando Alembic explícito.

## CD automático da main

O workflow `.github/workflows/deploy.yml` é acionado por `workflow_run`, depois que o workflow
**CI** termina na `main`. Ele ainda verifica que a execução veio de um `push` no próprio
repositório e que a conclusão foi `success`. Assim, pull requests e execuções com falha não recebem
segredos de produção nem publicam uma nova versão.

Cada commit aprovado recebe uma tag imutável `sha-<commit-completo>` nas imagens da API, worker e
frontend. O deploy é pull-based: a VPS não expõe um endpoint de implantação e o GitHub não precisa
alcançar o SSH. Um timer root-owned consulta `origin/main` por HTTPS e só aceita a versão quando as
três imagens daquele SHA já existem no GHCR. Se o CI ainda estiver executando ou uma publicação
estiver incompleta, o watcher termina sem alterar a aplicação e tenta novamente no minuto seguinte.

Quando encontra uma release completa, `deploy/scripts/bootstrap.sh` confirma que o commit pertence
à `main`, recusa versões anteriores à atualmente implantada e executa o script versionado de
deploy. `flock` impede concorrência na VPS. O processo valida o Compose, mantém até cinco dumps
locais pré-migration, executa a migration e substitui os containers. A conclusão exige PostgreSQL,
Redis, API, worker, scheduler, frontend e Nginx saudáveis, além de readiness/status internos e
liveness público.

O job `Release for production watcher` registra no Environment `production` que as três imagens
imutáveis estão disponíveis. A confirmação da implantação é feita na própria VPS: o script só
grava a nova release como concluída depois dos healthchecks, de `/status` interno e do liveness
público; em falha, restaura o checkout e as imagens anteriores. Consulte a evidência com
`journalctl -u clinic-confirmations-cd.service`.

Os runners hospedados do GitHub não conseguem estabelecer conexão de entrada com esta VPS (SSH e
HTTPS expiram antes de alcançar o servidor). Por isso, o workflow não tenta validar a URL pública e
o watcher usa apenas conexões de saída. Essa separação evita um falso resultado vermelho após um
deploy saudável e também evita instalar um runner persistente dentro de uma VPS ligada a um
repositório público.

### Instalar o watcher na VPS

Instale os scripts e units como root; os arquivos do repositório não substituem automaticamente
essas cópias privilegiadas:

```bash
cd /opt/clinic-confirmations
sudo install -m 0755 -o root -g root deploy/scripts/bootstrap.sh \
  /usr/local/sbin/clinic-confirmations-deploy
sudo install -m 0755 -o root -g root deploy/scripts/watch-release.sh \
  /usr/local/sbin/clinic-confirmations-watch-release
sudo install -m 0644 -o root -g root deploy/systemd/clinic-confirmations-cd.service \
  /etc/systemd/system/clinic-confirmations-cd.service
sudo install -m 0644 -o root -g root deploy/systemd/clinic-confirmations-cd.timer \
  /etc/systemd/system/clinic-confirmations-cd.timer
sudo systemctl daemon-reload
sudo systemctl enable --now clinic-confirmations-cd.timer
```

Valide o agendamento e uma execução manual:

```bash
systemctl list-timers clinic-confirmations-cd.timer
sudo systemctl start clinic-confirmations-cd.service
journalctl -u clinic-confirmations-cd.service --since today
```

O timer usa somente conexões de saída HTTPS e acesso local ao Docker. Um runner self-hosted não foi
adotado porque este é um repositório público e código de workflows executado no host aumentaria a
superfície de ataque da VPS.

### Configurar o GitHub Environment

Crie o Environment `production` e limite a origem do deploy à branch `main`. Cadastre estas
variáveis de ambiente:

| Variável | Exemplo |
| --- | --- |
| `PRODUCTION_URL` | `https://clinica.example.com` |

Com GitHub CLI autenticado, o valor pode ser enviado sem gravá-lo no repositório:

```bash
gh variable set PRODUCTION_URL --env production --body 'https://clinica.example.com'
```

As senhas do PostgreSQL, o Basic Auth, o login do GHCR e os certificados permanecem apenas na VPS.
Se as imagens forem privadas, autentique o Docker da VPS uma vez com um token limitado a
`read:packages`.

### Rollback do CD

Se migration, inicialização ou healthcheck falhar, o script restaura automaticamente o checkout,
`IMAGE_TAG`, `APP_VERSION` e containers da versão anterior. Os arquivos de estado e backups ficam
em `.deploy/`, ignorado pelo Git. Os logs do workflow mostram se o rollback também ficou saudável.

O rollback não executa `alembic downgrade` nem restaura o dump automaticamente. Uma migration nova
deve permanecer compatível com a imagem anterior para que o rollback de aplicação seja seguro. Se
isso não for possível, use uma migration expand/contract e remova estruturas antigas somente em
uma entrega posterior.

Para acompanhar uma entrega, abra **Actions → CD**. O deployment também aparece no Environment
`production`, associado ao SHA exato que está na VPS.

## 7. Fazer backup e restauração

Backup em formato customizado, ajustando usuário e banco caso tenham sido alterados:

```bash
docker compose --env-file .env.production -f compose.yaml -f compose.prod.yaml \
  exec -T postgres pg_dump -U clinic -d clinic_confirmations -Fc > clinic.dump
```

A restauração substitui dados existentes. Confirme o arquivo e pare os processos escritores:

```bash
docker compose --env-file .env.production -f compose.yaml -f compose.prod.yaml \
  stop api worker scheduler
docker compose --env-file .env.production -f compose.yaml -f compose.prod.yaml \
  exec -T postgres pg_restore -U clinic -d clinic_confirmations --clean --if-exists < clinic.dump
docker compose --env-file .env.production -f compose.yaml -f compose.prod.yaml \
  up -d migrate api worker scheduler
```

Mantenha cópias em armazenamento externo e teste a restauração periodicamente.

## 8. Verificar e acompanhar

```bash
docker compose --env-file .env.production -f compose.yaml -f compose.prod.yaml ps
docker compose --env-file .env.production -f compose.yaml -f compose.prod.yaml logs -f api worker
curl -fsS https://clinica.example.com/health/ready
curl -fsS https://clinica.example.com/status
```

Configure rotação dos logs do Docker e alertas externos para healthcheck, espaço em disco, backup e
expiração do certificado.

## GHCR

O workflow `.github/workflows/publish.yml` publica imagens `linux/amd64` e `linux/arm64` quando uma
tag `v*` é enviada ou quando o workflow é iniciado manualmente:

```bash
git tag v1.0.0
git push origin v1.0.0
```

Imagens publicadas:

- `ghcr.io/<owner>/clinic-confirmations-api:<tag>`;
- `ghcr.io/<owner>/clinic-confirmations-worker:<tag>`;
- `ghcr.io/<owner>/clinic-confirmations-frontend:<tag>`.

O workflow usa `GITHUB_TOKEN` limitado a `contents:read` e `packages:write`.

## Portainer

1. Em **Registries**, cadastre `ghcr.io` com usuário e token `read:packages`.
2. Use um endpoint **Docker Standalone**, não Swarm, pois o stack depende das condições de saúde do
   Compose.
3. Em **Stacks → Add stack → Repository**, informe o Git do projeto e use
   `deploy/portainer/stack.yaml`. O modo Git também disponibiliza o template relativo do Nginx.
4. Cadastre `DOMAIN`, `GHCR_OWNER`, `IMAGE_TAG` e uma `POSTGRES_PASSWORD` hexadecimal forte no
   formulário de ambiente. Não salve esses valores no repositório.
5. Emita o primeiro certificado no host e faça o deploy ou redeploy do stack.
6. Para atualizar, altere `IMAGE_TAG`, habilite **Re-pull image** e use **Update the stack**.
7. Verifique a conclusão de `migrate`, os healthchecks e os logs antes de remover a tag anterior.

Portainer não substitui backup, controle de migration nem rollback documentado.
