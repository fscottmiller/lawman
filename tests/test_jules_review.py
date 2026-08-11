import unittest
from pathlib import Path
from typing import Any, Mapping

from lawman.jules_review import (
    PullRequest,
    ReviewError,
    final_agent_message,
    review_comment,
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


class JulesReviewContract(unittest.TestCase):
    def test_workflow_triggers_reviews_for_supported_pull_request_events(self) -> None:
        workflow = WORKFLOW.read_text(encoding="utf-8")

        self.assertIn("types: [opened, reopened, ready_for_review, synchronize]", workflow)
        self.assertIn("workflow_dispatch:", workflow)
        self.assertIn("github.event.pull_request.draft", workflow)
        self.assertTrue(pull_request().trusted)
        self.assertTrue(pull_request(draft=True).draft)

    def test_workflow_skips_forks_without_exposing_secrets(self) -> None:
        workflow = WORKFLOW.read_text(encoding="utf-8")
        skip_step, review_step = workflow.split("- name: Run advisory Jules review")

        self.assertIn("head.repo.full_name != github.repository", skip_step)
        self.assertNotIn("JULES_API_KEY", skip_step)
        self.assertIn("head.repo.full_name == github.repository", review_step)
        self.assertIn("JULES_API_KEY: ${{ secrets.JULES_API_KEY }}", review_step)
        self.assertFalse(pull_request(head_repository="someone/fork").trusted)

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

        self.assertNotIn("github.event.pull_request.title", workflow)
        self.assertNotIn("github.event.pull_request.body", workflow)
        self.assertNotIn("document.get(\"title\")", module)
        self.assertNotIn("document.get(\"body\")", module)
        run_lines = [line.strip() for line in workflow.splitlines() if line.strip().startswith("run:")]
        self.assertEqual(len(run_lines), 2)
        self.assertTrue(all('${{' not in line for line in run_lines))

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
