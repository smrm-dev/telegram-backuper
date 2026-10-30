# Telegram Backuper

A local web UI to sign in to Telegram, choose source and destination chats,
and start a backup. Messages are saved to MongoDB first, then sent from the
archive to the destination as new messages. Attachments are downloaded locally
and uploaded when sending. Everything runs on your computer.

## Run with Docker Compose

```sh
cp .env.example .env
mkdir -p sessions
```

Set `API_ID` and `API_HASH` in `.env` using your Telegram application credentials
from [my.telegram.org](https://my.telegram.org).

```sh
docker compose up --build -d
```

Open [localhost:8080](http://localhost:8080).

1. Enter your phone number, then the code Telegram sends you. Enter your
   two-step verification password if requested.
2. Select a source chat and a different destination chat. Refresh chats if needed.
3. Click **Start / resume backup**. Progress appears below the controls.
4. Use **Stop** to pause or **Log out** to stop the job and revoke this UI's
   Telegram session. Closing the browser does not stop a running backup.

One account and one backup run are supported at a time. All browser tabs share
that account and job. The UI is published only on the host loopback interface.

Each run copies the source history available at its start, oldest first. Run it
again to pick up newer messages. Progress is scoped to the signed-in account,
source, and destination. Completed messages are skipped on resume. A crash or
stop between Telegram accepting a message and MongoDB recording it can cause a
duplicate on resume. Failures stop the job; inspect logs and resume after fixing
the cause. Telegram flood waits are respected automatically.

The account must be allowed to read the source and post to the destination.
Service messages are archived but skipped for sending. Text, formatting,
photos, documents, audio, and video are saved and sent individually. Album grouping,
replies, edits, and deletions are not mirrored. Web previews may be regenerated.
Other media types stop the archive with an error rather than silently lose data.
Telegram can still reject downloads or sends based on account permissions.

Attachments persist under `/data/media` in the `app_data` volume (or `media/`
for local Python execution); MongoDB stores their paths and message content.
The entire available history is archived before delivery begins. Sending reads
saved MongoDB records and local attachment files; it never forwards Telegram
messages. Failed sends remain pending and are retried on resume.

## Data and troubleshooting

MongoDB is internal to Compose at `mongodb://mongodb:27017/` and persists in
`mongodb_data`. UI archives and cursors use the `ui_messages` and `ui_progress`
collections in `telegram_backup`. Legacy CLI data is not imported into UI jobs.
Telegram's reusable session is stored in `sessions/ui.session` on the host.
Treat session files as credentials. Logout revokes the UI session; archived
messages and progress remain available for future sign-ins.

```sh
docker compose logs -f ui
docker compose down
```

Stopping containers preserves saved data. `docker compose down --volumes`
deletes MongoDB and the `app_data` volume, but not the host `sessions/` folder.

## Run without Docker

Install Python 3.10+, [uv](https://docs.astral.sh/uv/), and MongoDB, then:

```sh
uv sync --locked
cp .env.example .env
# Set API_ID and API_HASH, and MONGODB_URI if needed.
uv run python ui.py
```

Open [localhost:8080](http://localhost:8080). Local Python execution binds to
127.0.0.1 by default. The original `backup.py`, `send.py`, and `sign_in.py`
remain available as legacy scripts and require their additional chat/account
settings; the UI does not use those scripts or their session files.
