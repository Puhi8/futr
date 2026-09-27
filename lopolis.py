# This is an API wrapper for the lopolispro.si school management platform
# Copyright (C) 2026  Lenart Kladnik
#
# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with this program.  If not, see <https://www.gnu.org/licenses/>.

import re
import subprocess
from datetime import datetime
import json
from typing import Any
import urllib.request
import urllib.error
import urllib.response
import urllib.parse
import http.cookiejar

class LoginError(Exception):...

class API:
    def __init__(self, session) -> None:
        self.session = session
        self._next_action_names = {"timetable": "getWeekTimetable", "meals": "registerMeal", "unset_meals": "unregisterMeal", "evaluations": "getEvaluations"}

    def _request(self, path: str) -> Any:
        """
        Wrapper around Session.request
        It assumes that the data coming from the request is valid json
        """
        return json.loads(str(self.session.request(path, text=True)))

    def _format_date(self, date: datetime) -> str:
        return date.strftime("%Y-%m-%d")

    def _parse_next_js_action_response(self, data: str, parse_json: bool = True) -> dict[int, Any]:
        res = {}

        parts = re.split(r'(\d+):(I?\{|I?\[|")', data)[1:]

        for i in range(0, len(parts), 3):
            id = int(parts[i])
            val = parts[i + 1] + parts[i + 2].strip()

            res.update({int(id): (json.loads(val) if parse_json else val)})

        return res

    def _get_next_action(self, path: str, id: str | None = None) -> str:
        if not id:
            id = path.strip()[1:]

        name = self._next_action_names[id]
        html = str(self.session.request(path, text=True)).replace("\\n", "\n")

        scripts = re.findall(r'script src="/_next/static/chunks/([^"]+\.js)"', html)
        scripts += [c for c in re.findall(r'\\"script\\",\\"script-\d+\\",\{\\"src\\":\\"/_next/static/chunks/([^\\]+\.js)', html) if c not in scripts]

        for chunk in scripts:
            try:
                js = str(self.session.request(f"/_next/static/chunks/{chunk}", text=True))
            except urllib.error.HTTPError:
                continue

            m = re.search(r'createServerReference\)\("([a-f0-9]{42})"[^)]*?"' + name + '"', js)
            if m:
                return m.group(1)

        raise LookupError(f"next action {name!r} not found on {path}")

    def _get_next_router_state_tree(self, path: str):
        next_header_data = self.session.request(path, headers={"rsc": 1, "next-router-prefetch": 1, "next-url": path}, text=True)
        next_router_state_tree = json.loads(self.session.api._parse_next_js_action_response(str(next_header_data), parse_json=False)[0])['f'][0][0]
        next_router_state_tree[:] = [x if x != '$undefined' else 'null' for x in next_router_state_tree] # Replace all $undefined with null

        return urllib.parse.quote_plus(json.dumps(next_router_state_tree))

    def get_chat_unread_count(self) -> Any:
        return self._request("/api/chat_unread_count")

    def get_evaluations(self) -> Any:
        # These headers encode the next js action, so the server knows to respond with the raw data and not the html page
        headers = {
            "next-action": self._get_next_action("/evaluations"),
            "next-router-state-tree": self._get_next_router_state_tree("/evaluations")
        }
        r = self.session.request("/evaluations", method="POST", headers=headers, text=True)

        return self._parse_next_js_action_response(str(r))[1]

    def get_banners(self) -> Any:
        return self._request("/api/banners")

    def get_absences(self) -> Any:
        return self._request("/api/absences")

    def get_timetable(self, date: datetime = datetime.today()) -> Any:
        # These headers encode the next js action, so the server knows to respond with the raw data and not the html page
        headers = {
            "next-action": self._get_next_action("/timetable"),
            "next-router-state-tree": self._get_next_router_state_tree("/timetable")
        }

        r = self.session.request("/timetable", data=[self._format_date(date)], method="POST", headers=headers, text=True)

        return self._parse_next_js_action_response(str(r))[1]

    def get_meals_menu(self, date: datetime) -> Any:
        return self._request(f"/api/meals/menus?date={self._format_date(date)}")

    def set_meals_menu(self, date: datetime, meal_id: int, meal_type: str = "snack") -> Any:
        strdate = self._format_date(date)

        # These headers encode the next js action, so the server knows to respond with the raw data and not the html page
        headers = {
            "next-action": self._get_next_action("/meals"),
            "next-router-state-tree": self._get_next_router_state_tree("/meals")
        }

        r = self.session.request(f"/meals?date={strdate}", data=[{"type": meal_type, "date": strdate, "menu": meal_id}], method="POST", headers=headers, text=True)

        return self._parse_next_js_action_response(str(r))[1]

    def unset_meals_menu(self, date: datetime, meal_type = "snack") -> Any:
        strdate = self._format_date(date)

        headers = {
            "next-action": self._get_next_action("/meals", "unset_meals"),
            "next-router-state-tree": self._get_next_router_state_tree("/meals")
        }

        r = self.session.request(f"/meals?date={strdate}", data=[{"type": meal_type, "date": strdate}], method="POST", headers=headers, text=True)

        return self._parse_next_js_action_response(str(r))[1]

class CreateSession:
    def __init__(self, username: str, password: str) -> None:
        self._cookie_jar = http.cookiejar.CookieJar()
        self._opener = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(self._cookie_jar))

        self.username = username
        self.password = password

    def _get_login_token(self) -> str | None:
        data = urllib.parse.urlencode({
            "uporabnik": self.username,
            "geslo": self.password,
            "pin": "",
            "captcha": "false",
            "koda": "",
            "prijava_redirect": ""
        }).encode("utf-8")

        self._opener.open(
            "https://www.lopolispro.si/p/ajax_prijava",
            data=data
        )

        for cookie in self._cookie_jar:
            if cookie.name == "lopolis_session":
                return cookie.value

        raise LoginError("Failed to get the login token, check your credentials and try again.")

    def _get_otp_url(self, login_token: str) -> str | None:
        # Needs HTTP/2 -> use subprocess + curl

        res = subprocess.run(
            [
                "curl",
                "https://www.lopolispro.si/webapp",
                "-H", f"Cookie: lopolis_session={login_token}",
                "-I"
            ],
            capture_output=True,
            text=True
        )

        m = re.search(r"location: (.+)", res.stdout)
        if m:
            return m.group(1)

        raise LoginError("Failed to get the OTP url, check your credentials and try again.")

    def _get_ses_cookie(self, otp_url: str) -> str | None:
        self._opener.open(otp_url)

        for cookie in self._cookie_jar:
            if cookie.name == "ses":
                return cookie.value

        raise LoginError("Failed to get the session cookie, check your credentials and try again.")

    def cookie(self) -> str | None:
        login_token = self._get_login_token()
        if not login_token: return

        otp_url = self._get_otp_url(login_token)
        if not otp_url: return

        return self._get_ses_cookie(otp_url)

class Session:
    def __init__(self, username: str, password: str):
        self._username = username
        self._password = password

        self._ses_cookie = CreateSession(self._username, self._password).cookie()
        self.api = API(self)

    def request(self, path: str, subdomain: str = "starsi", data: Any = [], method: str = "GET", headers: dict = {}, text: bool = False) -> urllib.response.addinfourl | str:
        if path.startswith("/"):
            path = path[1:]
        if path.endswith("/"):
            path = path[:-1]

        subdomain = str("".join(filter(str.isalpha, subdomain)))
        url = f"https://{subdomain}.lopolispro.si/{path}"

        _headers = {
            "Cookie": f"ses={self._ses_cookie}",
            "Content-Type": "text/plain;charset=UTF-8",
        }
        headers.update(_headers)

        request = urllib.request.Request(
            url,
            data=json.dumps(data).encode("utf-8"),
            headers=headers,
            method=method
        )
        res = urllib.request.urlopen(request)

        if text:
            return res.read().decode("utf-8")

        return res

    def refresh(self):
        self._ses_cookie = CreateSession(self._username, self._password).cookie()
