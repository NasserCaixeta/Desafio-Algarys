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
