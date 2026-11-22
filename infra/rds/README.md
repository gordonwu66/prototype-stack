# Dev RDS setup

One-time steps to point the API at the dev RDS Postgres instance. Run commands from the repo root.

The app never uses your AWS root user. It connects to Postgres as its own database roles:

| Role | Used by | Can |
| - | - | - |
| `app` | the API (`DB_USER`) | read and write rows |
| `app_owner` | Alembic, `pnpm db:migrate` (`DB_MIGRATION_USER`) | own and change the schema |

They log in with passwords stored in `apps/api/.env`, which is gitignored. To have them log in with an AWS identity instead of passwords, see [IAM authentication](#optional-iam-authentication).

## 1. Collect the instance details

In the RDS console, open **Databases**, then your instance.

- **Connectivity & security** has the **Endpoint**, the **Port** and the region. These go into `DB_HOST`, `DB_PORT` and `AWS_REGION`.
- **Configuration** has the **Engine version** and the **Master username**. Postgres 18 is assumed; on 17, see `docs/HYBRID_SEARCH.md`, open question 1. The master password is the one you set when creating the instance, or it is in Secrets Manager if you chose "Managed in AWS Secrets Manager".

Your machine has to reach the instance on port 5432. There are two ways:
- **Publicly accessible**: set **Publicly accessible = Yes** on the instance, and add a security-group inbound rule for TCP 5432 from **My IP** only. Never use `0.0.0.0/0`.
- **Private**: keep it private and tunnel through SSM port forwarding from an EC2 instance in the same VPC. Then use `DB_HOST=localhost`, with `DB_SSLMODE=require` (the certificate won't match `localhost`).

## 2. Download the RDS CA bundle

```bash
pnpm db:cert      # saves apps/api/certs/rds-global-bundle.pem (gitignored)
```

The API verifies the server's certificate against this bundle (`DB_SSLMODE=verify-full`).

## 3. Create the database and roles

Run [bootstrap.sql](bootstrap.sql) once as the master user. It creates the two roles and the `prototype` database owned by `app_owner`. It also gives `app` read/write access to every table `app_owner`'s migrations create, and installs pgvector for the search tables.

```bash
export APP_PW=$(openssl rand -hex 24) OWNER_PW=$(openssl rand -hex 24)
psql "host=<endpoint> port=5432 dbname=postgres user=<master user> sslmode=verify-full sslrootcert=apps/api/certs/rds-global-bundle.pem" \
  -v app_password="$APP_PW" -v owner_password="$OWNER_PW" -f infra/rds/bootstrap.sql
echo "DB_PASSWORD=$APP_PW"; echo "DB_MIGRATION_PASSWORD=$OWNER_PW"
```

psql prompts for the master password.

## 4. Fill in `apps/api/.env`

The placeholders are already in `apps/api/.env`, and [`.env.example`](../../apps/api/.env.example) describes each one.

```bash
DB_HOST=<endpoint>
DB_PORT=5432
DB_NAME=prototype
DB_USER=app
DB_PASSWORD=<APP_PW from step 3>
DB_MIGRATION_USER=app_owner
DB_MIGRATION_PASSWORD=<OWNER_PW from step 3>
DB_SSLMODE=verify-full
```

## 5. Migrate and run

```bash
pnpm db:migrate   # as app_owner: creates chat_sessions and chat_messages
pnpm dev:api      # as app
```

On startup, the API checks that it can connect and that the schema is at the latest migration, and stops with a message if not. Migrations never run on startup; run `pnpm db:migrate` after pulling new ones. To add one, edit `apps/api/src/api/db/models.py`, then run `pnpm db:revision "<what changed>"` and review the generated file in `apps/api/alembic/versions/`.

## Optional: IAM authentication

With IAM authentication, the roles log in with 15-minute tokens signed by an AWS identity, so no database password is stored anywhere. Locally, that identity is an IAM user made only for this app. On ECS it becomes the task role, with no keys at all. This path is wired up and its token signing is tested, but it hasn't been run against a real RDS instance yet.

1. **Enable it on the instance:** click **Modify**, choose **Database authentication**, then **Password and IAM database authentication**, and apply immediately.
2. **Create the app's IAM user:** in IAM, go to **Users**, choose **Create user**, and name it `prototype-stack-app`, with no console access. Add this inline policy. The resource ID (`db-…`) is under the instance's **Configuration** tab.

   ```json
   {
     "Version": "2012-10-17",
     "Statement": [
       {
         "Effect": "Allow",
         "Action": "rds-db:connect",
         "Resource": [
           "arn:aws:rds-db:<region>:<account-id>:dbuser:<resource-id>/app",
           "arn:aws:rds-db:<region>:<account-id>:dbuser:<resource-id>/app_owner"
         ]
       }
     ]
   }
   ```

3. **Create an access key:** open the user's **Security credentials**, choose **Create access key**, then **Application running outside AWS**. Either put the key in `apps/api/.env` as `AWS_ACCESS_KEY_ID` / `AWS_SECRET_ACCESS_KEY`, or run `aws configure --profile prototype-stack` and set `AWS_PROFILE=prototype-stack`.
4. **Switch the roles to IAM:** as the master user, run `GRANT rds_iam TO app, app_owner;`. After this, those roles log in only with IAM tokens.
5. **Configure the app:** in `apps/api/.env`, set `DB_IAM_AUTH=true` and `AWS_REGION=<region>`, and clear both `DB_*PASSWORD` values.

Never create access keys for the root user. For your own console and CLI work, an IAM Identity Center user (or an admin IAM user) is safer than root.

## Tests

Tests never touch RDS. `pnpm db:test:up` starts a throwaway Postgres 18 + pgvector 0.8.2 container matching the instance, and `pnpm test:api:db` runs the API tests against it. Plain `pnpm test:api` uses the in-memory store.
