"""SQLite-Datenbank: Inhalte, Quellen, Durchläufe, Sync-Codes, Meldungen."""
import json
import os
import sqlite3
import threading

DB_PATH = os.environ.get("DB_PATH", os.path.join(os.path.dirname(__file__), "..", "data.db"))
LOCK = threading.Lock()

SCHEMA = """
create table if not exists items(
  id integer primary key autoincrement,
  title text, text text, url text, source_id text, source text, method text,
  published text, summary text, summary_en text, category text, keywords text,
  priority integer, location text, region text, lat real, lon real, event_date text,
  confidence real, engine text, status text, flags text,
  views integer default 0, clicks integer default 0, saves integer default 0,
  created text default (datetime('now','localtime'))
);
create unique index if not exists items_url on items(url);
create table if not exists sources(
  id text primary key, name text, method text, url text, enabled integer default 1,
  last_run text, last_status text, last_error text, last_new integer default 0, total integer default 0
);
create table if not exists runs(
  id integer primary key autoincrement, started text, finished text,
  fetched integer default 0, new integer default 0, duplicates integer default 0,
  processed integer default 0, live integer default 0, review integer default 0,
  tokens_in integer default 0, tokens_out integer default 0, log text
);
create table if not exists sync_codes(code text primary key, profile text, created text default (datetime('now','localtime')));
create table if not exists stats(day text, key text, n integer default 0, primary key(day, key));
create table if not exists accounts(name text primary key, salt text, pin_hash text, profile text, created text default (datetime('now','localtime')), updated text);
create table if not exists reports(id integer primary key autoincrement, item_id integer, reason text, status text default 'offen', created text default (datetime('now','localtime')));
"""


def connect():
    c = sqlite3.connect(DB_PATH, check_same_thread=False)
    c.row_factory = sqlite3.Row
    return c


def init():
    with LOCK, connect() as c:
        c.executescript(SCHEMA)


def rows(sql, args=()):
    with connect() as c:
        return [dict(r) for r in c.execute(sql, args).fetchall()]


def one(sql, args=()):
    r = rows(sql, args)
    return r[0] if r else None


def exec_(sql, args=()):
    with LOCK, connect() as c:
        cur = c.execute(sql, args)
        c.commit()
        return cur.lastrowid


def item_out(r):
    """Datenbankzeile -> JSON für die Website."""
    r = dict(r)
    for k in ("keywords", "flags"):
        try:
            r[k] = json.loads(r[k]) if r.get(k) else []
        except Exception:
            r[k] = []
    return r
