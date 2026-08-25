from __future__ import annotations

import json
import os
from typing import Protocol

from google.cloud import tasks_v2


class WorkDispatcher(Protocol):
    def dispatch(self, run_id: str) -> None: ...


class CloudTasksDispatcher:
    def __init__(self) -> None:
        self.client = tasks_v2.CloudTasksClient()
        self.project = os.environ["GOOGLE_CLOUD_PROJECT"]
        self.location = os.getenv("EVIDENCE_TASKS_LOCATION", "us-central1")
        self.queue = os.getenv("EVIDENCE_TASKS_QUEUE", "rootstory-evidence-audits")
        self.service_url = os.environ["EVIDENCE_AGENT_URL"].rstrip("/")
        self.service_account = os.environ["EVIDENCE_TASKS_SERVICE_ACCOUNT"]

    def dispatch(self, run_id: str) -> None:
        parent = self.client.queue_path(self.project, self.location, self.queue)
        task = {
            "http_request": {
                "http_method": tasks_v2.HttpMethod.POST,
                "url": f"{self.service_url}/v1/internal/audits/{run_id}/work",
                "headers": {
                    "Content-Type": "application/json",
                    "X-Evidence-Worker-Token": os.environ["EVIDENCE_WORKER_TOKEN"],
                },
                "body": json.dumps({"runId": run_id}).encode(),
                "oidc_token": {
                    "service_account_email": self.service_account,
                    "audience": self.service_url,
                },
            }
        }
        self.client.create_task(parent=parent, task=task)
