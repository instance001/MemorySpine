# MemorySpine v0.1

**MemorySpine** is a small, boring-on-purpose tool that converts a ChatGPT `conversations.json` export (or full data export zip) into a local, human-readable markdown "spine" of your conversations.

Here, "spine" means a plain local markdown archive plus chronological index. It is not hidden memory, automatic summarisation, or a claim that the tool interprets the conversations for you.

It is designed for:

- basic, offline, personal data sovereignty
- people who just want their chats in plain text/markdown
- being easy for others to read, audit, and extend

This is the minimal, stable foundation release. More advanced indexing, project extraction, and summarisation live in separate tooling.

## Features (v0.1)

- Accepts:
  - a full ChatGPT export zip (e.g. `chatgpt-data-export-2025-11-30.zip`)
  - a `conversations.json` file
  - or a folder containing `conversations.json`
- Produces:
  - one markdown file per conversation
  - a simple `index.md` linking all conversations by timestamp
- No dependencies beyond the Python standard library.
- No network calls, no telemetry, no analytics.

## Storage Layout

MemorySpine does not use app-data folders, background services, or hidden state. It reads only the path passed through `--input` and writes markdown only under the directory passed through `--output`.

If `--output` is omitted, output is written to `./output` relative to the current working directory. That folder is ignored by Git for local runs.

## Installation

Clone the repo and make sure you have Python 3.9+ installed.

```bash
git clone https://github.com/instance001/MemorySpine.git
cd MemorySpine
