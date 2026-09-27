import http.server
import socketserver
from typing import Any
import lopolis
import json
import os.path
from datetime import datetime, timedelta
import argparse
import sys

parser = argparse.ArgumentParser("futr")
parser.add_argument("--port", default=5847, type=int)
parser.add_argument("--docker", action="store_true")
parser.add_argument("--verbose", "-v", action="store_true", help="log each stage of ordering/gathering")
args = parser.parse_args()

PORT = args.port
if args.docker:
    DATA_BASE = "/data/"
else:
    DATA_BASE = "data/"
DATA_FP = DATA_BASE + "meals.json"
CREDS_FP = DATA_BASE + "creds.json"
SERVE_PREFIX = "/serve"

if not os.path.exists(DATA_BASE):
    os.mkdir(DATA_BASE)

creds_exist = False
try:
    creds = json.load(open(CREDS_FP))
    USERNAME = creds["username"]
    PASSWORD = creds["password"]
    session = lopolis.Session(USERNAME, PASSWORD)
    creds_exist = True
except FileNotFoundError:
    pass

history: dict = {}

UNSET_MEAL = -1
MEAL_NOT_FOUND = -2
EMPTY_MEALS_FILE = {"meals": [], "unordered": []}

def ensure_meals_file():
    if os.path.exists(DATA_FP) and os.path.getsize(DATA_FP) >= len(json.dumps(EMPTY_MEALS_FILE)) :
        return

    print("Making empty meals.json")

    data_dir = os.path.dirname(DATA_FP)
    if data_dir:
        os.makedirs(data_dir, exist_ok=True)

    write_meals(EMPTY_MEALS_FILE)

def log(stage: str, msg: str):
    if args.verbose:
        print(f"[{stage}] {msg}", file=sys.stderr)

def get_meal_id(options: list[tuple[str, int]]) -> tuple[int, str]:
    ensure_meals_file()
    meals = json.load(open(DATA_FP))["meals"]

    for meal in meals:
        if meal.startswith("KATERA KOLI "):
            meal_n = meal.split("KOLI ")[1].split(".")[0]
            return options[int(meal_n) - 1][1], options[int(meal_n) - 1][0].title() # Choose the given id (-1 because it"s not 0 indexed)

        if meal == "ODJAVI":
            return UNSET_MEAL, "Odjava"

        for name, id in options:
            if name.lower() == meal.lower():
                return id, name.title()

    return MEAL_NOT_FOUND, ""

def set_meals() -> list[str]:
    failed: list[str] = []
    next_moday = datetime.today() + timedelta((0 - datetime.today().weekday()) % 7)
    # log("order", f"week of {next_moday.strftime('%d.%m.%Y')}")
    for i in range(5):
        date = next_moday + timedelta(i)

        # day = date.strftime("%d.%m")
        # log("order", f"{day} fetching menu")
        snack = session.api.get_meals_menu(date)["items"][0]["menus"]["snack"]
        opts = [(i["description"].strip(), int(i["id"])) for i in snack]
        id, desc = get_meal_id(opts)

        if id == MEAL_NOT_FOUND:
            # log("order", f"{day} no preference matches the {len(opts)} menu options")
            failed.append(date.strftime("%d-%m"))
            continue

        if id == UNSET_MEAL:
            # log("order", f"{day} cancelling meal")
            r = session.api.unset_meals_menu(date)
        else:
            # log("order", f"{day} ordering {desc!r} (id {id})")
            r = session.api.set_meals_menu(date, id)

        if not r["ok"]:
            # log("order", f"{day} FAILED: {r.get('error', r)}")
            failed.append(date.strftime("%d-%m"))
            continue

        # log("order", f"{day} ok")
        datestr = date.strftime("%d-%m")
        if not (datestr in history.keys()):
            history.update({datestr: desc})

    # log("order", f"done, {5 - len(failed)}/5 days set" + (f", failed: {', '.join(failed)}" if failed else ""))
    return failed

def gather_meals(n: int) -> list:
    gathered: list[str] = []
    # log("gather", f"scanning the last {n} days")
    for i in range(n):
        date = datetime.today() - timedelta(i)

        try:
            snack = session.api.get_meals_menu(date)["items"][0]["menus"]["snack"]
            names = [i["description"].strip() for i in snack]

            for i in names:
                if not i in gathered:
                    i = i.replace("SENDIVČ", "Sendvič")
                    gathered.append(i)
        except:
            pass

    try:
        gathered.remove("NI")
        gathered.remove("medicinsko predpisane diete po dogovoru")
        gathered.remove("")
    except:
        pass

    for i in range(1, 5):
        gathered.append(f"KATERA KOLI {i}.")

    gathered.append("ODJAVI")

    return gathered

def write_meals(meals: dict):
    with open(DATA_FP, "w") as f:
        f.write(json.dumps(meals))

def save_gathered(n: int):
    gathered: list[str] = gather_meals(n)
    meals = {"meals": [], "unordered": []}

    if os.path.exists(DATA_FP):
        ensure_meals_file()
        meals: dict[str, list[str]] = json.load(open(DATA_FP))

    for each in meals["meals"]:
        if not each in gathered:
            meals["meals"].remove(each)

        else:
            gathered.remove(each)

    meals["unordered"] = gathered

    # log("gather", f"{len(meals['meals'])} known, {len(gathered)} unordered")
    write_meals(meals)

def strip_dict(obj: dict[str, Any], *fields: str) -> dict:
    new_obj = {}
    for field in fields:
        if field in obj.keys():
            new_obj.update({field: obj[field]})

    return new_obj

class Handler(http.server.SimpleHTTPRequestHandler):
    def do_GET(self):
        try:
            if self.path == "/":
                self.serve_file("index.html")

            elif self.path == "/api/credentials":
                if creds_exist:
                    return self.serve_json(200, b"true")

                return self.serve_json(200, b"false")

            elif self.path.startswith("/assets/"):
                self.serve_file(self.path)

            elif not creds_exist:
                self.send_response(301)
                self.send_header("Location", "/")
                self.end_headers()

            elif self.path == "/api/meals":
                data = b"[]"
                if os.path.exists(DATA_FP):
                    ensure_meals_file()
                    data = json.dumps(json.load(open(DATA_FP))["meals"]).encode()

                self.serve_json(200, data)

            elif self.path == "/api/unordered":
                data = b"[]"
                if os.path.exists(DATA_FP):
                    ensure_meals_file()
                    data = json.dumps(json.load(open(DATA_FP))["unordered"]).encode()

                self.serve_json(200, data)

            elif self.path == "/api/history":
                self.serve_json(200, json.dumps(history).encode())

            elif self.path == "/api/order":
                # log("order", "refreshing session")
                session.refresh()
                failed = set_meals()
                if failed:
                    return self.serve_json(500, json.dumps({"ok": False, "message": f"Failed for: {', '.join(failed)}"}).encode())

                return self.serve_json(200, b"{\"ok\": true}")

            elif self.path == "/api/set" or self.path == "/api/gather":
                if self.path == "/api/set":
                    session.refresh()
                    set_meals()

                elif self.path == "/api/gather":
                    session.refresh()
                    save_gathered(32)

                self.send_response(301)
                self.send_header("Location", "/")
                self.end_headers()

            else:
                self.serve_file("404.html", 404)

        except Exception as e:
            print(f"[do_GET] Failed to serve {self.path}: {e}")
            self.serve_file("500.html", 500)

    def do_POST(self):
        try:
            if self.path == "/api/credentials":
                try:
                    data = strip_dict(self.get_form(), "username", "password")

                    if data:
                        with open(CREDS_FP, "w") as f:
                            f.write(json.dumps(data))

                    return self.serve_json(200, b"{\"ok\": true}")
                except Exception as e:
                    print(f"[do_POST] Failed to serve {self.path}: {e}")
                    return self.serve_json(500, b"{\"ok\": false}")

            elif not creds_exist:
                return self.serve_json(403, b"{\"status\": 403, \"message\": \"Credentials not set\"}")

            elif self.path == "/api/meals":
                try:
                    data = strip_dict(self.get_form(), "meals", "unordered")

                    if data:
                        write_meals(data)

                    return self.serve_json(200, b"{\"ok\": true}")
                except Exception as e:
                    print(f"[do_POST] Failed to serve {self.path}: {e}")
                    return self.serve_json(500, b"{\"ok\": false}")

        except Exception as e:
            print(f"[do_POST] Failed to serve {self.path}: {e}")
            return self.serve_json(500, b"{\"status\": 500, \"message\": \"Internal server error\"}")

    def serve_json(self, status, data: bytes):
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def get_form(self):
        return json.loads(self.rfile.read(int(self.headers['Content-Length'])))

    def serve_file(self, relative_path: str, status: int = 200):
        if relative_path.startswith("/"):
            relative_path = relative_path[1:]
        self.path = os.path.join(SERVE_PREFIX, relative_path)
        self._status = status
        return super().do_GET()

    def send_response(self, code, message=None):
        # ponytail: SimpleHTTPRequestHandler.do_GET always sends 200 for a found file; override with the intended status
        if code == 200:
            code = self.__dict__.pop("_status", 200)
        super().send_response(code, message)

socketserver.TCPServer.allow_reuse_address = True
with socketserver.TCPServer(("", PORT), Handler) as httpd:
    print(f"Serving on http://localhost:{PORT}")
    try:
        httpd.serve_forever()

    except KeyboardInterrupt:
        pass
