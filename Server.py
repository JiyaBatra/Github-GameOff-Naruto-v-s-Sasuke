"""
Run this on ONE computer:   python server.py
Everyone else connects to that computer's IP address from the game.
"""
import json
import socket
import threading
import traceback

import database
from network import PORT

clients = {}   # username -> Client (logged-in users only)
invites = {}   # target username -> inviter username
state_lock = threading.RLock()


class Client:
    def __init__(self, sock):
        self.sock = sock
        self.username = None
        self.status = "auth"      # auth / lobby / battle
        self.opponent = None
        self.send_lock = threading.Lock()

    def send(self, msg):
        try:
            data = (json.dumps(msg) + "\n").encode("utf-8")
            with self.send_lock:
                self.sock.sendall(data)
        except OSError:
            pass


def notify(username, text, refresh=False):
    with state_lock:
        target = clients.get(username)
    if target:
        target.send({"t": "notify", "msg": text, "refresh": refresh})


def send_lobby(c):
    me = c.username
    with state_lock:
        available = {
            n for n, cl in clients.items()
            if cl.status == "lobby" and n != me
        }

    friends = [
        {"name": n, "online": n in available}
        for n in database.get_friends(me)
    ]
    friends.sort(key=lambda f: not f["online"])

    suggestions = [
        {"name": n, "online": n in available}
        for n in database.get_suggestions(me, 6)
    ]

    c.send({
        "t": "lobby",
        "friends": friends,
        "requests": database.get_pending_requests(me),
        "suggestions": suggestions,
    })


def start_match(host, guest):
    host.status = guest.status = "battle"
    host.opponent = guest
    guest.opponent = host
    database.record_match(host.username, guest.username)

    host.send({
        "t": "match_start", "side": 0,
        "me": "Naruto", "opp": "Sasuke", "opp_user": guest.username,
    })
    guest.send({
        "t": "match_start", "side": 1,
        "me": "Sasuke", "opp": "Naruto", "opp_user": host.username,
    })
    print(f"Match started: {host.username} vs {guest.username}")


def end_battle(c):
    with state_lock:
        opp = c.opponent
        c.opponent = None
        if c.status == "battle":
            c.status = "lobby"
        if opp is not None and opp.opponent is c:
            opp.opponent = None
            opp.status = "lobby"
            opp.send({"t": "opp_left"})


def handle_auth(c, msg):
    t = msg.get("t")
    if t not in ("login", "register"):
        return

    name = str(msg.get("username", "")).strip()
    password = str(msg.get("password", ""))

    if t == "register":
        ok, text = database.create_account(name, password)
        if not ok:
            c.send({"t": "auth_fail", "msg": text})
            return
    elif not database.login_account(name, password):
        c.send({"t": "auth_fail", "msg": "Invalid username or password."})
        return

    with state_lock:
        if name in clients:
            c.send({"t": "auth_fail", "msg": "Already logged in elsewhere."})
            return
        c.username = name
        c.status = "lobby"
        clients[name] = c

    c.send({"t": "auth_ok", "user": name})
    print(f"{name} logged in")


def handle(c, msg):
    if c.username is None:
        handle_auth(c, msg)
        return

    t = msg.get("t")
    me = c.username

    if t == "get_lobby":
        send_lobby(c)

    elif t == "friend_request":
        to = str(msg.get("to", "")).strip()
        ok, text = database.send_friend_request(me, to)
        c.send({"t": "info", "msg": text})
        if ok:
            notify(to, f"{me} sent you a friend request!", refresh=True)
        send_lobby(c)

    elif t == "friend_accept":
        frm = str(msg.get("from", ""))
        ok, text = database.accept_friend_request(me, frm)
        c.send({"t": "info", "msg": text})
        if ok:
            notify(frm, f"{me} accepted your friend request!", refresh=True)
        send_lobby(c)

    elif t == "friend_reject":
        frm = str(msg.get("from", ""))
        ok, text = database.reject_friend_request(me, frm)
        c.send({"t": "info", "msg": text})
        send_lobby(c)

    elif t == "invite":
        to = str(msg.get("to", ""))
        with state_lock:
            target = clients.get(to)
            if c.status != "lobby":
                return
            if target is None or target.status != "lobby" or to == me:
                c.send({"t": "info", "msg": f"{to} is offline or busy."})
                return
            if not database.are_friends(me, to):
                c.send({"t": "info", "msg": "You can only invite friends."})
                return
            invites[to] = me
        target.send({"t": "invited", "from": me})
        c.send({"t": "info", "msg": f"Invite sent to {to}."})

    elif t == "invite_accept":
        frm = str(msg.get("from", ""))
        with state_lock:
            host = clients.get(frm)
            if (invites.get(me) != frm or host is None
                    or host.status != "lobby" or c.status != "lobby"):
                c.send({"t": "info", "msg": "That invite has expired."})
                return
            del invites[me]
            start_match(host, c)

    elif t == "invite_decline":
        frm = str(msg.get("from", ""))
        with state_lock:
            if invites.get(me) == frm:
                del invites[me]
        notify(frm, f"{me} declined your invite.")

    elif t == "game":
        opp = c.opponent
        if c.status == "battle" and opp is not None:
            opp.send(msg)

    elif t == "leave":
        end_battle(c)


def cleanup(c):
    end_battle(c)
    with state_lock:
        if c.username and clients.get(c.username) is c:
            del clients[c.username]
            print(f"{c.username} disconnected")
        for target, inviter in list(invites.items()):
            if c.username in (target, inviter):
                del invites[target]
    try:
        c.sock.close()
    except OSError:
        pass


def client_thread(sock):
    c = Client(sock)
    sock.setsockopt(socket.IPPROTO_TCP, socket.TCP_NODELAY, 1)
    buf = b""
    try:
        while True:
            data = sock.recv(4096)
            if not data:
                break
            buf += data
            while b"\n" in buf:
                line, buf = buf.split(b"\n", 1)
                if not line.strip():
                    continue
                try:
                    msg = json.loads(line.decode("utf-8"))
                except ValueError:
                    continue
                if isinstance(msg, dict):
                    try:
                        handle(c, msg)
                    except Exception:
                        traceback.print_exc()
    except OSError:
        pass
    finally:
        cleanup(c)


def get_lan_ip():
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect(("8.8.8.8", 80))   # no data is actually sent
        ip = s.getsockname()[0]
        s.close()
        return ip
    except OSError:
        return "unknown"


def main():
    database.create_database()
    server = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    server.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    server.bind(("0.0.0.0", PORT))
    server.listen()

    print("=" * 50)
    print("Server running!")
    print(f"Same PC:      127.0.0.1")
    print(f"Same WiFi:    {get_lan_ip()}   (give this IP to your friend)")
    print(f"Port:         {PORT}")
    print("Press Ctrl+C to stop.")
    print("=" * 50)

    try:
        while True:
            sock, _ = server.accept()
            threading.Thread(
                target=client_thread, args=(sock,), daemon=True
            ).start()
    except KeyboardInterrupt:
        print("\nServer stopped.")
    finally:
        server.close()


if __name__ == "__main__":
    main()