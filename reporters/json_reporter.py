"""JSON reporter — outputs report as formatted JSON."""

import json


class JsonReporter:
    def render(self, report: dict) -> str:
        return json.dumps(report, indent=2, ensure_ascii=False)
