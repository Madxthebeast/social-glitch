import logging
import os
APP_NAME = "SOCIAL GLITCH"
TAGLINE = "Connect privately. Share securely."
LOGIN_SUBTITLE = "Let's secure your social world."
USE_MOCK = os.environ.get("SG_USE_MOCK", "0") != "0"
BACKEND_HOST = os.environ.get("SG_BACKEND_HOST", "127.0.0.1")
BACKEND_PORT = int(os.environ.get("SG_BACKEND_PORT", "5050"))
BACKEND_TIMEOUT = 5

FONT = "Segoe UI"

C = {
    "bg": ("#f7f5f2", "#111111"),
    "sidebar": ("#ffffff", "#181818"),
    "card": ("#ffffff", "#1f1f1f"),
    "card_alt": ("#f1efec", "#2a2a2a"),
    "border": ("#e4e0dc", "#383838"),
    "text": ("#211f1e", "#f5f2ef"),
    "muted": ("#76716d", "#aaa39d"),
    "accent": ("#e60023", "#ff3355"),
    "accent_hover": ("#ad001b", "#e60023"),
    "success": ("#087f5b", "#35c79a"),
    "warning": ("#a15c00", "#f2a93b"),
    "error": ("#cc001f", "#ff5a73"),
    "error_hover": ("#9f0018", "#e60023"),
    "security": ("#3157c9", "#6f8cff"),
}
LEVEL_COLOR = {
    "normal": C["text"], "success": C["success"], "warning": C["warning"],
    "error": C["error"], "security": C["security"],
}
logging.basicConfig(
    filename="socialglitch_debug.log", level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s: %(message)s",
)
log = logging.getLogger("socialglitch")

"""The only module that talks to the backend.
Wire format (TCP, one JSON object per line, both directions):
  request : {"action": "friends.list", "token": "<str|null>", "params": {...}}
  reply   : {"ok": true,  "data": {...}}
            {"ok": false, "error": "ACCESS_DENIED"}
`auth.login` must put a "token" key inside data; it is kept here and sent
with every later request. The GUI never sees it.
"""


import json
import socket

from dataclasses import dataclass
from typing import Any

ERROR_MESSAGES = {
    "INVALID_CREDENTIALS": "Invalid username or password",
    "ACCOUNT_DISABLED": "Account disabled",
    "CONNECTION": "Unable to connect to backend.",
    "USERNAME_TAKEN": "Username already exists.",
    "INVALID_USERNAME": "Invalid username.",
    "ACCESS_DENIED": "Access denied.",
    "USER_NOT_FOUND": "User not found.",
    "INVALID_INPUT": "Some of the information you entered is not valid.",
    "WEAK_PASSWORD": "That password is too weak.",
    "ALREADY_EXISTS": "That already exists or is pending.",
    "NOT_FOUND": "That item could not be found.",
    "EXPIRED": "That invitation has expired.",
    "AUTH_REQUIRED": "Please log in again.",
    "EMAIL_SEND_FAILED": "Unable to send the verification code. Check the backend email configuration.",
    "INVALID_CODE": "Invalid or expired verification code.",
    "WRONG_ANSWER": "Security answer is incorrect.",
    "EMAIL_NOT_CONFIGURED": "Email recovery is not configured on the backend.",
    "SESSION_EXPIRED": "Your session has expired. Please log in again.",
    "ACCOUNT_TEMP_LOCKED": "Too many failed attempts. Try again in 5 minutes.",
}
DEFAULT_ERROR = "Something went wrong.\nPlease try again."

@dataclass
class Result:
    ok: bool
    data: Any = None
    error: str = ""
    @property
    def message(self):
        return ERROR_MESSAGES.get(self.error, DEFAULT_ERROR)
class BackendInterface:
    def __init__(self, transport=None):

        self._transport = transport
        self._token = None

    def _tcp(self, action, params):
        req = {"action": action, "token": self._token, "params": params}
        with socket.create_connection((BACKEND_HOST, BACKEND_PORT), BACKEND_TIMEOUT) as s:
            s.sendall((json.dumps(req) + "\n").encode())
            buf = b""
            while not buf.endswith(b"\n") and len(buf) < 4_000_000:
                chunk = s.recv(4096)
                if not chunk:
                    break
                buf += chunk
        reply = json.loads(buf.decode())
        data = reply.get("data")
        if action == "auth.login" and reply["ok"]:
            self._token = data.pop("token", None)
        return bool(reply["ok"]), data, reply.get("error", "")
    def _call(self, action, **params):
        try:
            if self._transport is not None:
                ok, data, err = self._transport.call(action, params)
            else:
                ok, data, err = self._tcp(action, params)
        except OSError as exc:
            log.error("backend unreachable (%s): %s", action, exc)
            return Result(False, error="CONNECTION")
        except (ValueError, KeyError, TypeError) as exc:
            log.error("bad backend reply (%s): %s", action, exc)
            return Result(False, error="BAD_RESPONSE")
        except Exception:
            log.exception("unexpected failure in %s", action)
            return Result(False, error="INTERNAL")
        if not ok:
            log.info("%s -> %s", action, err)
        return Result(ok, data, err)
    def ping(self): return self._call("ping")
    def login(self, username, password): return self._call("auth.login", username=username, password=password)
    def register(self, name, username, password, email, question, answer): return self._call("auth.register", name=name, username=username, password=password, email=email, question=question, answer=answer)
    def logout(self):
        res = self._call("auth.logout"); self._token = None; return res
    def change_password(self, old, new): return self._call("auth.change_password", old=old, new=new)
    def recovery_question(self, username): return self._call("auth.recovery_question", username=username)
    def reset_security(self, username, answer, new_password): return self._call("auth.reset_security", username=username, answer=answer, new_password=new_password)
    def send_email_code(self, username): return self._call("auth.send_code", username=username)
    def reset_email(self, username, code, new_password): return self._call("auth.reset_email", username=username, code=code, new_password=new_password)

    def get_dashboard(self): return self._call("dashboard.get")
    def get_profile(self, user_id=None): return self._call("profile.get", user_id=user_id)
    def update_name(self, name): return self._call("profile.update_name", name=name)
    def change_username(self, username): return self._call("profile.change_username", username=username)

    def list_friends(self): return self._call("friends.list")
    def remove_friend(self, user_id): return self._call("friends.remove", user_id=user_id)
    def send_friend_request(self, sg_id): return self._call("friends.request", sg_id=sg_id)
    def list_requests(self): return self._call("friends.requests")
    def respond_request(self, request_id, accept): return self._call("friends.respond", request_id=request_id, accept=accept)
    def cancel_request(self, request_id): return self._call("friends.cancel", request_id=request_id)
    def list_blocked(self): return self._call("blocks.list")
    def block_user(self, user_id): return self._call("blocks.add", user_id=user_id)
    def unblock_user(self, user_id): return self._call("blocks.remove", user_id=user_id)
    def list_posts(self): return self._call("posts.list")
    def create_post(self, text, visibility): return self._call("posts.create", text=text, visibility=visibility)
    def delete_post(self, post_id): return self._call("posts.delete", post_id=post_id)
    def like_post(self, post_id): return self._call("posts.like", post_id=post_id)
    def comment_post(self, post_id, text): return self._call("posts.comment", post_id=post_id, text=text)
    def list_conversations(self): return self._call("messages.conversations")
    def get_messages(self, user_id): return self._call("messages.get", user_id=user_id)
    def send_message(self, user_id, text): return self._call("messages.send", user_id=user_id, text=text)
    def delete_message(self, message_id): return self._call("messages.delete", message_id=message_id)

    def list_notifications(self): return self._call("notifications.list")
    def mark_all_read(self): return self._call("notifications.read_all")
    def unread_count(self): return self._call("notifications.unread_count")

    def list_invitations(self): return self._call("invites.list")
    def create_invitation(self, receiver_sg_id): return self._call("invites.create", receiver_sg_id=receiver_sg_id)
    def respond_invitation(self, invite_id, accept): return self._call("invites.respond", invite_id=invite_id, accept=accept)
    def revoke_invitation(self, invite_id): return self._call("invites.revoke", invite_id=invite_id)
    def get_privacy(self): return self._call("privacy.get")
    def set_privacy(self, settings): return self._call("privacy.set", **settings)
    def security_overview(self): return self._call("security.overview")
    def activity_log(self): return self._call("security.activity")
    def submit_report(self, target_type, target_id, reason, description):
        return self._call("reports.submit", target_type=target_type, target_id=target_id, reason=reason, description=description)
    def admin_stats(self): return self._call("admin.stats")
    def admin_reports(self): return self._call("admin.reports")
    def admin_set_report_status(self, report_id, status): return self._call("admin.report_status", report_id=report_id, status=status)
    def admin_users(self): return self._call("admin.users")
    def admin_set_account(self, user_id, enabled): return self._call("admin.set_enabled", user_id=user_id, enabled=enabled)
    def admin_logs(self): return self._call("admin.logs")

def create_backend():
    if USE_MOCK:
        return BackendInterface(MockBackend())
    return BackendInterface()
"""Throwaway in-memory backend for developing the GUI without the C server.
Not a security reference: passwords are plain text here, on purpose, to keep
it short. Delete this file when the real backend is connected.
Demo logins: demo / Demo@1234, admin / Admin@1234, locked / Locked@1234 (disabled).
"""
import itertools
import random
import time
PUBLIC = {"ping", "auth.login", "auth.register"}
class MockError(Exception):
    pass
class MockBackend:
    def __init__(self):
        self.me = None
        self._n = itertools.count(1000)
        self.users, self.pairs, self.requests = {}, set(), []
        self.blocks, self.posts, self.msgs = set(), [], []
        self.notes, self.invites, self.reports, self.logs = [], [], [], []
        self._seed()
    def nid(self): return next(self._n)

    def _add(self, name, username, pw, role="user", enabled=True):
        uid = self.nid()
        self.users[uid] = dict(
            id=uid, sg_id=f"SG-{random.randint(100000, 999999)}", name=name,
            username=username, password=pw, role=role, enabled=enabled, failed=0,
            privacy=dict(visibility="private", profile_view="friends",
                         friend_requests="everyone", messages="friends"))
        return uid
    def log(self, uid, text, level="normal"):
        self.logs.append(dict(uid=uid, time=time.time(), text=text, level=level))
    def note(self, uid, cat, text):
        self.notes.append(dict(id=self.nid(), uid=uid, category=cat, text=text, time=time.time(), read=False))
    def pub(self, uid):
        u = self.users[uid]
        return dict(id=uid, name=u["name"], username=u["username"])
    def is_friend(self, a, b): return frozenset((a, b)) in self.pairs
    def is_blocked(self, a, b): return (a, b) in self.blocks or (b, a) in self.blocks
    def friends_of(self, uid): return [next(iter(p - {uid})) for p in self.pairs if uid in p]

    def user(self, uid):
        if uid not in self.users:
            raise MockError("USER_NOT_FOUND")
        return self.users[uid]

    def _seed(self):
        me = self._add("Demo User", "demo", "Demo@1234")
        alex = self._add("Alex Carter", "alex", "Alex@1234")
        sam = self._add("Sam Rivera", "sam", "Sam@1234")
        jordan = self._add("Jordan Lee", "jordan", "Jordan@1234")
        riley = self._add("Riley Quinn", "riley", "Riley@1234")
        self._add("Site Admin", "admin", "Admin@1234", role="admin")
        self._add("Locked Account", "locked", "Locked@1234", enabled=False)
        self.users[sam]["privacy"]["visibility"] = "public"
        self.pairs |= {frozenset((me, alex)), frozenset((me, sam))}
        self.requests += [dict(id=self.nid(), frm=jordan, to=me), dict(id=self.nid(), frm=me, to=riley)]
        now = time.time()
        self.msgs.append(dict(id=self.nid(), frm=alex, to=me, text="Welcome aboard!", time=now - 3600, read=False))
        self.posts += [
            dict(id=self.nid(), author=alex, time=now - 7200, visibility="friends", text="Testing the friends-only feed.", likes=set(), comments=[]),
            dict(id=self.nid(), author=sam, time=now - 600, visibility="public", text="Public post, anyone can see this.", likes=set(), comments=[]),
        ]
        self.note(me, "friend_request", "Jordan Lee sent you a friend request.")
        self.note(me, "message", "You received a new message.")
        self.log(me, "Privacy setting updated", "security")
    def call(self, action, p):
        time.sleep(0.12)
        if action not in PUBLIC and not self.me:
            return False, None, "AUTH_REQUIRED"
        if action.startswith("admin.") and self.me["role"] != "admin":
            return False, None, "ACCESS_DENIED"
        fn = getattr(self, "h_" + action.replace(".", "_"), None)
        if fn is None:
            return False, None, "NOT_FOUND"
        try:
            return True, fn(p), ""
        except MockError as e:
            return False, None, str(e)
    def h_ping(self, p): return {"mode": "mock"}
    def h_auth_login(self, p):
        u = next((x for x in self.users.values() if x["username"] == p["username"]), None)
        if not u or u["password"] != p["password"]:
            if u:
                u["failed"] += 1
                self.log(u["id"], "Failed login attempt", "warning")
            raise MockError("INVALID_CREDENTIALS")
        if not u["enabled"]:
            raise MockError("ACCOUNT_DISABLED")
        self.me = u
        self.log(u["id"], "Successful login", "security")
        return {"user": dict(id=u["id"], sg_id=u["sg_id"], name=u["name"], username=u["username"], role=u["role"])}
    def h_auth_register(self, p):
        name, un, pw = p["name"].strip(), p["username"].strip(), p["password"]
        if not name or not un or len(pw) < 8:
            raise MockError("INVALID_INPUT")
        if any(x["username"].lower() == un.lower() for x in self.users.values()):
            raise MockError("USERNAME_TAKEN")
        uid = self._add(name, un, pw)
        self.log(uid, "Account created", "security")
        return {"sg_id": self.users[uid]["sg_id"]}
    def h_auth_logout(self, p):
        self.me = None
        return {}

    def h_auth_change_password(self, p):
        if self.me["password"] != p["old"]:
            raise MockError("INVALID_CREDENTIALS")
        if len(p["new"]) < 8:
            raise MockError("WEAK_PASSWORD")
        self.me["password"] = p["new"]
        self.log(self.me["id"], "Password changed", "security")
        self.note(self.me["id"], "security", "Your password was changed.")
        return {}
    def h_dashboard_get(self, p):
        me = self.me["id"]
        return dict(
            friends=len(self.friends_of(me)),
            unread_messages=sum(1 for m in self.msgs if m["to"] == me and not m["read"]),
            notifications=sum(1 for n in self.notes if n["uid"] == me and not n["read"]),
            account=self.me["privacy"]["visibility"].upper(), security_status="PROTECTED",
            recent_activity=self.h_security_activity(p)[:6])
    def h_profile_get(self, p):
        uid = p.get("user_id") or self.me["id"]
        u = self.user(uid)
        info = dict(id=uid, sg_id=u["sg_id"], name=u["name"], username=u["username"], role=u["role"],
                    account_type=u["privacy"]["visibility"].upper(), friends=len(self.friends_of(uid)),
                    posts=sum(1 for x in self.posts if x["author"] == uid))
        me = self.me["id"]
        if uid == me or self.is_friend(me, uid):
            return info
        if self.is_blocked(me, uid) or not (u["privacy"]["visibility"] == "public" and u["privacy"]["profile_view"] == "everyone"):
            return dict(restricted=True, id=uid, name=u["name"], username=u["username"])
        return info

    def h_profile_update_name(self, p):
        if not p["name"].strip():
            raise MockError("INVALID_INPUT")
        self.me["name"] = p["name"].strip()
        return {}
    def h_profile_change_username(self, p):
        un = p["username"].strip()
        if len(un) < 3:
            raise MockError("INVALID_USERNAME")
        if any(x["username"].lower() == un.lower() and x is not self.me for x in self.users.values()):
            raise MockError("USERNAME_TAKEN")
        self.me["username"] = un
        return {}
    def h_friends_list(self, p):
        return [dict(self.pub(f), online=f % 2 == 0) for f in self.friends_of(self.me["id"])]

    def h_friends_remove(self, p):
        self.pairs.discard(frozenset((self.me["id"], p["user_id"])))
        return {}

    def h_friends_request(self, p):
        me = self.me["id"]
        t = next((u for u in self.users.values() if u["sg_id"].lower() == p["sg_id"].strip().lower()), None)
        if not t:
            raise MockError("USER_NOT_FOUND")
        if t["id"] == me:
            raise MockError("INVALID_INPUT")
        if self.is_blocked(me, t["id"]) or t["privacy"]["friend_requests"] == "nobody":
            raise MockError("ACCESS_DENIED")
        if self.is_friend(me, t["id"]) or any({r["frm"], r["to"]} == {me, t["id"]} for r in self.requests):
            raise MockError("ALREADY_EXISTS")
        self.requests.append(dict(id=self.nid(), frm=me, to=t["id"]))
        self.note(t["id"], "friend_request", f"{self.me['name']} sent you a friend request.")
        return {}
    def h_friends_requests(self, p):
        me = self.me["id"]
        return dict(received=[dict(id=r["id"], user=self.pub(r["frm"])) for r in self.requests if r["to"] == me],
                    sent=[dict(id=r["id"], user=self.pub(r["to"])) for r in self.requests if r["frm"] == me])
    def h_friends_respond(self, p):
        r = next((r for r in self.requests if r["id"] == p["request_id"] and r["to"] == self.me["id"]), None)
        if not r:
            raise MockError("NOT_FOUND")
        self.requests.remove(r)
        if p["accept"]:
            self.pairs.add(frozenset((r["frm"], r["to"])))
            self.note(r["frm"], "friend_request", f"{self.me['name']} accepted your friend request.")
        return {}

    def h_friends_cancel(self, p):
        r = next((r for r in self.requests if r["id"] == p["request_id"] and r["frm"] == self.me["id"]), None)
        if not r:
            raise MockError("NOT_FOUND")
        self.requests.remove(r)
        return {}
    def h_blocks_list(self, p):
        return [self.pub(b) for a, b in self.blocks if a == self.me["id"]]
    def h_blocks_add(self, p):
        me, other = self.me["id"], self.user(p["user_id"])["id"]
        self.blocks.add((me, other))
        self.pairs.discard(frozenset((me, other)))
        self.requests = [r for r in self.requests if {r["frm"], r["to"]} != {me, other}]
        self.log(me, f"Blocked @{self.users[other]['username']}", "security")
        return {}

    def h_blocks_remove(self, p):
        self.blocks.discard((self.me["id"], p["user_id"]))
        return {}

    def can_see(self, post):
        me, a = self.me["id"], post["author"]
        if a == me:
            return True
        if self.is_blocked(me, a):
            return False
        return post["visibility"] == "public" or (post["visibility"] == "friends" and self.is_friend(me, a))

    def h_posts_list(self, p):
        me = self.me["id"]
        return [dict(id=x["id"], author=self.pub(x["author"]), time=x["time"], visibility=x["visibility"],
                     text=x["text"], likes=len(x["likes"]), liked=me in x["likes"],
                     comments=len(x["comments"]), mine=x["author"] == me)
                for x in sorted(self.posts, key=lambda x: -x["time"]) if self.can_see(x)]
    def h_posts_create(self, p):
        text = p["text"].strip()
        if not text or len(text) > 500 or p["visibility"] not in ("public", "friends", "private"):
            raise MockError("INVALID_INPUT")
        self.posts.append(dict(id=self.nid(), author=self.me["id"], time=time.time(), visibility=p["visibility"], text=text, likes=set(), comments=[]))
        self.log(self.me["id"], "Post created")
        return {}
    def _post(self, pid):
        x = next((x for x in self.posts if x["id"] == pid), None)
        if not x or not self.can_see(x):
            raise MockError("NOT_FOUND")
        return x

    def h_posts_delete(self, p):
        x = self._post(p["post_id"])
        if x["author"] != self.me["id"]:
            raise MockError("ACCESS_DENIED")
        self.posts.remove(x)
        return {}

    def h_posts_like(self, p):
        x = self._post(p["post_id"])
        x["likes"] ^= {self.me["id"]}
        return {}
    def h_posts_comment(self, p):
        x = self._post(p["post_id"])
        if not p["text"].strip():
            raise MockError("INVALID_INPUT")
        x["comments"].append(dict(author=self.me["id"], text=p["text"].strip()))
        return {}
    def can_message(self, other):
        me = self.me["id"]
        if self.is_blocked(me, other):
            return False
        rule = self.users[other]["privacy"]["messages"]
        return rule == "everyone" or (rule == "friends" and self.is_friend(me, other))

    def h_messages_conversations(self, p):
        me, out = self.me["id"], []
        for f in self.friends_of(me):
            convo = [m for m in self.msgs if {m["frm"], m["to"]} == {me, f}]
            out.append(dict(user=self.pub(f), last=convo[-1]["text"] if convo else "",
                            unread=sum(1 for m in convo if m["to"] == me and not m["read"])))
        return out
    def h_messages_get(self, p):
        me, other = self.me["id"], self.user(p["user_id"])["id"]
        convo = sorted((m for m in self.msgs if {m["frm"], m["to"]} == {me, other}), key=lambda m: m["time"])
        for m in convo:
            if m["to"] == me:
                m["read"] = True
        return dict(can_message=self.can_message(other),
                    messages=[dict(id=m["id"], mine=m["frm"] == me, text=m["text"], time=m["time"]) for m in convo])

    def h_messages_send(self, p):
        other = self.user(p["user_id"])["id"]
        if not self.can_message(other):
            raise MockError("ACCESS_DENIED")
        if not p["text"].strip():
            raise MockError("INVALID_INPUT")
        self.msgs.append(dict(id=self.nid(), frm=self.me["id"], to=other, text=p["text"].strip(), time=time.time(), read=False))
        self.note(other, "message", "You received a new message.")
        return {}

    def h_messages_delete(self, p):
        m = next((m for m in self.msgs if m["id"] == p["message_id"] and m["frm"] == self.me["id"]), None)
        if not m:
            raise MockError("NOT_FOUND")
        self.msgs.remove(m)
        return {}

    def h_notifications_list(self, p):
        mine = [n for n in self.notes if n["uid"] == self.me["id"]]
        return sorted(({k: v for k, v in n.items() if k != "uid"} for n in mine), key=lambda n: -n["time"])

    def h_notifications_read_all(self, p):
        for n in self.notes:
            if n["uid"] == self.me["id"]:
                n["read"] = True
        return {}
    def h_notifications_unread_count(self, p):
        return {"count": sum(1 for n in self.notes if n["uid"] == self.me["id"] and not n["read"])}

    def _status(self, i):
        return "expired" if i["status"] == "pending" and time.time() > i["expires"] else i["status"]

    def h_invites_list(self, p):
        me = self.me["id"]
        def row(i, other):
            return dict(id=i["id"], user=self.pub(i[other]), status=self._status(i), expires=i["expires"], payload=i["payload"])
        return dict(sent=[row(i, "to") for i in self.invites if i["frm"] == me],
                    received=[row(i, "frm") for i in self.invites if i["to"] == me])

    def h_invites_create(self, p):
        t = next((u for u in self.users.values() if u["sg_id"].lower() == p["receiver_sg_id"].strip().lower()), None)
        if not t:
            raise MockError("USER_NOT_FOUND")
        if t["id"] == self.me["id"] or self.is_blocked(self.me["id"], t["id"]):
            raise MockError("ACCESS_DENIED")
        iid = f"INV-{self.nid():06d}"
        inv = dict(id=iid, frm=self.me["id"], to=t["id"], status="pending", expires=time.time() + 86400,
                   payload=f"SG_INVITE|{self.me['sg_id']}|{iid}")
        self.invites.append(inv)
        self.note(t["id"], "invitation", "You received a private invitation.")
        return dict(id=iid, payload=inv["payload"], expires=inv["expires"])
    def _invite(self, iid, who):
        i = next((i for i in self.invites if i["id"] == iid and i[who] == self.me["id"]), None)
        if not i:
            raise MockError("NOT_FOUND")
        if self._status(i) == "expired":
            raise MockError("EXPIRED")
        if i["status"] != "pending":
            raise MockError("INVALID_INPUT")
        return i
    def h_invites_respond(self, p):
        i = self._invite(p["invite_id"], "to")
        i["status"] = "accepted" if p["accept"] else "rejected"
        if p["accept"]:
            self.pairs.add(frozenset((i["frm"], i["to"])))
        return {}
    def h_invites_revoke(self, p):
        self._invite(p["invite_id"], "frm")["status"] = "revoked"
        return {}

    CHOICES = dict(visibility={"public", "private"}, profile_view={"everyone", "friends", "nobody"},
                   friend_requests={"everyone", "friends_of_friends", "nobody"}, messages={"everyone", "friends", "nobody"})
    def h_privacy_get(self, p): return dict(self.me["privacy"])

    def h_privacy_set(self, p):
        for k, v in p.items():
            if v not in self.CHOICES.get(k, ()):
                raise MockError("INVALID_INPUT")
        self.me["privacy"].update(p)
        self.log(self.me["id"], "Privacy setting updated", "security")
        return {}

    def h_security_activity(self, p):
        mine = [dict(time=l["time"], text=l["text"], level=l["level"]) for l in self.logs if l["uid"] == self.me["id"]]
        return sorted(mine, key=lambda l: -l["time"])[:40]
    def h_security_overview(self, p):
        me = self.me["id"]
        acts = self.h_security_activity(p)
        logins = [a for a in acts if a["text"] == "Successful login"]
        return dict(account_status="Protected", privacy=self.me["privacy"]["visibility"].capitalize(),
                    password="Strong", last_login=logins[0]["time"] if logins else None,
                    failed_logins=self.me["failed"], blocked=sum(1 for a, _ in self.blocks if a == me),
                    events=[a for a in acts if a["level"] == "security"][:5])
    def h_reports_submit(self, p):
        if p["target_type"] not in ("user", "post", "message") or not p["target_id"].strip() or not p["reason"].strip():
            raise MockError("INVALID_INPUT")
        rid = f"REP-{self.nid():05d}"
        self.reports.append(dict(id=rid, reporter=self.me["username"], target_type=p["target_type"], target_id=p["target_id"].strip(),
                                 reason=p["reason"].strip(), description=p["description"].strip(), status="open", time=time.time()))
        self.log(self.me["id"], f"Report {rid} submitted")
        return {"id": rid}

    def h_admin_stats(self, p):
        return dict(reports=sum(1 for r in self.reports if r["status"] != "closed"),
                    active_users=sum(1 for u in self.users.values() if u["enabled"]),
                    disabled=sum(1 for u in self.users.values() if not u["enabled"]),
                    security_events=sum(1 for l in self.logs if l["level"] in ("security", "warning")))

    def h_admin_reports(self, p): return sorted(self.reports, key=lambda r: -r["time"])

    def h_admin_report_status(self, p):
        r = next((r for r in self.reports if r["id"] == p["report_id"]), None)
        if not r or p["status"] not in ("reviewing", "closed"):
            raise MockError("NOT_FOUND")
        r["status"] = p["status"]
        return {}
    def h_admin_users(self, p):
        return [dict(id=u["id"], name=u["name"], username=u["username"], role=u["role"], enabled=u["enabled"]) for u in self.users.values()]
    def h_admin_set_enabled(self, p):
        u = self.user(p["user_id"])
        if u["id"] == self.me["id"]:
            raise MockError("ACCESS_DENIED")
        u["enabled"] = bool(p["enabled"])
        self.log(self.me["id"], f"{'Re-enabled' if p['enabled'] else 'Disabled'} @{u['username']}", "security")
        return {}
    def h_admin_logs(self, p):
        return [dict(time=l["time"], text=f"@{self.users[l['uid']]['username']}: {l['text']}", level=l["level"])
                for l in sorted(self.logs, key=lambda l: -l["time"])[:80]]
import customtkinter as ctk

WHITE = ("#ffffff", "#ffffff")
def _button(master, text, command, fg, hover, color, **kw):
    kw.setdefault("height", 36)
    return ctk.CTkButton(master, text=text, command=command, fg_color=fg, hover_color=hover,
                         text_color=color, corner_radius=10, font=ctk.CTkFont(FONT, 13, "bold"), **kw)

def primary_button(master, text, command=None, **kw):
    return _button(master, text, command, C["accent"], C["accent_hover"], WHITE, **kw)
def secondary_button(master, text, command=None, **kw):
    return _button(master, text, command, C["card_alt"], C["border"], C["text"], **kw)

def danger_button(master, text, command=None, **kw):
    return _button(master, text, command, C["error"], C["error_hover"], WHITE, **kw)
def ghost_button(master, text, command=None, **kw):
    return _button(master, text, command, "transparent", C["card_alt"], C["text"], **kw)

import time
import customtkinter as ctk
from PIL import Image, ImageDraw, ImageFont, ImageOps
def font(size=13, weight="normal"):
    return ctk.CTkFont(FONT, size, weight)

class Card(ctk.CTkFrame):
    def __init__(self, master, **kw):
        kw.setdefault("fg_color", C["card"])
        kw.setdefault("corner_radius", 14)
        kw.setdefault("border_width", 1)
        kw.setdefault("border_color", C["border"])
        super().__init__(master, **kw)
class StatCard(Card):
    def __init__(self, master, title, value="…"):
        super().__init__(master)
        ctk.CTkLabel(self, text=title, font=font(12), text_color=C["muted"]).pack(anchor="w", padx=16, pady=(14, 0))
        self.value = ctk.CTkLabel(self, text=value, font=font(26, "bold"))
        self.value.pack(anchor="w", padx=16, pady=(0, 14))

    def set(self, value, color=None):
        self.value.configure(text=str(value), text_color=color or C["text"])

def empty_state(master, title, sub=""):
    box = ctk.CTkFrame(master, fg_color="transparent")
    ctk.CTkLabel(box, text=title, font=font(15, "bold"), text_color=C["muted"]).pack()
    if sub:
        ctk.CTkLabel(box, text=sub, font=font(12), text_color=C["muted"]).pack(pady=(2, 0))
    return box

def time_ago(ts):
    d = max(0, time.time() - ts)
    for size, name in ((86400, "day"), (3600, "hour"), (60, "minute")):
        if d >= size:
            n = int(d // size)
            return f"{n} {name}{'s' if n != 1 else ''} ago"
    return "just now"

def time_left(ts):
    rem = ts - time.time()
    if rem <= 0:
        return "Expired"
    return f"{int(rem // 3600)}h {int(rem % 3600 // 60)}m left"
_SHADES = ["#0f766e", "#1f6feb", "#8957e5", "#bf4b8a", "#b35900", "#2f855a"]
_avatars = {}
def _pil_font(px):
    for name in ("DejaVuSans-Bold.ttf", "arialbd.ttf", "Arial Bold.ttf"):
        try:
            return ImageFont.truetype(name, px)
        except OSError:
            continue
    try:
        return ImageFont.load_default(px)
    except TypeError:
        return ImageFont.load_default()
def avatar(master, name, size=48):
    key = (name, size)
    if key not in _avatars:
        s = size * 4
        img = Image.new("RGBA", (s, s), (0, 0, 0, 0))
        d = ImageDraw.Draw(img)
        d.ellipse((0, 0, s - 1, s - 1), fill=_SHADES[sum(map(ord, name)) % len(_SHADES)])
        letter = (name.strip()[:1] or "?").upper()
        try:
            d.text((s / 2, s / 2), letter, fill="white", font=_pil_font(int(s * 0.5)), anchor="mm")
        except ValueError:
            d.text((s * 0.38, s * 0.3), letter, fill="white", font=_pil_font(int(s * 0.5)))
        _avatars[key] = ctk.CTkImage(img, size=(size, size))
    return ctk.CTkLabel(master, image=_avatars[key], text="")

def person_row(master, user, online=None):
    row = Card(master)
    row.pack(fill="x", pady=4)
    avatar(row, user["name"], 40).pack(side="left", padx=(12, 8), pady=10)
    if online is not None:
        ctk.CTkLabel(row, text="●", width=14, text_color=C["success"] if online else C["muted"]).pack(side="left")
    box = ctk.CTkFrame(row, fg_color="transparent")
    box.pack(side="left", pady=8)
    ctk.CTkLabel(box, text=user["name"], font=font(14, "bold")).pack(anchor="w")
    ctk.CTkLabel(box, text="@" + user["username"], font=font(12), text_color=C["muted"]).pack(anchor="w")
    actions = ctk.CTkFrame(row, fg_color="transparent")
    actions.pack(side="right", padx=10)
    return actions
ICONS = {"normal": "✓", "success": "✓", "warning": "⚠", "security": "🔐", "error": "✕"}
def activity_list(frame, events, empty="No activity yet."):
    for w in frame.winfo_children():
        w.destroy()
    if not events:
        ctk.CTkLabel(frame, text=empty, text_color=C["muted"]).pack(pady=20)
        return
    for e in events:
        level = e.get("level", "normal")
        color = LEVEL_COLOR.get(level, C["text"])
        r = ctk.CTkFrame(frame, fg_color="transparent")
        r.pack(fill="x", padx=14, pady=3)
        ctk.CTkLabel(r, text=ICONS.get(level, "•"), text_color=color, width=26).pack(side="left")
        ctk.CTkLabel(r, text=time.strftime("%H:%M", time.localtime(e["time"])), text_color=C["muted"], width=50).pack(side="left")
        ctk.CTkLabel(r, text=e["text"], text_color=color, anchor="w").pack(side="left", fill="x", expand=True)
class Tabs(ctk.CTkFrame):
    def __init__(self, master, names, on_change=None):
        super().__init__(master, fg_color="transparent")
        self.on_change = on_change
        self.pages = {n: ctk.CTkFrame(self, fg_color="transparent") for n in names}
        self.bar = ctk.CTkSegmentedButton(
            self, values=names, command=self.show, selected_color=C["accent"],
            selected_hover_color=C["accent_hover"], unselected_color=C["card_alt"],
            unselected_hover_color=C["border"], text_color=C["text"])
        self.bar.pack(anchor="w", pady=(0, 12))
        self.bar.set(names[0])
        self.swap(names[0])
    def swap(self, name):
        for p in self.pages.values():
            p.pack_forget()
        self.pages[name].pack(fill="both", expand=True)
    def show(self, name):
        self.bar.set(name)
        self.swap(name)
        if self.on_change:
            self.on_change(name)

    @property
    def current(self):
        return self.bar.get()
import customtkinter as ctk
class _Modal(ctk.CTkToplevel):
    def __init__(self, parent, title, width=400, height=200):
        root = parent.winfo_toplevel()
        super().__init__(root)
        self.title(title)
        self.resizable(False, False)
        self.configure(fg_color=C["bg"])
        x = max(root.winfo_rootx() + (root.winfo_width() - width) // 2, 0)
        y = max(root.winfo_rooty() + (root.winfo_height() - height) // 2, 0)
        self.geometry(f"{width}x{height}+{x}+{y}")
        self.transient(root)
        self.result = None
        self.after(120, self._focus)

    def _focus(self):
        try:
            self.grab_set()
            self.focus_force()
        except Exception:
            pass

    def close(self, value=None):
        self.result = value
        self.destroy()

    def ask(self):
        self.wait_window()
        return self.result
def _head(d, title, message):
    ctk.CTkLabel(d, text=title, font=font(16, "bold")).pack(anchor="w", padx=22, pady=(20, 4))
    if message:
        ctk.CTkLabel(d, text=message, wraplength=350, justify="left", text_color=C["muted"]).pack(anchor="w", padx=22)

def _bar(d):
    bar = ctk.CTkFrame(d, fg_color="transparent")
    bar.pack(side="bottom", fill="x", padx=22, pady=18)
    return bar

def confirm(parent, title, message, ok_text="Confirm", danger=False):
    d = _Modal(parent, title, 400, 190)
    _head(d, title, message)
    bar = _bar(d)
    (danger_button if danger else primary_button)(bar, ok_text, lambda: d.close(True)).pack(side="right")
    secondary_button(bar, "Cancel", lambda: d.close(False)).pack(side="right", padx=8)
    return bool(d.ask())
def info(parent, title, message):
    d = _Modal(parent, title, 400, 220)
    _head(d, title, message)
    primary_button(_bar(d), "OK", d.close).pack(side="right")
    d.ask()
def prompt(parent, title, label, initial="", secret=False):
    d = _Modal(parent, title, 400, 210)
    _head(d, title, label)
    entry = ctk.CTkEntry(d, height=36, show="•" if secret else "")
    entry.pack(fill="x", padx=22, pady=10)
    entry.insert(0, initial)
    entry.bind("<Return>", lambda e: d.close(entry.get()))
    bar = _bar(d)
    primary_button(bar, "OK", lambda: d.close(entry.get())).pack(side="right")
    secondary_button(bar, "Cancel", d.close).pack(side="right", padx=8)
    d.after(200, entry.focus_set)
    return d.ask()
def qr_image(payload, px=240):
    import qrcode
    qr = qrcode.QRCode(box_size=8, border=2)
    qr.add_data(payload)
    qr.make(fit=True)
    img = qr.make_image(fill_color="black", back_color="white")
    img = img.get_image() if hasattr(img, "get_image") else img
    return img.convert("RGB").resize((px, px))

def qr_dialog(parent, payload, invitation_id, expires_ts):
    d = _Modal(parent, "Invitation QR code", 380, 520)
    ctk.CTkLabel(d, text="SOCIAL GLITCH INVITATION", font=font(16, "bold"), text_color=C["accent"]).pack(pady=(20, 10))
    try:
        pic = ctk.CTkImage(qr_image(payload), size=(240, 240))
        ctk.CTkLabel(d, image=pic, text="").pack()
    except Exception:
        ctk.CTkLabel(d, text="QR code could not be generated.", text_color=C["error"]).pack(pady=40)
    ctk.CTkLabel(d, text="Scan this QR code to receive\na private invitation.", text_color=C["muted"]).pack(pady=10)
    ctk.CTkLabel(d, text=f"Invitation:\n{invitation_id}", font=font(14, "bold")).pack()
    ctk.CTkLabel(d, text=f"Expires:\n{time_left(expires_ts)}", text_color=C["muted"]).pack(pady=8)
    primary_button(d, "Close", d.close).pack(pady=8)
    d.ask()
import customtkinter as ctk
class Navbar(ctk.CTkFrame):
    def __init__(self, master, on_bell, on_user):
        super().__init__(master, fg_color=C["sidebar"], corner_radius=0, height=56)
        ctk.CTkLabel(self, text="◈ " + APP_NAME, font=font(16, "bold"), text_color=C["accent"]).pack(side="left", padx=18)
        self.user_btn = ghost_button(self, "👤", on_user, width=120)
        self.user_btn.pack(side="right", padx=(0, 12), pady=10)
        self.bell = ghost_button(self, "🔔", on_bell, width=60)
        self.bell.pack(side="right", pady=10)
    def set_user(self, name):
        self.user_btn.configure(text=f"👤  {name}")
    def set_unread(self, n):
        self.bell.configure(text=f"🔔 {n}" if n else "🔔")
import customtkinter as ctk

CATEGORY_ICON = {"friend_request": "🔔", "message": "✉", "invitation": "🔗", "security": "🔐", "report": "⚑"}
_toast = {"w": None}

def show_toast(root, text, kind="normal"):
    if _toast["w"] is not None:
        try:
            _toast["w"].destroy()
        except Exception:
            pass
    color = {"error": C["error"], "success": C["success"]}.get(kind, C["accent"])
    t = ctk.CTkFrame(root, fg_color=C["card"], border_width=2, border_color=color, corner_radius=12)
    ctk.CTkLabel(t, text=text, font=font(13), justify="left", wraplength=320).pack(padx=16, pady=10)
    t.place(relx=1.0, rely=1.0, x=-20, y=-20, anchor="se")
    _toast["w"] = t
    def drop():
        try:
            t.destroy()
        except Exception:
            pass
    root.after(3200, drop)
def notification_row(master, item):
    unread = not item["read"]
    row = Card(master, fg_color=C["card_alt"] if unread else C["card"],
               border_color=C["accent"] if unread else C["border"])
    row.pack(fill="x", pady=4)
    ctk.CTkLabel(row, text=CATEGORY_ICON.get(item["category"], "•"), font=font(18), width=40).pack(side="left", padx=(8, 0), pady=10)
    ctk.CTkLabel(row, text=item["text"], font=font(13, "bold" if unread else "normal"), anchor="w").pack(side="left", fill="x", expand=True, padx=6)
    ctk.CTkLabel(row, text=time_ago(item["time"]), font=font(11), text_color=C["muted"]).pack(side="right", padx=12)
    if unread:
        ctk.CTkLabel(row, text="●", text_color=C["accent"], width=16).pack(side="right")
    return row
import customtkinter as ctk

NAV = [
    ("dashboard", "Dashboard", "▦"), ("profile", "Profile", "◉"), ("friends", "Friends", "👥"),
    ("posts", "Posts", "✎"), ("messages", "Messages", "✉"), ("invitations", "Invitations", "🔗"),
    ("notifications", "Notifications", "🔔"), ("privacy", "Privacy", "🔒"), ("security", "Security", "🛡"),
    ("reports", "Reports", "⚑"), ("settings", "Settings", "⚙"),
]

class Sidebar(ctk.CTkFrame):
    def __init__(self, master, on_nav, on_logout, is_admin=False):
        super().__init__(master, fg_color=C["sidebar"], corner_radius=0, width=210)
        self.pack_propagate(False)
        self.compact = False
        self.buttons = {}
        items = NAV + ([("admin", "Admin", "★")] if is_admin else [])
        for key, label, icon in items:
            b = ctk.CTkButton(self, text=f"  {icon}   {label}", anchor="w", height=38, corner_radius=8,
                              fg_color="transparent", hover_color=C["card_alt"], text_color=C["text"],
                              font=font(13), command=lambda k=key: on_nav(k))
            b.pack(fill="x", padx=10, pady=2)
            self.buttons[key] = (b, label, icon)
        self.logout = ctk.CTkButton(self, text="  ⏻   Logout", anchor="w", height=38, corner_radius=8,
                                    fg_color="transparent", hover_color=C["card_alt"], text_color=C["error"],
                                    font=font(13), command=on_logout)
        self.logout.pack(side="bottom", fill="x", padx=10, pady=12)
    def select(self, key):
        for k, (b, _, _) in self.buttons.items():
            b.configure(fg_color=C["card_alt"] if k == key else "transparent")
    def set_compact(self, flag):
        if flag == self.compact:
            return
        self.compact = flag
        self.configure(width=64 if flag else 210)
        for b, label, icon in self.buttons.values():
            b.configure(text=icon if flag else f"  {icon}   {label}", anchor="center" if flag else "w")
        self.logout.configure(text="⏻" if flag else "  ⏻   Logout", anchor="center" if flag else "w")
import customtkinter as ctk
class Screen(ctk.CTkFrame):


    def __init__(self, master, app):
        super().__init__(master, fg_color="transparent")
        self.app = app
        self.build()
    def build(self): pass
    def on_show(self, **kw): pass

    @property
    def be(self):
        return self.app.backend

    def run(self, fn, done=None, button=None, *args, **kw):
        self.app.run_async(fn, done, button, *args, **kw)
    def ok(self, res):
        if not res.ok:
            self.app.report_error(res)
        return res.ok

    def header(self, title, sub=None):
        ctk.CTkLabel(self, text=title, font=font(24, "bold")).pack(anchor="w")
        if sub:
            ctk.CTkLabel(self, text=sub, font=font(13), text_color=C["muted"]).pack(anchor="w")
        ctk.CTkFrame(self, height=10, fg_color="transparent").pack()

    def scroll(self, parent=None):
        return ctk.CTkScrollableFrame(parent or self, fg_color="transparent")

    @staticmethod
    def wipe(frame):
        for w in frame.winfo_children():
            w.destroy()

import customtkinter as ctk
class AdminScreen(Screen):


    def build(self):
        self.header("ADMIN CENTER")
        grid = ctk.CTkFrame(self, fg_color="transparent")
        grid.pack(fill="x")
        self.stats = {}
        for i, (key, title) in enumerate([("reports", "Reports"), ("active_users", "Active Users"),
                                          ("disabled", "Disabled Accounts"), ("security_events", "Security Events")]):
            grid.grid_columnconfigure(i, weight=1, uniform="a")
            c = StatCard(grid, title)
            c.grid(row=0, column=i, sticky="ew", padx=4, pady=4)
            self.stats[key] = c
        self.tabs = Tabs(self, ["Reports", "Users", "Logs"], on_change=lambda n: self.load())
        self.tabs.pack(fill="both", expand=True, pady=(10, 0))
        self.reports = self.scroll(self.tabs.pages["Reports"]); self.reports.pack(fill="both", expand=True)
        self.users = self.scroll(self.tabs.pages["Users"]); self.users.pack(fill="both", expand=True)
        self.logs = Card(self.tabs.pages["Logs"]); self.logs.pack(fill="both", expand=True)
    def on_show(self, **kw):
        self.run(self.be.admin_stats, self.got_stats)
        self.load()

    def load(self):
        t = self.tabs.current
        if t == "Reports":
            self.run(self.be.admin_reports, self.got_reports)
        elif t == "Users":
            self.run(self.be.admin_users, self.got_users)
        else:
            self.run(self.be.admin_logs, lambda r: self.ok(r) and activity_list(self.logs, r.data))
    def got_stats(self, res):
        if self.ok(res):
            for k, card in self.stats.items():
                card.set(res.data[k])

    def got_reports(self, res):
        if not self.ok(res):
            return
        self.wipe(self.reports)
        if not res.data:
            empty_state(self.reports, "No reports.").pack(pady=40)
        for r in res.data:
            card = Card(self.reports)
            card.pack(fill="x", pady=4)
            top = ctk.CTkFrame(card, fg_color="transparent")
            top.pack(fill="x", padx=14, pady=(10, 2))
            ctk.CTkLabel(top, text=r["id"], font=font(14, "bold")).pack(side="left")
            color = {"open": C["warning"], "reviewing": C["security"], "closed": C["muted"]}.get(r["status"], C["text"])
            ctk.CTkLabel(top, text=r["status"].upper(), text_color=color, font=font(11, "bold")).pack(side="right")
            ctk.CTkLabel(card, text=f"{r['target_type'].capitalize()} {r['target_id']} · by @{r['reporter']} · {time_ago(r['time'])}",
                         text_color=C["muted"], font=font(12)).pack(anchor="w", padx=14)
            ctk.CTkLabel(card, text=f"Reason: {r['reason']}\n{r['description']}".strip(), justify="left", wraplength=620, anchor="w").pack(anchor="w", padx=14, pady=4)
            if r["status"] != "closed":
                bar = ctk.CTkFrame(card, fg_color="transparent")
                bar.pack(anchor="e", padx=12, pady=(0, 10))
                if r["status"] == "open":
                    secondary_button(bar, "Review", lambda r=r: self.set_status(r, "reviewing"), width=80, height=30).pack(side="left", padx=2)
                primary_button(bar, "Close", lambda r=r: self.set_status(r, "closed"), width=80, height=30).pack(side="left", padx=2)
    def set_status(self, r, status):
        def done(res):
            if self.ok(res):
                self.on_show()
        self.run(self.be.admin_set_report_status, done, None, r["id"], status)
    def got_users(self, res):
        if not self.ok(res):
            return
        self.wipe(self.users)
        for u in res.data:
            a = person_row(self.users, u)
            ctk.CTkLabel(a, text=f"{u['role'].capitalize()} · {'Active' if u['enabled'] else 'Disabled'}",
                         text_color=C["success"] if u["enabled"] else C["error"], font=font(12)).pack(side="left", padx=8)
            if u["id"] != self.app.user["id"]:
                if u["enabled"]:
                    danger_button(a, "Disable", lambda u=u: self.toggle(u, False), width=80, height=30).pack(side="left")
                else:
                    secondary_button(a, "Re-enable", lambda u=u: self.toggle(u, True), width=90, height=30).pack(side="left")
    def toggle(self, u, enable):
        verb = "Re-enable" if enable else "Disable"
        if confirm(self, f"{verb} account", f"{verb} the account of @{u['username']}?", verb, not enable):
            def done(res):
                if self.ok(res):
                    self.app.toast(f"Account {'enabled' if enable else 'disabled'}.", "success")
                    self.on_show()
            self.run(self.be.admin_set_account, done, None, u["id"], enable)
import customtkinter as ctk
class DashboardScreen(Screen):
    def build(self):
        self.header("Dashboard")
        self.welcome = ctk.CTkLabel(self, text="", font=font(15), text_color=C["muted"])
        self.welcome.pack(anchor="w")
        grid = ctk.CTkFrame(self, fg_color="transparent")
        grid.pack(fill="x", pady=10)
        for i in range(3):
            grid.grid_columnconfigure(i, weight=1, uniform="stat")
        titles = [("friends", "Friends"), ("unread", "Unread Messages"), ("notes", "Notifications"),
                  ("account", "Account"), ("security", "Security Status")]
        self.cards = {}
        for i, (key, title) in enumerate(titles):
            c = StatCard(grid, title)
            c.grid(row=i // 3, column=i % 3, sticky="ew", padx=5, pady=5)
            self.cards[key] = c
        ctk.CTkLabel(self, text="Your private space", font=font(20, "bold")).pack(anchor="w", pady=(8, 2))
        ctk.CTkLabel(self, text="A calm, visual feed for friends, ideas and secure conversations.", text_color=C["muted"]).pack(anchor="w", pady=(0, 8))
        ctk.CTkLabel(self, text="Recent Activity", font=font(15, "bold")).pack(anchor="w", pady=(8, 6))
        self.feed = Card(self)
        self.feed.pack(fill="both", expand=True)
    def on_show(self, **kw):
        self.welcome.configure(text=f"Welcome, {self.app.user['name']}")
        self.run(self.be.get_dashboard, self.loaded)
    def loaded(self, res):
        if not self.ok(res):
            return
        d = res.data
        self.cards["friends"].set(d["friends"])
        self.cards["unread"].set(d["unread_messages"])
        self.cards["notes"].set(d["notifications"])
        self.cards["account"].set(d["account"], C["security"])
        self.cards["security"].set(d["security_status"], C["success"] if d["security_status"] == "PROTECTED" else C["warning"])
        activity_list(self.feed, d["recent_activity"])
import customtkinter as ctk
class FriendsScreen(Screen):
    def build(self):
        self.header("Friends")
        self.friends = []
        self.tabs = Tabs(self, ["Friends", "Received", "Sent", "Blocked"], on_change=lambda n: self.load())
        self.tabs.pack(fill="both", expand=True)
        pg = self.tabs.pages

        top = ctk.CTkFrame(pg["Friends"], fg_color="transparent")
        top.pack(fill="x")
        self.search = ctk.CTkEntry(top, placeholder_text="Search friends...", height=36)
        self.search.pack(side="left", fill="x", expand=True)
        self.search.bind("<KeyRelease>", lambda e: self.draw_friends())
        self.count = ctk.CTkLabel(top, text="", text_color=C["muted"])
        self.count.pack(side="left", padx=12)
        add = ctk.CTkFrame(pg["Friends"], fg_color="transparent")
        add.pack(fill="x", pady=8)
        self.sg_id = ctk.CTkEntry(add, placeholder_text="Add a friend by Social Glitch ID (SG-...)", height=36)
        self.sg_id.pack(side="left", fill="x", expand=True)
        self.add_btn = primary_button(add, "Send request", self.send_request, width=130)
        self.add_btn.pack(side="left", padx=(8, 0))
        self.f_list = self.scroll(pg["Friends"])
        self.f_list.pack(fill="both", expand=True)
        self.r_list = self.scroll(pg["Received"]); self.r_list.pack(fill="both", expand=True)
        self.s_list = self.scroll(pg["Sent"]); self.s_list.pack(fill="both", expand=True)
        ctk.CTkLabel(pg["Blocked"], text="Blocked users cannot send you\nmessages or friend requests.",
                     text_color=C["muted"], justify="left").pack(anchor="w", pady=(0, 8))
        self.b_list = self.scroll(pg["Blocked"]); self.b_list.pack(fill="both", expand=True)

    def on_show(self, tab=None, **kw):
        if tab:
            self.tabs.show(tab)
        else:
            self.load()

    def load(self):
        t = self.tabs.current
        if t == "Friends":
            self.run(self.be.list_friends, self.got_friends)
        elif t in ("Received", "Sent"):
            self.run(self.be.list_requests, self.got_requests)
        else:
            self.run(self.be.list_blocked, self.got_blocked)
    def act(self, fn, msg, *args):
        def done(res):
            if self.ok(res):
                self.app.toast(msg, "success")
                self.load()
                self.app.refresh_unread()
        self.run(fn, done, None, *args)

    def got_friends(self, res):
        if self.ok(res):
            self.friends = res.data
            self.draw_friends()

    def draw_friends(self):
        self.wipe(self.f_list)
        q = self.search.get().strip().lower()
        shown = [f for f in self.friends if q in f["name"].lower() or q in f["username"].lower()]
        self.count.configure(text=f"{len(self.friends)} friends")
        if not shown:
            msg = "No friends found." if q else "No friends yet."
            empty_state(self.f_list, msg, "" if q else "Add someone using their Social Glitch ID.").pack(pady=40)
        for f in shown:
            a = person_row(self.f_list, f, online=f.get("online", False))
            secondary_button(a, "View", lambda u=f: self.view(u), width=62, height=30).pack(side="left", padx=2)
            secondary_button(a, "Message", lambda u=f: self.app.navigate("messages", user_id=u["id"]), width=80, height=30).pack(side="left", padx=2)
            secondary_button(a, "Block", lambda u=f: self.block(u), width=62, height=30).pack(side="left", padx=2)
            danger_button(a, "Remove", lambda u=f: self.remove(u), width=72, height=30).pack(side="left", padx=2)
    def send_request(self):
        sg = self.sg_id.get().strip()
        if not sg:
            return
        def done(res):
            if self.ok(res):
                self.sg_id.delete(0, "end")
                self.app.toast("Friend request sent.", "success")
        self.run(self.be.send_friend_request, done, self.add_btn, sg)

    def view(self, u):
        def done(res):
            if not self.ok(res):
                return
            d = res.data
            if d.get("restricted"):
                info(self, d["name"], f"@{d['username']}\n\n🔒 This profile is private.")
            else:
                info(self, d["name"], f"@{d['username']}\n{d['sg_id']}\nAccount: {d['account_type']}\n"
                                      f"{d['friends']} friends · {d['posts']} posts")
        self.run(self.be.get_profile, done, None, u["id"])
    def block(self, u):
        if confirm(self, "Block user", f"Block {u['name']}? They won't be able to message you or send requests.", "Block", True):
            self.act(self.be.block_user, "User blocked.", u["id"])

    def remove(self, u):
        if confirm(self, "Remove friend", f"Remove {u['name']} from your friends?", "Remove", True):
            self.act(self.be.remove_friend, "Friend removed.", u["id"])

    def got_requests(self, res):
        if not self.ok(res):
            return
        self.wipe(self.r_list)
        self.wipe(self.s_list)
        if not res.data["received"]:
            empty_state(self.r_list, "No pending requests.").pack(pady=40)
        for r in res.data["received"]:
            a = person_row(self.r_list, r["user"])
            primary_button(a, "ACCEPT", lambda r=r: self.act(self.be.respond_request, "Friend added.", r["id"], True), width=84, height=30).pack(side="left", padx=2)
            secondary_button(a, "REJECT", lambda r=r: self.act(self.be.respond_request, "Request rejected.", r["id"], False), width=84, height=30).pack(side="left", padx=2)
        if not res.data["sent"]:
            empty_state(self.s_list, "No sent requests.").pack(pady=40)
        for r in res.data["sent"]:
            a = person_row(self.s_list, r["user"])
            secondary_button(a, "CANCEL", lambda r=r: self.act(self.be.cancel_request, "Request cancelled.", r["id"]), width=84, height=30).pack()

    def got_blocked(self, res):
        if not self.ok(res):
            return
        self.wipe(self.b_list)
        if not res.data:
            empty_state(self.b_list, "You haven't blocked anyone.").pack(pady=40)
        for u in res.data:
            a = person_row(self.b_list, u)
            secondary_button(a, "UNBLOCK", lambda u=u: self.act(self.be.unblock_user, "User unblocked.", u["id"]), width=90, height=30).pack()
import customtkinter as ctk
STATUS_COLOR = {"pending": C["warning"], "accepted": C["success"], "rejected": C["error"],
                "revoked": C["muted"], "expired": C["muted"]}
class InvitationsScreen(Screen):
    def build(self):
        self.header("Invitations")
        self.tabs = Tabs(self, ["Create", "Sent", "Received"], on_change=lambda n: self.load())
        self.tabs.pack(fill="both", expand=True)
        card = Card(self.tabs.pages["Create"])
        card.pack(anchor="nw", fill="x")
        ctk.CTkLabel(card, text="Create Private Invitation", font=font(16, "bold")).pack(anchor="w", padx=18, pady=(16, 4))
        ctk.CTkLabel(card, text="Receiver ID:", text_color=C["muted"]).pack(anchor="w", padx=18)
        self.receiver = ctk.CTkEntry(card, placeholder_text="SG-______", width=260, height=38)
        self.receiver.pack(anchor="w", padx=18, pady=6)
        self.gen = primary_button(card, "GENERATE INVITATION", self.generate, width=220)
        self.gen.pack(anchor="w", padx=18, pady=(4, 14))
        self.result = ctk.CTkFrame(card, fg_color="transparent")
        self.result.pack(anchor="w", padx=18, pady=(0, 14))
        self.sent = self.scroll(self.tabs.pages["Sent"]); self.sent.pack(fill="both", expand=True)
        self.recv = self.scroll(self.tabs.pages["Received"]); self.recv.pack(fill="both", expand=True)
    def on_show(self, **kw):
        self.load()
    def load(self):
        if self.tabs.current != "Create":
            self.run(self.be.list_invitations, self.loaded)

    def generate(self):
        rid = self.receiver.get().strip()
        if not rid:
            self.app.toast("Enter the receiver's Social Glitch ID.", "error")
            return
        def done(res):
            if not self.ok(res):
                return
            d = res.data
            self.wipe(self.result)
            ctk.CTkLabel(self.result, text="Invitation ID:", text_color=C["muted"]).pack(anchor="w")
            ctk.CTkLabel(self.result, text=d["id"], font=font(20, "bold"), text_color=C["accent"]).pack(anchor="w")
            secondary_button(self.result, "SHOW QR CODE", lambda: qr_dialog(self, d["payload"], d["id"], d["expires"]), width=160).pack(anchor="w", pady=6)
            self.receiver.delete(0, "end")
        self.run(self.be.create_invitation, done, self.gen, rid)

    def loaded(self, res):
        if not self.ok(res):
            return
        self.wipe(self.sent)
        self.wipe(self.recv)
        if not res.data["sent"]:
            empty_state(self.sent, "No invitations sent.").pack(pady=40)
        if not res.data["received"]:
            empty_state(self.recv, "No invitations received.").pack(pady=40)
        for i in res.data["sent"]:
            a = self.row(self.sent, i, "To")
            if i["status"] == "pending":
                secondary_button(a, "QR", lambda i=i: qr_dialog(self, i["payload"], i["id"], i["expires"]), width=50, height=30).pack(side="left", padx=2)
                danger_button(a, "Revoke", lambda i=i: self.revoke(i), width=72, height=30).pack(side="left", padx=2)
        for i in res.data["received"]:
            a = self.row(self.recv, i, "From")
            if i["status"] == "pending":
                primary_button(a, "Accept", lambda i=i: self.respond(i, True), width=72, height=30).pack(side="left", padx=2)
                secondary_button(a, "Reject", lambda i=i: self.respond(i, False), width=72, height=30).pack(side="left", padx=2)
    def row(self, parent, inv, word):
        a = person_row(parent, inv["user"])
        text = inv["status"].capitalize() + (f" · {time_left(inv['expires'])}" if inv["status"] == "pending" else "")
        ctk.CTkLabel(a, text=f"{inv['id']}\n{text}", font=font(11), justify="right", text_color=STATUS_COLOR.get(inv["status"], C["text"])).pack(side="left", padx=10)
        return a
    def respond(self, inv, accept):
        def done(res):
            if self.ok(res):
                self.app.toast("Invitation accepted." if accept else "Invitation rejected.", "success")
                self.load()
        self.run(self.be.respond_invitation, done, None, inv["id"], accept)
    def revoke(self, inv):
        if confirm(self, "Revoke invitation", f"Revoke {inv['id']}?", "Revoke", True):
            def done(res):
                if self.ok(res):
                    self.load()
            self.run(self.be.revoke_invitation, done, None, inv["id"])
import customtkinter as ctk
class AuthBackground(ctk.CTkFrame):
    def __init__(self, master):
        super().__init__(master, fg_color="#000000", corner_radius=0)
        self._photo = None
        self._source = None
        self._label = ctk.CTkLabel(self, text="")
        self._label.place(relx=0, rely=0, relwidth=1, relheight=1)
        path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "social_glitch_auth_background.png")
        try:
            self._source = Image.open(path).convert("RGB")
            self.bind("<Configure>", self._resize)
            self.after(20, self._resize)
        except Exception:
            log.exception("Unable to load authentication background: %s", path)
    def _resize(self, _event=None):
        if self._source is None:
            return
        w = max(2, self.winfo_width())
        h = max(2, self.winfo_height())
        try:
            img = ImageOps.fit(
                self._source, (w, h),
                method=Image.Resampling.LANCZOS,
                centering=(0.5, 0.5)
            )
            self._photo = ctk.CTkImage(light_image=img, dark_image=img, size=(w, h))
            self._label.configure(image=self._photo)
        except Exception:
            log.exception("Unable to resize authentication background")
class LoginScreen(ctk.CTkFrame):

    def __init__(self, master, app):
        super().__init__(master, fg_color="#000000")
        self.app = app
        bg = AuthBackground(self)
        bg.place(relx=0, rely=0, relwidth=1, relheight=1)
        card = Card(self, width=400)
        card.place(relx=0.5, rely=0.5, anchor="center")
        inner = ctk.CTkFrame(card, fg_color="transparent")
        inner.pack(padx=36, pady=30)

        ctk.CTkLabel(inner, text="◈ " + APP_NAME, font=font(26, "bold"), text_color=C["accent"]).pack()
        ctk.CTkLabel(inner, text=LOGIN_SUBTITLE, text_color=C["muted"]).pack(pady=(0, 18))
        ctk.CTkLabel(inner, text="Welcome Back", font=font(18, "bold")).pack(anchor="w", pady=(0, 8))
        ctk.CTkLabel(inner, text="Username", text_color=C["muted"]).pack(anchor="w")
        self.user = ctk.CTkEntry(inner, width=320, height=38)
        self.user.pack(pady=(2, 10))
        ctk.CTkLabel(inner, text="Password", text_color=C["muted"]).pack(anchor="w")
        row = ctk.CTkFrame(inner, fg_color="transparent")
        row.pack()
        self.pw = ctk.CTkEntry(row, width=270, height=38, show="•")
        self.pw.pack(side="left", pady=2)
        self.eye = ghost_button(row, "👁", self.toggle, width=44, height=38)
        self.eye.pack(side="left", padx=(6, 0))

        self.error = ctk.CTkLabel(inner, text="", text_color=C["error"], wraplength=320)
        self.error.pack(pady=6)
        self.btn = primary_button(inner, "LOGIN", self.submit, width=320, height=40)
        self.btn.pack()
        ghost_button(inner, "FORGOT PASSWORD?", lambda: app.show_auth("forgot"), width=320).pack(pady=(8, 0))
        ctk.CTkLabel(inner, text="Don't have an account?", text_color=C["muted"]).pack(pady=(10, 4))
        secondary_button(inner, "CREATE ACCOUNT", lambda: app.show_auth("register"), width=320).pack()
        self.status = ctk.CTkLabel(inner, text=app.mode_text(), font=font(11), text_color=C["muted"])
        self.status.pack(pady=(16, 0))
        for e in (self.user, self.pw):
            e.bind("<Return>", lambda ev: self.submit())
        self.after(150, self.user.focus_set)
    def toggle(self):
        self.pw.configure(show="" if self.pw.cget("show") else "•")
    def submit(self):
        u, p = self.user.get().strip(), self.pw.get()
        if not u or not p:
            self.error.configure(text="Please enter your username and password.")
            return
        self.error.configure(text="Signing in…", text_color=C["muted"])
        self.pw.delete(0, "end")
        self.app.run_async(self.app.backend.login, self.done, self.btn, u, p)

    def done(self, res):
        if res.ok:
            self.app.on_login(res.data["user"])
        else:
            self.error.configure(text=res.message, text_color=C["error"])

class ForgotPasswordScreen(ctk.CTkFrame):
    def __init__(self, master, app):
        super().__init__(master, fg_color="#000000")
        self.app = app
        bg = AuthBackground(self)
        bg.place(relx=0, rely=0, relwidth=1, relheight=1)
        self.card = Card(self, width=470)
        self.card.place(relx=0.5, rely=0.5, anchor="center")
        self.username = ""
        self.question = ""
        self.build_choice()
    def clear(self):
        for w in self.card.winfo_children():
            w.destroy()
    def title(self, subtitle=""):
        ctk.CTkLabel(
            self.card, text="◈ " + APP_NAME,
            font=font(23, "bold"), text_color=C["accent"]
        ).pack(pady=(25, 2))
        ctk.CTkLabel(
            self.card, text="Password Recovery",
            font=font(18, "bold")
        ).pack()
        if subtitle:
            ctk.CTkLabel(
                self.card, text=subtitle,
                text_color=C["muted"], wraplength=360
            ).pack(pady=(4, 12))

    def build_choice(self):
        self.clear()
        self.title("Choose how you want to recover your account.")
        box = ctk.CTkFrame(self.card, fg_color="transparent")
        box.pack(padx=38, pady=(0, 28), fill="x")
        ctk.CTkLabel(box, text="Username", text_color=C["muted"]).pack(anchor="w")
        self.user_entry = ctk.CTkEntry(box, width=350, height=38)
        self.user_entry.pack(pady=(2, 14))
        ctk.CTkLabel(
            box, text="Recovery method",
            font=font(13, "bold")
        ).pack(anchor="w", pady=(2, 6))

        primary_button(
            box, "1  •  ANSWER SECURITY QUESTION",
            self.start_security, width=350, height=42
        ).pack(pady=4)
        secondary_button(
            box, "2  •  SEND CODE TO EMAIL",
            self.start_email, width=350, height=42
        ).pack(pady=4)

        self.msg = ctk.CTkLabel(
            box, text="", text_color=C["error"],
            wraplength=350
        )
        self.msg.pack(pady=8)

        ghost_button(
            box, "Back to login",
            lambda: self.app.show_auth("login"),
            width=350
        ).pack()
    def start_security(self):
        u = self.user_entry.get().strip()
        if not u:
            self.msg.configure(text="Enter your username first.")
            return
        self.username = u
        self.msg.configure(text="Loading your recovery question...", text_color=C["muted"])
        self.app.run_async(self.app.backend.recovery_question, self.got_question, None, u)
    def got_question(self, res):
        if not res.ok:
            self.msg.configure(text=res.message, text_color=C["error"])
            return
        self.question = res.data["question"]
        self.build_security()
    def build_security(self):
        self.clear()
        self.title("Method 1 — answer your account recovery question.")

        box = ctk.CTkFrame(self.card, fg_color="transparent")
        box.pack(padx=38, pady=(0, 28), fill="x")
        ctk.CTkLabel(box, text=f"Username: {self.username}", text_color=C["muted"]).pack(anchor="w")
        ctk.CTkLabel(
            box, text=self.question,
            font=font(14, "bold"), text_color=C["accent"],
            wraplength=350, justify="left"
        ).pack(anchor="w", pady=(12, 8))
        ctk.CTkLabel(box, text="Answer", text_color=C["muted"]).pack(anchor="w")
        self.answer_entry = ctk.CTkEntry(box, width=350, height=38)
        self.answer_entry.pack(pady=(2, 12))

        ctk.CTkLabel(box, text="New password", text_color=C["muted"]).pack(anchor="w")
        self.newpw = ctk.CTkEntry(box, width=350, height=38, show="•")
        self.newpw.pack(pady=(2, 12))

        self.msg = ctk.CTkLabel(box, text="", wraplength=350)
        self.msg.pack(pady=5)

        primary_button(
            box, "RESET PASSWORD", self.reset_security,
            width=350, height=40
        ).pack()
        ghost_button(
            box, "Use email code instead",
            self.start_email, width=350
        ).pack(pady=(8, 0))
        ghost_button(
            box, "Back",
            self.build_choice, width=350
        ).pack(pady=(4, 0))
    def reset_security(self):
        answer = self.answer_entry.get().strip()
        pw = self.newpw.get()
        if not answer or not pw:
            self.msg.configure(text="Enter the answer and a new password.", text_color=C["error"])
            return
        if len(pw) < 8 or password_strength(pw)[0] == "Weak":
            self.msg.configure(text="Choose a stronger password.", text_color=C["error"])
            return
        self.app.run_async(
            self.app.backend.reset_security,
            self.reset_done, None,
            self.username, answer, pw
        )
    def start_email(self):
        u = self.username or getattr(self, "user_entry", None).get().strip()
        if not u:
            if hasattr(self, "msg"):
                self.msg.configure(text="Enter your username first.", text_color=C["error"])
            return
        self.username = u
        self.clear()
        self.title("Method 2 — receive a one-time code by email.")
        box = ctk.CTkFrame(self.card, fg_color="transparent")
        box.pack(padx=38, pady=(0, 28), fill="x")
        ctk.CTkLabel(
            box, text=f"A verification code will be sent to the email linked to @{u}.",
            text_color=C["muted"], wraplength=350
        ).pack(anchor="w", pady=(0, 12))

        self.email_msg = ctk.CTkLabel(box, text="Sending code...", text_color=C["muted"], wraplength=350)
        self.email_msg.pack(pady=8)

        self.app.run_async(
            self.app.backend.send_email_code,
            self.code_sent, None, self.username
        )
    def code_sent(self, res):
        if not res.ok:
            self.email_msg.configure(text=res.message, text_color=C["error"])
            ghost_button(self.card, "Back", self.build_choice, width=350).pack(pady=(0, 20))
            return

        self.clear()
        self.title("Method 2 — enter the email verification code.")

        box = ctk.CTkFrame(self.card, fg_color="transparent")
        box.pack(padx=38, pady=(0, 28), fill="x")
        ctk.CTkLabel(
            box, text="A 6-digit code was sent to your registered email.",
            text_color=C["muted"], wraplength=350
        ).pack(anchor="w", pady=(0, 12))

        ctk.CTkLabel(box, text="Verification code", text_color=C["muted"]).pack(anchor="w")
        self.code = ctk.CTkEntry(box, width=350, height=38)
        self.code.pack(pady=(2, 12))
        ctk.CTkLabel(box, text="New password", text_color=C["muted"]).pack(anchor="w")
        self.newpw2 = ctk.CTkEntry(box, width=350, height=38, show="•")
        self.newpw2.pack(pady=(2, 12))
        self.msg = ctk.CTkLabel(box, text="", wraplength=350)
        self.msg.pack(pady=5)
        primary_button(
            box, "VERIFY & RESET PASSWORD",
            self.reset_email, width=350, height=40
        ).pack()

        ghost_button(
            box, "Use security question instead",
            self.build_security, width=350
        ).pack(pady=(8, 0))

        ghost_button(
            box, "Back to login",
            lambda: self.app.show_auth("login"), width=350
        ).pack(pady=(4, 0))

    def reset_email(self):
        code = self.code.get().strip()
        pw = self.newpw2.get()
        if not code or not pw:
            self.msg.configure(text="Enter the code and a new password.", text_color=C["error"])
            return
        if len(pw) < 8 or password_strength(pw)[0] == "Weak":
            self.msg.configure(text="Choose a stronger password.", text_color=C["error"])
            return
        self.app.run_async(
            self.app.backend.reset_email,
            self.reset_done, None,
            self.username, code, pw
        )
    def reset_done(self, res):
        if not res.ok:
            self.msg.configure(text=res.message, text_color=C["error"])
            return
        self.clear()
        box = ctk.CTkFrame(self.card, fg_color="transparent")
        box.pack(padx=45, pady=40)
        ctk.CTkLabel(
            box, text="✓", font=font(40, "bold"),
            text_color=C["success"]
        ).pack()
        ctk.CTkLabel(
            box, text="Password reset successfully!",
            font=font(17, "bold")
        ).pack(pady=8)
        ctk.CTkLabel(
            box, text="You can now log in with your new password.",
            text_color=C["muted"], wraplength=330
        ).pack(pady=(0, 18))
        primary_button(
            box, "GO TO LOGIN",
            lambda: self.app.show_auth("login"),
            width=220
        ).pack()
import time
import tkinter as tk
import customtkinter as ctk

class MessagesScreen(Screen):
    def build(self):
        self.header("Messages")
        self.active = None
        self.last_ids = None
        body = ctk.CTkFrame(self, fg_color="transparent")
        body.pack(fill="both", expand=True)
        body.grid_columnconfigure(1, weight=1)
        body.grid_rowconfigure(0, weight=1)
        left = Card(body, width=250)
        left.grid(row=0, column=0, sticky="ns", padx=(0, 12))
        left.pack_propagate(False)
        ctk.CTkLabel(left, text="Conversations", font=font(14, "bold")).pack(anchor="w", padx=14, pady=(12, 4))
        self.convs = self.scroll(left)
        self.convs.pack(fill="both", expand=True, padx=4, pady=4)
        right = Card(body)
        right.grid(row=0, column=1, sticky="nsew")
        top = ctk.CTkFrame(right, fg_color="transparent")
        top.pack(fill="x", padx=14, pady=(10, 0))
        self.title = ctk.CTkLabel(top, text="", font=font(15, "bold"))
        self.title.pack(side="left")
        self.block_btn = danger_button(top, "Block user", self.block, width=96, height=28)
        self.chat = self.scroll(right)
        self.chat.pack(fill="both", expand=True, padx=6, pady=6)
        comp = ctk.CTkFrame(right, fg_color="transparent")
        comp.pack(fill="x", padx=12, pady=(0, 12))
        self.entry = ctk.CTkEntry(comp, placeholder_text="Type a message...", height=38)
        self.entry.pack(side="left", fill="x", expand=True)
        self.entry.bind("<Return>", lambda e: self.send())
        self.send_btn = primary_button(comp, "SEND", self.send, width=80, height=38)
        self.send_btn.pack(side="left", padx=(8, 0))
        self.show_hint("Select a conversation")
        self.set_composer(False)
        self.tick()
    def on_show(self, user_id=None, **kw):
        self.pending = user_id
        self.run(self.be.list_conversations, self.got_convs)
    def set_composer(self, enabled):
        st = "normal" if enabled else "disabled"
        self.entry.configure(state=st)
        self.send_btn.configure(state=st)
    def show_hint(self, text, sub=""):
        self.wipe(self.chat)
        empty_state(self.chat, text, sub).pack(pady=60)
    def got_convs(self, res):
        if not self.ok(res):
            return
        self.wipe(self.convs)
        if not res.data:
            self.show_hint("No messages yet.", "Start a conversation with a friend.")
            return
        for c in res.data:
            u = c["user"]
            label = u["name"] + (f"   ({c['unread']})" if c["unread"] else "")
            sel = self.active and self.active["id"] == u["id"]
            ctk.CTkButton(self.convs, text=label, anchor="w", height=40, corner_radius=8,
                          fg_color=C["card_alt"] if sel else "transparent", hover_color=C["card_alt"],
                          text_color=C["accent"] if c["unread"] else C["text"],
                          font=font(13, "bold" if c["unread"] else "normal"),
                          command=lambda u=u: self.open(u)).pack(fill="x", pady=1)
        if self.pending:
            target = next((c["user"] for c in res.data if c["user"]["id"] == self.pending), None)
            self.pending = None
            if target:
                self.open(target)

    def open(self, user):
        self.active = user
        self.last_ids = None
        self.title.configure(text=user["name"])
        self.block_btn.pack(side="right")
        self.load_chat()
    def load_chat(self):
        if self.active:
            self.run(self.be.get_messages, self.draw, None, self.active["id"])
    def draw(self, res):
        if not self.ok(res) or not self.active:
            return
        msgs = res.data["messages"]
        ids = [m["id"] for m in msgs]
        if ids == self.last_ids:
            return
        self.last_ids = ids
        self.wipe(self.chat)
        if not msgs:
            empty_state(self.chat, "No messages yet.", "Say hello!").pack(pady=60)
        for m in msgs:
            row = ctk.CTkFrame(self.chat, fg_color="transparent")
            row.pack(fill="x", pady=3)
            bub = ctk.CTkFrame(row, corner_radius=14, fg_color=C["accent"] if m["mine"] else C["card_alt"])
            bub.pack(anchor="e" if m["mine"] else "w", padx=8)
            txt = ctk.CTkLabel(bub, text=m["text"], wraplength=380, justify="left", text_color=("#ffffff", "#ffffff") if m["mine"] else C["text"])
            txt.pack(padx=12, pady=(8, 0), anchor="w")
            ts = ctk.CTkLabel(bub, text=time.strftime("%d %b, %H:%M", time.localtime(m["time"])), font=font(10),
                              text_color=("#e0f2f1", "#c9ece8") if m["mine"] else C["muted"])
            ts.pack(padx=12, pady=(0, 6), anchor="e")
            if m["mine"]:
                for w in (bub, txt, ts):
                    w.bind("<Button-3>", lambda e, m=m: self.msg_menu(e, m))
                    w.bind("<Button-2>", lambda e, m=m: self.msg_menu(e, m))
        self.set_composer(res.data["can_message"])
        if not res.data["can_message"]:
            self.entry.configure(placeholder_text="You can't message this user.")
        try:
            self.after(60, lambda: self.chat._parent_canvas.yview_moveto(1.0))
        except Exception:
            pass

    def msg_menu(self, event, m):
        menu = tk.Menu(self, tearoff=0)
        menu.add_command(label="Delete message", command=lambda: self.delete(m))
        menu.tk_popup(event.x_root, event.y_root)

    def delete(self, m):
        if confirm(self, "Delete message", "Delete this message?", "Delete", True):
            def done(res):
                if self.ok(res):
                    self.last_ids = None
                    self.load_chat()
            self.run(self.be.delete_message, done, None, m["id"])

    def send(self):
        text = self.entry.get().strip()
        if not text or not self.active:
            return
        def done(res):
            if self.ok(res):
                self.entry.delete(0, "end")
                self.load_chat()
        self.run(self.be.send_message, done, self.send_btn, self.active["id"], text)
    def block(self):
        if not self.active:
            return
        u = self.active
        if confirm(self, "Block user", f"Block {u['name']}? You won't be able to exchange messages.", "Block", True):
            def done(res):
                if self.ok(res):
                    self.active = None
                    self.title.configure(text="")
                    self.block_btn.pack_forget()
                    self.set_composer(False)
                    self.show_hint("User blocked.")
                    self.app.toast("User blocked.", "success")
                    self.on_show()
            self.run(self.be.block_user, done, None, u["id"])
    def tick(self):

        if self.active and self.winfo_ismapped():
            self.load_chat()
        self.after(5000, self.tick)
import customtkinter as ctk
FILTERS = {"All": None, "Friend requests": "friend_request", "Messages": "message",
           "Invitations": "invitation", "Security": "security", "Reports": "report"}
class NotificationsScreen(Screen):
    def build(self):
        self.header("Notifications")
        self.items = []
        top = ctk.CTkFrame(self, fg_color="transparent")
        top.pack(fill="x")
        self.filter = ctk.CTkSegmentedButton(top, values=list(FILTERS), command=lambda v: self.draw(),
                                             selected_color=C["accent"], selected_hover_color=C["accent_hover"],
                                             unselected_color=C["card_alt"], text_color=C["text"])
        self.filter.set("All")
        self.filter.pack(side="left")
        self.read_btn = secondary_button(top, "Mark all read", self.mark_read, width=120)
        self.read_btn.pack(side="right")
        self.list = self.scroll()
        self.list.pack(fill="both", expand=True, pady=10)

    def on_show(self, **kw):
        self.run(self.be.list_notifications, self.loaded)

    def loaded(self, res):
        if self.ok(res):
            self.items = res.data
            self.draw()
    def draw(self):
        self.wipe(self.list)
        want = FILTERS[self.filter.get()]
        shown = [n for n in self.items if want is None or n["category"] == want]
        if not shown:
            empty_state(self.list, "No notifications.", "You're all caught up.").pack(pady=40)
        for n in shown:
            notification_row(self.list, n)
    def mark_read(self):
        def done(res):
            if self.ok(res):
                self.app.refresh_unread()
                self.on_show()
        self.run(self.be.mark_all_read, done, self.read_btn)
import tkinter as tk
import customtkinter as ctk

VIS_LABEL = {"friends": "🔒 Friends Only", "public": "🌐 Public", "private": "🙈 Only Me"}

VIS_CHOICES = {"Friends only": "friends", "Public": "public", "Only me": "private"}

class PostsScreen(Screen):
    def build(self):
        self.header("Posts")
        self.wraps = []
        box = Card(self)
        box.pack(fill="x", pady=(0, 10))
        ctk.CTkLabel(box, text="What's on your mind?", font=font(14, "bold")).pack(anchor="w", padx=16, pady=(12, 6))
        self.text = ctk.CTkTextbox(box, height=70, fg_color=C["card_alt"], border_width=0)
        self.text.pack(fill="x", padx=16)
        row = ctk.CTkFrame(box, fg_color="transparent")
        row.pack(fill="x", padx=16, pady=10)
        ctk.CTkLabel(row, text="Visibility:", text_color=C["muted"]).pack(side="left")
        self.vis = ctk.CTkOptionMenu(row, values=list(VIS_CHOICES), width=140, fg_color=C["card_alt"],
                                     button_color=C["border"], text_color=C["text"])
        self.vis.set("Friends only")
        self.vis.pack(side="left", padx=8)
        self.post_btn = primary_button(row, "POST", self.submit, width=90)
        self.post_btn.pack(side="right")
        self.feed = self.scroll()
        self.feed.pack(fill="both", expand=True)
        self.bind("<Configure>", self.rewrap)
    def rewrap(self, event):
        for lbl in self.wraps:
            try:
                lbl.configure(wraplength=max(250, event.width - 150))
            except tk.TclError:
                pass

    def on_show(self, **kw):
        self.load()
    def load(self):
        self.run(self.be.list_posts, self.draw)
    def submit(self):
        txt = self.text.get("1.0", "end").strip()
        if not txt:
            self.app.toast("Write something first.", "error")
            return
        def done(res):
            if self.ok(res):
                self.text.delete("1.0", "end")
                self.app.toast("Posted.", "success")
                self.load()
        self.run(self.be.create_post, done, self.post_btn, txt, VIS_CHOICES[self.vis.get()])
    def draw(self, res):
        if not self.ok(res):
            return
        self.wipe(self.feed)
        self.wraps = []
        if not res.data:
            empty_state(self.feed, "No posts yet.", "Share something with your friends.").pack(pady=40)
        for p in res.data:
            card = Card(self.feed)
            card.pack(fill="x", pady=6)
            head = ctk.CTkFrame(card, fg_color="transparent")
            head.pack(fill="x", padx=14, pady=(12, 4))
            avatar(head, p["author"]["name"], 40).pack(side="left")
            meta = ctk.CTkFrame(head, fg_color="transparent")
            meta.pack(side="left", padx=10)
            ctk.CTkLabel(meta, text=p["author"]["name"], font=font(14, "bold")).pack(anchor="w")
            ctk.CTkLabel(meta, text=f"@{p['author']['username']} · {time_ago(p['time'])} · {VIS_LABEL.get(p['visibility'], '')}",
                         font=font(11), text_color=C["muted"]).pack(anchor="w")
            more = ghost_button(head, "⋮", width=30, height=28)
            more.configure(command=lambda b=more, p=p: self.menu(b, p))
            more.pack(side="right")
            body = ctk.CTkLabel(card, text=p["text"], wraplength=560, justify="left", anchor="w")
            body.pack(fill="x", padx=16, pady=6)
            self.wraps.append(body)
            bar = ctk.CTkFrame(card, fg_color="transparent")
            bar.pack(fill="x", padx=10, pady=(0, 8))
            ghost_button(bar, f"{'♥' if p['liked'] else '♡'} {p['likes']}  Like", lambda p=p: self.like(p), width=90, height=30).pack(side="left")
            ghost_button(bar, f"💬 {p['comments']}  Comment", lambda p=p: self.comment(p), width=110, height=30).pack(side="left")
    def menu(self, btn, p):
        m = tk.Menu(self, tearoff=0)
        if p["mine"]:
            m.add_command(label="Delete post", command=lambda: self.delete(p))
        else:
            m.add_command(label="Report post", command=lambda: self.app.navigate("reports", target="Post", target_id=str(p["id"])))
        m.tk_popup(btn.winfo_rootx(), btn.winfo_rooty() + btn.winfo_height())
    def like(self, p):
        self.run(self.be.like_post, lambda r: self.ok(r) and self.load(), None, p["id"])

    def comment(self, p):
        txt = prompt(self, "Add a comment", "Your comment")
        if txt and txt.strip():
            def done(res):
                if self.ok(res):
                    self.load()
            self.run(self.be.comment_post, done, None, p["id"], txt.strip())
    def delete(self, p):
        if confirm(self, "Delete post", "Delete this post? This cannot be undone.", "Delete", True):
            def done(res):
                if self.ok(res):
                    self.app.toast("Post deleted.", "success")
                    self.load()
            self.run(self.be.delete_post, done, None, p["id"])
import tkinter as tk
import customtkinter as ctk
GROUPS = [
    ("visibility", "Account Visibility", [("public", "Public"), ("private", "Private")]),
    ("profile_view", "Who can view your profile?", [("everyone", "Everyone"), ("friends", "Friends"), ("nobody", "Nobody")]),
    ("friend_requests", "Who can send friend requests?", [("everyone", "Everyone"), ("friends_of_friends", "Friends of friends"), ("nobody", "Nobody")]),
    ("messages", "Who can message you?", [("friends", "Friends"), ("everyone", "Everyone"), ("nobody", "Nobody")]),
]
class PrivacyForm(ctk.CTkFrame):
    def __init__(self, master, app):
        super().__init__(master, fg_color="transparent")
        self.app = app
        self.vars = {key: tk.StringVar() for key, _, _ in GROUPS}
        self.status = ctk.CTkLabel(self, text="", font=font(13, "bold"), text_color=C["security"])
        self.status.pack(anchor="w", pady=(0, 8))
        for key, title, options in GROUPS:
            card = Card(self)
            card.pack(fill="x", pady=5)
            ctk.CTkLabel(card, text=title, font=font(14, "bold")).pack(anchor="w", padx=16, pady=(12, 4))
            for value, label in options:
                ctk.CTkRadioButton(card, text=label, variable=self.vars[key], value=value, command=self.refresh_status,
                                   fg_color=C["accent"], hover_color=C["accent_hover"]).pack(anchor="w", padx=22, pady=3)
            ctk.CTkFrame(card, height=8, fg_color="transparent").pack()
        self.save_btn = primary_button(self, "SAVE PRIVACY SETTINGS", self.save, width=240)
        self.save_btn.pack(anchor="w", pady=12)
    def refresh_status(self):
        if self.vars["visibility"].get() == "private":
            self.status.configure(text="🔒 Your account is currently private.")
        else:
            self.status.configure(text="🌐 Your account is currently public.")
    def load(self):
        def done(res):
            if not res.ok:
                self.app.report_error(res)
                return
            for k, v in self.vars.items():
                v.set(res.data.get(k, ""))
            self.refresh_status()
        self.app.run_async(self.app.backend.get_privacy, done)

    def save(self):
        settings = {k: v.get() for k, v in self.vars.items()}
        def done(res):
            if res.ok:
                self.app.toast("Privacy settings saved.", "success")
            else:
                self.app.report_error(res)
        self.app.run_async(self.app.backend.set_privacy, done, self.save_btn, settings)
class PrivacyScreen(Screen):
    def build(self):
        self.header("PRIVACY CENTER")
        scroll = self.scroll()
        scroll.pack(fill="both", expand=True)
        self.form = PrivacyForm(scroll, self.app)
        self.form.pack(fill="x")

    def on_show(self, **kw):
        self.form.load()
import customtkinter as ctk

class ProfileScreen(Screen):
    def build(self):
        self.header("Profile")
        self.card = Card(self)
        self.card.pack(anchor="n", pady=10)
    def on_show(self, **kw):
        self.run(self.be.get_profile, self.loaded)
    def loaded(self, res):
        if not self.ok(res):
            return
        d = res.data
        self.wipe(self.card)
        box = ctk.CTkFrame(self.card, fg_color="transparent")
        box.pack(padx=70, pady=28)
        avatar(box, d["name"], 96).pack()
        ctk.CTkLabel(box, text=d["name"], font=font(22, "bold")).pack(pady=(10, 0))
        ctk.CTkLabel(box, text="@" + d["username"], text_color=C["muted"]).pack()
        ctk.CTkLabel(box, text=d["sg_id"], font=font(14, "bold"), text_color=C["accent"]).pack(pady=4)
        icon = "🔒" if d["account_type"] == "PRIVATE" else "🌐"
        ctk.CTkLabel(box, text=f"{icon} {d['account_type']}", font=font(13, "bold"), text_color=C["security"]).pack()
        ctk.CTkLabel(box, text=f"Role: {d['role'].capitalize()}", text_color=C["muted"], font=font(12)).pack(pady=(2, 10))
        stats = ctk.CTkFrame(box, fg_color="transparent")
        stats.pack(pady=8)
        for n, label in ((d["friends"], "Friends"), (d["posts"], "Posts")):
            s = ctk.CTkFrame(stats, fg_color="transparent")
            s.pack(side="left", padx=20)
            ctk.CTkLabel(s, text=str(n), font=font(20, "bold")).pack()
            ctk.CTkLabel(s, text=label, text_color=C["muted"]).pack()
        secondary_button(box, "EDIT PROFILE", self.edit, width=200).pack(pady=(14, 0))
        self.current_name = d["name"]
    def edit(self):
        name = prompt(self, "Edit profile", "Display name", self.current_name)
        if name is None or not name.strip():
            return
        def done(res):
            if self.ok(res):
                self.app.user["name"] = name.strip()
                self.app.navbar.set_user(name.strip())
                self.app.toast("Profile updated.", "success")
                self.on_show()
        self.run(self.be.update_name, done, None, name.strip())
import re
import customtkinter as ctk



def password_strength(pw):

    score = sum([
        len(pw) >= 10, len(pw) >= 12,
        bool(re.search("[a-z]", pw) and re.search("[A-Z]", pw)),
        bool(re.search(r"\d", pw)),
        bool(re.search(r"[^\w\s]", pw)),
    ])
    if not pw:
        return "", 0, C["muted"]
    if score <= 2:
        return "Weak", 0.25, C["error"]
    if score == 3:
        return "Fair", 0.5, C["warning"]
    if score == 4:
        return "Strong", 0.8, C["security"]
    return "Very strong", 1.0, C["success"]
class RegisterScreen(ctk.CTkFrame):
    SECURITY_QUESTIONS = [
        "What was the name of your first school?",
        "What is your favorite childhood nickname?",
        "What was the name of your first pet?",
        "What is the name of your favorite teacher?",
        "What city were you born in?",
    ]

    def __init__(self, master, app):
        super().__init__(master, fg_color="#000000")
        self.app = app
        bg = AuthBackground(self)
        bg.place(relx=0, rely=0, relwidth=1, relheight=1)
        self.card = Card(self, width=460)
        self.card.place(relx=0.5, rely=0.5, anchor="center")
        self.selected_question = random.choice(self.SECURITY_QUESTIONS)
        self.form()
    def form(self):
        for w in self.card.winfo_children():
            w.destroy()
        f = ctk.CTkFrame(self.card, fg_color="transparent")
        f.pack(padx=36, pady=24)
        ctk.CTkLabel(f, text="◈ " + APP_NAME, font=font(22, "bold"), text_color=C["accent"]).pack()
        ctk.CTkLabel(f, text="Create your account", font=font(16, "bold")).pack(pady=(6, 10))

        self.fields = {}
        fields = [
            ("name", "Full name", False),
            ("username", "Username", False),
            ("email", "Email address", False),
            ("pw", "Password", True),
            ("pw2", "Confirm password", True),
        ]
        for key, label, secret in fields:
            ctk.CTkLabel(f, text=label, text_color=C["muted"]).pack(anchor="w")
            e = ctk.CTkEntry(f, width=350, height=36, show="•" if secret else "")
            e.pack(pady=(2, 7))
            self.fields[key] = e
        self.fields["pw"].bind("<KeyRelease>", self.update_strength)
        bar_row = ctk.CTkFrame(f, fg_color="transparent")
        bar_row.pack(fill="x")
        self.bar = ctk.CTkProgressBar(bar_row, width=250, height=8)
        self.bar.set(0)
        self.bar.pack(side="left")
        self.strength = ctk.CTkLabel(bar_row, text="", font=font(12, "bold"))
        self.strength.pack(side="left", padx=10)
        ctk.CTkLabel(f, text="Account recovery question", font=font(13, "bold")).pack(anchor="w", pady=(10, 2))
        self.question_label = ctk.CTkLabel(
            f, text=self.selected_question, text_color=C["accent"],
            wraplength=350, justify="left"
        )
        self.question_label.pack(anchor="w", pady=(0, 4))
        ctk.CTkLabel(f, text="Your answer", text_color=C["muted"]).pack(anchor="w")
        self.answer = ctk.CTkEntry(f, width=350, height=36)
        self.answer.pack(pady=(2, 7))

        ctk.CTkLabel(
            f, text="This question will be used for the first password-recovery method.",
            text_color=C["muted"], font=font(11), wraplength=350
        ).pack(anchor="w")

        ctk.CTkLabel(
            f, text="🔒 Your account will be PRIVATE by default.",
            text_color=C["muted"], font=font(12)
        ).pack(pady=(8, 0))
        self.error = ctk.CTkLabel(f, text="", text_color=C["error"], wraplength=350)
        self.error.pack(pady=6)
        self.btn = primary_button(f, "CREATE ACCOUNT", self.submit, width=350, height=40)
        self.btn.pack()
        ghost_button(f, "Back to login", lambda: self.app.show_auth("login")).pack(pady=(8, 0))

    def update_strength(self, _=None):
        label, value, color = password_strength(self.fields["pw"].get())
        self.bar.set(value)
        self.bar.configure(progress_color=color)
        self.strength.configure(text=label, text_color=color)

    def submit(self):
        v = {k: e.get() for k, e in self.fields.items()}
        name, user = v["name"].strip(), v["username"].strip()
        email, answer = v["email"].strip(), self.answer.get().strip()

        problem = None
        if not name or not user or not email or not v["pw"] or not v["pw2"] or not answer:
            problem = "Please fill in every field."
        elif not re.fullmatch(r"[A-Za-z0-9_]{3,20}", user):
            problem = "Username must be 3-20 letters, numbers or underscores."
        elif not re.fullmatch(r"[^@\s]+@[^@\s]+\.[^@\s]+", email):
            problem = "Enter a valid email address."
        elif v["pw"] != v["pw2"]:
            problem = "Passwords do not match."
        elif len(v["pw"]) < 8 or password_strength(v["pw"])[0] == "Weak":
            problem = "Choose a stronger password (8+ characters, mix of cases and digits)."
        if problem:
            self.error.configure(text=problem)
            return
        self.error.configure(text="")
        pw = v["pw"]
        self.fields["pw"].delete(0, "end")
        self.fields["pw2"].delete(0, "end")
        self.app.run_async(
            self.app.backend.register, self.done, self.btn,
            name, user, pw, email, self.selected_question, answer
        )
    def done(self, res):
        if not res.ok:
            self.error.configure(text=res.message)
            return

        for w in self.card.winfo_children():
            w.destroy()
        box = ctk.CTkFrame(self.card, fg_color="transparent")
        box.pack(padx=45, pady=34)
        ctk.CTkLabel(box, text="✓", font=font(40, "bold"), text_color=C["success"]).pack()
        ctk.CTkLabel(
            box, text="Account created successfully!",
            font=font(17, "bold")
        ).pack(pady=6)
        ctk.CTkLabel(
            box, text="Your Social Glitch ID:",
            text_color=C["muted"]
        ).pack(pady=(10, 0))
        ctk.CTkLabel(
            box, text=res.data["sg_id"],
            font=font(24, "bold"), text_color=C["accent"]
        ).pack(pady=(0, 10))
        ctk.CTkLabel(
            box, text="Your email is now linked for password recovery.",
            text_color=C["muted"], wraplength=330
        ).pack(pady=(0, 18))
        primary_button(
            box, "GO TO LOGIN",
            lambda: self.app.show_auth("login"), width=220
        ).pack()
import customtkinter as ctk

class ReportsScreen(Screen):
    def build(self):
        self.header("Report", "Reports are reviewed by an administrator. Submitting one does not decide anyone's guilt.")
        card = Card(self)
        card.pack(fill="x")
        f = ctk.CTkFrame(card, fg_color="transparent")
        f.pack(fill="x", padx=20, pady=18)
        ctk.CTkLabel(f, text="Target", text_color=C["muted"]).pack(anchor="w")
        self.target = ctk.CTkOptionMenu(f, values=["User", "Post", "Message"], width=160, fg_color=C["card_alt"],
                                        button_color=C["border"], text_color=C["text"])
        self.target.pack(anchor="w", pady=(2, 10))
        ctk.CTkLabel(f, text="Target ID", text_color=C["muted"]).pack(anchor="w")
        self.target_id = ctk.CTkEntry(f, height=36)
        self.target_id.pack(fill="x", pady=(2, 10))
        ctk.CTkLabel(f, text="Reason", text_color=C["muted"]).pack(anchor="w")
        self.reason = ctk.CTkEntry(f, height=36)
        self.reason.pack(fill="x", pady=(2, 10))
        ctk.CTkLabel(f, text="Description", text_color=C["muted"]).pack(anchor="w")
        self.desc = ctk.CTkTextbox(f, height=100, fg_color=C["card_alt"], border_width=0)
        self.desc.pack(fill="x", pady=(2, 12))
        self.btn = primary_button(f, "SUBMIT REPORT", self.submit, width=200)
        self.btn.pack(anchor="w")
        self.msg = ctk.CTkLabel(f, text="", font=font(13, "bold"), justify="left")
        self.msg.pack(anchor="w", pady=8)

    def on_show(self, target=None, target_id=None, **kw):
        if target:
            self.target.set(target)
            self.target_id.delete(0, "end")
            self.target_id.insert(0, target_id or "")
            self.msg.configure(text="")

    def submit(self):
        tid, reason = self.target_id.get().strip(), self.reason.get().strip()
        if not tid or not reason:
            self.msg.configure(text="Please fill in the target ID and a reason.", text_color=C["error"])
            return
        def done(res):
            if res.ok:
                self.msg.configure(text=f"Report submitted successfully.\nReport ID: {res.data['id']}", text_color=C["success"])
                for e in (self.target_id, self.reason):
                    e.delete(0, "end")
                self.desc.delete("1.0", "end")
            else:
                self.msg.configure(text=res.message, text_color=C["error"])
        self.run(self.be.submit_report, done, self.btn, self.target.get().lower(), tid, reason, self.desc.get("1.0", "end").strip())
import time
import customtkinter as ctk

class SecurityScreen(Screen):
    def build(self):
        self.header("SECURITY CENTER")
        body = self.scroll()
        body.pack(fill="both", expand=True)
        self.status = Card(body)
        self.status.pack(fill="x", pady=5)
        ctk.CTkLabel(body, text="Recent security events", font=font(15, "bold")).pack(anchor="w", pady=(12, 4))
        self.events = Card(body)
        self.events.pack(fill="x")
        ctk.CTkLabel(body, text="RECENT ACTIVITY", font=font(15, "bold")).pack(anchor="w", pady=(16, 4))
        self.log = Card(body)
        self.log.pack(fill="x")
    def on_show(self, **kw):
        self.run(self.be.security_overview, self.got_overview)
        self.run(self.be.activity_log, lambda r: self.ok(r) and activity_list(self.log, r.data))

    def got_overview(self, res):
        if not self.ok(res):
            return
        d = res.data
        self.wipe(self.status)
        ok = d["account_status"].lower() == "protected"
        last = time.strftime("%d %b %Y, %H:%M", time.localtime(d["last_login"])) if d["last_login"] else "Unknown"
        rows = [
            ("Account Status", "● " + d["account_status"], C["success"] if ok else C["warning"]),
            ("Privacy", "● " + d["privacy"], C["security"]),
            ("Password", "● " + d["password"], C["success"] if d["password"] == "Strong" else C["warning"]),
            ("Recent Login", last, C["text"]),
            ("Failed Logins", str(d["failed_logins"]), C["warning"] if d["failed_logins"] else C["text"]),
            ("Blocked Users", str(d["blocked"]), C["text"]),
        ]
        for label, value, color in rows:
            r = ctk.CTkFrame(self.status, fg_color="transparent")
            r.pack(fill="x", padx=18, pady=5)
            ctk.CTkLabel(r, text=label, text_color=C["muted"]).pack(side="left")
            ctk.CTkLabel(r, text=value, text_color=color, font=font(13, "bold")).pack(side="right")
        activity_list(self.events, d["events"], "No security events.")
import customtkinter as ctk

class SettingsScreen(Screen):
    def build(self):
        self.header("Settings")
        self.tabs = Tabs(self, ["Account", "Privacy", "Security", "Application"], on_change=self.tab_changed)
        self.tabs.pack(fill="both", expand=True)
        pg = self.tabs.pages
        acc = self.scroll(pg["Account"]); acc.pack(fill="both", expand=True)
        self.name = self.field(acc, "Display name", self.save_name)
        self.username = self.field(acc, "Username", self.save_username, "Usernames may be restricted by the backend.")
        card = Card(acc); card.pack(fill="x", pady=6)
        ctk.CTkLabel(card, text="Change password", font=font(14, "bold")).pack(anchor="w", padx=16, pady=(12, 4))
        self.pw = {}
        for key, label in (("old", "Current password"), ("new", "New password"), ("again", "Confirm new password")):
            e = ctk.CTkEntry(card, placeholder_text=label, show="•", height=36)
            e.pack(fill="x", padx=16, pady=3)
            self.pw[key] = e
        self.pw_btn = primary_button(card, "Update password", self.save_password, width=170)
        self.pw_btn.pack(anchor="w", padx=16, pady=12)

        p_scroll = self.scroll(pg["Privacy"]); p_scroll.pack(fill="both", expand=True)
        self.privacy = PrivacyForm(p_scroll, self.app); self.privacy.pack(fill="x")
        sec = ctk.CTkFrame(pg["Security"], fg_color="transparent"); sec.pack(fill="x")
        secondary_button(sec, "Open login activity", lambda: self.app.navigate("security"), width=220).pack(anchor="w", pady=4)
        secondary_button(sec, "Manage blocked users", lambda: self.app.navigate("friends", tab="Blocked"), width=220).pack(anchor="w", pady=4)
        self.sec_alerts = ctk.CTkSwitch(sec, text="Show security notifications", progress_color=C["accent"], command=self.prefs)
        self.sec_alerts.select(); self.sec_alerts.pack(anchor="w", pady=10)
        app = ctk.CTkFrame(pg["Application"], fg_color="transparent"); app.pack(fill="x")
        ctk.CTkLabel(app, text="Theme", text_color=C["muted"]).pack(anchor="w")
        ctk.CTkLabel(app, text="Pinterest-inspired warm light mode + clean dark mode", text_color=C["muted"], font=font(11)).pack(anchor="w", pady=(0, 4))
        self.theme = ctk.CTkOptionMenu(app, values=["Dark", "Light", "System"], command=lambda v: ctk.set_appearance_mode(v.lower()),
                                       fg_color=C["card_alt"], button_color=C["border"], text_color=C["text"])
        self.theme.set("Dark"); self.theme.pack(anchor="w", pady=(2, 12))
        self.toasts = ctk.CTkSwitch(app, text="Pop-up notifications", progress_color=C["accent"], command=self.prefs)
        self.toasts.select(); self.toasts.pack(anchor="w", pady=4)
        secondary_button(app, "Log out", self.app.logout, width=140).pack(anchor="w", pady=20)

    def field(self, parent, label, command, hint=""):
        card = Card(parent); card.pack(fill="x", pady=6)
        ctk.CTkLabel(card, text=label, font=font(14, "bold")).pack(anchor="w", padx=16, pady=(12, 4))
        row = ctk.CTkFrame(card, fg_color="transparent"); row.pack(fill="x", padx=16, pady=(0, 12))
        e = ctk.CTkEntry(row, height=36); e.pack(side="left", fill="x", expand=True)
        primary_button(row, "Save", command, width=80).pack(side="left", padx=(8, 0))
        if hint:
            ctk.CTkLabel(card, text=hint, font=font(11), text_color=C["muted"]).pack(anchor="w", padx=16, pady=(0, 10))
        return e

    def on_show(self, **kw):
        for entry, key in ((self.name, "name"), (self.username, "username")):
            entry.delete(0, "end")
            entry.insert(0, self.app.user[key])
        self.privacy.load()
    def tab_changed(self, name):
        if name == "Privacy":
            self.privacy.load()
    def prefs(self):
        self.app.prefs["toasts"] = bool(self.toasts.get())
        self.app.prefs["security_alerts"] = bool(self.sec_alerts.get())

    def save_name(self):
        n = self.name.get().strip()
        if not n:
            return self.app.toast("Name cannot be empty.", "error")
        def done(res):
            if self.ok(res):
                self.app.user["name"] = n
                self.app.navbar.set_user(n)
                self.app.toast("Name updated.", "success")
        self.run(self.be.update_name, done, None, n)

    def save_username(self):
        u = self.username.get().strip()
        def done(res):
            if self.ok(res):
                self.app.user["username"] = u
                self.app.toast("Username updated.", "success")
        self.run(self.be.change_username, done, None, u)
    def save_password(self):
        old, new, again = (self.pw[k].get() for k in ("old", "new", "again"))
        if not old or not new:
            return self.app.toast("Fill in both password fields.", "error")
        if new != again:
            return self.app.toast("New passwords do not match.", "error")
        if len(new) < 8:
            return self.app.toast("New password must be at least 8 characters.", "error")
        for e in self.pw.values():
            e.delete(0, "end")
        def done(res):
            if self.ok(res):
                self.app.toast("Password changed.", "success")
        self.run(self.be.change_password, done, self.pw_btn, old, new)

import queue
import threading
import tkinter as tk
import customtkinter as ctk
SCREENS = {
    "dashboard": DashboardScreen, "profile": ProfileScreen, "friends": FriendsScreen,
    "posts": PostsScreen, "messages": MessagesScreen, "invitations": InvitationsScreen,
    "notifications": NotificationsScreen, "privacy": PrivacyScreen, "security": SecurityScreen,
    "reports": ReportsScreen, "settings": SettingsScreen, "admin": AdminScreen,
}
class App(ctk.CTk):
    def __init__(self):
        super().__init__()
        ctk.set_appearance_mode("dark")
        self.title(APP_NAME)
        self._app_icon = None
        try:
            from PIL import Image, ImageTk
            base_dir = os.path.dirname(os.path.abspath(__file__))
            ico_path = os.path.join(base_dir, "social_glitch_app_icon.ico")
            png_path = os.path.join(base_dir, "social_glitch_app_icon.png")
            if os.path.exists(ico_path):
                try:
                    self.iconbitmap(ico_path)
                except Exception:
                    log.exception("Could not set Windows ICO application icon")
            if os.path.exists(png_path):
                self._app_icon = ImageTk.PhotoImage(
                    Image.open(png_path).convert("RGBA")
                )
                try:
                    self.iconphoto(True, self._app_icon)
                except Exception:
                    log.exception("Could not set PNG application icon")
        except Exception:
            log.exception("Could not load Social Glitch app icon")
        self.geometry("1120x720")
        self.minsize(900, 640)
        self.configure(fg_color=C["bg"])

        self.backend = create_backend()
        self.user = None
        self.prefs = {"toasts": True, "security_alerts": True}
        self.page = None
        self.screens, self.current = {}, None
        self._results = queue.Queue()
        self._unread = 0
        self._unread_job = None

        self.report_callback_exception = self._tk_error
        self.bind("<Configure>", self._resized, add="+")
        self.after(40, self._drain)
        self.show_splash()
    def run_async(self, fn, done=None, button=None, *args, **kw):
        if button is not None:
            button.configure(state="disabled")
        def work():
            try:
                res = fn(*args, **kw)
            except Exception:
                log.exception("worker crashed")
                res = Result(False, error="INTERNAL")
            self._results.put((res, done, button))
        threading.Thread(target=work, daemon=True).start()
    def _drain(self):
        try:
            while True:
                res, done, button = self._results.get_nowait()
                try:
                    if button is not None and button.winfo_exists():
                        button.configure(state="normal")
                    if done:
                        done(res)
                except tk.TclError:
                    pass
                except Exception:
                    log.exception("callback failed")
                    self.toast("Something went wrong.\nPlease try again.", "error")
        except queue.Empty:
            pass
        self.after(40, self._drain)
    def _tk_error(self, exc, val, tb):
        log.error("tk callback error", exc_info=(exc, val, tb))
        self.toast("Something went wrong.\nPlease try again.", "error")
    def toast(self, text, kind="normal"):
        if self.prefs["toasts"] or kind == "error":
            show_toast(self, text, kind)
    def report_error(self, res):
        if res.error in ("AUTH_REQUIRED", "SESSION_EXPIRED") and self.user:
            self.user = None
            self.show_auth()
        self.toast(res.message, "error")

    def mode_text(self):
        return "● Demo mode (mock backend)" if USE_MOCK else "● Using C backend"
    def _drop_page(self):
        if self.page is not None:
            self.page.destroy()
            self.page = None
        self.screens, self.current = {}, None

    def show_splash(self):
        self._drop_page()
        self.page = ctk.CTkFrame(self, fg_color=C["bg"])
        self.page.pack(fill="both", expand=True)
        box = ctk.CTkFrame(self.page, fg_color="transparent")
        box.place(relx=0.5, rely=0.5, anchor="center")
        ctk.CTkLabel(box, text="◈", font=ctk.CTkFont(size=54), text_color=C["accent"]).pack()
        ctk.CTkLabel(box, text=APP_NAME, font=ctk.CTkFont(size=38, weight="bold")).pack(pady=(4, 6))
        ctk.CTkLabel(box, text=TAGLINE.replace(". ", ".\n"), font=ctk.CTkFont(size=15), text_color=C["muted"]).pack()
        bar = ctk.CTkProgressBar(box, mode="indeterminate", width=260, progress_color=C["accent"])
        bar.pack(pady=(28, 10))
        bar.start()
        status = ctk.CTkLabel(box, text="Initializing secure environment...", text_color=C["muted"])
        status.pack()

        def pinged(res):
            if not res.ok:
                status.configure(text="Backend not reachable", text_color=C["warning"])
            self.after(900, self.show_auth)
        self.run_async(self.backend.ping, pinged)
    def show_auth(self, view="login"):
        self._drop_page()
        screen_cls = RegisterScreen if view == "register" else ForgotPasswordScreen if view == "forgot" else LoginScreen
        self.page = screen_cls(self, self)
        self.page.pack(fill="both", expand=True)

    def on_login(self, user):
        self.user = user
        self.show_main()

    def show_main(self):
        self._drop_page()
        self.page = ctk.CTkFrame(self, fg_color="transparent")
        self.page.pack(fill="both", expand=True)
        self.page.grid_columnconfigure(1, weight=1)
        self.page.grid_rowconfigure(1, weight=1)
        self.navbar = Navbar(self.page, lambda: self.navigate("notifications"), lambda: self.navigate("profile"))
        self.navbar.grid(row=0, column=0, columnspan=2, sticky="ew")
        self.navbar.set_user(self.user["name"])
        self.sidebar = Sidebar(self.page, self.navigate, self.logout, self.user.get("role") == "admin")
        self.sidebar.grid(row=1, column=0, sticky="ns")
        self.content = ctk.CTkFrame(self.page, fg_color="transparent")
        self.content.grid(row=1, column=1, sticky="nsew", padx=24, pady=18)
        self.navigate("dashboard")
        self.refresh_unread()
    def _resized(self, event):
        if event.widget is self and self.user and self.page is not None and hasattr(self, "sidebar"):
            self.sidebar.set_compact(event.width < 1000)
    def navigate(self, key, **kw):
        if key == "admin" and self.user.get("role") != "admin":
            self.toast("Access denied.", "error")
            return
        if self.current is not None:
            self.current.pack_forget()
        if key not in self.screens:
            self.screens[key] = SCREENS[key](self.content, self)
        self.current = self.screens[key]
        self.current.pack(fill="both", expand=True)
        self.sidebar.select(key)
        self.current.on_show(**kw)

    def refresh_unread(self):
        if not self.user:
            return
        def got(res):
            if res.ok:
                n = res.data["count"]
                if n > self._unread:
                    self.toast("You have new notifications.")
                self._unread = n
                self.navbar.set_unread(n)
        self.run_async(self.backend.unread_count, got)
        if self._unread_job:
            self.after_cancel(self._unread_job)
        self._unread_job = self.after(20000, self.refresh_unread)
    def logout(self):
        if not confirm(self, "Log out", "Do you want to log out of Social Glitch?", "Log out"):
            return
        if self._unread_job:
            self.after_cancel(self._unread_job)
            self._unread_job = None
        self.run_async(self.backend.logout)
        self.user, self._unread = None, 0
        self.show_auth()

if __name__ == "__main__":
    App().mainloop()
