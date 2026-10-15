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
- **Quizzes and polls, run by the moderator.** Single- or multiple-choice
  questions, polls with no correct answer, optional images and anonymous
  answers. The moderator reveals the results one question at a time.
  Editing a quiz never changes the results of a past run.
- **Projector view.** The screen at the front of the room shows the join
  code, a QR code for the participant link, the top questions, and the
  current quiz question in step with the moderator.
- **Export.** The admin can export sessions, questions, attendee profiles,
  feedback, quiz runs and quizzes as JSON or as an Excel workbook.

![How Prashna brings an admin, moderators, participants and a projector into one live session for Q&A and quizzes, and what it produces afterwards](https://raw.githubusercontent.com/kvsankar/prashna/main/docs/images/prashna-infographic.png)

*How Prashna runs a session. An admin sets it up and a moderator runs the
room. Participants join on their phones, and the projector shows the room
the same state. At the end you have the ranked questions, the quiz
results, the attendee profiles and the feedback.*

## Why Prashna

- **It runs on your own laptop.** One command installs it. You need no
  server and no subscription.
- **Your audience can reach it over the internet.** A built-in tunnel puts
  it online. The tunnel needs `cloudflared` or `ngrok`.
- **Your data stays on your machine.** Prashna stores its data in a folder
  on your computer.
- **It is free and open source,** under the MIT License.

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

**Already have uv?** This command installs the same `prashna` command. It
is the same on macOS, Linux, and Windows:

```sh
uv tool install prashna
```

To try Prashna first, this command runs it without installing the
`prashna` command:

```sh
uvx prashna
```

It keeps using the version that uv already has. To get the newest
version, run:

```sh
uvx prashna@latest
```

**Already have Python 3.11 or newer?** Install without uv, using
[pipx](https://pipx.pypa.io/):

```sh
pipx install prashna
```

Or use pip inside a virtual environment in the folder `.prashna` in your
home folder. A plain `pip install` into the system Python is refused on
Debian, Ubuntu, and some other Linux distributions
("externally-managed-environment"); the virtual environment avoids that.

On macOS and Linux, create the environment, then install Prashna into it:

```sh
python3 -m venv ~/.prashna
```

```sh
~/.prashna/bin/pip install prashna
```

On Windows, in PowerShell:

```powershell
py -m venv $HOME\.prashna
```

```powershell
$HOME\.prashna\Scripts\pip install prashna
```

### Start and update

Start Prashna:

```sh
prashna
```

If you installed it into a virtual environment, start it from there. On
macOS and Linux:

```sh
~/.prashna/bin/prashna
```

On Windows:

```powershell
$HOME\.prashna\Scripts\prashna
```

To update an installation made with the one-command installer or with uv,
run:

```sh
uv tool upgrade prashna
```

To update the virtual environment, stop Prashna first. On macOS and Linux:

```sh
~/.prashna/bin/pip install --upgrade prashna
```

On Windows:

```powershell
$HOME\.prashna\Scripts\pip install --upgrade prashna
```

The [user guide](https://github.com/kvsankar/prashna/blob/main/docs/user-guide.md#update-prashna)
gives the update and uninstall commands for every install method.

## Quick tutorial

This tutorial takes about ten minutes. You can do it alone on your
laptop, with a second browser window as the participant.

### 1. Start Prashna and create the admin

Run `prashna`. On the first run, Prashna prints a one-time setup link in
the terminal and opens it in your browser. On that page, choose the
admin's username and password (at least 8 characters), then click
**Create admin**. The setup link works only once. After that, sign in at
<http://127.0.0.1:8000/>.

The terminal also shows the data folder, where Prashna keeps its
database. Keep the terminal open: Prashna runs until you press Ctrl+C.

### 2. Create a session

A session is one gathering, for example one class or one talk. Under
**Your sessions**, type a title in the **New session title** box and click
**+ New session**. Click the new row to open the session page.

On the session page, click **Start session** when the audience is ready.

### 3. Open the projector page

On the session page, click **Projector** at the top. The projector page
opens in a new tab. Show that tab on the screen that the room sees. It
shows the join code, a QR code, the top questions and the current quiz
question. Click the QR code to enlarge it.

### 4. Let the audience join

People scan the QR code with their phone camera, or open the participant
link. The link is under **Participants join at:** in the
**Invite participants** card, inside **Set up** on the session page.
People can also type the session code on the Prashna home page. They need
no account and no app.

Phones can reach Prashna only after you put it online (step 7). To try
it alone first, click **Participant view** at the top of the session page.

### 5. Ask and upvote

On the participant page, type a question under **Your question** and click
**Ask**. A question is anonymous unless the participant ticks
**Show my name**. Other participants click the ▲ beside a question to
upvote it. The questions with the most votes rise to the top.

On the session page, the **Questions** card lists the questions. Type a
reply if you want to, and click **Mark responded**. Click **Remove** to
hide a question from participants.

### 6. Run a short quiz

1. Click **Quiz library** at the top of the home page. Type a title in
   the **New quiz title** box and click **+ New**.
2. In the editor, click the **+** button to add a question, and type the
   question. Click **+ Answer** for each answer. Tick **Correct** beside
   the right answer, or tick **Poll (no correct answer)** for a poll.
3. Click **Add to session ▾** on the quiz's row and choose your session.
4. On the session page, in the **Quiz** card, click **Start**. The
   question appears on the phones and on the projector page.
5. When people have answered, click **Reveal results →**. Voting on that
   question closes, and the projector page shows the results. Click
   **Next question →**, and on the last question, **Finish quiz →**.

### 7. Put Prashna online for your audience

By default, Prashna listens only on your own computer
(`http://127.0.0.1:8000`). Phones cannot open that address. Choose one of
these ways to let them in.

#### Over the internet, with a tunnel

Stop Prashna with Ctrl+C, then
start it with a Cloudflare quick tunnel. This needs the `cloudflared`
program and no account:

```sh
prashna --tunnel cloudflare
```

Or use ngrok, signed in to your ngrok account:

```sh
prashna --tunnel ngrok
```

Prashna prints the public address (`Participants join at: https://…`).
The participant link and the QR code use that address. You keep using
`http://127.0.0.1:8000` yourself. Ctrl+C stops Prashna and the tunnel.

#### On the same Wi-Fi network

Start Prashna so that other devices on
the network can reach it:

```sh
prashna --host 0.0.0.0
```

Then find your laptop's address on the network, for example
`192.168.1.20`, in your network settings. On the session page, open
**Set up** and type `http://192.168.1.20:8000` (with your address) in the
**Base URL** box. The participant link and the QR code then use that
address. Anyone on the same network can reach Prashna while it runs.

The user guide explains how to install `cloudflared` and `ngrok`, and how
the two tunnels differ.

## User guide

The [user guide](https://github.com/kvsankar/prashna/blob/main/docs/user-guide.md)
covers everything else. It explains the roles, quizzes and polls,
feedback, sharing moderation with a co-host, and tunnels. It also covers
where your data is, export, backup and restore, updating, uninstalling,
resetting the admin password, and troubleshooting. To run Prashna in Docker, see the
[container guide](https://github.com/kvsankar/prashna/blob/main/distribution/README.md).

The landing page is <https://sankara.net/prashna/>.

## Licence

Prashna is under the MIT License. See
[LICENSE](https://github.com/kvsankar/prashna/blob/main/LICENSE).

For contributors: the
[development guide](https://github.com/kvsankar/prashna/blob/main/docs/development.md)
covers setup, tests, checks and releases.
