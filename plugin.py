"""Beszel: host status and usage from the hub (PocketBase API), systems sync, agent rollout."""
from __future__ import annotations

from labdex.plugins.base import Change, PluginError
from labdex.plugins.base import Plugin as Base

INSTALL_SCRIPT = "https://raw.githubusercontent.com/henrygd/beszel/main/supplemental/scripts/install-agent.sh"
STATE = {"up": "up", "down": "down"}  # paused, pending: unknown


class Plugin(Base):
    def _api(self):
        s = self.settings
        if not s.get("url"):
            raise PluginError("set the hub URL first")
        http = self.ctx.http(s["url"].rstrip("/") + "/", verify=bool(s.get("verify_tls", True)), timeout=10)
        r = http.post("api/collections/users/auth-with-password", json={"identity": s.get("email", ""), "password": s.get("password", "")})
        d = r.json()
        if not d.get("token"):
            raise PluginError("Beszel didn't accept the user")
        http.s.headers["Authorization"] = d["token"]
        self._user = (d.get("record") or {}).get("id")
        return http

    def _systems(self, http=None) -> list[dict]:
        http = http or self._api()
        out, page = [], 1
        while True:
            d = http.get("api/collections/systems/records", params={"page": page, "perPage": 200}).json()
            out += d.get("items") or []
            if page >= int(d.get("totalPages") or 1):
                return out
            page += 1

    def _matched(self, systems):
        match = self.ctx.match_host()
        for s in systems:
            yield (match(s.get("host", "")) or match(s.get("name", ""))), s

    def test(self):
        return f"{len(self._systems())} systems in Beszel"

    # --------------------------------------------------------------- status
    def run_poll(self, params):
        report, unmatched = {}, 0
        for host, s in self._matched(self._systems()):
            if host is None:
                unmatched += 1
                continue
            info = s.get("info") or {}
            state = STATE.get(s.get("status", ""), "unknown")
            detail = f"{s.get('status', '?')}" + (f" · CPU {info.get('cpu', 0):.0f} % · memory {info.get('mp', 0):.0f} % · disk {info.get('dp', 0):.0f} %"
                                                  if state == "up" else "")
            if state == "down" and host in report and report[host]["state"] == "up":
                continue
            report[host] = {"state": state, "detail": detail,
                            "data": {k: info.get(k) for k in ("cpu", "mp", "dp", "u", "v", "la") if info.get(k) is not None}}
        self.ctx.report_status(report)
        return {"hosts": len(report), "unmatched": unmatched}

    # ---------------------------------------------------------- systems sync
    def _address(self, h: dict) -> str:
        addr = (h.get("module_settings") or {}).get("address")
        if addr:
            return addr
        prim = next((i for i in h.get("interfaces", []) if i.get("primary")), None) or next(iter(h.get("interfaces") or []), None)
        return (prim or {}).get("ip4") or (prim or {}).get("ip6") or ""

    def plan_sync_systems(self, params):
        known = {host for host, _ in self._matched(self._systems()) if host}
        port = str(self.settings.get("agent_port") or 45876)
        changes = []
        for h in self.ctx.hosts():
            if h["name"] in known or h.get("kind") == "vip":
                continue
            addr = self._address(h)
            if not addr:
                self.log(f"{h['name']}: no address, skipped")
                continue
            changes.append(Change("create", "system", h["name"], f"{addr}:{port}", after={"name": h["name"], "host": addr, "port": port}))
        return changes

    def apply_sync_systems(self, changes, params):
        http = self._api()
        for c in changes:
            http.post("api/collections/systems/records", json={**c.after, "users": [self._user] if self._user else []})
            self.log(f"added {c.name}")
        return {"added": len(changes)}

    # --------------------------------------------------------------- agent
    def run_install_agent(self, params):
        s = self.settings
        if not s.get("agent_key") and not s.get("agent_token"):
            raise PluginError("set the hub public key (or a universal token) first")
        args = ["-p", str(s.get("agent_port") or 45876)]
        if s.get("agent_key"):
            args += ["-k", s["agent_key"]]
        if s.get("agent_token"):
            args += ["-t", s["agent_token"], "-url", s["url"].rstrip("/")]
        play = [{"name": "Beszel agent", "hosts": "all", "become": True, "gather_facts": False, "tasks": [
            {"name": "download the install script", "ansible.builtin.get_url": {"url": INSTALL_SCRIPT, "dest": "/tmp/beszel-install-agent.sh", "mode": "0700"}},
            {"name": "install and start the agent", "ansible.builtin.command": {"argv": ["sh", "/tmp/beszel-install-agent.sh", *args],
                                                                             "creates": "/opt/beszel-agent/beszel-agent"}, "no_log": True},
        ]}]
        res = self.ctx.ansible(inline=play, limit=params["host"])
        if not res.ok:
            raise PluginError(f"install failed (rc={res.rc}, failed={res.failed}, unreachable={res.unreachable})")
        return {"changed": res.changed}

    # -------------------------------------------------------------- widgets
    def widget_systems(self, host):
        items = []
        for name, s in self._matched(self._systems()):
            st = s.get("status", "")
            items.append({"label": s.get("name", "?"), "state": {"up": "up", "down": "down", "paused": "warn"}.get(st, "unknown"),
                          "detail": st, "link": f"/hosts/{name}" if name else ""})
        items.sort(key=lambda i: (i["state"] != "down", i["label"]))
        down = sum(1 for i in items if i["state"] == "down")
        return {"kind": "status", "items": items[:25], "sub": f"{len(items)} systems, {down} down" if items else "no systems yet"}

    def widget_host(self, host):
        for name, s in self._matched(self._systems()):
            if name == host["name"]:
                info = s.get("info") or {}
                if s.get("status") != "up":
                    return {"kind": "status", "items": [{"label": s.get("name", ""), "state": "down" if s.get("status") == "down" else "unknown",
                                                         "detail": s.get("status", "")}]}
                up_d = int(info.get("u") or 0) // 86400

                def tone(p):
                    return "err" if p >= 90 else "warn" if p >= 75 else "ok"
                return {"kind": "list", "items": [
                    {"label": "CPU", "value": f"{info.get('cpu', 0):.0f} %", "tone": tone(info.get("cpu", 0))},
                    {"label": "memory", "value": f"{info.get('mp', 0):.0f} %", "tone": tone(info.get("mp", 0))},
                    {"label": "disk", "value": f"{info.get('dp', 0):.0f} %", "tone": tone(info.get("dp", 0))},
                    {"label": "load", "value": " ".join(f"{x:.2f}" for x in info.get("la") or [])},
                ], "sub": f"up {up_d} d · agent {info.get('v', '?')}"}
        return {"kind": "list", "items": [], "sub": "not in Beszel (add it with “Add hosts as systems”)"}
