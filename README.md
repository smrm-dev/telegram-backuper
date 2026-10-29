# Telegram Backuper

Manage dependencies and run the scripts with [uv](https://docs.astral.sh/uv/).
Python 3.10 or newer is required.

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

Use numeric values for all fields except `API_HASH`. MongoDB must be running at
`mongodb://localhost:27017/`; the scripts use the `telegram_backup` database.

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
