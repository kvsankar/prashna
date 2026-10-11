# Prashna

![How prashna brings an admin, moderators, participants and a projector into one live session for Q&A and quizzes, and what it produces afterwards](https://raw.githubusercontent.com/kvsankar/prashna/main/docs/images/prashna-infographic.png)

*How prashna runs a session with an audience: an admin sets it up, a moderator runs the room, participants join on their phones and the projector shows the room the same state. Questions are asked and upvoted, versioned quizzes are run question by question, and the session ends with ranked questions, quiz results, run reports, attendee profiles and feedback. The [infographic source](https://github.com/kvsankar/prashna/blob/main/docs/images/prashna-infographic.html) is kept with the image.*

A live Q&A and quiz tool for any session with an audience: training,
lectures, workshops, town halls, meetups. *Prashna* (प्रश्न) is
Sanskrit for *question*.

Two core features:

- **Anonymous Q&A.** Participants post questions and upvote each other's.
  The moderator responds in text or out loud. A removed question is hidden
  from participants and kept for the record.
- **Moderator-run quizzes.** Single- or multiple-choice questions, optional
  images, anonymous answers, results revealed one question at a time, a lobby
  screen on the projector, and optional live counts while people answer.
  Quizzes are versioned: editing a quiz never changes the report of a past
  run.

A **projector view** for the screen at the front of the room shows the join
code, a QR code for the participant link, the top questions, and the current
quiz question in step with the moderator.

The admin can **export** sessions, Q&A questions, attendee profiles,
feedback, quiz runs, and quizzes as JSON or as an Excel workbook.

## Install

Choose one of these. Each installs the same `prashna` command.

**One command, on macOS, Linux, or Windows.** Works on a machine without
Python; it installs [uv](https://docs.astral.sh/uv/), which fetches Python if
needed.

```bash
curl -LsSf https://kvsankar.github.io/prashna/install.sh | sh                  # macOS / Linux
powershell -ExecutionPolicy ByPass -c "irm https://kvsankar.github.io/prashna/install.ps1 | iex"   # Windows
```

**Already have Python 3.11 or newer?** Install without uv, using
[pipx](https://pipx.pypa.io/):

```bash
pipx install prashna
```

Or use pip inside a virtual environment:

```bash
python3 -m venv ~/.prashna
~/.prashna/bin/pip install prashna          # Windows: ~\.prashna\Scripts\pip install prashna
```

A plain `pip install` into the system Python is refused on Debian, Ubuntu,
and some other Linux distributions ("externally-managed-environment"); the
virtual environment avoids that.

**Already have uv?** `uvx prashna` installs and starts it in one step.

Then start it:

```bash
prashna                                     # virtual environment: ~/.prashna/bin/prashna
```

Update with `uv tool upgrade prashna`, `pipx upgrade prashna`, or
`~/.prashna/bin/pip install --upgrade prashna`. `prashna --help` lists the
options: port, data folder, and backups.

## First run

`prashna` serves on <http://127.0.0.1:8000> and opens your browser on a
one-time page where you choose the admin's username and password. The page
works once. After that, sign in to create sessions and write quizzes.
Prashna keeps its data in your app-data folder.

## Share over the internet

To let people join from their own phones over the internet, start Prashna
with a tunnel:

```bash
prashna --tunnel cloudflare      # Cloudflare quick tunnel: no account needed
prashna --tunnel ngrok           # ngrok: uses your signed-in ngrok
```

Prashna starts the tunnel, waits until its public address works, and prints
it (`Participants join at: https://…`). Participant links and the projector's
QR code use that address automatically, while you keep using
`http://127.0.0.1:8000` yourself. Ctrl+C stops Prashna and the tunnel
together.

You need the tunnel program once:

- **Cloudflare:** install `cloudflared` (macOS: `brew install cloudflared`;
  Windows: `winget install --id Cloudflare.cloudflared`; Linux:
  [Cloudflare's downloads](https://developers.cloudflare.com/cloudflare-one/connections/connect-networks/downloads/)).
  No account is needed.
- **ngrok:** install it from [ngrok.com/download](https://ngrok.com/download)
  and sign in once with `ngrok config add-authtoken <your token>`.

On the free plans they differ like this:

| | Cloudflare quick tunnel | ngrok free plan |
| --- | --- | --- |
| Account | None | Required |
| Address | New on every start | The same every time |
| Participants | Go straight in | See an ngrok warning page once and click "Visit" |
| Limits | 200 requests in progress at once | 20,000 requests and 1 GB per month |

For a live room, prefer Cloudflare. Every live update makes each
participant's page fetch new data, so one session with a large audience can
use up ngrok's monthly request allowance.

The address is public while the tunnel runs. Stop Prashna when the session
ends.

## Roles

| Role | Page | Who gets in |
| --- | --- | --- |
| Admin | `/` | The person who signed in with the admin password. Creates sessions and quizzes. |
| Moderator | `/m/<code>` | The admin who owns the session, or anyone the admin gives the moderator link to, such as a co-host. Runs the room. |
| Participant | `/s/<code>` | Anyone with the session code or QR code. No account; an optional profile. |
| Projector | `/p/<code>` | Anyone. Read-only, for the room's screen. |
| Quiz library | `/quizzes` | The admin. Writes quizzes and reads run reports. |

The admin who owns a session can do everything a moderator can, on the same
page, plus the session's settings. The moderator link is how the admin hands
the room to someone without an admin account.

## Documentation

- [Behaviour specification](https://github.com/kvsankar/prashna/blob/main/docs/specs.md): every use case and its tests.
- [UX rules](https://github.com/kvsankar/prashna/blob/main/docs/UX.md): the frontend design system.
- [Architecture](https://github.com/kvsankar/prashna/blob/main/docs/architecture.md): components, data model, design decisions, and risks.
- [Development guide](https://github.com/kvsankar/prashna/blob/main/docs/development.md): setup, environment variables, tests, checks, and releases.
- [Engineering backlog](https://github.com/kvsankar/prashna/blob/main/docs/todo.md).
- [Performance measurement](https://github.com/kvsankar/prashna/blob/main/performance/README.md).

To run Prashna in Docker instead, see the
[container guide](https://github.com/kvsankar/prashna/blob/main/distribution/README.md).
The production deployment behind nginx is described in the
[deployment runbook](https://github.com/kvsankar/prashna/blob/main/deploy/README.md).

## License

MIT. See [LICENSE](https://github.com/kvsankar/prashna/blob/main/LICENSE).

## Status

Prashna runs in production at `prashna.sankara.net` for a single operator. It
is released as a container image.
Product ideas that need a decision are listed in the
[deferred appendix](https://github.com/kvsankar/prashna/blob/main/docs/specs.md#deferred-decision-needed)
of the specification.
