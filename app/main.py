from __future__ import annotations

import os
from datetime import date, datetime, timedelta
from typing import Any, Dict, List, Optional

import psycopg
from dotenv import load_dotenv
from fastapi import FastAPI, Form, HTTPException, Request
from fastapi.responses import HTMLResponse, RedirectResponse, JSONResponse
from fastapi.templating import Jinja2Templates

load_dotenv(".env")

app = FastAPI()

templates = Jinja2Templates(directory="app/templates")


def get_db_url() -> str:
    db_url = os.getenv("DATABASE_URL", "").strip()
    if not db_url:
        raise RuntimeError("DATABASE_URL not set")
    return db_url


def monday_of_week(d: date) -> date:
    # Monday start (Mon=0 ... Sun=6)
    return d - timedelta(days=d.weekday())


def parse_week_start(value: Optional[str]) -> date:
    if not value:
        return monday_of_week(date.today())
    try:
        d = datetime.strptime(value, "%Y-%m-%d").date()
        return monday_of_week(d)
    except ValueError:
        # If someone passes junk, just default safely
        return monday_of_week(date.today())


def fetch_all_accounts() -> List[Dict[str, Any]]:
    db_url = get_db_url()
    with psycopg.connect(db_url) as conn:
        with conn.cursor() as cur:
            cur.execute("select id::text, name from public.accounts order by name asc;")
            rows = cur.fetchall()
    return [{"id": r[0], "name": r[1]} for r in rows]


def fetch_account(account_id: str) -> Optional[Dict[str, Any]]:
    db_url = get_db_url()
    with psycopg.connect(db_url) as conn:
        with conn.cursor() as cur:
            cur.execute(
                "select id::text, name from public.accounts where id = %s;",
                (account_id,),
            )
            row = cur.fetchone()
    if not row:
        return None
    return {"id": row[0], "name": row[1]}


def fetch_plan(account_id: str, week_start: date) -> Dict[str, Any]:
    db_url = get_db_url()
    with psycopg.connect(db_url) as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                select objectives, actions, objections, recap
                from public.weekly_plans
                where account_id = %s and week_start = %s
                limit 1;
                """,
                (account_id, week_start),
            )
            row = cur.fetchone()

    return {
        "objectives": row[0] if row else None,
        "actions": row[1] if row else None,
        "objections": row[2] if row else None,
        "recap": row[3] if row else None,
    }


def upsert_plan(account_id: str, week_start: date, objectives: str | None, actions: str | None, objections: str | None, recap: str | None) -> None:
    db_url = get_db_url()
    with psycopg.connect(db_url) as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                insert into public.weekly_plans (account_id, week_start, objectives, actions, objections, recap)
                values (%s,%s,%s,%s,%s,%s)
                on conflict (account_id, week_start)
                do update set
                  objectives = excluded.objectives,
                  actions = excluded.actions,
                  objections = excluded.objections,
                  recap = excluded.recap,
                  updated_at = now();
                """,
                (account_id, week_start, objectives, actions, objections, recap),
            )
        conn.commit()


def ensure_contacts_table() -> None:
    # Safe no-op if already exists. Keeps things stable for today.
    db_url = get_db_url()
    with psycopg.connect(db_url) as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                create table if not exists public.contacts (
                  id uuid primary key default gen_random_uuid(),
                  account_id uuid not null references public.accounts(id) on delete cascade,
                  name text not null,
                  role text not null default 'buyer',
                  phone text,
                  email text,
                  notes text,
                  created_at timestamptz not null default now()
                );
                """
            )
        conn.commit()


def fetch_contacts(account_id: str) -> List[Dict[str, Any]]:
    ensure_contacts_table()
    db_url = get_db_url()
    with psycopg.connect(db_url) as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                select id::text, name, role, phone, email, notes
                from public.contacts
                where account_id = %s
                order by created_at desc;
                """,
                (account_id,),
            )
            rows = cur.fetchall()
    return [
        {"id": r[0], "name": r[1], "role": r[2], "phone": r[3], "email": r[4], "notes": r[5]}
        for r in rows
    ]


def insert_contact(account_id: str, name: str, role: str, phone: str | None, email: str | None, notes: str | None) -> None:
    ensure_contacts_table()
    db_url = get_db_url()
    with psycopg.connect(db_url) as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                insert into public.contacts (account_id, name, role, phone, email, notes)
                values (%s,%s,%s,%s,%s,%s);
                """,
                (account_id, name, role, phone, email, notes),
            )
        conn.commit()


@app.get("/", response_class=JSONResponse)
def root():
    return {"status": "ok", "message": "Dev Workflows API is running"}


@app.get("/db-check", response_class=JSONResponse)
def db_check():
    try:
        db_url = get_db_url()
        with psycopg.connect(db_url) as conn:
            with conn.cursor() as cur:
                cur.execute("select 1;")
                cur.fetchone()
        return {"ok": True, "database": "connected"}
    except Exception as e:
        return {"ok": False, "error": str(e)}


@app.get("/accounts", response_class=JSONResponse)
def accounts_api():
    return fetch_all_accounts()


@app.get("/ui", response_class=HTMLResponse)
def ui_home(request: Request):
    accounts = fetch_all_accounts()
    default_week = monday_of_week(date.today()).strftime("%Y-%m-%d")
    return templates.TemplateResponse(
        "index.html",
        {"request": request, "accounts": accounts, "default_week_start": default_week},
    )


@app.get("/ui/account/{account_id}", response_class=HTMLResponse)
def ui_account(request: Request, account_id: str, week_start: Optional[str] = None):
    ws = parse_week_start(week_start)
    account = fetch_account(account_id)
    if not account:
        # go home if account id is invalid
        return RedirectResponse(url="/ui", status_code=303)

    plan = fetch_plan(account_id, ws)
    contacts = fetch_contacts(account_id)

    return templates.TemplateResponse(
        "account.html",
        {
            "request": request,
            "account": account,
            "week_start": ws.strftime("%Y-%m-%d"),
            "plan": plan,
            "contacts": contacts,
        },
    )


@app.post("/ui/account/{account_id}/plan")
def ui_save_plan(
    account_id: str,
    week_start: str = Form(...),
    actions: str | None = Form(None),
    objectives: str | None = Form(None),
    objections: str | None = Form(None),
    recap: str | None = Form(None),
):
    ws = parse_week_start(week_start)
    upsert_plan(account_id, ws, objectives, actions, objections, recap)
    return RedirectResponse(url=f"/ui/account/{account_id}?week_start={ws.strftime('%Y-%m-%d')}", status_code=303)


@app.post("/ui/account/{account_id}/contact")
def ui_add_contact(
    account_id: str,
    week_start: str = Form(...),
    name: str = Form(...),
    role: str = Form(...),
    phone: str | None = Form(None),
    email: str | None = Form(None),
    notes: str | None = Form(None),
):
    # role allowlist (buyer/manager/owner)
    role = (role or "").strip().lower()
    if role not in {"buyer", "manager", "owner"}:
        role = "buyer"

    insert_contact(account_id, name, role, phone, email, notes)
    ws = parse_week_start(week_start)
    return RedirectResponse(url=f"/ui/account/{account_id}?week_start={ws.strftime('%Y-%m-%d')}", status_code=303)
