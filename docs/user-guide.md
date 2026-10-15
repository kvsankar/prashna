# Prashna user guide

This guide is for the people who run sessions with Prashna: trainers,
teachers, speakers and their co-hosts. It explains how to run a session,
how each feature works, and how to look after the installation. To
install Prashna and try it in ten minutes, read the
[README](../README.md) first.

In this guide, bold text such as **Start session** is a label that you
see in Prashna.

## Roles

Prashna has four roles. Each role has its own page. `<code>` is the
session code, six letters and digits that Prashna makes for each session.

| Role | Page | Who gets in |
| --- | --- | --- |
| Admin | `/` | The person who signs in with the admin password. Creates sessions and quizzes. |
| Moderator | `/m/<code>` | The admin who owns the session, or anyone the admin gives the moderator link to, such as a co-host. Runs the room. |
| Participant | `/s/<code>` | Anyone with the session code, the link or the QR code. No account; an optional profile. |
| Projector | `/p/<code>` | Anyone. Read-only, for the room's screen. |

The admin also has the quiz library at `/quizzes`, where the admin writes
quizzes and reads the results of past quiz runs.

The admin who owns a session can do everything a moderator can, on the
same page, and also change the session's settings. The page `/m/<code>`
is called the session page in this guide.

## Run a session

A session is one gathering, for example one class, one workshop or one
talk. A session has three states, shown as a badge: **Not started**,
**Live** and **Ended**.

1. Sign in on the home page. Under **Your sessions**, type a title in the
   **New session title** box and click **+ New session**.
2. Click the session's row to open the session page.
3. Before the audience arrives, open the projector page (click
   **Projector**) and show it on the room's screen. Prepare your quizzes
   (see [Quizzes and polls](#quizzes-and-polls)).
4. When the audience is ready, click **Start session**. You can also
   click **Start** on the session's row on the home page. Starting a quiz
   also starts the session.
5. People join with the QR code, the link or the session code. They ask
   questions, upvote them and answer quizzes.
6. At the end, click **End session** and confirm. Participants can then
   read the questions, but they cannot ask new questions or vote.

To rename a session, change the **Title** in the **Session settings**
card, inside **Set up**. To delete a session and all its data, end it
first. Then click **Delete session…** there, or **Delete** on its row on
the home page. For a session with data, type the title and click
**Delete forever**.

The session page header shows how many people are online: the
participants who used the page in the last 30 seconds.

## Questions and answers

### For participants

A participant types a question under **Your question** and clicks
**Ask**. On a computer, Ctrl+Enter (Cmd+Enter on a Mac) also sends it.

Questions are anonymous. To show a name with one question, the
participant ticks **Show my name** and types a name. The box clears after
each question, so each question is a new choice. Prashna never shows the
name from the participant's profile with a question.

To upvote a question, a participant clicks the ▲ beside it. A second
click removes the vote. The list shows the questions without a response
first, with the most votes at the top. A participant's own questions are
marked.

### For moderators

The **Questions** card on the session page lists every question.

- To reply, type the reply in the question's box if you want to, and
  click **Mark responded**. A question that you answer out loud needs no
  text. Answered questions move to the answered part of the participants'
  list. **Update response** changes the reply, and **Reopen** marks the
  question as not answered again.
- To hide a question, for example spam or a duplicate, click **Remove**.
  Participants no longer see it and cannot vote on it. You still see it,
  and **Restore** brings it back. Removed questions stay in the export.

When the session ends, the questions stay visible to everyone, but
nobody can ask or vote.

## Quizzes and polls

A quiz is a set of questions that you write once in the quiz library and
run in any session. Each run of a quiz in a session is a quiz run.

### Write a quiz

1. Click **Quiz library** at the top of the home page.
2. Type a title in the **New quiz title** box and click **+ New**. The
   editor opens below the list. Prashna saves each change as you make it.
3. Click the **+** button to add a question, and type the question.
   Choose single choice or multiple choice for each question.
4. Click **+ Answer** for each answer. Each question needs at least 2
   answers.
5. Tick **Correct** beside each right answer: exactly one for a
   single-choice question, one or more for a multiple-choice question.
6. For a poll, tick **Poll (no correct answer)**. A poll collects answers
   and has no right answer.

You can add an image to a question or to an answer. An image can be up
to 5 MB. SVG images are not accepted.

A new quiz is a draft. Click **Publish** to make it ready. Prashna checks
the quiz first. It marks each problem in the editor and shows how many
problems are left to fix. **Unpublish** makes a ready quiz a draft again.
**Duplicate** makes an editable copy.

Editing a quiz never changes a quiz run that has started. Prashna keeps a
copy of the quiz, as it was, for each run.

### Run a quiz

1. Add the quiz to the session. In the quiz library, click
   **Add to session ▾** on the quiz's row and choose the session. Or, on
   the session page, choose the quiz in the **Quiz** card and click
   **+ Add quiz**. A valid draft is published when you add it.
2. The quiz is now queued. The projector page shows "Next up:" and the
   quiz title, and asks the room to scan the code.
3. Click **Start**. Only one quiz can be live in a session at a time. If
   you edited the quiz after you added it, Start plays the edited quiz.
4. Participants see the question at the top of their page. They choose an
   answer and click **Submit answer**. They can change it with
   **Update answer** until you reveal the results.
5. Click **Reveal results →**. Voting on that question closes. The
   projector page and the phones show how many people chose each answer,
   and the correct answer. A revealed question stays closed, also when
   you go back to it.
6. Click **Next question →** to go on, or **← Prev** to go back. On the
   last question, click **Finish quiz →**.

The **⋯** menu on the quiz run has the other actions:

- **Finish quiz** ends the run early and keeps the results.
- **Reopen voting** opens a revealed question again.
- **Show vote counts to audience** shows the answers as they come in
  (see below). **Hide vote counts from audience** turns this off.
- **Remove from session** removes a queued run.
- **Delete run (discard results)** deletes a live run and its answers,
  after you confirm.

When a quiz run finishes, it disappears from the participants' pages.
The projector page keeps the last question with the final results. The
admin opens the full results with **View results →** on the session page,
or in the quiz library.

### Vote counts while people answer

The vote counts are off by default. When you turn them on for a quiz run:

- for a question with a correct answer, the phones show only how many
  people have answered. The projector page shows the spread of the votes
  as "Option A", "Option B" and so on. It hides the answer texts, so
  nobody can follow the crowd;
- for a poll, the phones and the projector page show each answer with its
  count and percentage.

Quiz answers are anonymous. The results show how many people chose each
answer, not who chose it.

## Feedback

Feedback is a star rating from 1 to 5 with two optional comments, "What
went well?" and "What could be better?".

Feedback is closed when you create a session. To open it, click
**Open feedback** in the **Session lifecycle** card. You can open it in
any state, also after the session ends. **Close feedback** closes it.

While feedback is open, participants see a **Feedback** card. They choose
the stars, write comments if they want to, and click **Submit feedback**.
They can change and send it again, or remove it with **Clear feedback**.

The **Feedback** card on the session page shows the average rating, the
number of responses, and each response. Feedback is anonymous.

### Attendee profiles

Participants can also fill in an optional profile: **Add your profile**
on their page. It holds fields such as a name, email, organization and
a photograph. The **Attendee profiles** card on the session page lists
the profiles. Prashna never links a profile to that person's questions,
quiz answers or feedback.

## The projector page

The projector page (`/p/<code>`) is for the screen at the front of the
room. Open it with **Projector** on the session page or on the home page.
It shows:

- the session title and the join code in large type;
- the participant link and a QR code for it. Click the QR code to show
  it full screen, and click again to close it;
- the top questions that have no response yet, by votes;
- the current quiz question, or "Next up:" while a quiz is queued, and
  the results after you reveal them.

The projector page has no links or buttons, so the room sees only the
session. It updates by itself. If the network drops, it connects again
without your help.

## Share moderation

A co-host can run the room without an admin account. You give them the
moderator link.

1. On the session page, open **Set up**. In the **Session settings**
   card, click **Share moderator URL**. Prashna copies the link.
2. Send the link to your co-host. Treat it like a password: anyone with
   the link can moderate the session.
3. Your co-host opens the link and sees the session page.

A co-host can do what a moderator does: start and end the session, run
quizzes, reply to and remove questions, and open feedback. A co-host can
add only ready quizzes. A co-host does not see the session settings, the
**Base URL** box or the export menus. A co-host sees attendee profiles
without the email, contact number and LinkedIn profile.

To stop every shared link from working, click **Change moderator key**
and confirm with **Change key**. Open co-host pages then ask for the key.
Share the new link with anyone who should keep access.

## Put Prashna online

By default, Prashna listens only on your own computer, at
`http://127.0.0.1:8000`. Other devices cannot open that address. There
are two ways to let phones in.

### Over the internet, with a tunnel

A tunnel gives your laptop a public `https://` address while Prashna
runs. Start Prashna with a Cloudflare quick tunnel:

```sh
prashna --tunnel cloudflare
```

Or with ngrok:

```sh
prashna --tunnel ngrok
```

Prashna starts the tunnel, waits until its public address works, and
prints it (`Participants join at: https://…`). Participant links, the QR
codes and the copied moderator link use that address. You keep using
`http://127.0.0.1:8000` yourself. Ctrl+C stops Prashna and the tunnel
together. If the tunnel stops by itself, the terminal says so; start
Prashna again to get a new address.

You need the tunnel program once.

- Cloudflare: install `cloudflared`. No account is needed. On macOS,
  run `brew install cloudflared`. On Windows, run
  `winget install --id Cloudflare.cloudflared`. On Linux, use
  [Cloudflare's downloads](https://developers.cloudflare.com/cloudflare-one/connections/connect-networks/downloads/).
- ngrok: install it from [ngrok.com/download](https://ngrok.com/download),
  then sign in once with `ngrok config add-authtoken <your token>`.

On the free plans they differ like this:

| | Cloudflare quick tunnel | ngrok free plan |
| --- | --- | --- |
| Account | None | Required |
| Address | New on every start | The same every time |
| Participants | Go straight in | See an ngrok warning page once and click "Visit" |
| Limits | 200 requests in progress at once | 20,000 requests and 1 GB per month |

For a live room, prefer Cloudflare. Every live update makes each
participant's page fetch new data, so one session with a large audience
can use up ngrok's monthly request allowance.

The address is public while the tunnel runs. Stop Prashna when the
session ends.

### On the same Wi-Fi network

When everyone is on the same network as your laptop, start Prashna so
that other devices can reach it:

```sh
prashna --host 0.0.0.0
```

Anyone on that network can then reach Prashna while it runs. The
terminal still shows `http://127.0.0.1:8000`, which works only on your
laptop. Find your laptop's address on the network, for example
`192.168.1.20`, in your network settings. Then set the session's
**Base URL** to `http://192.168.1.20:8000` (with your address), as
described below.

### Base URL

The **Base URL** box sets the address in the participant link and the QR
code of one session. It is on the session page, in the
**Invite participants** card inside **Set up**. Only the admin who owns
the session sees it.

Type the address, for example `http://192.168.1.20:8000`, and click
outside the box. The address must start with `http://` or `https://`.
**Use default** clears it. With no Base URL, Prashna uses the tunnel's
address when it runs with one, or else the address of the page you are
on.

## Where your data is

Prashna keeps its data in one data folder on your computer:

| System | Data folder |
| --- | --- |
| Linux | `~/.local/share/prashna` (or `$XDG_DATA_HOME/prashna` when `XDG_DATA_HOME` is set) |
| macOS | `~/Library/Application Support/prashna` |
| Windows | `%LOCALAPPDATA%\prashna` |

The terminal shows the folder each time Prashna starts. The folder holds:

- `prashna.db`, the database with your sessions, questions, quizzes and
  results;
- `uploads`, the quiz images and participants' photographs;
- `secret-key`, which Prashna uses to sign the admin's sign-in;
- `setup-token`, the one-time setup code, until you create the admin;
- `prashna.log`, Prashna's log file.

To keep the data somewhere else, give a folder with `--data-dir`:

```sh
prashna --data-dir ~/prashna-workshop
```

Give the same `--data-dir` to the other commands, for example
`prashna --data-dir ~/prashna-workshop backup create backup.tar.gz`.
The environment variable `PRASHNA_DATA_DIR` does the same as `--data-dir`.

The data folder is not the folder of a virtual environment (`.prashna`
in your home folder). Removing Prashna does not remove the data folder.

## Export

The admin can download data as one JSON file or as one Excel workbook.
Each export menu offers **JSON** and **Excel**.

| What | Where |
| --- | --- |
| All your sessions and quizzes | Home page, **Your sessions** card: **Export all data ▾** |
| One session, with all its data | Session page, **Session lifecycle** card: **Export session ▾** |
| One session's questions, attendee profiles or feedback | Session page, the **Questions**, **Attendee profiles** or **Feedback** card: **Export ▾** |
| One quiz run | Quiz library, the run's results |
| One quiz | Quiz library, the quiz's **⋯** menu |

Only the admin who owns the data can export it; co-hosts cannot. Exports
of sessions and profiles contain participants' names and contact
details, so keep those files safe. Exports keep the anonymity of
questions, quiz answers and feedback.

## Back up and restore

A backup is one file that holds the database and the uploads. It does
not hold the `secret-key`, so after a restore on another computer, sign
in again.

To make a backup, run this command. Prashna can keep running.

```sh
prashna backup create prashna-backup.tar.gz
```

To restore a backup:

1. Stop Prashna with Ctrl+C.
2. Run this command:

   ```sh
   prashna backup restore prashna-backup.tar.gz --confirm
   ```

3. Start Prashna again.

Restore replaces all the current data with the data in the backup.
Without `--confirm`, it changes nothing. Before it replaces anything, it
saves the current data in a file named `prashna-pre-restore-<time>.tar.gz`
beside the backup file. On a computer with no Prashna data yet, there is
nothing to save, and the restore says so.

If you use `--data-dir`, put it before `backup`, for example
`prashna --data-dir ~/prashna-workshop backup create prashna-backup.tar.gz`.

## Update Prashna

Stop Prashna before you update it. Your data folder stays as it is, and
the new version uses it.

With the one-command installer or with uv:

```sh
uv tool upgrade prashna
```

With pipx:

```sh
pipx upgrade prashna
```

With a virtual environment, on macOS and Linux:

```sh
~/.prashna/bin/pip install --upgrade prashna
```

With a virtual environment, on Windows:

```powershell
$HOME\.prashna\Scripts\pip install --upgrade prashna
```

With `uvx`, run the newest version:

```sh
uvx prashna@latest
```

To see which version you have:

```sh
prashna --version
```

## Uninstall Prashna

Uninstalling removes the `prashna` command. It does not remove your data
folder.

With the one-command installer or with uv:

```sh
uv tool uninstall prashna
```

With pipx:

```sh
pipx uninstall prashna
```

With a virtual environment, delete its folder. On macOS and Linux:

```sh
rm -rf ~/.prashna
```

On Windows:

```powershell
Remove-Item -Recurse -Force $HOME\.prashna
```

The one-command installer also installed uv, which stays. To remove uv,
see [uv's uninstall steps](https://docs.astral.sh/uv/getting-started/installation/#uninstallation).

To delete your data as well, make a backup first if you may need it.
Then delete the data folder. This deletes every session, quiz and
result. On Linux:

```sh
rm -rf ~/.local/share/prashna
```

On macOS:

```sh
rm -rf ~/Library/Application\ Support/prashna
```

On Windows:

```powershell
Remove-Item -Recurse -Force $env:LOCALAPPDATA\prashna
```

## Reset the admin password

If you know the password, change it on the home page with
**Change password**.

If you forgot it, run this command on the computer that holds the data
folder:

```sh
prashna reset-password
```

It asks for the new password twice. The password needs at least 8
characters. When it succeeds, it prints `Password changed for <name>.`
The new password works at once, also while Prashna runs. Devices that are
already signed in stay signed in. Add `--data-dir` if you use one.

In Docker, run:

```sh
docker compose exec prashna python -m prashna reset-password
```

## Troubleshooting

### The port is in use

Prashna stops with "Port 8000 is already in use"
when another program, or another Prashna, uses the port. Stop the other
program, or start on another port:

```sh
prashna --port 8001
```

### The browser did not open

This happens, for example, over SSH.
Prashna prints the address in the terminal; copy it into a browser. On
the first run, the terminal shows the one-time setup link, which ends in
`/#setup=…`. To start without a browser on purpose, run
`prashna --no-browser`.

### The setup link is lost

Until you create the admin, the setup link
stays the same. Stop Prashna and start it again; the terminal shows the
link again. You can also run `prashna --no-browser`, which prints the
link.

### The tunnel does not start

If `cloudflared` or `ngrok` is not
installed, Prashna stops and shows how to install it. If the tunnel prints
no address within 45 seconds, Prashna stops and shows the tunnel's last
lines; check your internet connection and try again. With ngrok, sign in
once with `ngrok config add-authtoken <your token>`. A new Cloudflare
address can need up to a minute before it works. Prashna waits for it,
and says so if it needs longer.

### Phones cannot open the link

The link probably starts with
`http://127.0.0.1`. That address always means "this device", so on a
phone it points at the phone. Put Prashna online with a tunnel, or use
the same Wi-Fi network with `--host 0.0.0.0` and the **Base URL** (see
[Put Prashna online](#put-prashna-online)). On the same network, also
check that your computer's firewall allows incoming connections to
Prashna.

### People see "too fast" messages

Prashna slows down anyone who sends
too much too fast. Many people can share one internet connection, for
example the venue's Wi-Fi when you use a tunnel. Then raise the number
of people on one network in the **Limits** card on the home page.

### You forgot the admin password

See
[Reset the admin password](#reset-the-admin-password).

## Run Prashna in Docker

To run Prashna in a container instead, see the
[container guide](../distribution/README.md).
