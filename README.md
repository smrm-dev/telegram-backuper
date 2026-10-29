# Telegram Backuper

Manage dependencies and run the scripts with [uv](https://docs.astral.sh/uv/).
Python 3.10 or newer is required.

## Run with Docker Compose

With Docker and Docker Compose installed, Python, uv, and MongoDB do not need
to be installed on the host. The app and MongoDB run in separate containers.

```sh
cp .env.example .env
mkdir -p sessions
```

Edit `.env` with your Telegram credentials and chat settings, then build:

```sh
docker compose build
```

Run a backup (interactive Telegram login is supported):

```sh
docker compose run --rm app
```

Send stored messages:

```sh
docker compose run --rm app python /app/send.py
```

Both commands start MongoDB automatically and wait until it is healthy.
MongoDB is available to the app at `mongodb://mongodb:27017/`; its port is
not published to the host. Compose sets `MONGODB_URI` to this internal address.

MongoDB messages persist in the `mongodb_data` named volume. The backup cursor
(`last_message_id.txt`) persists in the `app_data` named volume. Telegram
sessions persist in the host's `sessions/` directory. Existing host MongoDB
data and the host's `last_message_id.txt` are not automatically imported.

Stop containers while retaining saved data:

```sh
docker compose down
```

`docker compose down --volumes` deletes the database and backup cursor volumes.
Run commands from the same project directory to reuse the same volumes.

The existing `sign_in.py` starts at account 21. To use it, set
`NUMBER_OF_ACCOUNTS` above 21 and run it inside the mounted session directory:

```sh
docker compose run --rm -w /data/sessions app python /app/sign_in.py
```

This writes `sessions/account_N.session` on the host, ready for `send.py`.
`backup.py` creates its own `sessions/session_name.session` on first login.

## Setup

```sh
uv sync --locked
mkdir -p sessions
```

Create a `.env` file in the project root with these values:

```dotenv
API_ID=your_telegram_api_id
API_HASH=your_telegram_api_hash
SOURCE_CHAT_ENTITY=your_source_chat_id
TARGET_CHAT_ID=your_target_chat_id
NUMBER_OF_ACCOUNTS=your_account_count
BATCH_SIZE=your_batch_size
```

Use numeric values for all fields except `API_HASH`. For local Python execution,
MongoDB defaults to `mongodb://localhost:27017/`; set `MONGODB_URI` in `.env` to
use another address. The scripts use the `telegram_backup` database.

## Run

Run commands from the project root:

```sh
uv run python backup.py
uv run python send.py
uv run python sign_in.py
```

`backup.py` uses `sessions/session_name`. `send.py` uses `sessions/account_N`.
`sign_in.py` currently starts at account 21 and writes `account_N.session` in
the project root; adjust its `start_from` value as needed and move those session
files into `sessions/` before using them with `send.py`.

## Dependencies

Dependencies are declared in `pyproject.toml`, with resolved versions in
`uv.lock`. To add or update dependencies:

```sh
uv add package-name
uv lock --upgrade
uv sync --locked
```
