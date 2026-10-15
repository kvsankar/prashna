# Prashna

<p align="center">
  <img src="https://raw.githubusercontent.com/kvsankar/prashna/main/docs/images/prashna-hero.jpg" alt="A teacher under a banyan tree, with students raising their hands and question marks rising to an oil lamp" width="50%" />
</p>

Prashna is a live Q&A and quiz tool for trainers, teachers and speakers who
run a workshop, a class or a talk. *Prashna* (प्रश्न) is Sanskrit for
*question*.

In a room, most people do not ask questions out loud. From the front, you
cannot tell who is following and who is lost. With Prashna, people use
their phones to ask questions without giving their names, and to answer
short quizzes. You see what the room wants to know and what it understood.

## What Prashna does

- **Anonymous Q&A.** Participants post questions and upvote each other's.
  The moderator responds in text or out loud. A removed question is hidden
  from participants and kept for the record.
- **Moderator-run quizzes.** Single- or multiple-choice questions, optional
  images, anonymous answers, results revealed one question at a time, a lobby
  screen on the projector, and optional live counts while people answer.
  Quizzes are versioned: editing a quiz never changes the report of a past
  run.
- **Projector view.** The screen at the front of the room shows the join
  code, a QR code for the participant link, the top questions, and the
  current quiz question in step with the moderator.
- **Export.** The admin can export sessions, Q&A questions, attendee
  profiles, feedback, quiz runs, and quizzes as JSON or as an Excel workbook.

![How prashna brings an admin, moderators, participants and a projector into one live session for Q&A and quizzes, and what it produces afterwards](https://raw.githubusercontent.com/kvsankar/prashna/main/docs/images/prashna-infographic.png)

*How prashna runs a session with an audience: an admin sets it up, a moderator runs the room, participants join on their phones and the projector shows the room the same state. Questions are asked and upvoted, versioned quizzes are run question by question, and the session ends with ranked questions, quiz results, run reports, attendee profiles and feedback. The [infographic source](https://github.com/kvsankar/prashna/blob/main/docs/images/prashna-infographic.html) is kept with the image.*

## Why Prashna

- **It runs on your own laptop.** One command installs it. You need no
  server and no subscription.
- **Your audience can reach it over the internet.** A built-in tunnel puts
  it online. The tunnel needs `cloudflared` or `ngrok`.
- **Your data stays on your machine.** Prashna stores its data in a folder
  on your computer.
- **It is free and open source,** under the MIT licence.

## Install

Choose one of these. Each installs the same `prashna` command.

**One command, on macOS, Linux, or Windows.** This works on a machine
without Python. It installs [uv](https://docs.astral.sh/uv/), which fetches
Python if needed.

On macOS and Linux:

```sh
curl -LsSf https://sankara.net/prashna/install.sh | sh
```

On Windows, in PowerShell:

```powershell
powershell -ExecutionPolicy ByPass -c "irm https://sankara.net/prashna/install.ps1 | iex"
```

The landing page <https://sankara.net/prashna/> shows the same commands.

**Already have Python 3.11 or newer?** Install without uv, using
[pipx](https://pipx.pypa.io/):

```sh
pipx install prashna
```

Or use pip inside a virtual environment. First create the environment:

```sh
python3 -m venv ~/.prashna
```

Then install Prashna into it. On macOS and Linux:

```sh
~/.prashna/bin/pip install prashna
```

On Windows:

```powershell
~\.prashna\Scripts\pip install prashna
```

A plain `pip install` into the system Python is refused on Debian, Ubuntu,
and some other Linux distributions ("externally-managed-environment"); the
virtual environment avoids that.

**Already have uv?** This command installs and starts Prashna in one step:

```sh
uvx prashna
```

## Start and update

Start Prashna:

```sh
prashna
```

If you installed it into a virtual environment, start it from there:

```sh
~/.prashna/bin/prashna
```

To update, use the tool you installed with. With uv:

```sh
uv tool upgrade prashna
```

With pipx:

```sh
pipx upgrade prashna
```

With the virtual environment:

```sh
~/.prashna/bin/pip install --upgrade prashna
```

To list every option (the address and port, the data folder,
`--no-browser`, `--tunnel`, and the `backup` and `reset-password`
commands):

```sh
prashna --help
```

If you forget the admin password, set a new one:

```sh
prashna reset-password
```

## First run

`prashna` serves on <http://127.0.0.1:8000> and opens your browser on a
one-time page where you choose the admin's username and password. The page
works once. After that, sign in to create sessions and write quizzes.
Prashna keeps its data in your app-data folder.

## Share over the internet

To let people join from their own phones over the internet, start Prashna
with a tunnel. With a Cloudflare quick tunnel (no account needed):

```sh
prashna --tunnel cloudflare
```

With ngrok (uses your signed-in ngrok):

```sh
prashna --tunnel ngrok
```

Prashna starts the tunnel, waits until its public address works, and prints
it (`Participants join at: https://…`). Participant links and the projector's
QR code use that address automatically, while you keep using
`http://127.0.0.1:8000` yourself. Ctrl+C stops Prashna and the tunnel
together.

You need the tunnel program once.

**Cloudflare.** Install `cloudflared`. No account is needed. On macOS:

```sh
brew install cloudflared
```

On Windows:

```powershell
winget install --id Cloudflare.cloudflared
```

On Linux, use
[Cloudflare's downloads](https://developers.cloudflare.com/cloudflare-one/connections/connect-networks/downloads/).

**ngrok.** Install it from [ngrok.com/download](https://ngrok.com/download),
then sign in once:

```sh
ngrok config add-authtoken <your token>
```

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
the room to someone without an admin account. Someone with the link sees
attendee profiles without their email, phone number, or LinkedIn profile.
To stop every shared link from working, the admin changes the moderator key
in the session's settings.

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
is released as a Python package on PyPI and as a container image.
Product ideas that need a decision are listed in the
[deferred appendix](https://github.com/kvsankar/prashna/blob/main/docs/specs.md#deferred-decision-needed)
of the specification.
