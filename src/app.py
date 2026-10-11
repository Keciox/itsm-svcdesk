# ai-generated: 80% - I drafted the Flask service structure and then rewrote the SLA and state-machine logic to match the contract.
import json
import os
import sqlite3
import uuid
from datetime import datetime, time, timedelta, timezone
from zoneinfo import ZoneInfo

from flask import Flask, jsonify, request

app = Flask(__name__)
app.config["JSON_SORT_KEYS"] = False

DB_PATH = os.environ.get("SVCDESK_DB", "/data/svcdesk.db")
TZ = ZoneInfo("Europe/Warsaw")
TIME_FORMAT = "%Y-%m-%dT%H:%M:%SZ"

C1 = "wallclock"
C2 = "immutable"
C3 = "vip"


def ensure_db():
    os.makedirs(os.path.dirname(DB_PATH) or ".", exist_ok=True)
    conn = sqlite3.connect(DB_PATH)
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS tickets (
            id TEXT PRIMARY KEY,
            title TEXT NOT NULL,
            description TEXT NOT NULL,
            reporter_name TEXT NOT NULL,
            reporter_email TEXT,
            reporter_vip INTEGER NOT NULL,
            impact INTEGER NOT NULL,
            urgency INTEGER NOT NULL,
            priority TEXT NOT NULL,
            state TEXT NOT NULL,
            created_at TEXT NOT NULL,
            acknowledged_at TEXT,
            resolved_at TEXT,
            closed_at TEXT,
            related_to TEXT,
            sla_ack_due_at TEXT NOT NULL,
            sla_resolve_due_at TEXT NOT NULL
        )
        """
    )
    conn.commit()
    conn.close()


def utc_now():
    return datetime.now(timezone.utc)


def parse_rfc3339(value):
    if value is None:
        raise ValueError("missing timestamp")
    if value.endswith("Z"):
        value = value[:-1] + "+00:00"
    dt = datetime.fromisoformat(value)
    if dt.tzinfo is None:
        raise ValueError("timestamp missing timezone")
    return dt.astimezone(timezone.utc)


def request_now():
    if os.environ.get("SVCDESK_TEST_CLOCK", "0").lower() in {"1", "true"}:
        header = request.headers.get("X-Test-Clock")
        if header is not None:
            try:
                return parse_rfc3339(header)
            except ValueError:
                return None
    return utc_now()


def error_response(code, message, status):
    payload = {"error": {"code": code, "message": message}}
    return jsonify(payload), status


def to_z(dt):
    if dt is None:
        return None
    return dt.astimezone(timezone.utc).strftime(TIME_FORMAT)


def iso_to_dt(value):
    if value is None:
        return None
    return parse_rfc3339(value)


def is_business_hour(dt):
    local = dt.astimezone(TZ)
    day_start = datetime.combine(local.date(), time(8, 0), tzinfo=TZ)
    day_end = datetime.combine(local.date(), time(16, 0), tzinfo=TZ)
    return day_start <= local < day_end and local.weekday() < 5


def next_business_start(dt):
    local = dt.astimezone(TZ)
    candidate = datetime.combine(local.date(), time(8, 0), tzinfo=TZ)
    if local.weekday() < 5:
        if local.time() < time(8, 0):
            return candidate
        if local.time() < time(16, 0):
            return local
        candidate = datetime.combine(local.date() + timedelta(days=1), time(8, 0), tzinfo=TZ)
        while candidate.weekday() >= 5:
            candidate = candidate + timedelta(days=1)
        return candidate
    candidate = datetime.combine(local.date() + timedelta(days=1), time(8, 0), tzinfo=TZ)
    while candidate.weekday() >= 5:
        candidate = candidate + timedelta(days=1)
    return candidate


def add_business_time(start_utc, target_seconds):
    current = start_utc.astimezone(TZ)
    remaining = timedelta(seconds=target_seconds)
    while remaining > timedelta(0):
        if current.weekday() < 5 and time(8, 0) <= current.time() < time(16, 0):
            day_end = datetime.combine(current.date(), time(16, 0), tzinfo=TZ)
            available = day_end - current
            if remaining <= available:
                return (current + remaining).astimezone(timezone.utc)
            remaining -= available
            current = datetime.combine(current.date() + timedelta(days=1), time(8, 0), tzinfo=TZ)
            while current.weekday() >= 5:
                current = current + timedelta(days=1)
        else:
            current = next_business_start(current)
    return current.astimezone(timezone.utc)


def compute_sla(priority, created_at):
    if priority == "P1" and C1 == "wallclock":
        ack_due = created_at + timedelta(minutes=15)
        resolve_due = created_at + timedelta(hours=4)
        return ack_due, resolve_due

    mapping = {
        "P1": (15 * 60, 4 * 60 * 60),
        "P2": (60 * 60, 8 * 60 * 60),
        "P3": (4 * 60 * 60, 24 * 60 * 60),
        "P4": (8 * 60 * 60, 72 * 60 * 60),
    }
    ack_seconds, resolve_seconds = mapping[priority]
    ack_due = add_business_time(created_at, ack_seconds)
    resolve_due = add_business_time(created_at, resolve_seconds)
    return ack_due, resolve_due


def compute_priority(impact, urgency, reporter_vip):
    matrix = {
        1: {1: "P1", 2: "P2", 3: "P3"},
        2: {1: "P2", 2: "P3", 3: "P4"},
        3: {1: "P3", 2: "P4", 3: "P4"},
    }
    priority = matrix[impact][urgency]
    if reporter_vip and C3 == "vip":
        if priority in {"P3", "P4"}:
            return "P2"
    return priority


def fetch_ticket(ticket_id):
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    row = conn.execute("SELECT * FROM tickets WHERE id=?", (ticket_id,)).fetchone()
    conn.close()
    return row


def serialize_ticket(row):
    if row is None:
        return None
    result = {
        "id": row["id"],
        "title": row["title"],
        "description": row["description"],
        "reporter": {
            "name": row["reporter_name"],
            "email": row["reporter_email"],
            "vip": bool(row["reporter_vip"]),
        },
        "impact": row["impact"],
        "urgency": row["urgency"],
        "priority": row["priority"],
        "state": row["state"],
        "created_at": to_z(iso_to_dt(row["created_at"])),
        "acknowledged_at": to_z(iso_to_dt(row["acknowledged_at"])),
        "resolved_at": to_z(iso_to_dt(row["resolved_at"])),
        "closed_at": to_z(iso_to_dt(row["closed_at"])),
        "related_to": row["related_to"],
        "sla": {
            "ack_due_at": to_z(iso_to_dt(row["sla_ack_due_at"])),
            "resolve_due_at": to_z(iso_to_dt(row["sla_resolve_due_at"])),
        },
    }
    return result


def ticket_row_from_dict(ticket):
    return {
        "id": ticket["id"],
        "title": ticket["title"],
        "description": ticket["description"],
        "reporter_name": ticket["reporter"]["name"],
        "reporter_email": ticket["reporter"].get("email"),
        "reporter_vip": int(ticket["reporter"].get("vip", False)),
        "impact": ticket["impact"],
        "urgency": ticket["urgency"],
        "priority": ticket["priority"],
        "state": ticket["state"],
        "created_at": to_z(parse_rfc3339(ticket["created_at"])),
        "acknowledged_at": to_z(parse_rfc3339(ticket["acknowledged_at"])) if ticket.get("acknowledged_at") else None,
        "resolved_at": to_z(parse_rfc3339(ticket["resolved_at"])) if ticket.get("resolved_at") else None,
        "closed_at": to_z(parse_rfc3339(ticket["closed_at"])) if ticket.get("closed_at") else None,
        "related_to": ticket.get("related_to"),
        "sla_ack_due_at": to_z(parse_rfc3339(ticket["sla"]["ack_due_at"])),
        "sla_resolve_due_at": to_z(parse_rfc3339(ticket["sla"]["resolve_due_at"])),
    }


def validation_error(message):
    return error_response("validation", message, 400)


def create_ticket_from_payload(payload):
    if not isinstance(payload, dict):
        return validation_error("request body must be a JSON object")

    title = payload.get("title")
    if not isinstance(title, str) or not (1 <= len(title) <= 200):
        return validation_error("title is required")

    description = payload.get("description", "")
    if description is None:
        description = ""
    if not isinstance(description, str) or len(description) > 4000:
        return validation_error("description too long")

    reporter = payload.get("reporter")
    if not isinstance(reporter, dict):
        return validation_error("reporter is required")

    reporter_name = reporter.get("name")
    if not isinstance(reporter_name, str) or not (1 <= len(reporter_name) <= 100):
        return validation_error("reporter.name is required")

    reporter_email = reporter.get("email")
    if reporter_email is not None and not isinstance(reporter_email, str):
        return validation_error("reporter.email must be a string or null")

    vip_value = reporter.get("vip", False)
    if not isinstance(vip_value, bool):
        return validation_error("reporter.vip must be a boolean")

    impact = payload.get("impact")
    urgency = payload.get("urgency")
    if type(impact) is not int or impact not in (1, 2, 3):
        return validation_error("impact must be an integer 1..3")
    if type(urgency) is not int or urgency not in (1, 2, 3):
        return validation_error("urgency must be an integer 1..3")

    created_at = request_now()
    if created_at is None:
        return error_response("validation", "X-Test-Clock is not a valid RFC 3339 instant", 400)
    ticket_id = str(uuid.uuid4())
    priority = compute_priority(impact, urgency, vip_value)
    ack_due_at, resolve_due_at = compute_sla(priority, created_at)

    inserted = {
        "id": ticket_id,
        "title": title,
        "description": description,
        "reporter": {"name": reporter_name, "email": reporter_email, "vip": vip_value},
        "impact": impact,
        "urgency": urgency,
        "priority": priority,
        "state": "new",
        "created_at": to_z(created_at),
        "acknowledged_at": None,
        "resolved_at": None,
        "closed_at": None,
        "related_to": payload.get("related_to"),
        "sla": {"ack_due_at": to_z(ack_due_at), "resolve_due_at": to_z(resolve_due_at)},
    }

    conn = sqlite3.connect(DB_PATH)
    conn.execute(
        """
        INSERT INTO tickets (id, title, description, reporter_name, reporter_email, reporter_vip, impact, urgency,
        priority, state, created_at, acknowledged_at, resolved_at, closed_at, related_to, sla_ack_due_at, sla_resolve_due_at)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            inserted["id"],
            inserted["title"],
            inserted["description"],
            inserted["reporter"]["name"],
            inserted["reporter"]["email"],
            int(inserted["reporter"]["vip"]),
            inserted["impact"],
            inserted["urgency"],
            inserted["priority"],
            inserted["state"],
            inserted["created_at"],
            inserted["acknowledged_at"],
            inserted["resolved_at"],
            inserted["closed_at"],
            inserted["related_to"],
            inserted["sla"]["ack_due_at"],
            inserted["sla"]["resolve_due_at"],
        ),
    )
    conn.commit()
    conn.close()
    row = fetch_ticket(ticket_id)
    return jsonify(serialize_ticket(row)), 201


def get_ticket_for_response(ticket_id):
    row = fetch_ticket(ticket_id)
    if row is None:
        return error_response("not_found", "ticket not found", 404)
    return jsonify(serialize_ticket(row))


def do_transition(ticket_id, action):
    now = request_now()
    if now is None:
        return error_response("validation", "X-Test-Clock is not a valid RFC 3339 instant", 400)
    row = fetch_ticket(ticket_id)
    if row is None:
        return error_response("not_found", "ticket not found", 404)

    state = row["state"]
    data = serialize_ticket(row)
    if action == "ack":
        if state != "new":
            return error_response("invalid_transition", "acknowledge requires a new ticket", 409)
        updated = data.copy()
        updated["state"] = "acknowledged"
        updated["acknowledged_at"] = to_z(now)
        conn = sqlite3.connect(DB_PATH)
        conn.execute(
            "UPDATE tickets SET state=?, acknowledged_at=? WHERE id=?",
            (updated["state"], updated["acknowledged_at"], ticket_id),
        )
        conn.commit()
        conn.close()
        return get_ticket_for_response(ticket_id)

    if action == "start":
        if state != "acknowledged":
            return error_response("invalid_transition", "start requires an acknowledged ticket", 409)
        conn = sqlite3.connect(DB_PATH)
        conn.execute("UPDATE tickets SET state=? WHERE id=?", ("in_progress", ticket_id))
        conn.commit()
        conn.close()
        return get_ticket_for_response(ticket_id)

    if action == "resolve":
        if state != "in_progress":
            return error_response("invalid_transition", "resolve requires an in_progress ticket", 409)
        conn = sqlite3.connect(DB_PATH)
        conn.execute("UPDATE tickets SET state=?, resolved_at=? WHERE id=?", ("resolved", to_z(now), ticket_id))
        conn.commit()
        conn.close()
        return get_ticket_for_response(ticket_id)

    if action == "close":
        if state != "resolved":
            return error_response("invalid_transition", "close requires a resolved ticket", 409)
        conn = sqlite3.connect(DB_PATH)
        conn.execute("UPDATE tickets SET state=?, closed_at=? WHERE id=?", ("closed", to_z(now), ticket_id))
        conn.commit()
        conn.close()
        return get_ticket_for_response(ticket_id)

    if action == "reopen":
        if state == "new":
            return error_response("invalid_transition", "reopen requires a resolved or closed ticket", 409)
        if state == "resolved":
            resolved_at = iso_to_dt(row["resolved_at"])
            if resolved_at is None:
                return error_response("invalid_transition", "resolved ticket has no resolution time", 409)
            if now > resolved_at + timedelta(days=7):
                return error_response("reopen_window_expired", "reopen window has expired", 409)
            conn = sqlite3.connect(DB_PATH)
            conn.execute(
                "UPDATE tickets SET state=?, resolved_at=NULL WHERE id=?",
                ("in_progress", ticket_id),
            )
            conn.commit()
            conn.close()
            return get_ticket_for_response(ticket_id)
        if state == "closed":
            if C2 != "reopen":
                return error_response("ticket_closed", "closed tickets are immutable", 409)
            closed_at = iso_to_dt(row["closed_at"])
            if closed_at is not None and now > closed_at + timedelta(days=7):
                return error_response("reopen_window_expired", "reopen window has expired", 409)
            conn = sqlite3.connect(DB_PATH)
            conn.execute("UPDATE tickets SET state=?, closed_at=NULL, resolved_at=NULL WHERE id=?", ("in_progress", ticket_id))
            conn.commit()
            conn.close()
            return get_ticket_for_response(ticket_id)
        return error_response("invalid_transition", "reopen is not valid for this state", 409)

    return error_response("invalid_transition", "unexpected action", 409)


def compute_sla_snapshot(ticket_row, now):
    priority = ticket_row["priority"]
    ack_due = iso_to_dt(ticket_row["sla_ack_due_at"])
    resolve_due = iso_to_dt(ticket_row["sla_resolve_due_at"])
    ack_breached = False
    if ticket_row["acknowledged_at"] is None:
        ack_breached = now > ack_due
    else:
        ack_breached = iso_to_dt(ticket_row["acknowledged_at"]) > ack_due

    resolve_breached = False
    if ticket_row["resolved_at"] is None:
        resolve_breached = now > resolve_due
    else:
        resolve_breached = iso_to_dt(ticket_row["resolved_at"]) > resolve_due

    paused = False
    if ticket_row["state"] not in {"resolved", "closed"} and priority in {"P2", "P3", "P4"} and not is_business_hour(now):
        paused = True
    return {
        "priority": priority,
        "ack_due_at": to_z(ack_due),
        "resolve_due_at": to_z(resolve_due),
        "ack_breached": ack_breached,
        "resolve_breached": resolve_breached,
        "paused": paused,
    }


@app.errorhandler(404)
def not_found(_):
    return error_response("not_found", "route not found", 404)


@app.errorhandler(405)
def method_not_allowed(_):
    return error_response("invalid_method", "method not allowed", 405)


@app.get("/health")
def health():
    now = request_now()
    if now is None:
        return error_response("validation", "X-Test-Clock is not a valid RFC 3339 instant", 400)
    return jsonify({"status": "ok", "service": "svcdesk"})


@app.route("/tickets", methods=["GET", "POST"])
def tickets_collection():
    if request.method == "GET":
        now = request_now()
        if now is None:
            return error_response("validation", "X-Test-Clock is not a valid RFC 3339 instant", 400)
        state_filter = request.args.get("state")
        priority_filter = request.args.get("priority")
        conn = sqlite3.connect(DB_PATH)
        conn.row_factory = sqlite3.Row
        query = "SELECT * FROM tickets"
        params = []
        if state_filter:
            query += " WHERE state = ?"
            params.append(state_filter)
        if priority_filter:
            if params:
                query += " AND priority = ?"
            else:
                query += " WHERE priority = ?"
            params.append(priority_filter)
        rows = conn.execute(query, tuple(params)).fetchall()
        conn.close()
        return jsonify([serialize_ticket(row) for row in rows])

    payload = request.get_json(silent=True)
    return create_ticket_from_payload(payload)


@app.route("/tickets/<ticket_id>", methods=["GET"])
def get_ticket(ticket_id):
    now = request_now()
    if now is None:
        return error_response("validation", "X-Test-Clock is not a valid RFC 3339 instant", 400)
    return get_ticket_for_response(ticket_id)


@app.route("/tickets/<ticket_id>/sla", methods=["GET"])
def ticket_sla(ticket_id):
    now = request_now()
    if now is None:
        return error_response("validation", "X-Test-Clock is not a valid RFC 3339 instant", 400)
    row = fetch_ticket(ticket_id)
    if row is None:
        return error_response("not_found", "ticket not found", 404)
    return jsonify(compute_sla_snapshot(row, now))


@app.route("/tickets/<ticket_id>/ack", methods=["POST"])
def ack_ticket(ticket_id):
    return do_transition(ticket_id, "ack")


@app.route("/tickets/<ticket_id>/start", methods=["POST"])
def start_ticket(ticket_id):
    return do_transition(ticket_id, "start")


@app.route("/tickets/<ticket_id>/resolve", methods=["POST"])
def resolve_ticket(ticket_id):
    return do_transition(ticket_id, "resolve")


@app.route("/tickets/<ticket_id>/close", methods=["POST"])
def close_ticket(ticket_id):
    return do_transition(ticket_id, "close")


@app.route("/tickets/<ticket_id>/reopen", methods=["POST"])
def reopen_ticket(ticket_id):
    return do_transition(ticket_id, "reopen")


if __name__ == "__main__":
    ensure_db()
    app.run(host="0.0.0.0", port=8080, debug=False)
