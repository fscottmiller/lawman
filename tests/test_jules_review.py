import json
import os
import tempfile
import unittest
from pathlib import Path
from typing import Any, Mapping
from unittest.mock import patch

from lawman.jules_review import (
    PullRequest,
    ReviewError,
    final_agent_message,
    find_jules_source,
    load_pull_request,
    review_comment,
    run,
    session_request,
    upsert_review_comment,
    wait_for_session,
)

ROOT = Path(__file__).resolve().parents[1]
WORKFLOW = ROOT / ".github" / "workflows" / "jules-review.yml"
DOCUMENTATION = ROOT / "docs" / "jules-reviews.md"
MODULE = ROOT / "lawman" / "jules_review.py"
SHA = "a" * 40


class FakeClient:
    def __init__(self, responses: list[Any]) -> None:
        self.responses = responses
        self.requests: list[tuple[str, str, Mapping[str, Any] | None]] = []

    def request(self, method: str, path: str, payload: Mapping[str, Any] | None = None) -> Any:
        self.requests.append((method, path, payload))
        if not self.responses:
            raise AssertionError(f"unexpected request: {method} {path}")
        response = self.responses.pop(0)
        if isinstance(response, Exception):
            raise response
        return response


def pull_request(*, head_repository: str = "fscottmiller/lawman", draft: bool = False) -> PullRequest:
    return PullRequest(
        repository="fscottmiller/lawman",
        number=16,
        head_ref="agent/advisory-jules-reviews",
        head_sha=SHA,
        head_repository=head_repository,
        base_ref="main",
        draft=draft,
    )


def pull_request_document(
    *, head_repository: str = "fscottmiller/lawman", draft: bool = False
) -> dict[str, Any]:
    return {
        "number": 16,
        "draft": draft,
        "head": {
            "ref": "agent/advisory-jules-reviews",
            "sha": SHA,
            "repo": {"full_name": head_repository},
        },
        "base": {"ref": "main"},
    }


class JulesReviewContract(unittest.TestCase):
    def test_workflow_triggers_reviews_for_supported_pull_request_events(self) -> None:
        workflow = WORKFLOW.read_text(encoding="utf-8")

        self.assertIn("types: [opened, reopened, ready_for_review, synchronize]", workflow)
        self.assertIn("workflow_dispatch:", workflow)
        self.assertTrue(pull_request().trusted)
        self.assertTrue(pull_request(draft=True).draft)

        with tempfile.TemporaryDirectory() as directory:
            event = Path(directory) / "event.json"
            output = Path(directory) / "output"
            event.write_text(
                json.dumps({"pull_request": pull_request_document(draft=True)}),
                encoding="utf-8",
            )
            environment = {
                "GITHUB_REPOSITORY": "fscottmiller/lawman",
                "GITHUB_OUTPUT": str(output),
            }
            with patch.dict(os.environ, environment, clear=True):
                self.assertEqual(run(["--event", str(event), "--guard-only"]), 0)
            self.assertEqual(output.read_text(encoding="utf-8"), "reviewable=false\n")

    def test_workflow_skips_forks_without_exposing_secrets(self) -> None:
        workflow = WORKFLOW.read_text(encoding="utf-8")
        guard_job, review_job = workflow.split("\n  review:\n")

        self.assertNotIn("JULES_API_KEY", guard_job)
        self.assertIn("reviewable: ${{ steps.guard.outputs.reviewable }}", guard_job)
        self.assertIn("if: needs.guard.outputs.reviewable == 'true'", review_job)
        self.assertIn("JULES_API_KEY: ${{ secrets.JULES_API_KEY }}", review_job)
        self.assertFalse(pull_request(head_repository="someone/fork").trusted)

        with tempfile.TemporaryDirectory() as directory:
            event = Path(directory) / "event.json"
            output = Path(directory) / "output"
            event.write_text(
                json.dumps({"pull_request": pull_request_document(head_repository="someone/fork")}),
                encoding="utf-8",
            )
            environment = {
                "GITHUB_REPOSITORY": "fscottmiller/lawman",
                "GITHUB_OUTPUT": str(output),
            }
            with patch.dict(os.environ, environment, clear=True):
                self.assertEqual(run(["--event", str(event), "--guard-only"]), 0)
            self.assertEqual(output.read_text(encoding="utf-8"), "reviewable=false\n")

    def test_session_request_is_bound_to_head_branch_and_review_only(self) -> None:
        request = session_request("sources/github/fscottmiller/lawman", pull_request())

        self.assertEqual(
            request["sourceContext"]["githubRepoContext"]["startingBranch"],
            "agent/advisory-jules-reviews",
        )
        self.assertEqual(request["automationMode"], "AUTOMATION_MODE_UNSPECIFIED")
        prompt = request["prompt"]
        self.assertIn(SHA, prompt)
        self.assertIn(f"git checkout --detach {SHA}", prompt)
        self.assertIn("verify `git rev-parse HEAD`", prompt)
        self.assertIn("Do not modify files", prompt)
        self.assertIn("do not make a merge decision", prompt.replace("\n", " "))

    def test_jules_failures_are_bounded_and_advisory(self) -> None:
        completed = wait_for_session(
            FakeClient([{"name": "sessions/1", "state": "COMPLETED"}]),
            {"name": "sessions/1"},
            timeout=1.0,
            poll_interval=0.0,
        )
        self.assertEqual(completed["state"], "COMPLETED")

        timeout_client = FakeClient([])
        ticks = iter([0.0, 1.0])
        with self.assertRaisesRegex(ReviewError, "timed out"):
            wait_for_session(
                timeout_client,
                {"name": "sessions/1", "state": "QUEUED"},
                timeout=1.0,
                poll_interval=0.0,
                clock=lambda: next(ticks),
                sleep=lambda _: None,
            )

        with self.assertRaisesRegex(ReviewError, "failed"):
            wait_for_session(
                FakeClient([]),
                {"name": "sessions/1", "state": "FAILED"},
                timeout=1.0,
                poll_interval=0.0,
            )
        with self.assertRaisesRegex(ReviewError, "unknown state"):
            wait_for_session(
                FakeClient([]),
                {"name": "sessions/1", "state": "FUTURE_STATE"},
                timeout=1.0,
                poll_interval=0.0,
            )
        with self.assertRaisesRegex(ReviewError, "API unavailable"):
            wait_for_session(
                FakeClient([ReviewError("API unavailable")]),
                {"name": "sessions/1"},
                timeout=1.0,
                poll_interval=0.0,
            )
        with self.assertRaisesRegex(ReviewError, "malformed"):
            final_agent_message(FakeClient([{"activities": {}}]), {"name": "sessions/1"})
        self.assertIn("continue-on-error: true", WORKFLOW.read_text(encoding="utf-8"))

    def test_completed_session_produces_sha_specific_review_comment(self) -> None:
        client = FakeClient(
            [
                {
                    "activities": [
                        {"agentMessaged": {"agentMessage": "Earlier note"}},
                        {"sessionCompleted": {}},
                        {"agentMessaged": {"agentMessage": "One actionable finding"}},
                    ]
                }
            ]
        )
        session = {"name": "sessions/1", "state": "COMPLETED", "url": "https://jules.google.com/task/1"}

        message = final_agent_message(client, session)
        body = review_comment(pull_request(), session, message)

        self.assertEqual(message, "One actionable finding")
        self.assertIn(f"<!-- lawman-jules-review:{SHA} -->", body)
        self.assertIn(f"Reviewed commit `{SHA}`", body)
        self.assertIn("https://jules.google.com/task/1", body)

    def test_same_sha_review_comment_is_updated(self) -> None:
        marker = f"<!-- lawman-jules-review:{SHA} -->"
        client = FakeClient([[{"id": 42, "body": marker + " old"}], {"id": 42}])

        operation = upsert_review_comment(client, pull_request(), marker + " new")

        self.assertEqual(operation, "updated")
        self.assertEqual(client.requests[-1][0], "PATCH")
        self.assertEqual(client.requests[-1][1], "/repos/fscottmiller/lawman/issues/comments/42")
        self.assertEqual(client.requests[-1][2], {"body": marker + " new"})

    def test_review_integration_has_no_merge_authority(self) -> None:
        workflow = WORKFLOW.read_text(encoding="utf-8")
        module = MODULE.read_text(encoding="utf-8")

        self.assertIn("pull-requests: write", workflow)
        self.assertNotIn("statuses: write", workflow)
        self.assertNotIn("checks: write", workflow)
        self.assertNotIn("pulls/merge", module)
        self.assertNotIn('"/reviews"', module)
        self.assertNotIn("AUTO_CREATE_PR\"", module)

    def test_pull_request_content_is_not_shell_interpolated(self) -> None:
        workflow = WORKFLOW.read_text(encoding="utf-8")
        module = MODULE.read_text(encoding="utf-8")

        self.assertIn("pull_request_target:", workflow)
        self.assertNotIn("\n  pull_request:\n", workflow)
        trusted_ref = "ref: ${{ github.event.pull_request.base.sha || github.event.repository.default_branch }}"
        self.assertEqual(workflow.count(trusted_ref), 2)
        self.assertEqual(workflow.count("persist-credentials: false"), 2)
        self.assertNotIn("github.event.pull_request.title", workflow)
        self.assertNotIn("github.event.pull_request.body", workflow)
        self.assertNotIn("document.get(\"title\")", module)
        self.assertNotIn("document.get(\"body\")", module)
        run_lines = [line.strip() for line in workflow.splitlines() if line.strip().startswith("run:")]
        self.assertEqual(len(run_lines), 2)
        self.assertTrue(all('${{' not in line for line in run_lines))

    def test_load_pull_request_uses_embedded_target_event(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            event = Path(directory) / "event.json"
            event.write_text(json.dumps({"pull_request": pull_request_document()}), encoding="utf-8")
            client = FakeClient([])

            loaded = load_pull_request(event, "fscottmiller/lawman", client)

        self.assertEqual(loaded, pull_request())
        self.assertEqual(client.requests, [])

    def test_load_pull_request_resolves_manual_dispatch_input(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            event = Path(directory) / "event.json"
            event.write_text(json.dumps({"inputs": {"pull_request": "16"}}), encoding="utf-8")
            client = FakeClient([pull_request_document()])

            loaded = load_pull_request(event, "fscottmiller/lawman", client)

        self.assertEqual(loaded, pull_request())
        self.assertEqual(client.requests, [("GET", "/repos/fscottmiller/lawman/pulls/16", None)])

    def test_load_pull_request_rejects_unreadable_and_malformed_events(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            missing = Path(directory) / "missing.json"
            malformed = Path(directory) / "malformed.json"
            malformed.write_text("{", encoding="utf-8")
            invalid_input = Path(directory) / "invalid-input.json"
            invalid_input.write_text(json.dumps({"inputs": {"pull_request": "zero"}}), encoding="utf-8")

            for event in (missing, malformed):
                with self.subTest(event=event.name), self.assertRaisesRegex(ReviewError, "unreadable"):
                    load_pull_request(event, "fscottmiller/lawman", FakeClient([]))
            with self.assertRaisesRegex(ReviewError, "positive integer"):
                load_pull_request(invalid_input, "fscottmiller/lawman", FakeClient([]))

    def test_jules_source_discovery_skips_unknown_sources_and_paginates(self) -> None:
        client = FakeClient(
            [
                {"sources": [{"name": "sources/future/1", "futureRepo": {}}], "nextPageToken": "next page"},
                {
                    "sources": [
                        {
                            "name": "sources/github/lawman",
                            "githubRepo": {"owner": "fscottmiller", "repo": "lawman"},
                        }
                    ]
                },
            ]
        )

        source = find_jules_source(client, "fscottmiller/lawman")

        self.assertEqual(source, "sources/github/lawman")
        self.assertEqual(client.requests[1][1], "/sources?pageSize=100&pageToken=next%20page")

    def test_review_comment_discovery_paginates(self) -> None:
        marker = f"<!-- lawman-jules-review:{SHA} -->"
        first_page = [{"id": identifier, "body": "unrelated"} for identifier in range(100)]
        client = FakeClient([first_page, [{"id": 142, "body": marker + " old"}], {"id": 142}])

        operation = upsert_review_comment(client, pull_request(), marker + " new")

        self.assertEqual(operation, "updated")
        self.assertIn("page=2", client.requests[1][1])
        self.assertEqual(client.requests[-1][1], "/repos/fscottmiller/lawman/issues/comments/142")

    def test_jules_review_documentation_matches_public_behavior(self) -> None:
        documentation = DOCUMENTATION.read_text(encoding="utf-8")

        for claim in (
            "install the Jules GitHub app",
            "`JULES_API_KEY`",
            "Pull requests from forks are skipped",
            "advisory",
            "run it manually",
        ):
            self.assertIn(claim, documentation)


if __name__ == "__main__":
    unittest.main()
