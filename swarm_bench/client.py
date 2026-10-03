"""Tiny scoped HTTP adapter: expose these methods as tools to your agents."""

import json
from urllib.parse import urlencode
from urllib.request import Request, urlopen

from .common import read_json


class AgentClient:
    def __init__(self, connection_file):
        connection = read_json(connection_file)
        self._base_url = connection["base_url"].rstrip("/")
        self._token = connection["token"]

    def _request(self, path, body=None):
        headers = {"Authorization": "Bearer " + self._token, "Content-Type": "application/json"}
        data = None if body is None else json.dumps(body).encode("utf-8")
        request = Request(self._base_url + path, data=data, headers=headers)
        with urlopen(request, timeout=30) as response:
            return json.load(response)

    def context(self):
        """Read the question, your role and the current ballot phase."""
        return self._request("/context")

    def list_files(self):
        """List entries in the workspace."""
        return self._request("/files")

    def read_file(self, path):
        """Read a workspace entry at the given path."""
        return self._request("/file?" + urlencode({"path": path}))

    def read_board(self, after=0):
        """Read messages after the given cursor; use zero for full history."""
        if isinstance(after, bool) or not isinstance(after, int) or after < 0:
            raise ValueError("after must be a nonnegative integer")
        return self._request(f"/board?after={after}")

    def post_message(self, content, evidence=None):
        """Publish a message with optional evidence references."""
        return self._request("/messages", {"content": content, "evidence": evidence or []})

    def submit_ballot(self, stage, answer, base_answer, justification):
        """Seal your private answer. Numbers are strings or integers, unknowns are None."""
        return self._request("/ballots", {"stage": stage, "answer": answer,
            "base_answer": base_answer, "justification": justification})
